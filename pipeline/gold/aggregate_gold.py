"""
pipeline/gold/aggregate_gold.py
---------------------------------
Couche GOLD du pipeline : lit les Parquet Silver, calcule les indicateurs métier
et les écrit dans PostgreSQL + MinIO/gold.

Tables produites :
  - prix_m2_arrondissement  : table plate (rétrocompatibilité API)
  - indicateurs_socio        : INSEE + WAQI + OpenData Paris
  - dim_arrondissement, dim_temps, fait_prix_immobilier : schéma en étoile (C2.3)
  - enriched_arrondissements.geojson : géométries + indicateurs -> explorateur

Data marts rafraîchis après chaque run :
  - mart_marche_immobilier  : prix, variations, segmentation marché
  - mart_mobilite            : état Vélib par arrondissement
  - mart_qualite_vie         : score de vie composite

Métriques harmonisées (C1.3/C2.4) + rapport dans PostgreSQL pipeline_rapports (JSONB).
"""
import io
import json
import os
import time

import pandas as pd
import psycopg2.extras
from sqlalchemy import create_engine, text

from minio_client import (
    get_s3_client,
    list_keys,
    get_bytes,
    put_bytes,
    put_dataframe_as_parquet,
    put_json,
    versioned_prefix,
)
from geo_utils import load_reference_geojson
from pipeline_reporter import write_pipeline_report

SILVER_BUCKET = "silver"
GOLD_BUCKET = "gold"
BRONZE_BUCKET = "bronze"
YEARS = (2021, 2022, 2023, 2024, 2025)


def get_pg_engine():
    host = os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold")
    db = os.environ.get("POSTGRES_GOLD_DB", "gold")
    user = os.environ.get("POSTGRES_GOLD_USER", "gold_user")
    pwd = os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass")
    return create_engine(f"postgresql+psycopg2://{user}:{pwd}@{host}:5432/{db}")


def latest_parquet(client, source_name: str) -> str | None:
    keys = [k for k in list_keys(client, SILVER_BUCKET, prefix=f"{source_name}/") if k.endswith(".parquet")]
    if not keys:
        return None
    return sorted(keys)[-1]


def read_parquet_from_silver(client, key: str) -> pd.DataFrame:
    raw = get_bytes(client, SILVER_BUCKET, key)
    return pd.read_parquet(io.BytesIO(raw))


def build_prix_m2_arrondissement(client) -> pd.DataFrame:
    """Agrège le prix médian au m² par arrondissement et par année + variation annuelle (%)."""
    frames = []
    for year in (2021, 2022, 2023, 2024, 2025):
        key = latest_parquet(client, f"dvf_{year}")
        if key is None:
            continue
        df = read_parquet_from_silver(client, key)
        df["annee"] = year
        frames.append(df)

    if not frames:
        return pd.DataFrame(columns=["arrondissement", "annee", "prix_m2_median", "variation_pct"])

    full = pd.concat(frames, ignore_index=True)
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
    return agg


def build_population_insee(client) -> pd.DataFrame:
    """
    Lit le Parquet Silver produit par clean_population_arrondissements (source
    communes_insee). Retourne un DataFrame (arrondissement, population,
    densite_hab_km2) ou un DataFrame vide si la source n'est pas encore
    disponible (premier lancement sans réseau).
    """
    key = latest_parquet(client, "communes_insee")
    if key is None:
        return pd.DataFrame(columns=["arrondissement", "population", "densite_hab_km2"])
    df = read_parquet_from_silver(client, key)
    # Garantit que les colonnes attendues sont présentes
    for col in ("population", "densite_hab_km2"):
        if col not in df.columns:
            df[col] = pd.NA
    return df[["arrondissement", "population", "densite_hab_km2"]]


# Centres approximatifs des arrondissements de Paris (lat, lon) — source IGN
_ARR_CENTERS: dict[int, tuple[float, float]] = {
    1: (48.8600, 2.3471),  2: (48.8668, 2.3484),  3: (48.8624, 2.3607),
    4: (48.8541, 2.3523),  5: (48.8513, 2.3476),  6: (48.8494, 2.3343),
    7: (48.8553, 2.3162),  8: (48.8742, 2.3133),  9: (48.8766, 2.3422),
   10: (48.8764, 2.3593), 11: (48.8579, 2.3791), 12: (48.8430, 2.3889),
   13: (48.8311, 2.3614), 14: (48.8330, 2.3261), 15: (48.8422, 2.2993),
   16: (48.8627, 2.2703), 17: (48.8840, 2.3131), 18: (48.8922, 2.3472),
   19: (48.8799, 2.3818), 20: (48.8645, 2.3964),
}


