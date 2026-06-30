import json
import os
import random
import time

import requests
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

from geo_utils import find_arrondissement

TOPIC_EVENTS = "events.stream"
TOPIC_MOBILITE = "mobilite.raw"

ARRONDISSEMENTS = list(range(1, 21))
BASE_QUALITE_AIR = {  # repli si WAQI indisponible ; plus haut = meilleur
    1: 60, 2: 62, 3: 65, 4: 63, 5: 68, 6: 64, 7: 66, 8: 61, 9: 67, 10: 72,
    11: 70, 12: 69, 13: 71, 14: 67, 15: 66, 16: 64, 17: 68, 18: 74, 19: 76, 20: 75,
}

# Boîte englobant Paris intra-muros (lat_min, lon_min, lat_max, lon_max).
PARIS_BBOX = "48.815,2.225,48.902,2.470"
WAQI_TOKEN = os.environ.get("WAQI_API_TOKEN", "").strip()
AIR_QUALITY_POLL_INTERVAL_S = int(os.environ.get("AIR_QUALITY_POLL_INTERVAL_S", "300"))
VELIB_POLL_INTERVAL_S = 60

VELIB_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "velib-disponibilite-en-temps-reel/exports/json"
)


def connect_with_retry(bootstrap_servers: str, max_attempts: int = 20):
    for attempt in range(1, max_attempts + 1):
        try:
            return KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
            )
        except NoBrokersAvailable:
            print(f"Kafka indisponible, tentative {attempt}/{max_attempts}...")
            time.sleep(5)
    raise RuntimeError("Impossible de se connecter à Kafka après plusieurs tentatives.")


def fetch_real_air_quality_events() -> list[dict]:
    """Récupère les vraies stations WAQI dans Paris et les rattache à leur arrondissement."""
    if not WAQI_TOKEN:
        return []
    try:
        resp = requests.get(
            "https://api.waqi.info/map/bounds/",
            params={"latlng": PARIS_BBOX, "token": WAQI_TOKEN},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        if payload.get("status") != "ok":
            return []
    except Exception as exc:
        print(f"WAQI indisponible ({exc}), repli sur la génération synthétique")
        return []

    events = []
    for station in payload.get("data", []):
        aqi_raw = station.get("aqi")
        if aqi_raw in (None, "-", ""):
            continue
        try:
            aqi = float(aqi_raw)
        except (TypeError, ValueError):
            continue

        arr = find_arrondissement(station.get("lon"), station.get("lat"))
        if arr is None:
            continue

        events.append({
            "arrondissement": arr,
            "indice_qualite_air": aqi,
            "horodatage": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })
    return events


def make_air_quality_event() -> dict:
    """Repli synthétique, utilisé uniquement si WAQI est sans token configuré."""
    arr = random.choice(ARRONDISSEMENTS)
    indice = round(max(10, min(100, random.gauss(BASE_QUALITE_AIR[arr], 4))), 1)
    return {
        "arrondissement": arr,
        "indice_qualite_air": indice,
        "horodatage": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def fetch_real_velib_events() -> list[dict]:
   
    try:
        resp = requests.get(VELIB_URL, timeout=20)
        resp.raise_for_status()
        stations = resp.json()
    except Exception as exc:
        print(f"Vélib indisponible ({exc}), aucun événement publié ce cycle")
        return []

    events = []
    for station in stations:
        coords = station.get("coordonnees_geo")
        if not coords:
            continue
        lat = coords.get("lat")
        lon = coords.get("lon")
        if lat is None or lon is None:
            continue

        arr = find_arrondissement(lon, lat)
        if arr is None:
            continue  # station hors Paris intra-muros (Boulogne, etc.)

        velos = station.get("numbikesavailable")
        bornes = station.get("numdocksavailable")
        if velos is None or bornes is None:
            continue

        events.append({
            "arrondissement": arr,
            "station_code": station.get("stationcode", ""),
            "station_nom": station.get("name", ""),
            "velos_disponibles": int(velos),
            "bornes_libres": int(bornes),
            "horodatage": time.strftime("%Y-%m-%dT%H:%M:%S"),
        })

    print(f"[{TOPIC_MOBILITE}] {len(events)} stations Vélib résolues en arrondissements Paris")
    return events


def main():
    bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    producer = connect_with_retry(bootstrap)
    using_real_air_quality = bool(WAQI_TOKEN)
    mode_air = "WAQI réel" if using_real_air_quality else "synthétique (pas de WAQI_API_TOKEN)"
    print(f"Producteur démarré — qualité air: {mode_air} | Vélib: OpenData Paris réel")

    last_air_quality_poll = 0.0
    last_velib_poll = 0.0
    cached_air_quality_events: list[dict] = []

    while True:
        now = time.time()

        # --- Qualité de l'air (toutes les AIR_QUALITY_POLL_INTERVAL_S secondes) ---
        if using_real_air_quality and (now - last_air_quality_poll) >= AIR_QUALITY_POLL_INTERVAL_S:
            fetched = fetch_real_air_quality_events()
            if fetched:
                cached_air_quality_events = fetched
                print(f"[{TOPIC_EVENTS}] {len(fetched)} stations WAQI récupérées")
            last_air_quality_poll = now

        if random.random() < 0.5:
            event = random.choice(cached_air_quality_events) if cached_air_quality_events else make_air_quality_event()
            producer.send(TOPIC_EVENTS, value=event)
            print(f"[{TOPIC_EVENTS}] {event}")

        # --- Vélib (toutes les 60 secondes) ---
        if (now - last_velib_poll) >= VELIB_POLL_INTERVAL_S:
            velib_events = fetch_real_velib_events()
            for ev in velib_events:
                producer.send(TOPIC_MOBILITE, value=ev)
            last_velib_poll = now

        producer.flush()
        time.sleep(random.uniform(2, 6))


if __name__ == "__main__":
    main()
