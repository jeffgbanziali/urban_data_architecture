import json
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from sqlalchemy import create_engine, text

TOPIC_MOBILITE = "mobilite.raw"
WINDOW_SECONDS = 10


def connect_consumer(bootstrap_servers: str, max_attempts: int = 20) -> KafkaConsumer:
    for attempt in range(1, max_attempts + 1):
        try:
            return KafkaConsumer(
                TOPIC_MOBILITE,
                bootstrap_servers=bootstrap_servers,
                value_deserializer=lambda v: json.loads(v.decode("utf-8")),
                auto_offset_reset="latest",
                enable_auto_commit=True,
                group_id="urban-micro-batch",
                # poll avec timeout court pour que la boucle de fenêtre reste précise
                consumer_timeout_ms=1000,
            )
        except NoBrokersAvailable:
            print(f"Kafka indisponible, tentative {attempt}/{max_attempts}...")
            time.sleep(5)
    raise RuntimeError("Impossible de se connecter à Kafka.")


def get_engine() -> object:
    host = os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold")
    db = os.environ.get("POSTGRES_GOLD_DB", "gold")
    user = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
    pwd = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")
    engine = create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:5432/{db}")
    for attempt in range(1, 20):
        try:
            with engine.connect():
                return engine
        except Exception:
            print(f"PostgreSQL indisponible, tentative {attempt}...")
            time.sleep(5)
    raise RuntimeError("Impossible de se connecter à PostgreSQL.")


INSERT_MICRO_BATCH = text(
    """
    INSERT INTO agregats_micro_batch
        (arrondissement, fenetre_debut, fenetre_fin, nb_stations, velos_moyen)
    VALUES (:arrondissement, :fenetre_debut, :fenetre_fin, :nb_stations, :velos_moyen)
    ON CONFLICT (arrondissement, fenetre_debut) DO UPDATE SET
        fenetre_fin  = EXCLUDED.fenetre_fin,
        nb_stations  = EXCLUDED.nb_stations,
        velos_moyen  = EXCLUDED.velos_moyen
    """
)


def flush_window(engine, window_data: dict, fenetre_debut: datetime, fenetre_fin: datetime):
    """
    Écrit un agrégat par arrondissement pour la fenêtre écoulée.
    window_data : {arrondissement -> [velos_disponibles, ...]}
    """
    if not window_data:
        return

    rows = []
    for arr, velos_list in window_data.items():
        nb = len(velos_list)
        moyen = round(sum(velos_list) / nb, 2)
        rows.append({
            "arrondissement": arr,
            "fenetre_debut": fenetre_debut.isoformat(),
            "fenetre_fin": fenetre_fin.isoformat(),
            "nb_stations": nb,
            "velos_moyen": moyen,
        })

    with engine.begin() as conn:
        for row in rows:
            conn.execute(INSERT_MICRO_BATCH, row)

    print(
        f"[micro-batch] fenêtre {fenetre_debut.strftime('%H:%M:%S')} → "
        f"{fenetre_fin.strftime('%H:%M:%S')} : "
        f"{len(rows)} arrondissements persistés"
    )


def main():
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    consumer = connect_consumer(bootstrap)
    engine = get_engine()
    print(f"Micro-batch processor démarré (fenêtre {WINDOW_SECONDS}s) sur '{TOPIC_MOBILITE}'")

    window_data: dict = defaultdict(list)
    fenetre_debut = datetime.now(timezone.utc)

    while True:
        # Consomme pendant WINDOW_SECONDS secondes
        deadline = time.time() + WINDOW_SECONDS
        while time.time() < deadline:
            try:
                for message in consumer:
                    ev = message.value
                    arr = ev.get("arrondissement")
                    velos = ev.get("velos_disponibles")
                    if arr and velos is not None:
                        window_data[arr].append(int(velos))
                    if time.time() >= deadline:
                        break
            except StopIteration:
                # consumer_timeout_ms expiré — fenêtre peut-être vide, on attend
                break

        fenetre_fin = datetime.now(timezone.utc)
        flush_window(engine, dict(window_data), fenetre_debut, fenetre_fin)

        window_data.clear()
        fenetre_debut = fenetre_fin


if __name__ == "__main__":
    main()
