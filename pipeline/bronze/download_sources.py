"""
pipeline/bronze/download_sources.py
-------------------------------------
Télécharge les sources de données ouvertes et les écrit en zone BRONZE de MinIO
avec un préfixe horodaté (format : {source}/YYYY/MM/DD/HHMMSS/{source}.ext).

Principe de résilience : chaque source est traitée de façon indépendante.
Un échec réseau sur DVF ne bloque pas le téléchargement INSEE, ni les espaces
verts. Le rapport JSON final reflète le taux de réussite réel.

Après dépôt MinIO, le rapport est inséré dans la table PostgreSQL
`pipeline_rapports` (JSONB) pour interrogation analytique via
GET /admin/rapports-qualite sans parcourir les fichiers MinIO un par un.

Métriques systématiquement calculées : duree_s, volume_octets, taux_succes_pct,
debit_octets_par_s — harmonisées avec les couches Silver et Gold (C2.4).
"""
import gzip
import io
import time
import traceback
import zipfile

import pandas as pd
import requests

from minio_client import get_s3_client, put_bytes, put_json, versioned_prefix
from pipeline_reporter import write_pipeline_report

BRONZE_BUCKET = "bronze"

# Sources de données ouvertes mobilisées par le projet Urban Data Explorer.
# `kind` détermine comment la réponse HTTP doit être interprétée avant écriture.
SOURCES = {
    # ===== DVF (Demandes de Valeurs Foncières) — marché immobilier =====
    "dvf_2025": {
        "url": "https://files.data.gouv.fr/geo-dvf/latest/csv/2025/departements/75.csv.gz",
        "kind": "gzip_csv",
    },
    "dvf_2024": {
        "url": "https://files.data.gouv.fr/geo-dvf/latest/csv/2024/departements/75.csv.gz",
        "kind": "gzip_csv",
    },
    "dvf_2023": {
        "url": "https://files.data.gouv.fr/geo-dvf/latest/csv/2023/departements/75.csv.gz",
        "kind": "gzip_csv",
    },
    "dvf_2022": {
        "url": "https://files.data.gouv.fr/geo-dvf/latest/csv/2022/departements/75.csv.gz",
        "kind": "gzip_csv",
    },
    "dvf_2021": {
        "url": "https://files.data.gouv.fr/geo-dvf/latest/csv/2021/departements/75.csv.gz",
        "kind": "gzip_csv",
    },

    # ===== Qualité de l'air =====
    "qualite_air_stations": {
        "url": "https://data.airparif.asso.fr/api/v1/stations",
        "kind": "json",
    },

    # ===== Criminalité (SSMSI / ministère de l'Intérieur) =====
    # Base communale des principaux indicateurs de crimes et délits, qui inclut
    # depuis mars 2023 les arrondissements de Paris (champ "CODGEO_2024" du type
    # 75056 pour Paris global, ou code arrondissement spécifique selon les
    # millésimes). Source officielle, mise à jour annuellement par le SSMSI.
    "criminalite_communale": {
        "url": "https://www.data.gouv.fr/api/1/datasets/r/44ef4323-1097-48d5-8719-3c544b55d294",
        "kind": "gzip_csv",
    },

    # ===== Transports en commun =====
    # IDFM — Emplacement des gares IDF complet (toutes les gares IDF dont metro + RER).
    # Colonnes clés : geo_point_2d (lat,lon), metro (0/1), rer (0/1), train (0/1).
    # Ce dataset inclut les arrêts individuels de métro, RER, Transilien et tram.
    "metro_stations": {
        "url": "https://data.iledefrance-mobilites.fr/api/explore/v2.1/catalog/datasets/"
               "emplacement-des-gares-idf/exports/csv",
        "kind": "csv",
    },
    "velib_stations": {
        "url": "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/"
               "velib-disponibilite-en-temps-reel/exports/csv",
        "kind": "csv",
    },

    # ===== Équipements et environnement =====
    "espaces_verts": {
        "url": "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/espaces_verts/exports/csv",
        "kind": "csv",
    },

    # ===== Données géographiques (référentiel pour la carte choroplèthe) =====
    "arrondissements": {
        "url": "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/arrondissements/exports/geojson",
        "kind": "geojson",
    },
    "quartiers": {
        "url": "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/quartier_paris/exports/geojson",
        "kind": "geojson",
    },

    # ===== Démographie — populations légales INSEE 2021 (niveau arrondissement) =====
    # ZIP "Populations légales 2021" (data.gouv.fr / INSEE) — contient
    # donnees_communes.csv avec les 20 arrondissements de Paris (codes 75101-75120)
    # et la colonne pmun (population municipale légale 2021).
    "communes_insee": {
        "url": "https://static.data.gouv.fr/resources/populations-legales-2021/20240213-095355/ensemble.zip",
        "kind": "zip_extract",
        "file_in_zip": "donnees_communes.csv",
    },
}


