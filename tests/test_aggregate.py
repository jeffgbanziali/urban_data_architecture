import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingestion"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "aggregate"))

import aggregate_gold as ag  # noqa: E402


@pytest.fixture(autouse=True)
def no_bronze_geojson(monkeypatch):
    """Force le repli sur la copie de référence (pas de MinIO dans les tests)."""
    monkeypatch.setattr(ag, "latest_bronze_geojson", lambda client: None)


def test_build_enriched_geojson_merges_real_geometry_with_indicators():
    df_prix = pd.DataFrame([
        {"arrondissement": 7, "annee": 2023, "prix_m2_median": 14000.0, "variation_pct": None},
        {"arrondissement": 7, "annee": 2024, "prix_m2_median": 14500.0, "variation_pct": 3.57},
        {"arrondissement": 1, "annee": 2024, "prix_m2_median": 13700.0, "variation_pct": 2.1},
    ])
    df_socio = pd.DataFrame([
        {"arrondissement": 7, "population": 50000, "nb_espaces_verts": 1},
        {"arrondissement": 1, "population": 16000, "nb_espaces_verts": 3},
    ])

    geojson = ag.build_enriched_geojson(client=None, df_prix=df_prix, df_socio=df_socio)

    assert len(geojson["features"]) == 20  # les 20 arrondissements, géométrie réelle
    assert all(f["geometry"]["type"] == "Polygon" for f in geojson["features"])

    arr7 = next(f for f in geojson["features"] if f["properties"]["NUM_ARR"] == 7)
    assert arr7["properties"]["value_prixM2_2024"] == 14500.0
    assert arr7["properties"]["value_variationPct_2024"] == 3.57
    assert arr7["properties"]["value_population"] == 50000.0
    assert arr7["properties"]["value_nb_espaces_verts"] == 1.0


def test_build_enriched_geojson_produces_strictly_valid_json():
    """Le JSON.parse() du navigateur rejette NaN/Infinity : on vérifie qu'on n'en produit jamais."""
    df_prix = pd.DataFrame([
        {"arrondissement": 7, "annee": 2023, "prix_m2_median": 14000.0, "variation_pct": None},  # 1ère année -> NaN
    ])
    df_socio = pd.DataFrame([{"arrondissement": 7, "population": 50000}])

    geojson = ag.build_enriched_geojson(client=None, df_prix=df_prix, df_socio=df_socio)

    json.dumps(geojson, allow_nan=False)  # lève une exception si un NaN s'est glissé

    arr7 = next(f for f in geojson["features"] if f["properties"]["NUM_ARR"] == 7)
    assert "value_variationPct_2023" not in arr7["properties"]


def test_build_enriched_geojson_handles_empty_dataframes():
    """Si Silver/Gold n'a encore rien produit, on doit quand même renvoyer la géométrie."""
    geojson = ag.build_enriched_geojson(client=None, df_prix=pd.DataFrame(), df_socio=pd.DataFrame())
    assert len(geojson["features"]) == 20
    arr1 = next(f for f in geojson["features"] if f["properties"]["NUM_ARR"] == 1)
    assert "value_prixM2_2024" not in arr1["properties"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
