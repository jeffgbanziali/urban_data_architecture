"""
pipeline/bronze/pipeline_reporter.py
--------------------------------------
Observabilité du pipeline : écrit les rapports qualité dans la table PostgreSQL
`pipeline_rapports` (JSONB). Remplace mongo_pipeline.py — MongoDB est supprimé
car PostgreSQL JSONB couvre exactement les mêmes besoins (stockage de documents
semi-structurés, requêtes filtrées par stage/taux_succes, tri par horodatage)
sans ajouter un quatrième système de persistence.

Ne lève jamais d'exception : la perte d'un rapport de monitoring ne doit pas
bloquer un run de pipeline réussi.
"""
import json
import os

import psycopg2


def _get_conn():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_GOLD_HOST", "postgres-gold"),
        database=os.environ.get("POSTGRES_GOLD_DB", "gold"),
        user=os.environ.get("POSTGRES_GOLD_USER", "gold_user"),
        password=os.environ.get("POSTGRES_GOLD_PASSWORD", "gold_pass"),
        connect_timeout=5,
    )


def write_pipeline_report(stage: str, report: dict) -> None:
    """
    Insère un rapport qualité dans pipeline_rapports (PostgreSQL JSONB).

    Les métriques scalaires sont extraites au niveau racine (colonnes indexées)
    et le rapport complet est conservé dans payload JSONB pour requêtes ad hoc.
    Le stage bronze niche ses métriques sous report["summary"] ; silver et gold
    les exposent au niveau racine — les deux cas sont gérés ici.
    """
    summary = report.get("summary", report)
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pipeline_rapports
                        (stage, duree_s, volume_octets,
                         debit_lignes_par_s, debit_octets_par_s, taux_succes_pct,
                         payload)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        stage,
                        _float(summary.get("duree_s")),
                        _int(summary.get("volume_octets")),
                        _float(summary.get("debit_lignes_par_s")),
                        _float(summary.get("debit_octets_par_s")),
                        _float(summary.get("taux_succes_pct")),
                        json.dumps(report, default=str),
                    ),
                )
        conn.close()
    except Exception as exc:
        print(f"[pipeline_reporter] warn: rapport non écrit en PostgreSQL ({exc})")


def _float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None