def fetch(url: str, timeout: int = 30) -> requests.Response:
    resp = requests.get(url, stream=True, timeout=timeout, headers={"User-Agent": "urban-data-explorer/1.0"})
    resp.raise_for_status()
    return resp


def handle_source(client, name: str, conf: dict) -> dict:
    """Télécharge une source et l'écrit en bronze. Retourne un statut détaillé."""
    started = time.time()
    prefix = versioned_prefix(name)
    result = {"source": name, "url": conf["url"], "status": "failed", "duration_s": None, "error": None}

    try:
        resp = fetch(conf["url"])
        raw_bytes = resp.content

        if conf["kind"] == "gzip_csv":
            decompressed = gzip.decompress(raw_bytes)
            key = f"{prefix}/{name}.csv"
            ok = put_bytes(client, BRONZE_BUCKET, key, decompressed, content_type="text/csv")
        elif conf["kind"] == "zip_extract":
            # Extrait un fichier spécifique depuis un ZIP en mémoire.
            zf = zipfile.ZipFile(io.BytesIO(raw_bytes))
            file_in_zip = conf.get("file_in_zip")
            with zf.open(file_in_zip) as inner:
                decompressed = inner.read()
            key = f"{prefix}/{name}.csv"
            ok = put_bytes(client, BRONZE_BUCKET, key, decompressed, content_type="text/csv")
        elif conf["kind"] in ("csv",):
            key = f"{prefix}/{name}.csv"
            ok = put_bytes(client, BRONZE_BUCKET, key, raw_bytes, content_type="text/csv")
        elif conf["kind"] in ("json",):
            key = f"{prefix}/{name}.json"
            ok = put_bytes(client, BRONZE_BUCKET, key, raw_bytes, content_type="application/json")
        elif conf["kind"] in ("geojson",):
            key = f"{prefix}/{name}.geojson"
            ok = put_bytes(client, BRONZE_BUCKET, key, raw_bytes, content_type="application/geo+json")
        else:  # binary (zip, etc.)
            key = f"{prefix}/{name}.bin"
            ok = put_bytes(client, BRONZE_BUCKET, key, raw_bytes, content_type="application/octet-stream")

        result["status"] = "success" if ok else "failed"
        result["key"] = key
        result["bytes"] = len(raw_bytes)
    except Exception as exc:  # noqa: BLE001 - on isole volontairement chaque source
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc(limit=3)

    result["duration_s"] = round(time.time() - started, 2)
    return result


def main():
    client = get_s3_client()
    run_start = time.time()
    report = {"run_started": time.strftime("%Y-%m-%dT%H:%M:%S"), "sources": []}

    print("=" * 60)
    print("INGESTION BRONZE — Urban Data Explorer")
    print("=" * 60)

    for name, conf in SOURCES.items():
        print(f"\nSource : {name}")
        outcome = handle_source(client, name, conf)
        report["sources"].append(outcome)
        status_label = "OK" if outcome["status"] == "success" else "ECHEC"
        print(f"   {status_label} en {outcome['duration_s']}s")
        if outcome.get("error"):
            print(f"   {outcome['error']}")

    n_ok = sum(1 for s in report["sources"] if s["status"] == "success")
    volume_total = sum(s.get("bytes", 0) for s in report["sources"] if s["status"] == "success")
    duree_totale = round(time.time() - run_start, 2)

    report["summary"] = {
        "total": len(SOURCES),
        "success": n_ok,
        "failed": len(SOURCES) - n_ok,
        # Métriques harmonisées C1.3 / C2.4
        "duree_s": duree_totale,
        "volume_octets": volume_total,
        "debit_octets_par_s": round(volume_total / max(duree_totale, 0.01), 1),
        "taux_succes_pct": round(100 * n_ok / max(len(SOURCES), 1), 1),
    }

    report_key = f"_reports/ingestion/{versioned_prefix('run')}.json"
    put_json(client, BRONZE_BUCKET, report_key, report)

    # Rapport dans PostgreSQL pipeline_rapports (JSONB) pour /admin/rapports-qualite
    write_pipeline_report("bronze", report)

    print("\n" + "=" * 60)
    print(f"Résumé : {n_ok}/{len(SOURCES)} sources réussies — {volume_total/1024/1024:.1f} MB en {duree_totale}s")
    print(f"Rapport : s3://{BRONZE_BUCKET}/{report_key}")
    print("=" * 60)
    return report


if __name__ == "__main__":
    main()