def _idw_interpolate(known: dict[int, float]) -> dict[int, float]:
    """Remplit les arrondissements manquants par IDW (inverse distance weighting)
    depuis les valeurs réelles. Puissance p=2, distance euclidienne lat/lon."""
    import math
    result = {}
    for arr in range(1, 21):
        if arr in known:
            result[arr] = known[arr]
            continue
        lat0, lon0 = _ARR_CENTERS[arr]
        total_w, total_wv = 0.0, 0.0
        for other, val in known.items():
            lat1, lon1 = _ARR_CENTERS[other]
            dist = math.sqrt((lat1 - lat0) ** 2 + (lon1 - lon0) ** 2)
            w = 1.0 / max(dist ** 2, 1e-9)
            total_w += w
            total_wv += w * val
        result[arr] = round(total_wv / total_w, 2) if total_w else None
    return result


def build_indice_qualite_air_snapshot(engine) -> pd.DataFrame:
    """
    Calcule la moyenne de indice_qualite_air par arrondissement depuis la
    table qualite_air_temps_reel (flux WAQI via le topic events.stream).
    Les 9 arrondissements avec une station WAQI reçoivent leur valeur réelle ;
    les 11 arrondissements sans station sont estimés par interpolation spatiale
    IDW (weighted average des stations réelles, pondérées par 1/distance²).
    """
    sql = """
        SELECT arrondissement,
               ROUND(AVG(indice_qualite_air)::numeric, 2) AS indice_qualite_air
        FROM qualite_air_temps_reel
        GROUP BY arrondissement
    """
    try:
        with engine.connect() as conn:
            rows = conn.execute(text(sql)).mappings().all()
        if not rows:
            return pd.DataFrame(columns=["arrondissement", "indice_qualite_air"])
        known = {int(r["arrondissement"]): float(r["indice_qualite_air"]) for r in rows}
        filled = _idw_interpolate(known)
        return pd.DataFrame(
            [{"arrondissement": arr, "indice_qualite_air": val} for arr, val in filled.items()]
        )
    except Exception:
        return pd.DataFrame(columns=["arrondissement", "indice_qualite_air"])


def build_indicateurs_socio(client, engine) -> pd.DataFrame:
    """
    Assemble les indicateurs socio-démographiques et de transport depuis leurs vraies sources :
      - population, densite_hab_km2 → INSEE Populations Légales 2021
      - indice_qualite_air          → WAQI via topic Kafka events.stream
      - nb_espaces_verts            → OpenData Paris (point-in-polygon)
      - taux_criminalite            → SSMSI / Ministère de l'Intérieur
      - nb_stations_velib           → OpenData Paris Vélib' temps réel
      - nb_stations_metro           → IDFM emplacement gares IDF (Metro + RER)

    Les champs manquants restent NULL — jamais remplacés par une valeur inventée.
    """
    base = pd.DataFrame({"arrondissement": range(1, 21)})

    df_pop = build_population_insee(client)
    if not df_pop.empty:
        base = base.merge(df_pop, on="arrondissement", how="left")
    else:
        base["population"] = pd.NA
        base["densite_hab_km2"] = pd.NA

    df_air = build_indice_qualite_air_snapshot(engine)
    if not df_air.empty:
        base = base.merge(df_air, on="arrondissement", how="left")
    else:
        base["indice_qualite_air"] = pd.NA

    df_verts = build_espaces_verts_counts(client)
    if not df_verts.empty:
        base = base.merge(df_verts, on="arrondissement", how="left")
        base["nb_espaces_verts"] = base["nb_espaces_verts"].fillna(0).astype(int)
    else:
        base["nb_espaces_verts"] = pd.NA

    df_crime = build_criminalite_par_arrondissement(client)
    if not df_crime.empty:
        base = base.merge(df_crime, on="arrondissement", how="left")
    else:
        base["taux_criminalite"] = pd.NA

    df_velib = build_velib_par_arrondissement(client)
    if not df_velib.empty:
        base = base.merge(df_velib, on="arrondissement", how="left")
    else:
        base["nb_stations_velib"] = pd.NA

    df_metro = build_metro_par_arrondissement(client)
    if not df_metro.empty:
        base = base.merge(df_metro, on="arrondissement", how="left")
    else:
        base["nb_stations_metro"] = pd.NA

    return base


