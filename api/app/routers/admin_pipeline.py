"""
api/app/routers/admin_pipeline.py
-----------------------------------
Endpoints d'administration du pipeline — réservés au rôle admin.
Interrogent la table PostgreSQL `pipeline_rapports` (JSONB) pour exposer :
  - GET /admin/rapports-qualite : runs filtrables par stage et seuil de succès
  - GET /admin/metriques-pipeline : évolution des métriques sur les derniers runs

La table pipeline_rapports remplace MongoDB :
  - Filtres (taux_succes_pct < seuil, stage = 'bronze') → SQL WHERE standard
  - Tri par date → ORDER BY run_started DESC
  - Payload complet → colonne JSONB interrogeable via -> et ->>
  - Aucun service supplémentaire — même PostgreSQL que le reste de l'application
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from app.auth import require_role
from app import db

router = APIRouter(prefix="/admin", tags=["Administration pipeline"])


@router.get("/rapports-qualite")
def get_rapports_qualite(
    stage: Optional[str] = Query(None, description="Filtrer par stage : bronze | silver | gold"),
    seuil_succes: float = Query(80.0, ge=0, le=100, description="Ne retourner que les runs avec taux_succes_pct < seuil"),
    limit: int = Query(20, ge=1, le=200),
    _: dict = Depends(require_role("admin")),
):
    """
    Retourne les runs du pipeline dont le taux de succès est inférieur au seuil —
    permet de détecter rapidement les exécutions dégradées.
    """
    where = ["taux_succes_pct < :seuil OR taux_succes_pct IS NULL"]
    params: dict = {"seuil": seuil_succes, "limit": limit}

    if stage:
        where.append("stage = :stage")
        params["stage"] = stage

    sql = f"""
        SELECT id, stage, run_started, duree_s, volume_octets,
               debit_lignes_par_s, debit_octets_par_s, taux_succes_pct, payload
        FROM pipeline_rapports
        WHERE {' AND '.join(where)}
        ORDER BY run_started DESC
        LIMIT :limit
    """
    with db.engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    rapports = [_serialize_row(r) for r in rows]
    return {"count": len(rapports), "seuil_succes_pct": seuil_succes, "rapports": rapports}


@router.get("/metriques-pipeline")
def get_metriques_pipeline(
    stage: Optional[str] = Query(None, description="bronze | silver | gold — tous si omis"),
    limit: int = Query(30, ge=1, le=200),
    _: dict = Depends(require_role("admin")),
):
    """
    Retourne l'évolution des métriques clés (duree_s, volume_octets,
    debit_lignes_par_s, taux_succes_pct) sur les derniers runs du pipeline.
    Permet de détecter une dérive progressive (source externe plus lente, etc.).
    """
    params: dict = {"limit": limit}
    where = ""
    if stage:
        where = "WHERE stage = :stage"
        params["stage"] = stage

    sql = f"""
        SELECT stage, run_started, duree_s, volume_octets,
               debit_lignes_par_s, debit_octets_par_s, taux_succes_pct
        FROM pipeline_rapports
        {where}
        ORDER BY run_started DESC
        LIMIT :limit
    """
    with db.engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()

    metriques = [dict(r) for r in rows]
    return {"count": len(metriques), "metriques": metriques}


def _serialize_row(row) -> dict:
    import json
    d = dict(row)
    payload = d.get("payload")
    if isinstance(payload, str):
        try:
            d["payload"] = json.loads(payload)
        except (ValueError, TypeError):
            d["payload"] = {}
    if d.get("run_started"):
        d["run_started"] = d["run_started"].isoformat()
    return d
