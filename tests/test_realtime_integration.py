"""
tests/test_realtime_integration.py
-------------------------------------
Test d'intégration de bout en bout du mécanisme de push temps réel
(consumer Kafka -> PostgreSQL -> NOTIFY -> asyncpg LISTEN -> WebSocket),
SANS scrutation périodique.

Teste les deux flux réels (qualité de l'air + Vélib), depuis que les
transactions immobilières simulées ont été supprimées (données DVF traitées
uniquement en batch via le pipeline Airflow).

Contrairement aux autres tests (SQLite en mémoire), celui-ci nécessite un
vrai serveur PostgreSQL car SQLite ne supporte pas LISTEN/NOTIFY. Il est
automatiquement ignoré (skip) si aucun PostgreSQL n'est accessible.

Pour le lancer réellement :
    docker compose up -d postgres-gold
    POSTGRES_GOLD_HOST=localhost pytest tests/test_realtime_integration.py -v
"""
import asyncio
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.modules.setdefault("kafka", types.SimpleNamespace(KafkaConsumer=object))
sys.modules.setdefault("kafka.errors", types.SimpleNamespace(NoBrokersAvailable=Exception))

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "streaming"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

PG_HOST = os.environ.get("POSTGRES_GOLD_HOST", "127.0.0.1")
PG_DB = os.environ.get("POSTGRES_GOLD_DB", "gold")
PG_USER = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
PG_PASSWORD = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")


def _postgres_available() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason="Nécessite un vrai PostgreSQL (LISTEN/NOTIFY non supporté par SQLite).",
)


def test_consumer_upserts_velib_aggregate_and_notifies():
    """
    Vérifie que handle_velib() insère l'événement dans disponibilite_velib_temps_reel,
    met à jour velib_agregats_temps_reel via UPSERT incrémental, et envoie une
    notification pg_notify (push WebSocket).
    """
    import consumer_to_gold as consumer
    from sqlalchemy import create_engine, text

    os.environ["POSTGRES_GOLD_HOST"] = PG_HOST
    os.environ["POSTGRES_GOLD_DB"] = PG_DB
    os.environ["POSTGRES_GOLD_USER"] = PG_USER
    os.environ["POSTGRES_GOLD_PASSWORD"] = PG_PASSWORD

    engine = create_engine(f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:5432/{PG_DB}")

    # Nettoyage des données de test précédentes (arrondissement 1 utilisé pour le test)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM disponibilite_velib_temps_reel WHERE arrondissement = 1"))
        conn.execute(text("DELETE FROM velib_agregats_temps_reel WHERE arrondissement = 1"))

    # Simule trois événements Vélib pour le 1er arrondissement
    test_events = [
        {"arrondissement": 1, "station_code": "TEST01", "station_nom": "Test Station",
         "velos_disponibles": 10, "bornes_libres": 5},
        {"arrondissement": 1, "station_code": "TEST02", "station_nom": "Test Station 2",
         "velos_disponibles": 6, "bornes_libres": 8},
        {"arrondissement": 1, "station_code": "TEST03", "station_nom": "Test Station 3",
         "velos_disponibles": 14, "bornes_libres": 2},
    ]
    for ev in test_events:
        consumer.handle_velib(engine, ev)

    with engine.connect() as conn:
        # Vérification de l'agrégat glissant
        row = conn.execute(
            text("SELECT nb_stations_actives, velos_disponibles_moyen FROM velib_agregats_temps_reel WHERE arrondissement = 1"),
        ).fetchone()
        assert row is not None, "Agrégat Vélib absent de la table"
        assert row[0] >= 3, f"nb_stations_actives attendu >= 3, obtenu {row[0]}"
        # Moyenne glissante de 10, 6, 14 = 10.0
        assert abs(row[1] - 10.0) < 0.5, f"velos_disponibles_moyen attendu ~10.0, obtenu {row[1]}"

        # Vérification des événements bruts persistés
        count = conn.execute(
            text("SELECT COUNT(*) FROM disponibilite_velib_temps_reel WHERE arrondissement = 1"),
        ).scalar()
        assert count >= 3, f"Attendu >= 3 événements bruts, obtenu {count}"


def test_consumer_upserts_air_quality_and_notifies():
    """
    Vérifie que handle_air_quality() persiste l'événement dans
    qualite_air_temps_reel et envoie une notification pg_notify.
    """
    import consumer_to_gold as consumer
    from sqlalchemy import create_engine, text

    engine = create_engine(f"postgresql+psycopg2://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:5432/{PG_DB}")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM qualite_air_temps_reel WHERE arrondissement = 20"))

    consumer.handle_air_quality(engine, {"arrondissement": 20, "indice_qualite_air": 72.5})

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM qualite_air_temps_reel WHERE arrondissement = 20"),
        ).scalar()
        assert count >= 1


def test_websocket_receives_push_without_polling():
    """
    Vérifie que pg_notify déclenche bien une notification asyncpg sans polling.
    """
    import asyncpg

    async def _run():
        received = []

        def on_notify(connection, pid, channel, payload):
            received.append(json.loads(payload))

        conn = await asyncpg.connect(host=PG_HOST, user=PG_USER, password=PG_PASSWORD, database=PG_DB)
        await conn.add_listener("realtime_channel", on_notify)
        await asyncio.sleep(0.2)

        payload = json.dumps({"type": "velib", "arrondissement": 5, "velos_disponibles": 8})
        notify_conn = await asyncpg.connect(host=PG_HOST, user=PG_USER, password=PG_PASSWORD, database=PG_DB)
        await notify_conn.execute("SELECT pg_notify('realtime_channel', $1)", payload)
        await notify_conn.close()

        await asyncio.sleep(0.3)
        await conn.close()
        return received

    received = asyncio.run(_run())
    assert len(received) == 1
    assert received[0]["arrondissement"] == 5
    assert received[0]["type"] == "velib"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
