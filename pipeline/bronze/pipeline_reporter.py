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
