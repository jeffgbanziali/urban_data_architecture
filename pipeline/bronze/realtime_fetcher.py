import json
import os
import time

import psycopg2
import requests

from geo_utils import find_arrondissement

WAQI_TOKEN = os.environ.get("WAQI_API_TOKEN", "").strip()
PARIS_BBOX = "48.815,2.225,48.902,2.470"
VELIB_URL = (
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
    "velib-disponibilite-en-temps-reel/exports/json"
)
NOTIFY_CHANNEL = "realtime_channel"


def _get_conn():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold"),
        dbname=os.environ.get("POSTGRES_GOLD_DB", "gold"),
        user=os.environ.get("POSTGRES_GOLD_USER", "gold_user"),
        password=os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass"),
    )


def fetch_and_store_air_quality() -> int:
    """
    Interroge l'API WAQI, résout chaque station en arrondissement,
    insère dans qualite_air_temps_reel et déclenche pg_notify.
    Retourne le nombre de mesures insérées.
    """
    if not WAQI_TOKEN:
        print("WAQI_API_TOKEN absent — tâche ignorée")
        return 0

    try:
        resp = requests.get(
            "https://api.waqi.info/map/bounds/",
            params={"latlng": PARIS_BBOX, "token": WAQI_TOKEN},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
    except Exception as exc:
        print(f"WAQI indisponible : {exc}")
        return 0

    if payload.get("status") != "ok":
        return 0

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
        events.append({"arrondissement": arr, "indice_qualite_air": aqi})

    if not events:
        return 0

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _get_conn() as conn, conn.cursor() as cur:
        for ev in events:
            cur.execute(
                "INSERT INTO qualite_air_temps_reel (arrondissement, indice_qualite_air) "
                "VALUES (%s, %s)",
                (ev["arrondissement"], ev["indice_qualite_air"]),
            )
            payload_json = json.dumps({"type": "qualite_air", "horodatage": ts, **ev})
            cur.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, payload_json))
        conn.commit()

    print(f"[air_quality] {len(events)} mesures insérées")
    return len(events)


def fetch_and_store_velib() -> int:
    """
    Interroge l'API OpenData Paris Vélib', résout chaque station par
    point-in-polygon, insère dans disponibilite_velib_temps_reel,
    met à jour velib_agregats_temps_reel et déclenche pg_notify.
    Retourne le nombre de stations traitées.
    """
    try:
        resp = requests.get(VELIB_URL, timeout=20)
        resp.raise_for_status()
        stations = resp.json()
    except Exception as exc:
        print(f"Vélib indisponible : {exc}")
        return 0

    events = []
    for station in stations:
        coords = station.get("coordonnees_geo")
        if not coords:
            continue
        lat, lon = coords.get("lat"), coords.get("lon")
        if lat is None or lon is None:
            continue
        arr = find_arrondissement(lon, lat)
        if arr is None:
            continue
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
        })

    if not events:
        return 0

    ts = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _get_conn() as conn, conn.cursor() as cur:
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
            payload_json = json.dumps({"type": "velib", "horodatage": ts, **ev})
            cur.execute("SELECT pg_notify(%s, %s)", (NOTIFY_CHANNEL, payload_json))
        conn.commit()

    print(f"[velib] {len(events)} stations traitées")
    return len(events)
