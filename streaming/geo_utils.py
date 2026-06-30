
import json
import logging
from functools import lru_cache
from pathlib import Path

from shapely.geometry import Point, shape

logger = logging.getLogger("geo_utils")

REFERENCE_GEOJSON_PATH = Path(__file__).parent / "reference" / "arrondissements.geojson"


@lru_cache(maxsize=1)
def _load_arrondissement_polygons(geojson_bytes: bytes | None = None):
   
    if geojson_bytes is not None:
        data = json.loads(geojson_bytes)
    else:
        with open(REFERENCE_GEOJSON_PATH, encoding="utf-8") as f:
            data = json.load(f)

    polygons = []
    for feature in data["features"]:
        props = feature.get("properties", {})
        arr = props.get("c_ar") or props.get("NUM_ARR") or props.get("c_arinsee")
        if arr is None:
            continue
        # c_arinsee est au format 751XX (75101..75120) : on normalise vers 1..20.
        arr = int(arr)
        if arr > 100:
            arr = arr - 75100
        polygons.append((arr, shape(feature["geometry"])))
    return polygons


def find_arrondissement(lon: float, lat: float, geojson_bytes: bytes | None = None) -> int | None:
    
    point = Point(lon, lat)
    for arr, polygon in _load_arrondissement_polygons(geojson_bytes):
        if polygon.contains(point):
            return arr
    return None


def load_reference_geojson() -> dict:
    """Charge la copie de référence du GeoJSON officiel des arrondissements."""
    with open(REFERENCE_GEOJSON_PATH, encoding="utf-8") as f:
        return json.load(f)