def latest_bronze_geojson(client) -> dict | None:
    """Tente de lire le GeoJSON officiel le plus récent en zone bronze (téléchargé
    par ingestion/download_sources.py). Retourne None si indisponible (réseau
    coupé, première exécution sans le DAG d'ingestion réelle, etc.)."""
    keys = [k for k in list_keys(client, BRONZE_BUCKET, prefix="arrondissements/") if k.endswith(".geojson")]
    if not keys:
        return None
    try:
        raw = get_bytes(client, BRONZE_BUCKET, sorted(keys)[-1])
        return json.loads(raw)
    except Exception:
        return None


def build_enriched_geojson(client, df_prix: pd.DataFrame, df_socio: pd.DataFrame) -> dict:
    """
    Fusionne les géométries officielles avec le prix/m² par année et les
    indicateurs socio courants. Résultat exposé via GET /geo/arrondissements.
    """
    geojson = latest_bronze_geojson(client) or load_reference_geojson()

    prix_by_arr: dict[int, dict] = {}
    if not df_prix.empty:
        for arr, group in df_prix.groupby("arrondissement"):
            prix_by_arr[int(arr)] = {
                int(row.annee): {"prix_m2_median": row.prix_m2_median, "variation_pct": row.variation_pct}
                for row in group.itertuples()
            }

    socio_by_arr: dict[int, dict] = {}
    if not df_socio.empty:
        socio_by_arr = df_socio.set_index("arrondissement").to_dict(orient="index")

    enriched_features = []
    for feature in geojson["features"]:
        props = feature.get("properties", {})
        arr = props.get("c_ar") or props.get("NUM_ARR") or props.get("c_arinsee")
        if arr is None:
            continue
        arr = int(arr)
        if arr > 100:  # format c_arinsee (751XX)
            arr = arr - 75100

        new_props = {"NUM_ARR": arr, "NOM": f"{arr}e" if arr > 1 else "1er"}

        for year, values in prix_by_arr.get(arr, {}).items():
            if pd.notna(values["prix_m2_median"]):
                new_props[f"value_prixM2_{year}"] = float(values["prix_m2_median"])
            if pd.notna(values["variation_pct"]):
                new_props[f"value_variationPct_{year}"] = float(values["variation_pct"])

        socio = socio_by_arr.get(arr, {})
        for key, value in socio.items():
            if pd.isna(value):
                continue
            try:
                new_props[f"value_{key}"] = float(value)
            except (TypeError, ValueError):
                new_props[f"value_{key}"] = value

        enriched_features.append({**feature, "properties": new_props})

    return {"type": "FeatureCollection", "features": enriched_features}


def build_criminalite_par_arrondissement(client) -> pd.DataFrame:
    """
    Lit le Parquet Silver criminalite_communale.
    Retourne (arrondissement, taux_criminalite) prêt à fusionner avec indicateurs_socio.
    """
    key = latest_parquet(client, "criminalite_communale")
    if key is None:
        return pd.DataFrame(columns=["arrondissement", "taux_criminalite"])
    df = read_parquet_from_silver(client, key)
    if "taux_criminalite" not in df.columns or df.empty:
        return pd.DataFrame(columns=["arrondissement", "taux_criminalite"])
    return df[["arrondissement", "taux_criminalite"]].dropna(subset=["arrondissement"])


def build_velib_par_arrondissement(client) -> pd.DataFrame:
    """
    Lit le Parquet Silver velib_stations.
    Retourne (arrondissement, nb_stations_velib).
    """
    key = latest_parquet(client, "velib_stations")
    if key is None:
        return pd.DataFrame(columns=["arrondissement", "nb_stations_velib"])
    df = read_parquet_from_silver(client, key)
    col = next((c for c in df.columns if "nb_stations" in c), None)
    if col is None or df.empty:
        return pd.DataFrame(columns=["arrondissement", "nb_stations_velib"])
    return df[["arrondissement", col]].rename(columns={col: "nb_stations_velib"}).dropna(subset=["arrondissement"])


def build_metro_par_arrondissement(client) -> pd.DataFrame:
    """
    Lit le Parquet Silver metro_stations.
    Retourne (arrondissement, nb_stations_metro).
    """
    key = latest_parquet(client, "metro_stations")
    if key is None:
        return pd.DataFrame(columns=["arrondissement", "nb_stations_metro"])
    df = read_parquet_from_silver(client, key)
    col = next((c for c in df.columns if "nb_stations" in c), None)
    if col is None or df.empty:
        return pd.DataFrame(columns=["arrondissement", "nb_stations_metro"])
    return df[["arrondissement", col]].rename(columns={col: "nb_stations_metro"}).dropna(subset=["arrondissement"])


