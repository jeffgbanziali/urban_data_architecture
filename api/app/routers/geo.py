import json
from pathlib import Path

from fastapi import APIRouter, Depends

from app.minio_client import try_get_bytes
from app.security import rate_limit

router = APIRouter(dependencies=[Depends(rate_limit)])

GOLD_BUCKET = "gold"
ENRICHED_GEOJSON_KEY = "enriched_arrondissements/latest.geojson"
FALLBACK_GEOJSON_PATH = Path(__file__).resolve().parent.parent / "static_data" / "arrondissements.geojson"


@router.get("/geo/arrondissements", tags=["Référentiel"])
def get_enriched_geojson():
    """GeoJSON des 20 arrondissements, enrichi des indicateurs Gold courants."""
    raw = try_get_bytes(GOLD_BUCKET, ENRICHED_GEOJSON_KEY)
    if raw is not None:
        return json.loads(raw)

    # Repli : géométries officielles sans indicateurs (le pipeline n'a pas
    # encore produit d'export, ou MinIO est temporairement indisponible).
    with open(FALLBACK_GEOJSON_PATH, encoding="utf-8") as f:
        fallback = json.load(f)
    for feature in fallback["features"]:
        props = feature.get("properties", {})
        arr = props.get("c_ar") or props.get("NUM_ARR") or props.get("c_arinsee")
        arr = int(arr) - 75100 if arr and arr > 100 else arr
        feature["properties"] = {"NUM_ARR": arr, "NOM": f"{arr}e" if arr else None}
    return fallback
