"""
tests/test_realtime_integration.py
-------------------------------------
Test d'intégration du mécanisme de push temps réel
(DAG Airflow → PostgreSQL NOTIFY → asyncpg LISTEN → WebSocket).

Teste les deux flux réels (qualité de l'air + Vélib). Nécessite un vrai
PostgreSQL car SQLite ne supporte pas LISTEN/NOTIFY. Automatiquement ignoré
si aucun PostgreSQL n'est accessible.

Pour le lancer :
    docker compose up -d postgres-gold
    POSTGRES_GOLD_HOST=localhost pytest tests/test_realtime_integration.py -v
"""
import asyncio
import json
import os
import sys

import pytest

PG_HOST = os.environ.get("POSTGRES_GOLD_HOST", "127.0.0.1")
PG_DB = os.environ.get("POSTGRES_GOLD_DB", "gold")
PG_USER = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
PG_PASSWORD = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")

NOTIFY_CHANNEL = "realtime_channel"


def _postgres_available() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(
            host=PG_HOST, dbname=PG_DB, user=PG_USER,
            password=PG_PASSWORD, connect_timeout=2,
        )
        conn.close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_available(),
    reason="Nécessite un vrai PostgreSQL (LISTEN/NOTIFY non supporté par SQLite).",
)


def _pg_conn():
    import psycopg2
    return psycopg2.connect(host=PG_HOST, dbname=PG_DB, user=PG_USER, password=PG_PASSWORD)


def test_velib_write_and_notify():
    """
    Reproduit la logique de realtime_fetcher.fetch_and_store_velib() :
    INSERT dans disponibilite_velib_temps_reel, UPSERT agrégat glissant,
    pg_notify. Vérifie l'intégrité de l'agrégat (moyenne mobile Welford).
    """
    conn = _pg_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM disponibilite_velib_temps_reel WHERE arrondissement = 1 AND station_code LIKE 'TEST%'")
        cur.execute("DELETE FROM velib_agregats_temps_reel WHERE arrondissement = 1")
        conn.commit()

    events = [
        {"arrondissement": 1, "station_code": "TEST01", "station_nom": "Test A", "velos_disponibles": 10, "bornes_libres": 5},
        {"arrondissement": 1, "station_code": "TEST02", "station_nom": "Test B", "velos_disponibles": 6,  "bornes_libres": 8},
        {"arrondissement": 1, "station_code": "TEST03", "station_nom": "Test C", "velos_disponibles": 14, "bornes_libres": 2},
    ]

    with conn.cursor() as cur:
        for ev in events:
            cur.execute(
                "INSERT INTO disponibilite_velib_temps_reel "
                "(arrondissement, station_code, station_nom, velos_disponibles, bornes_libres) "
                "VALUES (%s, %s, %s, %s, %s)",
                (ev["arrondissement"], ev["station_code"], ev["station_nom"],
                 ev["velos_disponibles"], ev["bornes_libres"]),
            )
            cur.execute(
                """
                INSERT INTO velib_agregats_temps_reel
                    (arrondissement, nb_stations_actives, velos_disponibles_moyen, derniere_maj)
                VALUES (%s, 1, %s, now())
                ON CONFLICT (arrondissement) DO UPDATE SET
                    nb_stations_actives     = velib_agregats_temps_reel.nb_stations_actives + 1,
                    velos_disponibles_moyen = velib_agregats_temps_reel.velos_disponibles_moyen
                        + (%s - velib_agregats_temps_reel.velos_disponibles_moyen)
                          / (velib_agregats_temps_reel.nb_stations_actives + 1),
                    derniere_maj = now()
                """,
                (ev["arrondissement"], ev["velos_disponibles"], ev["velos_disponibles"]),
            )
            payload = json.dumps({"type": "velib", "arrondissement": ev["arrondissement"],
                                  "velos_disponibles": ev["velos_disponibles"]})
            cur.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, payload))
        conn.commit()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT nb_stations_actives, velos_disponibles_moyen "
            "FROM velib_agregats_temps_reel WHERE arrondissement = 1"
        )
        row = cur.fetchone()
        assert row is not None, "Agrégat Vélib absent"
        assert row[0] >= 3, f"nb_stations_actives attendu >= 3, obtenu {row[0]}"
        assert abs(float(row[1]) - 10.0) < 0.5, f"moyenne attendue ~10.0, obtenue {row[1]}"

        cur.execute(
            "SELECT COUNT(*) FROM disponibilite_velib_temps_reel "
            "WHERE arrondissement = 1 AND station_code LIKE 'TEST%'"
        )
        assert cur.fetchone()[0] >= 3

    conn.close()


def test_air_quality_write_and_notify():
    """
    Reproduit la logique de realtime_fetcher.fetch_and_store_air_quality() :
    INSERT dans qualite_air_temps_reel + pg_notify.
    """
    conn = _pg_conn()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM qualite_air_temps_reel WHERE arrondissement = 20")
        cur.execute(
            "INSERT INTO qualite_air_temps_reel (arrondissement, indice_qualite_air) VALUES (%s, %s)",
            (20, 72.5),
        )
        payload = json.dumps({"type": "qualite_air", "arrondissement": 20, "indice_qualite_air": 72.5})
        cur.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, payload))
        conn.commit()

    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM qualite_air_temps_reel WHERE arrondissement = 20")
        assert cur.fetchone()[0] >= 1

    conn.close()


def test_websocket_receives_push_without_polling():
    """
    Vérifie que pg_notify déclenche immédiatement une notification asyncpg
    sans scrutation périodique — mécanisme utilisé par /ws/realtime.
    """
    import asyncpg

    async def _run():
        received = []

        def on_notify(connection, pid, channel, payload):
            received.append(json.loads(payload))

        conn = await asyncpg.connect(host=PG_HOST, user=PG_USER, password=PG_PASSWORD, database=PG_DB)
        await conn.add_listener(NOTIFY_CHANNEL, on_notify)
        await asyncio.sleep(0.2)

        payload = json.dumps({"type": "velib", "arrondissement": 5, "velos_disponibles": 8})
        notify_conn = await asyncpg.connect(host=PG_HOST, user=PG_USER, password=PG_PASSWORD, database=PG_DB)
        await notify_conn.execute("SELECT pg_notify($1, $2)", NOTIFY_CHANNEL, payload)
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