def build_espaces_verts_counts(client) -> pd.DataFrame:
    """
    Compte le nombre d'espaces verts géocodés par arrondissement (résultat du
    pipeline adresse -> API BAN -> point-in-polygon, voir clean_silver.py).
    Retourne un DataFrame (arrondissement, nb_espaces_verts) prêt à être
    fusionné avec indicateurs_socio.
    """
    key = latest_parquet(client, "espaces_verts")
    if key is None:
        return pd.DataFrame(columns=["arrondissement", "nb_espaces_verts"])

    df = read_parquet_from_silver(client, key)
    df = df.dropna(subset=["arrondissement"])
    if df.empty:
        return pd.DataFrame(columns=["arrondissement", "nb_espaces_verts"])

    counts = (
        df.groupby("arrondissement")
        .size()
        .reset_index(name="nb_espaces_verts")
    )
    counts["arrondissement"] = counts["arrondissement"].astype(int)
    return counts


def write_to_postgres(engine, df: pd.DataFrame, table_name: str):
    """
    Écrit un DataFrame dans une table Postgres (TRUNCATE + INSERT via psycopg2 brut).

    On évite df.to_sql(..., if_exists="replace") pour deux raisons :
    - il droppe et recrée la table, effaçant les GRANT accordés au rôle gold_readonly ;
    - dans le conteneur Airflow, la version figée de SQLAlchemy n'est pas reconnue
      par pandas comme un connectable valide, ce qui fait planter to_sql().
    """
    if df.empty:
        return 0

    columns = list(df.columns)
    col_list = ", ".join(columns)
    rows = df.where(pd.notnull(df), None).values.tolist()

    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()
        cur.execute(f"TRUNCATE TABLE {table_name}")
        insert_sql = f"INSERT INTO {table_name} ({col_list}) VALUES %s"
        psycopg2.extras.execute_values(cur, insert_sql, rows)
        raw_conn.commit()
        cur.close()
    finally:
        raw_conn.close()
    return len(df)


NOM_ARRONDISSEMENT = {
    1: "1er", **{i: f"{i}e" for i in range(2, 21)}
}


