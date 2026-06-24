"""
api/app/routers/geo.py
-------------------------
Expose le GeoJSON enrichi (géométries officielles des 20 arrondissements +
tous les indicateurs Gold courants, par année pour les prix) produit par
`aggregate/aggregate_gold.py::build_enriched_geojson`.

C'est cet endpoint que consomme l'explorateur de données du frontend pour sa
carte choroplèthe — il ferme la boucle architecture décrite dans le schéma :
Zone Gold (GeoJSON/Parquet) -> API Backend -> Dashboard Frontend.

Mode de repli : si MinIO est indisponible ou si le pipeline n'a encore jamais
tourné, on sert la géométrie officielle de référence (sans indicateurs) plutôt
que de renvoyer une erreur — le frontend affiche alors la carte avec des
valeurs manquantes plutôt que de planter, cohérent avec la résilience déjà en
place ailleurs dans le pipeline.
"""
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
