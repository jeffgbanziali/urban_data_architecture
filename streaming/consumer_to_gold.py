import json
import os
import time

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from sqlalchemy import create_engine, text

TOPIC_EVENTS = "events.stream"
TOPIC_MOBILITE = "mobilite.raw"
NOTIFY_CHANNEL = "realtime_channel"


def connect_consumer_with_retry(bootstrap_servers: str, max_attempts: int = 20):
    for attempt in range(1, max_attempts + 1):
        try:
            return KafkaConsumer(
                TOPIC_EVENTS,
                TOPIC_MOBILITE,
                bootstrap_servers=bootstrap_servers,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                group_id="urban-data-explorer-consumer",
            )
        except NoBrokersAvailable:
            print(f"Kafka indisponible, tentative {attempt}/{max_attempts}...")
            time.sleep(5)
    raise RuntimeError("Impossible de se connecter à Kafka après plusieurs tentatives.")


def get_engine_with_retry(max_attempts: int = 20):
    host = os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold")
    db = os.environ.get("POSTGRES_GOLD_DB", "gold")
    user = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
    pwd = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")
    engine = create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:5432/{db}")
    for attempt in range(1, max_attempts + 1):
        try:
            with engine.connect():
                return engine
        except Exception:
            print(f"PostgreSQL indisponible, tentative {attempt}/{max_attempts}...")
            time.sleep(5)
    raise RuntimeError("Impossible de se connecter à PostgreSQL après plusieurs tentatives.")


INSERT_AIR_QUALITY = text(
    "INSERT INTO qualite_air_temps_reel (arrondissement, indice_qualite_air) "
    "VALUES (:arrondissement, :indice_qualite_air)"
)

INSERT_VELIB = text(
    "INSERT INTO disponibilite_velib_temps_reel "
    "(arrondissement, station_code, station_nom, velos_disponibles, bornes_libres) "
    "VALUES (:arrondissement, :station_code, :station_nom, :velos_disponibles, :bornes_libres)"
)

# Moyenne glissante incrémentale par arrondissement, atomique (pas de race condition).
UPSERT_VELIB_AGGREGATE = text(
    """
    INSERT INTO velib_agregats_temps_reel
        (arrondissement, nb_stations_actives, velos_disponibles_moyen, derniere_maj)
    VALUES (:arrondissement, 1, :velos_disponibles, now())
    ON CONFLICT (arrondissement) DO UPDATE SET
        nb_stations_actives   = velib_agregats_temps_reel.nb_stations_actives + 1,
        velos_disponibles_moyen = velib_agregats_temps_reel.velos_disponibles_moyen
            + (:velos_disponibles - velib_agregats_temps_reel.velos_disponibles_moyen)
              / (velib_agregats_temps_reel.nb_stations_actives + 1),
        derniere_maj = now()
    """
)

NOTIFY = text("SELECT pg_notify(:channel, :payload)")


def handle_air_quality(engine, event: dict):
    payload = json.dumps({"type": "qualite_air", **event}, ensure_ascii=False)
    with engine.begin() as conn:
        conn.execute(INSERT_AIR_QUALITY, event)
        conn.execute(NOTIFY, {"channel": NOTIFY_CHANNEL, "payload": payload})
    print(f"[qualite_air] persistée : {event}")


def handle_velib(engine, event: dict):
    payload = json.dumps({"type": "velib", **event}, ensure_ascii=False)
    with engine.begin() as conn:
        conn.execute(INSERT_VELIB, event)
        conn.execute(UPSERT_VELIB_AGGREGATE, {
            "arrondissement": event["arrondissement"],
            "velos_disponibles": event["velos_disponibles"],
        })
        conn.execute(NOTIFY, {"channel": NOTIFY_CHANNEL, "payload": payload})
    print(f"[velib] persistée : arr={event['arrondissement']} velos={event['velos_disponibles']}")


def main():
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    consumer = connect_consumer_with_retry(bootstrap)
    engine = get_engine_with_retry()
    print(f"Consommateur Kafka démarré sur '{TOPIC_EVENTS}' et '{TOPIC_MOBILITE}'")

    for message in consumer:
        event = message.value
        try:
            if message.topic == TOPIC_EVENTS:
                handle_air_quality(engine, event)
            elif message.topic == TOPIC_MOBILITE:
                handle_velib(engine, event)
        except Exception as exc:
            print(f"Erreur traitement message ({message.topic}) : {exc}")


if __name__ == "__main__":
    main()
