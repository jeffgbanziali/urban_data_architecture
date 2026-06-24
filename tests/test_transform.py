"""
tests/test_transform.py
--------------------------
Tests unitaires de la couche de nettoyage Silver. Ne nécessitent ni MinIO ni
réseau : ils appellent directement les fonctions pures de transformation.

Les fixtures sont construites au format geo-dvf réel (colonnes code_postal,
valeur_fonciere, surface_reelle_bati, type_local) — le seul format ingéré par
le pipeline depuis la suppression des données synthétiques.

Lancer avec : pytest tests/test_transform.py -v
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "bronze"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "silver"))

import clean_silver  # noqa: E402
from clean_silver import clean_dvf, clean_population_arrondissements, clean_espaces_verts_demo  # noqa: E402


# ─────────────────────────────────────────────────────────────
# Fixtures DVF au vrai format geo-dvf (code_postal + valeur_fonciere)
# ─────────────────────────────────────────────────────────────

def _make_dvf_real(n_per_arr: int = 5) -> pd.DataFrame:
    """Construit un DataFrame au vrai format geo-dvf couvrant les 20 arrondissements."""
    import random
    rng = random.Random(42)
    BASE_PRIX = {
        1: 13700, 2: 12300, 3: 12800, 4: 13900, 5: 12600, 6: 14500, 7: 14200,
        8: 11400, 9: 10800, 10: 9600, 11: 10100, 12: 9300, 13: 9100, 14: 9700,
        15: 10000, 16: 11600, 17: 10300, 18: 9200, 19: 8200, 20: 8600,
    }
    rows = []
    for arr in range(1, 21):
        for i in range(n_per_arr):
            surface = rng.randint(20, 100)
            prix_m2 = max(3000, rng.gauss(BASE_PRIX[arr], BASE_PRIX[arr] * 0.1))
            rows.append({
                "id_mutation": f"2024-{arr:02d}-{i:04d}",
                "date_mutation": "2024-05-15",
                "code_postal": 75000 + arr,
                "surface_reelle_bati": surface,
                "valeur_fonciere": round(prix_m2 * surface, 2),
                "type_local": "Appartement",
            })
    return pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────
# Tests DVF
# ─────────────────────────────────────────────────────────────

def test_clean_dvf_detects_real_geo_dvf_format():
    """Le format geo-dvf réel (code_postal + valeur_fonciere) est détecté et nettoyé."""
    df = _make_dvf_real()
    cleaned, report = clean_dvf(df)
    assert report["format_detecte"] == "geo-dvf réel"
    assert cleaned["arrondissement"].between(1, 20).all()
    assert cleaned["prix_m2"].between(1000, 30000).all()
    assert cleaned["arrondissement"].nunique() == 20


def test_clean_dvf_removes_outliers_and_duplicates():
    df = _make_dvf_real()
    # Doublon volontaire
    df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    # Valeur aberrante volontaire
    df.loc[1, "valeur_fonciere"] = 9_999_999
    # Ligne hors Paris (code postal 92100 → arrondissement NA → supprimée)
    df.loc[2, "code_postal"] = 92100

    cleaned, report = clean_dvf(df)

    assert cleaned["prix_m2"].between(1000, 30000).all()
    assert cleaned["arrondissement"].notna().all()
    assert report["issues"]["doublons_supprimes"] >= 1
    assert report["issues"]["valeurs_aberrantes_filtrees"] >= 1
    assert report["issues"]["lignes_sans_arrondissement_supprimees"] >= 1
    assert report["schema_valide"] is True


def test_clean_dvf_imputes_missing_prix_by_arrondissement_median():
    df = _make_dvf_real()
    # Surface à 0 → prix_m2 = inf → NA après replace
    df.loc[0, "surface_reelle_bati"] = 0
    cleaned, report = clean_dvf(df)
    assert cleaned["prix_m2"].notna().all()
    assert report["issues"]["prix_m2_imputes_par_mediane_arr"] >= 1


def test_clean_dvf_excludes_non_residential():
    """Les locaux commerciaux et industriels sont exclus du calcul prix/m²."""
    df = pd.DataFrame([
        {"id_mutation": "A", "date_mutation": "2024-03-15", "valeur_fonciere": 650000,
         "code_postal": 75007, "type_local": "Appartement", "surface_reelle_bati": 45},
        {"id_mutation": "B", "date_mutation": "2024-06-10", "valeur_fonciere": 1200000,
         "code_postal": 75006, "type_local": "Appartement", "surface_reelle_bati": 80},
        {"id_mutation": "C", "date_mutation": "2024-02-20", "valeur_fonciere": 300000,
         "code_postal": 75011, "type_local": "Local industriel. commercial ou assimilé",
         "surface_reelle_bati": 60},
        {"id_mutation": "D", "date_mutation": "2024-04-01", "valeur_fonciere": 200000,
         "code_postal": 92100, "type_local": "Appartement", "surface_reelle_bati": 40},
    ])
    cleaned, report = clean_dvf(df)
    assert report["format_detecte"] == "geo-dvf réel"
    assert report["issues"]["lignes_non_habitation_exclues"] == 1
    assert report["issues"]["lignes_sans_arrondissement_supprimees"] == 1
    assert len(cleaned) == 2
    assert cleaned.loc[cleaned["id_mutation"] == "A", "arrondissement"].iloc[0] == 7
    assert abs(cleaned.loc[cleaned["id_mutation"] == "A", "prix_m2"].iloc[0] - 650000 / 45) < 0.01


def test_aggregation_variation_pct_logic():
    """Logique de aggregate_gold.py : médiane par an + variation annuelle (%)."""
    frames = []
    for year in (2021, 2022, 2023, 2024):
        df = _make_dvf_real()
        df["annee"] = year
        # On calcule prix_m2 à partir du format réel pour alimenter la logique d'agrégation
        df["prix_m2"] = df["valeur_fonciere"] / df["surface_reelle_bati"]
        df["arrondissement"] = (df["code_postal"] - 75000).where(
            df["code_postal"].between(75001, 75020)
        )
        frames.append(df)

    full = pd.concat(frames, ignore_index=True)
    full = full.dropna(subset=["arrondissement"])

    agg = (
        full.groupby(["arrondissement", "annee"])["prix_m2"]
        .median()
        .reset_index()
        .rename(columns={"prix_m2": "prix_m2_median"})
        .sort_values(["arrondissement", "annee"])
    )
    agg["variation_pct"] = (
        agg.groupby("arrondissement")["prix_m2_median"].pct_change().mul(100).round(2)
    )

    assert agg["arrondissement"].nunique() == 20
    assert agg.groupby("arrondissement").head(1)["variation_pct"].isna().all()


# ─────────────────────────────────────────────────────────────
# Tests population INSEE
# ─────────────────────────────────────────────────────────────

def test_clean_population_arrondissements_extracts_20_arrondissements():
    rows = []
    for i in range(1, 21):
        code = f"751{i:02d}"
        rows.append({"typecom": "ARM", "code_commune_insee": code,
                     "population": 50000 + i * 1000, "densite": 20000 + i * 500})
    rows.append({"typecom": "COM", "code_commune_insee": "92100", "population": 80000, "densite": 10000})
    rows.append({"typecom": "ARM", "code_commune_insee": "13055", "population": 900000, "densite": 3500})

    df_clean, report = clean_population_arrondissements(pd.DataFrame(rows))

    assert report.get("lignes_arm_751xx_trouvees") == 20
    assert "alerte" not in report, f"Alerte inattendue : {report.get('alerte')}"
    assert len(df_clean) == 20
    assert set(df_clean.columns) == {"arrondissement", "population", "densite_hab_km2"}
    arr7 = df_clean[df_clean["arrondissement"] == 7].iloc[0]
    assert int(arr7["population"]) == 57000


def test_clean_population_arrondissements_alerts_on_wrong_count():
    df_raw = pd.DataFrame([
        {"typecom": "ARM", "code_commune_insee": "75101", "population": 10000, "densite": 5000},
        {"typecom": "ARM", "code_commune_insee": "75102", "population": 20000, "densite": 8000},
    ])
    _, report = clean_population_arrondissements(df_raw)
    assert "alerte" in report


# ─────────────────────────────────────────────────────────────
# Tests espaces verts — vraies adresses parisiennes connues
# ─────────────────────────────────────────────────────────────

# Adresses réelles utilisées comme fixtures de test (pas générées — ce sont
# de vrais lieux parisiens avec leurs adresses officielles).
_ESPACES_VERTS_CONNUS = [
    ("Jardin des Tuileries",       "113 Rue de Rivoli, 75001 Paris"),
    ("Jardin du Palais-Royal",     "Place du Palais-Royal, 75001 Paris"),
    ("Jardin des Plantes",         "57 Rue Cuvier, 75005 Paris"),
    ("Jardin du Luxembourg",       "Rue de Médicis, 75006 Paris"),
    ("Champ de Mars",              "2 Allée Adrienne Lecouvreur, 75007 Paris"),
    ("Parc Monceau",               "35 Boulevard de Courcelles, 75008 Paris"),
    ("Parc Montsouris",            "2 Rue Gazan, 75014 Paris"),
    ("Parc des Buttes-Chaumont",   "1 Rue Botzaris, 75019 Paris"),
]

_COORDS_REELLES = {
    "113 Rue de Rivoli, 75001 Paris":             (2.3279, 48.8634),
    "Place du Palais-Royal, 75001 Paris":          (2.3372, 48.8634),
    "57 Rue Cuvier, 75005 Paris":                  (2.3589, 48.8438),
    "Rue de Médicis, 75006 Paris":                 (2.3372, 48.8462),
    "2 Allée Adrienne Lecouvreur, 75007 Paris":    (2.2945, 48.8556),
    "35 Boulevard de Courcelles, 75008 Paris":     (2.3089, 48.8800),
    "2 Rue Gazan, 75014 Paris":                    (2.3370, 48.8217),
    "1 Rue Botzaris, 75019 Paris":                 (2.3819, 48.8800),
}


def test_clean_espaces_verts_geocodes_and_resolves_arrondissement(monkeypatch):
    """
    Valide la chaîne complète adresse -> API BAN (simulée) -> point-in-polygon
    -> arrondissement, sans dépendre du réseau.
    """
    monkeypatch.setattr(clean_silver, "geocode_address", lambda a: _COORDS_REELLES.get(a, (None, None)))
    monkeypatch.setattr(clean_silver, "GEOCODE_THROTTLE_S", 0)

    df_raw = pd.DataFrame([{"nom": nom, "adresse": adresse} for nom, adresse in _ESPACES_VERTS_CONNUS])
    df_clean, report = clean_espaces_verts_demo(df_raw)

    assert report["issues"]["adresses_geocodees_avec_succes"] == len(df_raw)
    assert report["issues"]["arrondissements_resolus_par_point_in_polygon"] == len(df_raw)
    assert report["taux_geocodage_pct"] == 100.0

    champ_de_mars = df_clean.loc[df_clean["nom"] == "Champ de Mars", "arrondissement"].iloc[0]
    luxembourg = df_clean.loc[df_clean["nom"] == "Jardin du Luxembourg", "arrondissement"].iloc[0]
    assert champ_de_mars == 7
    assert luxembourg == 6


def test_clean_espaces_verts_handles_geocoding_failures_gracefully(monkeypatch):
    """Les échecs de géocodage sont comptés et tracés, jamais masqués (résilience)."""
    monkeypatch.setattr(clean_silver, "geocode_address", lambda adresse: (None, None))
    monkeypatch.setattr(clean_silver, "GEOCODE_THROTTLE_S", 0)

    df_raw = pd.DataFrame([{"nom": nom, "adresse": adresse} for nom, adresse in _ESPACES_VERTS_CONNUS])
    df_clean, report = clean_espaces_verts_demo(df_raw)

    assert report["issues"]["adresses_geocodage_echoue"] == len(df_raw)
    assert len(df_clean) == len(df_raw)
    assert df_clean["arrondissement"].isna().all()


def test_clean_espaces_verts_real_uses_provided_coordinates():
    """Le vrai fichier OpenData Paris fournit des coordonnées directement (geom_x_y)."""
    df_raw = pd.DataFrame([
        {"nom_ev": "CHAMP DE MARS", "adresse_numero": 2, "adresse_typevoie": "ALLEE",
         "adresse_libellevoie": "ADRIENNE LECOUVREUR", "adresse_codepostal": 75007,
         "geom_x_y": "48.8556, 2.2945"},
        {"nom_ev": "JARDIN DU LUXEMBOURG", "adresse_numero": None, "adresse_typevoie": "RUE",
         "adresse_libellevoie": "DE MEDICIS", "adresse_codepostal": 75006,
         "geom_x_y": "48.8462, 2.3372"},
        {"nom_ev": "ESPACE SANS COORDONNEES", "adresse_numero": 1, "adresse_typevoie": "RUE",
         "adresse_libellevoie": "INCONNUE", "adresse_codepostal": 75018,
         "geom_x_y": None},
    ])
    df_clean, report = clean_silver.clean_espaces_verts_real(df_raw)

    assert report["issues"]["coordonnees_presentes"] == 2
    assert report["issues"]["arrondissement_resolu_point_in_polygon"] == 2
    assert report["issues"]["arrondissement_resolu_repli_code_postal"] == 1
    assert report["issues"]["arrondissement_non_resolu"] == 0

    arr_by_nom = dict(zip(df_clean["nom"], df_clean["arrondissement"]))
    assert arr_by_nom["CHAMP DE MARS"] == 7
    assert arr_by_nom["JARDIN DU LUXEMBOURG"] == 6
    assert arr_by_nom["ESPACE SANS COORDONNEES"] == 18


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