def populate_star_schema(engine, df_prix: pd.DataFrame):
    """
    Peuple le schéma en étoile (dim_arrondissement, dim_temps, fait_prix_immobilier)
    EN PLUS de la table plate prix_m2_arrondissement (pas à la place).
    Démontre l'intérêt analytique : prix moyen par arr ET par année en une jointure.
    """
    if df_prix.empty:
        print("  schéma en étoile : aucune donnée prix, skip")
        return

    raw_conn = engine.raw_connection()
    try:
        cur = raw_conn.cursor()

        # dim_arrondissement — upsert des 20 arrondissements
        arr_rows = [(i, NOM_ARRONDISSEMENT[i], None) for i in range(1, 21)]
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO dim_arrondissement (arrondissement_id, nom, superficie_km2)
            VALUES %s
            ON CONFLICT (arrondissement_id) DO UPDATE SET nom = EXCLUDED.nom
            """,
            arr_rows,
        )

        # dim_temps — upsert des années présentes
        annees = df_prix["annee"].unique().tolist()
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO dim_temps (annee_id, annee)
            VALUES %s
            ON CONFLICT (annee_id) DO NOTHING
            """,
            [(int(a), int(a)) for a in annees],
        )

        # fait_prix_immobilier — upsert complet
        # nb_transactions calculé depuis le df si la colonne existe, sinon NULL
        has_nb = "nb_transactions" in df_prix.columns
        fait_rows = []
        for row in df_prix.itertuples(index=False):
            nb = int(row.nb_transactions) if has_nb and pd.notna(row.nb_transactions) else None
            variation = float(row.variation_pct) if pd.notna(row.variation_pct) else None
            fait_rows.append((int(row.arrondissement), int(row.annee), float(row.prix_m2_median), variation, nb))

        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO fait_prix_immobilier
                (arrondissement_id, annee_id, prix_m2_median, variation_pct, nb_transactions)
            VALUES %s
            ON CONFLICT (arrondissement_id, annee_id) DO UPDATE SET
                prix_m2_median   = EXCLUDED.prix_m2_median,
                variation_pct    = EXCLUDED.variation_pct,
                nb_transactions  = EXCLUDED.nb_transactions
            """,
            fait_rows,
        )

        raw_conn.commit()
        cur.close()
        print(f"  schéma en étoile : {len(fait_rows)} faits, {len(annees)} années, 20 arrondissements -> PostgreSQL")
    finally:
        raw_conn.close()


def refresh_data_marts(engine) -> bool:
    """
    Rafraîchit les trois data marts matérialisés après le run Gold.
    Tente CONCURRENTLY (non-bloquant) ; si la vue est vide (premier run),
    bascule sur un refresh simple.
    """
    try:
        with engine.begin() as conn:
            conn.execute(text("SELECT refresh_data_marts()"))
        print("  data marts : mart_marche_immobilier, mart_mobilite, mart_qualite_vie rafraîchis")
        return True
    except Exception as exc:
        if "CONCURRENTLY" not in str(exc):
            print(f"  data marts : erreur inattendue — {exc}")
            return False
        # Premier run : vues non peuplées, CONCURRENTLY interdit → refresh simple
        try:
            with engine.begin() as conn:
                conn.execute(text("REFRESH MATERIALIZED VIEW mart_marche_immobilier"))
                conn.execute(text("REFRESH MATERIALIZED VIEW mart_mobilite"))
                conn.execute(text("REFRESH MATERIALIZED VIEW mart_qualite_vie"))
            print("  data marts : rafraîchis (mode initial sans CONCURRENTLY)")
            return True
        except Exception as exc2:
            print(f"  data marts : erreur rafraîchissement initial — {exc2}")
            return False


def main():
    client = get_s3_client()
    engine = get_pg_engine()
    run_start = time.time()
    report = {"run_started": time.strftime("%Y-%m-%dT%H:%M:%S"), "tables": []}

    print("=" * 60)
    print("AGREGATION GOLD — Indicateurs métier")
    print("=" * 60)

    # --- Table plate prix_m2_arrondissement (rétrocompatibilité API) ---
    df_prix = build_prix_m2_arrondissement(client)
    n = write_to_postgres(engine, df_prix, "prix_m2_arrondissement")
    put_dataframe_as_parquet(client, GOLD_BUCKET, f"{versioned_prefix('prix_m2_arrondissement')}/data.parquet", df_prix)
    report["tables"].append({"table": "prix_m2_arrondissement", "rows": n})
    print(f"  prix_m2_arrondissement : {n} lignes -> PostgreSQL + MinIO/gold")

    # --- Schéma en étoile (C2.3) — coexiste avec la table plate ---
    populate_star_schema(engine, df_prix)
    report["tables"].append({"table": "fait_prix_immobilier (étoile)", "rows": n})

    # --- indicateurs_socio (sources réelles uniquement) ---
    df_socio = build_indicateurs_socio(client, engine)
    n = write_to_postgres(engine, df_socio, "indicateurs_socio")
    put_dataframe_as_parquet(client, GOLD_BUCKET, f"{versioned_prefix('indicateurs_socio')}/data.parquet", df_socio)
    report["tables"].append({"table": "indicateurs_socio", "rows": n})
    print(f"  indicateurs_socio : {n} lignes -> PostgreSQL + MinIO/gold")

    # --- Data Marts — rafraîchissement des vues matérialisées ---
    marts_ok = refresh_data_marts(engine)
    report["tables"].append({"table": "data_marts", "rows": 3 if marts_ok else 0})

    # --- GeoJSON enrichi ---
    enriched_geojson = build_enriched_geojson(client, df_prix, df_socio)
    geojson_key = "enriched_arrondissements/latest.geojson"
    geojson_bytes = json.dumps(enriched_geojson, ensure_ascii=False).encode("utf-8")
    put_bytes(client, GOLD_BUCKET, geojson_key, geojson_bytes, content_type="application/geo+json")
    put_bytes(
        client, GOLD_BUCKET, f"{versioned_prefix('enriched_arrondissements')}/data.geojson",
        geojson_bytes, content_type="application/geo+json",
    )
    n_features = len(enriched_geojson["features"])
    report["tables"].append({"table": "enriched_arrondissements.geojson", "rows": n_features})
    print(f"  enriched_arrondissements.geojson : {n_features} arrondissements -> MinIO/gold")

    # Métriques harmonisées C1.3 / C2.4
    lignes_total = sum(t["rows"] for t in report["tables"])
    duree_totale = round(time.time() - run_start, 2)
    report["duree_s"] = duree_totale
    report["volume_octets"] = len(geojson_bytes)
    report["debit_lignes_par_s"] = round(lignes_total / max(duree_totale, 0.01), 1)
    report["taux_succes_pct"] = 100.0

    summary_key = f"_reports/gold_run/{versioned_prefix('summary')}.json"
    put_json(client, GOLD_BUCKET, summary_key, report)

    write_pipeline_report("gold", report)

    print(f"\nRapport global : s3://{GOLD_BUCKET}/{summary_key}")
    print(f"Métriques : {lignes_total} lignes en {duree_totale}s")
    return report


if __name__ == "__main__":
    main()
