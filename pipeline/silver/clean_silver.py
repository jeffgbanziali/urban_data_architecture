import io
import json
import time

import pandas as pd
import requests

from minio_client import (
    get_s3_client,
    list_keys,
    get_bytes,
    put_dataframe_as_parquet,
    put_json,
    versioned_prefix,
)
from geo_utils import find_arrondissement
from pipeline_reporter import write_pipeline_report

BRONZE_BUCKET = "bronze"
SILVER_BUCKET = "silver"

PRIX_M2_MIN, PRIX_M2_MAX = 1000, 30000
BAN_GEOCODE_URL = "https://api-adresse.data.gouv.fr/search/"
GEOCODE_THROTTLE_S = 0.1  


def latest_object_for_source(client, source_name: str) -> str | None:
    """Retrouve la clé la plus récente pour une source donnée (versioning horodaté)."""
    keys = [k for k in list_keys(client, BRONZE_BUCKET, prefix=f"{source_name}/") if k.endswith((".csv",))]
    if not keys:
        return None
    return sorted(keys)[-1]  # le préfixe horodaté YYYY/MM/DD/HHMMSS trie naturellement


def read_csv_from_bronze(client, key: str) -> pd.DataFrame:
    """
    Lit un CSV depuis la zone bronze, de façon robuste face à deux pièges
    réels rencontrés en production :
      - BOM UTF-8 en tête de fichier (présent sur les exports OpenData Paris) ;
      - séparateur `;` (standard sur les exports OpenData Paris, dont les champs
        géométriques contiennent de nombreuses virgules internes — les
        confondre avec le séparateur fait exploser le nombre de colonnes
        détecté sur ces lignes).
    On détecte le séparateur le plus probable à partir de la ligne d'en-tête,
    et on tolère les lignes mal formées (`on_bad_lines="skip"`) plutôt que de
    faire planter tout le pipeline pour une poignée de lignes corrompues.
    """
    raw = get_bytes(client, BRONZE_BUCKET, key)
    text = raw.decode("utf-8-sig", errors="replace")  # utf-8-sig retire le BOM s'il est présent
    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","
    return pd.read_csv(io.StringIO(text), sep=sep, engine="python", on_bad_lines="skip")


def geocode_address(adresse: str) -> tuple[float, float] | tuple[None, None]:
    """Géocode une adresse via l'API BAN. Retourne (lon, lat) ou (None, None) en cas d'échec."""
    try:
        resp = requests.get(BAN_GEOCODE_URL, params={"q": adresse, "limit": 1}, timeout=5)
        resp.raise_for_status()
        features = resp.json().get("features", [])
        if features:
            lon, lat = features[0]["geometry"]["coordinates"]
            return lon, lat
    except Exception:
        pass
    return None, None


def clean_dvf(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Nettoie un jeu de données DVF (transactions immobilières).

    Accepte deux formats en entrée, détectés automatiquement :
      - le format de démonstration : `arrondissement` et `prix_m2` déjà calculés ;
      - le VRAI format geo-dvf (data.gouv.fr) : colonnes `code_postal`,
        `valeur_fonciere`, `surface_reelle_bati`, `type_local`. On calcule alors
        `arrondissement` à partir du code postal parisien (750XX) et `prix_m2`
        à partir de `valeur_fonciere / surface_reelle_bati`, en ne conservant
        que les locaux d'habitation (Appartement/Maison) — un terrain ou un
        local commercial n'a pas le même sens de "prix au m²".

    Basé sur le format officiel documenté de geo-dvf ; non testé contre le
    fichier réel exact (cf. les ajustements faits pour espaces_verts, qui eux
    ont été validés contre un vrai export). Si ce nettoyage produit des
    résultats inattendus sur votre fichier réel, partagez un extrait du CSV
    bronze comme pour espaces_verts et on l'ajustera de la même façon.
    """
    quality_report = {"rows_in": len(df), "issues": {}}
    df = df.copy()

    is_real_format = "arrondissement" not in df.columns and "code_postal" in df.columns
    quality_report["format_detecte"] = "geo-dvf réel" if is_real_format else "démonstration"

    if is_real_format:
        df["date_mutation"] = pd.to_datetime(df.get("date_mutation"), errors="coerce")
        df["surface_reelle_bati"] = pd.to_numeric(df.get("surface_reelle_bati"), errors="coerce")
        valeur_fonciere = pd.to_numeric(df.get("valeur_fonciere"), errors="coerce")
        code_postal = pd.to_numeric(df.get("code_postal"), errors="coerce")

        # Seuls les locaux d'habitation ont un "prix au m²" comparable entre eux.
        if "type_local" in df.columns:
            n_before = len(df)
            mask_habitation = df["type_local"].isin(["Appartement", "Maison"])
            df = df[mask_habitation]
            valeur_fonciere = valeur_fonciere[mask_habitation]
            code_postal = code_postal[mask_habitation]
            quality_report["issues"]["lignes_non_habitation_exclues"] = int(n_before - len(df))

        df["arrondissement"] = (code_postal - 75000).where(code_postal.between(75001, 75020))
        prix_m2 = valeur_fonciere / df["surface_reelle_bati"]
        df["prix_m2"] = prix_m2.replace([float("inf"), float("-inf")], pd.NA)
    else:
        df["date_mutation"] = pd.to_datetime(df.get("date_mutation"), errors="coerce")
        df["prix_m2"] = pd.to_numeric(df.get("prix_m2"), errors="coerce")
        df["surface_reelle_bati"] = pd.to_numeric(df.get("surface_reelle_bati"), errors="coerce")
        df["arrondissement"] = pd.to_numeric(df.get("arrondissement"), errors="coerce")

    # 2. Lignes sans arrondissement = non rattachables -> écartées
    n_no_arr = df["arrondissement"].isna().sum()
    df = df.dropna(subset=["arrondissement"])
    df["arrondissement"] = df["arrondissement"].astype(int)
    quality_report["issues"]["lignes_sans_arrondissement_supprimees"] = int(n_no_arr)

    # 3. Doublons sur la clé métier
    key_col = "id_mutation" if "id_mutation" in df.columns else None
    n_before = len(df)
    if key_col:
        df = df.drop_duplicates(subset=[key_col])
    else:
        df = df.drop_duplicates()
    quality_report["issues"]["doublons_supprimes"] = int(n_before - len(df))

    # 4. Imputation des valeurs manquantes de prix_m2 par la médiane de l'arrondissement
    n_missing_prix = df["prix_m2"].isna().sum()
    df["prix_m2"] = df.groupby("arrondissement")["prix_m2"].transform(lambda s: s.fillna(s.median()))
    quality_report["issues"]["prix_m2_imputes_par_mediane_arr"] = int(n_missing_prix)

    # 5. Filtrage des valeurs aberrantes
    n_before = len(df)
    df = df[(df["prix_m2"] >= PRIX_M2_MIN) & (df["prix_m2"] <= PRIX_M2_MAX)]
    quality_report["issues"]["valeurs_aberrantes_filtrees"] = int(n_before - len(df))

    # 6. Validation finale de schéma
    expected_cols = {"arrondissement", "prix_m2", "surface_reelle_bati", "date_mutation"}
    quality_report["schema_valide"] = expected_cols.issubset(set(df.columns))

    quality_report["rows_out"] = len(df)
    quality_report["taux_retenu_pct"] = round(100 * len(df) / max(quality_report["rows_in"], 1), 1)
    return df, quality_report


def clean_population_arrondissements(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Extrait population et densité pour les 20 arrondissements de Paris depuis le
    fichier "Communes et villes de France" de data.gouv.fr.

    Les arrondissements parisiens ont typecom == "ARM" et un code_insee du type
    "751XX" (ex: "75107" pour le 7e, "75120" pour le 20e). Le numéro
    d'arrondissement est les deux derniers chiffres, interprétés sans zéro de
    tête (ex: "75107" -> 7, "75120" -> 20).
    """
    quality_report = {"rows_in": len(df), "issues": {}}
    df = df.copy()

    # Harmonise les noms de colonnes (minuscules, sans espaces parasites)
    df.columns = [c.strip().lower() for c in df.columns]

    # Repère les colonnes réelles (le CSV change parfois de nom entre millésimes)
    col_typecom = next((c for c in df.columns if "typecom" in c), None)
    col_code = next((c for c in df.columns if c in ("code_commune_insee", "code_insee", "com", "codgeo")), None)
    col_pop = next((c for c in df.columns if c in ("population", "pop", "pop_totale", "p20_pop", "pmun", "ptot")), None)
    col_den = next((c for c in df.columns if "densite" in c or "densite_" in c or c == "den"), None)

    quality_report["colonnes_detectees"] = {
        "typecom": col_typecom, "code": col_code, "population": col_pop, "densite": col_den,
    }

    if col_code is None or col_pop is None:
        quality_report["erreur"] = "colonnes obligatoires (code_insee, population) introuvables"
        return pd.DataFrame(columns=["arrondissement", "population", "densite_hab_km2"]), quality_report

    df[col_code] = df[col_code].astype(str).str.strip()
    mask = df[col_code].str.startswith("751") & (df[col_code].str.len() == 5)

    # Filtre typecom == "ARM" si la colonne existe (sinon on garde le filtre code seul)
    if col_typecom:
        mask = mask & (df[col_typecom].astype(str).str.strip().str.upper() == "ARM")

    df_arr = df[mask].copy()
    quality_report["lignes_arm_751xx_trouvees"] = int(len(df_arr))

    if len(df_arr) != 20:
        quality_report["alerte"] = (
            f"Attendu 20 arrondissements parisiens (ARM + code 751XX), "
            f"trouvé {len(df_arr)}. Vérifiez le filtre typecom/code_insee."
        )

    if len(df_arr) == 0:
        quality_report["erreur"] = "Aucun arrondissement parisien (code 751XX) trouvé dans le CSV source"
        return pd.DataFrame(columns=["arrondissement", "population", "densite_hab_km2"]), quality_report

    # Surfaces officielles IGN (km²) — stables, utilisées pour calculer la densité
    # quand le fichier source ne contient pas de colonne densité.
    SUPERFICIE_KM2 = {
        1: 1.83, 2: 0.99, 3: 1.17, 4: 1.60, 5: 2.54, 6: 2.15, 7: 4.09, 8: 3.88,
        9: 2.18, 10: 2.89, 11: 3.67, 12: 16.32, 13: 7.15, 14: 5.64, 15: 8.50,
        16: 16.31, 17: 5.67, 18: 6.01, 19: 6.79, 20: 5.98,
    }

    df_arr["arrondissement"] = df_arr[col_code].astype(str).str[-2:].astype(int)
    df_arr["population"] = pd.to_numeric(df_arr[col_pop], errors="coerce").round().astype("Int64")

    col_den = next((c for c in df_arr.columns if "densite" in c or c == "den"), None)
    col_sup = next((c for c in df_arr.columns if "superficie" in c and "km2" in c), None)
    if col_den:
        df_arr["densite_hab_km2"] = pd.to_numeric(df_arr[col_den], errors="coerce").round().astype("Int64")
    elif col_sup:
        sup = pd.to_numeric(df_arr[col_sup], errors="coerce")
        df_arr["densite_hab_km2"] = (pd.to_numeric(df_arr[col_pop], errors="coerce") / sup.replace(0, pd.NA)).round().astype("Int64")
    else:
        df_arr["densite_hab_km2"] = df_arr["arrondissement"].map(
            lambda n: round(df_arr.loc[df_arr["arrondissement"] == n, "population"].iloc[0] / SUPERFICIE_KM2[n])
            if n in SUPERFICIE_KM2 else pd.NA
        )
        quality_report["issues"]["densite_calculee_depuis_superficie_ign"] = True

    df_out = df_arr[["arrondissement", "population", "densite_hab_km2"]].drop_duplicates(subset=["arrondissement"])
    df_out = df_out.sort_values("arrondissement").reset_index(drop=True)

    quality_report["rows_out"] = len(df_out)
    return df_out, quality_report


def clean_criminalite(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Nettoie le fichier criminalité communale SSMSI (national).
    Filtre les arrondissements parisiens (codes INSEE 75101-75120).
    Agrège sur l'année la plus récente : somme des faits, taux pour 1000 hab.
    Note : taux_pour_mille est une string avec virgule décimale dans la source.
    """
    quality_report = {"rows_in": len(df), "issues": {}}
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    col_codgeo = next((c for c in df.columns if c.startswith("codgeo")), None)
    if col_codgeo is None:
        quality_report["erreur"] = "Colonne CODGEO introuvable"
        return pd.DataFrame(columns=["arrondissement", "taux_criminalite", "nb_faits", "annee"]), quality_report

    # Les codes INSEE ont parfois des zéros en tête manquants (ex: "1001" au lieu de "01001")
    df[col_codgeo] = df[col_codgeo].astype(str).str.strip().str.zfill(5)
    mask = df[col_codgeo].str.match(r"^751\d{2}$")
    df_paris = df[mask].copy()
    quality_report["lignes_paris_arr"] = int(len(df_paris))

    if len(df_paris) == 0:
        quality_report["erreur"] = "Aucun code 75101-75120 trouvé (dataset national)"
        return pd.DataFrame(columns=["arrondissement", "taux_criminalite", "nb_faits", "annee"]), quality_report

    # Convertit taux_pour_mille (string avec virgule) → float
    if "taux_pour_mille" in df_paris.columns:
        df_paris["taux_pour_mille"] = (
            df_paris["taux_pour_mille"]
            .astype(str)
            .str.replace(",", ".", regex=False)
            .pipe(pd.to_numeric, errors="coerce")
        )

    df_paris["nombre"] = pd.to_numeric(df_paris.get("nombre"), errors="coerce").fillna(0)
    df_paris["insee_pop"] = pd.to_numeric(df_paris.get("insee_pop"), errors="coerce")
    df_paris["annee"] = pd.to_numeric(df_paris.get("annee"), errors="coerce")
    df_paris["arrondissement"] = df_paris[col_codgeo].str[-2:].astype(int)

    annee_max = df_paris["annee"].max()
    df_annee = df_paris[df_paris["annee"] == annee_max].copy()
    quality_report["annee_retenue"] = int(annee_max) if pd.notna(annee_max) else None

    agg = df_annee.groupby("arrondissement").agg(
        nb_faits=("nombre", "sum"),
        population_insee=("insee_pop", "first"),
    ).reset_index()

    agg["taux_criminalite"] = (
        (agg["nb_faits"] / agg["population_insee"].replace(0, pd.NA) * 1000).round(2)
    )
    agg["annee"] = int(annee_max) if pd.notna(annee_max) else None

    quality_report["rows_out"] = len(agg)
    return agg[["arrondissement", "taux_criminalite", "nb_faits", "annee"]], quality_report


def clean_velib_stations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Nettoie les données Vélib' temps réel (OpenData Paris).
    Compte les stations par arrondissement via point-in-polygon sur coordonnees_geo.
    Note : Paris a le code INSEE 75056 dans ce dataset (une seule commune),
    donc on ne filtre pas par code INSEE mais directement par coordonnées géographiques.
    """
    quality_report = {"rows_in": len(df), "issues": {}}
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    col_coord = next(
        (c for c in df.columns if "coordonnees" in c or "geo_point" in c or c == "geo point"),
        None
    )
    if col_coord is None:
        quality_report["erreur"] = "Aucune colonne de coordonnées trouvée"
        return pd.DataFrame(columns=["arrondissement", "nb_stations"]), quality_report

    arrs = []
    for val in df[col_coord]:
        arr = None
        if pd.notna(val) and "," in str(val):
            try:
                lat_s, lon_s = str(val).split(",", 1)
                arr = find_arrondissement(float(lon_s.strip()), float(lat_s.strip()))
            except (ValueError, TypeError):
                pass
        arrs.append(arr)

    df["arrondissement"] = arrs
    df_paris = df[df["arrondissement"].notna()].copy()
    df_paris["arrondissement"] = df_paris["arrondissement"].astype(int)

    quality_report["filtrage_par"] = f"point-in-polygon via {col_coord}"
    quality_report["stations_paris"] = int(len(df_paris))
    counts = df_paris.groupby("arrondissement").size().reset_index(name="nb_stations")
    quality_report["rows_out"] = len(counts)
    return counts, quality_report


def clean_metro_stations(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Nettoie les stations IDFM (emplacement-des-gares-idf).
    Filtre Metro + RER via colonnes binaires metro/rer (1=oui, 0=non).
    Résout l'arrondissement par point-in-polygon sur geo_point_2d (lat, lon).
    """
    quality_report = {"rows_in": len(df), "issues": {}}
    df = df.copy()
    df.columns = [c.strip().lower() for c in df.columns]

    # Filtre Metro + RER via colonnes binaires (plus fiable que colonne mode)
    has_binary = "metro" in df.columns or "rer" in df.columns
    if has_binary:
        masks = []
        for col in ("metro", "rer"):
            if col in df.columns:
                masks.append(pd.to_numeric(df[col], errors="coerce").fillna(0) == 1)
        combined = masks[0]
        for m in masks[1:]:
            combined = combined | m
        n_before = len(df)
        df = df[combined].copy()
        quality_report["issues"]["filtre_metro_rer_binaire"] = int(len(df))
        quality_report["issues"]["exclues_non_metro_rer"] = int(n_before - len(df))
    else:
        # Fallback : colonne mode texte (valeurs "METRO", "RER" selon source)
        col_mode = next((c for c in df.columns if c in ("mode", "mode_stif_stop")), None)
        if col_mode:
            mask = df[col_mode].astype(str).str.upper().str.strip().isin({"METRO", "RER"})
            if mask.sum() > 0:
                df = df[mask].copy()

    if df.empty:
        quality_report["erreur"] = "Aucune station Metro/RER après filtrage"
        return pd.DataFrame(columns=["arrondissement", "nb_stations_metro"]), quality_report

    # Coordonnées : geo_point_2d prioritaire (format IDFM "lat, lon")
    col_geo = next((c for c in df.columns if "geo_point" in c or c == "geo point"), None)
    col_lat = next((c for c in df.columns if c in ("lat", "latitude", "stop_lat")), None)
    col_lon = next((c for c in df.columns if c in ("lon", "longitude", "stop_lon", "lng")), None)

    if col_geo:
        lats, lons = [], []
        for val in df[col_geo]:
            if pd.notna(val) and "," in str(val):
                try:
                    a, b = str(val).split(",", 1)
                    lats.append(float(a.strip()))
                    lons.append(float(b.strip()))
                    continue
                except (ValueError, TypeError):
                    pass
            lats.append(None)
            lons.append(None)
        quality_report["coord_source"] = col_geo
    elif col_lat and col_lon:
        lats = pd.to_numeric(df[col_lat], errors="coerce").tolist()
        lons = pd.to_numeric(df[col_lon], errors="coerce").tolist()
        quality_report["coord_source"] = f"{col_lat}/{col_lon}"
    else:
        quality_report["erreur"] = f"Aucune colonne de coordonnées (colonnes: {list(df.columns)[:10]})"
        return pd.DataFrame(columns=["arrondissement", "nb_stations_metro"]), quality_report

    arrs = []
    for lat, lon in zip(lats, lons):
        arr = None
        if lat is not None and lon is not None and not pd.isna(lat) and not pd.isna(lon):
            arr = find_arrondissement(float(lon), float(lat))
        arrs.append(arr)

    df["arrondissement"] = arrs
    df_paris = df[df["arrondissement"].notna()].copy()
    df_paris["arrondissement"] = df_paris["arrondissement"].astype(int)

    quality_report["stations_paris"] = int(len(df_paris))
    counts = df_paris.groupby("arrondissement").size().reset_index(name="nb_stations_metro")
    quality_report["rows_out"] = len(counts)
    return counts, quality_report


def clean_espaces_verts_real(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Nettoie le VRAI jeu de données "Espaces verts et assimilés" de la Ville de
    Paris (opendata.paris.fr). Contrairement au jeu de démonstration, ce fichier
    fournit déjà des coordonnées dans la colonne `geom_x_y` (format "lat, lon") :
    pas besoin d'appeler l'API BAN (ce serait redondant et inutilement lent pour
    500 lignes). L'arrondissement est résolu par un vrai point-in-polygon sur la
    géométrie officielle, avec un repli sur le code postal (750XX) si la
    coordonnée est absente ou tombe juste à l'extérieur d'un polygone.
    """
    quality_report = {"rows_in": len(df), "issues": {}}
    df = df.copy()

    def build_adresse(row) -> str | None:
        parts = [
            str(row.get("adresse_numero", "") or "").strip(),
            str(row.get("adresse_typevoie", "") or "").strip(),
            str(row.get("adresse_libellevoie", "") or "").strip(),
        ]
        parts = [p for p in parts if p and p.lower() != "nan"]
        voie = " ".join(parts)
        cp = row.get("adresse_codepostal")
        cp_str = f", {int(cp)} Paris" if pd.notna(cp) else ""
        return f"{voie}{cp_str}".strip() or None

    def parse_geom_x_y(value) -> tuple[float, float] | tuple[None, None]:
        if pd.isna(value) or not isinstance(value, str) or "," not in value:
            return None, None
        try:
            lat_str, lon_str = value.split(",", 1)
            return float(lon_str.strip()), float(lat_str.strip())
        except ValueError:
            return None, None

    df["adresse"] = df.apply(build_adresse, axis=1)
    df["nom"] = df.get("nom_ev")

    lons, lats, arrondissements = [], [], []
    n_coords_ok, n_arr_ok = 0, 0
    for value in df.get("geom_x_y", pd.Series(dtype=str)):
        lon, lat = parse_geom_x_y(value)
        if lon is not None:
            n_coords_ok += 1
            arr = find_arrondissement(lon, lat)
            if arr is not None:
                n_arr_ok += 1
        else:
            arr = None
        lons.append(lon)
        lats.append(lat)
        arrondissements.append(arr)

    df["longitude"] = lons
    df["latitude"] = lats
    df["arrondissement"] = arrondissements

    # Repli sur le code postal (75001-75020) quand le point-in-polygon n'a pas
    # abouti mais qu'un code postal parisien valide est renseigné.
    cp_fallback = pd.to_numeric(df.get("adresse_codepostal"), errors="coerce")
    mask_fallback = df["arrondissement"].isna() & cp_fallback.between(75001, 75020)
    n_fallback = int(mask_fallback.sum())
    df.loc[mask_fallback, "arrondissement"] = (cp_fallback[mask_fallback] - 75000).astype(int)

    quality_report["issues"]["coordonnees_presentes"] = n_coords_ok
    quality_report["issues"]["coordonnees_absentes"] = quality_report["rows_in"] - n_coords_ok
    quality_report["issues"]["arrondissement_resolu_point_in_polygon"] = n_arr_ok
    quality_report["issues"]["arrondissement_resolu_repli_code_postal"] = n_fallback
    quality_report["issues"]["arrondissement_non_resolu"] = int(df["arrondissement"].isna().sum())
    quality_report["taux_geocodage_pct"] = round(100 * n_coords_ok / max(quality_report["rows_in"], 1), 1)

    df["arrondissement"] = pd.to_numeric(df["arrondissement"], errors="coerce")
    quality_report["rows_out"] = len(df)
    return df[["nom", "adresse", "longitude", "latitude", "arrondissement"]], quality_report


def clean_espaces_verts_demo(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Nettoie le jeu de DÉMONSTRATION d'espaces verts (12 parcs connus, adresse
    texte uniquement, sans coordonnées) — utilisé en repli si le vrai fichier
    OpenData Paris n'a pas pu être téléchargé (réseau indisponible). Démontre
    le géocodage complet :

        adresse (texte) --[API BAN]--> (lon, lat) --[point-in-polygon]--> arrondissement

    Chaque étape est journalisée dans le rapport qualité. Les échecs ne sont
    pas supprimés silencieusement : ils sont conservés avec arrondissement=NA
    et comptés.
    """
    quality_report = {"rows_in": len(df), "issues": {}}

    lons, lats, arrondissements = [], [], []
    n_geocode_ok, n_arr_ok = 0, 0

    for adresse in df.get("adresse", pd.Series(dtype=str)):
        lon, lat = geocode_address(str(adresse))
        time.sleep(GEOCODE_THROTTLE_S)

        if lon is not None:
            n_geocode_ok += 1
            arr = find_arrondissement(lon, lat)
            if arr is not None:
                n_arr_ok += 1
        else:
            arr = None

        lons.append(lon)
        lats.append(lat)
        arrondissements.append(arr)

    df = df.copy()
    df["longitude"] = lons
    df["latitude"] = lats
    df["arrondissement"] = arrondissements

    quality_report["issues"]["adresses_geocodees_avec_succes"] = n_geocode_ok
    quality_report["issues"]["adresses_geocodage_echoue"] = quality_report["rows_in"] - n_geocode_ok
    quality_report["issues"]["arrondissements_resolus_par_point_in_polygon"] = n_arr_ok
    quality_report["taux_geocodage_pct"] = round(100 * n_geocode_ok / max(quality_report["rows_in"], 1), 1)

    df["arrondissement"] = pd.to_numeric(df["arrondissement"], errors="coerce")
    quality_report["rows_out"] = len(df)
    return df, quality_report


def run_espaces_verts(client) -> dict:
    """
    Traite la source "espaces verts" en préférant toujours le vrai fichier
    OpenData Paris (clé bronze `espaces_verts/`) ; si celui-ci n'a pas pu être
    téléchargé (réseau indisponible, source modifiée...), on retombe sur le
    jeu de démonstration géocodé via BAN (clé bronze `espaces_verts_demo/`).
    La clé de sortie en zone Silver reste `espaces_verts` dans les deux cas,
    pour que la suite du pipeline (aggregate_gold.py) n'ait pas à distinguer
    les deux origines possibles.
    """
    source_label = "espaces_verts"

    key = latest_object_for_source(client, "espaces_verts")
    cleaner, origin = clean_espaces_verts_real, "réel (OpenData Paris)"
    if key is None:
        key = latest_object_for_source(client, "espaces_verts_demo")
        cleaner, origin = clean_espaces_verts_demo, "démo (géocodage BAN)"

    if key is None:
        return {"source": source_label, "status": "skipped", "reason": "aucune donnée bronze trouvée (ni réelle, ni démo)"}

    df_raw = read_csv_from_bronze(client, key)
    df_clean, quality_report = cleaner(df_raw)
    quality_report["source_origin"] = origin

    out_key = f"{versioned_prefix(source_label)}/{source_label}.parquet"
    put_dataframe_as_parquet(client, SILVER_BUCKET, out_key, df_clean)

    quality_key = f"_reports/quality/{versioned_prefix(source_label)}.json"
    quality_report["source_bronze_key"] = key
    quality_report["output_silver_key"] = out_key
    put_json(client, SILVER_BUCKET, quality_key, quality_report)

    return {"source": source_label, "status": "success", "output": out_key, "origin": origin, "quality": quality_report}


def run_for_source(client, source_name: str, cleaner) -> dict:
    key = latest_object_for_source(client, source_name)
    if key is None:
        return {"source": source_name, "status": "skipped", "reason": "aucune donnée bronze trouvée"}

    df_raw = read_csv_from_bronze(client, key)
    df_clean, quality_report = cleaner(df_raw)

    out_key = f"{versioned_prefix(source_name)}/{source_name}.parquet"
    put_dataframe_as_parquet(client, SILVER_BUCKET, out_key, df_clean)

    quality_key = f"_reports/quality/{versioned_prefix(source_name)}.json"
    quality_report["source_bronze_key"] = key
    quality_report["output_silver_key"] = out_key
    put_json(client, SILVER_BUCKET, quality_key, quality_report)

    return {"source": source_name, "status": "success", "output": out_key, "quality": quality_report}


def run_criminalite(client) -> dict:
    """
    Traite criminalite_communale avec lecture par chunks pour limiter la RAM.
    Le CSV national SSMSI fait ~600MB — le charger en entier tuerait le processus.
    On lit 50k lignes à la fois, filtre Paris (75101-75120) immédiatement,
    puis libère les grandes structures dès qu'elles ne sont plus nécessaires.
    """
    source_name = "criminalite_communale"
    key = latest_object_for_source(client, source_name)
    if key is None:
        return {"source": source_name, "status": "skipped", "reason": "aucune donnée bronze trouvée"}

    raw = get_bytes(client, BRONZE_BUCKET, key)
    text = raw.decode("utf-8-sig", errors="replace")
    del raw  # libère ~600MB immédiatement après décodage

    first_line = text.split("\n", 1)[0]
    sep = ";" if first_line.count(";") > first_line.count(",") else ","

    # Détection des colonnes depuis l'en-tête — permet de ne lire que l'utile
    header_cols = [c.strip().lower() for c in first_line.split(sep)]
    col_codgeo = next((c for c in header_cols if c.startswith("codgeo")), None)
    needed = {col_codgeo, "annee", "nombre", "taux_pour_mille", "insee_pop"} - {None}
    usecols_fn = lambda c: c.strip().lower() in needed  # noqa: E731

    quality_report = {"rows_in": 0, "issues": {}}
    paris_chunks = []

    for chunk in pd.read_csv(
        io.StringIO(text), sep=sep, engine="python", on_bad_lines="skip",
        chunksize=50_000, usecols=usecols_fn if col_codgeo else None,
    ):
        quality_report["rows_in"] += len(chunk)
        chunk.columns = [c.strip().lower() for c in chunk.columns]
        col = next((c for c in chunk.columns if c.startswith("codgeo")), None)
        if col is None:
            continue
        chunk[col] = chunk[col].astype(str).str.strip().str.zfill(5)
        paris_chunks.append(chunk[chunk[col].str.match(r"^751\d{2}$")])

    del text  # libère la chaîne complète après traitement des chunks

    if not paris_chunks:
        quality_report["erreur"] = "Aucun code 75101-75120 trouvé dans le fichier"
        return {"source": source_name, "status": "failed", "quality": quality_report}

    df = pd.concat(paris_chunks, ignore_index=True)
    del paris_chunks
    quality_report["lignes_paris_arr"] = len(df)

    col = next((c for c in df.columns if c.startswith("codgeo")), None)
    df["arrondissement"] = df[col].str[-2:].astype(int)

    if "taux_pour_mille" in df.columns:
        df["taux_pour_mille"] = (
            df["taux_pour_mille"].astype(str).str.replace(",", ".", regex=False)
            .pipe(pd.to_numeric, errors="coerce")
        )
    df["nombre"]    = pd.to_numeric(df.get("nombre"), errors="coerce").fillna(0)
    df["insee_pop"] = pd.to_numeric(df.get("insee_pop"), errors="coerce")
    df["annee"]     = pd.to_numeric(df.get("annee"), errors="coerce")

    annee_max = df["annee"].max()
    df_annee  = df[df["annee"] == annee_max].copy()
    quality_report["annee_retenue"] = int(annee_max) if pd.notna(annee_max) else None

    agg = df_annee.groupby("arrondissement").agg(
        nb_faits=("nombre", "sum"),
        population_insee=("insee_pop", "first"),
    ).reset_index()
    agg["taux_criminalite"] = (
        (agg["nb_faits"] / agg["population_insee"].replace(0, pd.NA) * 1000).round(2)
    )
    agg["annee"] = int(annee_max) if pd.notna(annee_max) else None
    df_clean = agg[["arrondissement", "taux_criminalite", "nb_faits", "annee"]]
    quality_report["rows_out"] = len(df_clean)

    out_key = f"{versioned_prefix(source_name)}/{source_name}.parquet"
    put_dataframe_as_parquet(client, SILVER_BUCKET, out_key, df_clean)
    quality_key = f"_reports/quality/{versioned_prefix(source_name)}.json"
    quality_report["source_bronze_key"] = key
    quality_report["output_silver_key"] = out_key
    put_json(client, SILVER_BUCKET, quality_key, quality_report)

    return {"source": source_name, "status": "success", "output": out_key, "quality": quality_report}


def run_rpls_logements_sociaux(client) -> dict:
    """
    Nettoie le RPLS 2021 (par commune, colonnes COM + TOT21).
    Filtre Paris (COM 75101-75120), retourne nb_lls par arrondissement.
    Le % est calculé en Gold après jointure avec INSEE IRIS (total logements).
    """
    source_name = "rpls_logements_sociaux"
    key = latest_object_for_source(client, source_name)
    if key is None:
        return {"source": source_name, "status": "skipped", "reason": "aucune donnée bronze trouvée"}

    df = read_csv_from_bronze(client, key)
    quality_report = {"rows_in": len(df), "issues": {}}
    df.columns = [c.strip().lower() for c in df.columns]

    # COM = code commune (ex. "75101"), TOT21 = total LLS 2021
    col_com = next((c for c in df.columns if c in ("com", "codgeo", "code_commune")), None)
    col_tot = next((c for c in df.columns if c in ("tot21", "tot20", "loue")), None)

    if col_com is None or col_tot is None:
        return {"source": source_name, "status": "failed", "quality": {
            "erreur": f"Colonnes COM/TOT21 introuvables (colonnes: {list(df.columns)[:15]})"
        }}

    df[col_com] = df[col_com].astype(str).str.strip().str.zfill(5)
    df_paris = df[df[col_com].str.match(r"^751\d{2}$")].copy()
    quality_report["lignes_paris"] = len(df_paris)

    if df_paris.empty:
        return {"source": source_name, "status": "failed", "quality": {"erreur": "Aucun code 75101-75120 trouvé"}}

    df_paris["arrondissement"] = df_paris[col_com].str[-2:].astype(int)
    df_paris["nb_lls"] = pd.to_numeric(df_paris[col_tot], errors="coerce").fillna(0).astype(int)

    df_clean = df_paris[["arrondissement", "nb_lls"]]
    quality_report["rows_out"] = len(df_clean)

    out_key = f"{versioned_prefix(source_name)}/{source_name}.parquet"
    put_dataframe_as_parquet(client, SILVER_BUCKET, out_key, df_clean)
    quality_key = f"_reports/quality/{versioned_prefix(source_name)}.json"
    quality_report["source_bronze_key"] = key
    quality_report["output_silver_key"] = out_key
    put_json(client, SILVER_BUCKET, quality_key, quality_report)

    return {"source": source_name, "status": "success", "output": out_key, "quality": quality_report}


def run_insee_rp_logements(client) -> dict:
    """
    Nettoie le fichier INSEE RP 2021 logements niveau IRIS.
    Code IRIS 9 chiffres → 5 premiers = commune (75101-75120 pour Paris).
    Agrège par arrondissement : P21_MAISON, P21_APPART → pct_appartements.
    """
    source_name = "insee_rp_logements"
    key = latest_object_for_source(client, source_name)
    if key is None:
        return {"source": source_name, "status": "skipped", "reason": "aucune donnée bronze trouvée"}

    df = read_csv_from_bronze(client, key)
    quality_report = {"rows_in": len(df), "issues": {}}
    df.columns = [c.strip().lower() for c in df.columns]

    # Colonne IRIS : code 9 chiffres. Les 5 premiers = code commune.
    col_iris = next((c for c in df.columns if c in ("iris", "code_iris", "com_iris")), None)
    if col_iris is None:
        return {"source": source_name, "status": "failed", "quality": {
            "erreur": f"Colonne IRIS introuvable (colonnes: {list(df.columns)[:10]})"
        }}

    df[col_iris] = df[col_iris].astype(str).str.strip().str.zfill(9)
    df["com"] = df[col_iris].str[:5]
    df_paris = df[df["com"].str.match(r"^751\d{2}$")].copy()
    quality_report["lignes_paris"] = len(df_paris)

    if df_paris.empty:
        return {"source": source_name, "status": "failed", "quality": {"erreur": "Aucun IRIS 75101-75120 trouvé"}}

    df_paris["arrondissement"] = df_paris["com"].str[-2:].astype(int)

    col_tot    = next((c for c in df_paris.columns if c in ("p21_log", "p21_rp", "p20_log")), None)
    col_maison = next((c for c in df_paris.columns if "maison" in c), None)
    col_appart = next((c for c in df_paris.columns if "appart" in c), None)

    if col_tot is None:
        return {"source": source_name, "status": "failed", "quality": {
            "erreur": f"Colonne total logements introuvable (colonnes: {list(df_paris.columns)[:15]})"
        }}

    for col in [col_tot, col_maison, col_appart]:
        if col:
            df_paris[col] = pd.to_numeric(df_paris[col], errors="coerce").fillna(0)

    df_paris["_nb_maisons"]      = df_paris[col_maison] if col_maison else 0
    df_paris["_nb_appartements"] = df_paris[col_appart] if col_appart else 0

    agg = df_paris.groupby("arrondissement").agg(
        nb_logements=(col_tot, "sum"),
        nb_maisons=("_nb_maisons", "sum"),
        nb_appartements=("_nb_appartements", "sum"),
    ).reset_index()

    agg["pct_appartements"] = (
        agg["nb_appartements"] / agg["nb_logements"].replace(0, pd.NA) * 100
    ).round(1)
    agg["type_dominant"] = agg.apply(
        lambda r: "appartement" if r["nb_appartements"] >= r["nb_maisons"] else "maison", axis=1
    )

    quality_report["rows_out"] = len(agg)
    out_key = f"{versioned_prefix(source_name)}/{source_name}.parquet"
    put_dataframe_as_parquet(client, SILVER_BUCKET, out_key, agg)
    quality_key = f"_reports/quality/{versioned_prefix(source_name)}.json"
    quality_report["source_bronze_key"] = key
    quality_report["output_silver_key"] = out_key
    put_json(client, SILVER_BUCKET, quality_key, quality_report)

    return {"source": source_name, "status": "success", "output": out_key, "quality": quality_report}


def main():
    client = get_s3_client()
    run_start = time.time()
    results = []

    print("=" * 60)
    print("TRANSFORMATION SILVER — Nettoyage & Qualité")
    print("=" * 60)

    for year in (2021, 2022, 2023, 2024, 2025):
        res = run_for_source(client, f"dvf_{year}", clean_dvf)
        results.append(res)
        print(f"  - dvf_{year}: {res['status']}")

    res = run_for_source(client, "communes_insee", clean_population_arrondissements)
    results.append(res)
    status_detail = ""
    if res["status"] == "success":
        q = res.get("quality", {})
        if "alerte" in q:
            status_detail = f" !! ALERTE : {q['alerte']}"
        else:
            status_detail = f" ({q.get('rows_out', '?')} arrondissements)"
    print(f"  - communes_insee (population/densite): {res['status']}{status_detail}")

    res = run_espaces_verts(client)
    results.append(res)
    label = res.get("origin", res.get("reason", ""))
    print(f"  - espaces_verts ({label}): {res['status']}")

    res = run_criminalite(client)
    results.append(res)
    if res["status"] == "success":
        q = res.get("quality", {})
        print(f"  - criminalite_communale: {res['status']} ({q.get('rows_out', '?')} arrondissements, année {q.get('annee_retenue', '?')})")
    else:
        print(f"  - criminalite_communale: {res['status']} — {res.get('reason', res.get('quality', {}).get('erreur', ''))}")

    res = run_for_source(client, "velib_stations", clean_velib_stations)
    results.append(res)
    if res["status"] == "success":
        q = res.get("quality", {})
        print(f"  - velib_stations: {res['status']} ({q.get('stations_paris', '?')} stations Paris)")
    else:
        print(f"  - velib_stations: {res['status']} — {res.get('reason', '')}")

    res = run_for_source(client, "metro_stations", clean_metro_stations)
    results.append(res)
    if res["status"] == "success":
        q = res.get("quality", {})
        print(f"  - metro_stations: {res['status']} ({q.get('stations_paris', '?')} stations Paris Metro/RER)")
    else:
        print(f"  - metro_stations: {res['status']} — {res.get('reason', '')}")

    res = run_rpls_logements_sociaux(client)
    results.append(res)
    if res["status"] == "success":
        q = res.get("quality", {})
        print(f"  - rpls_logements_sociaux: {res['status']} ({q.get('rows_out', '?')} arrondissements)")
    else:
        print(f"  - rpls_logements_sociaux: {res['status']} — {res.get('reason', res.get('quality', {}).get('erreur', ''))}")

    res = run_insee_rp_logements(client)
    results.append(res)
    if res["status"] == "success":
        q = res.get("quality", {})
        print(f"  - insee_rp_logements: {res['status']} ({q.get('rows_out', '?')} arrondissements)")
    else:
        print(f"  - insee_rp_logements: {res['status']} — {res.get('reason', res.get('quality', {}).get('erreur', ''))}")

    n_ok = sum(1 for r in results if r["status"] == "success")
    lignes_total = sum(
        r.get("quality", {}).get("rows_out", 0) for r in results if r["status"] == "success"
    )
    duree_totale = round(time.time() - run_start, 2)

    summary = {
        "run_started": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "results": results,
        # Métriques harmonisées C1.3 / C2.4
        "duree_s": duree_totale,
        "volume_octets": 0,  # Parquet — taille calculable mais non critique ici
        "debit_lignes_par_s": round(lignes_total / max(duree_totale, 0.01), 1),
        "taux_succes_pct": round(100 * n_ok / max(len(results), 1), 1),
    }

    summary_key = f"_reports/silver_run/{versioned_prefix('summary')}.json"
    put_json(client, SILVER_BUCKET, summary_key, summary)

    write_pipeline_report("silver", summary)

    print(f"\nRapport global : s3://{SILVER_BUCKET}/{summary_key}")
    print(f"Métriques : {n_ok}/{len(results)} sources — {lignes_total} lignes en {duree_totale}s")
    return results


if __name__ == "__main__":
    main()
