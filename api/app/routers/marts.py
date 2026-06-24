"""
api/app/routers/marts.py
--------------------------
Endpoints publics qui exposent les data marts Gold (vues matérialisées).
Rafraîchies après chaque run du pipeline Airflow (aggregate_gold.py).

  GET /marts/marche       → mart_marche_immobilier (prix, segment, tendance)
  GET /marts/qualite-vie  → mart_qualite_vie (population, air, espaces verts)
  GET /marts/mobilite     → mart_mobilite (Vélib par arrondissement)

Ces vues combinent les dimensions (schéma étoile) avec les données temps réel
pour offrir une vision analytique directement consommable par le frontend ou
des outils BI externes.
"""
from typing import Optional

from fastapi import APIRouter, Query
from sqlalchemy import text

from app import db

router = APIRouter(prefix="/marts", tags=["Data Marts Gold"])


@router.get("/marche")
def get_mart_marche(
    annee: Optional[int] = Query(None, description="Filtrer par année"),
    segment: Optional[str] = Query(None, description="premium | intermediaire | accessible"),
):
    """
    Marché immobilier par arrondissement et année.
    Inclut le prix médian au m², la variation annuelle et la segmentation de marché.
    """
    params: dict = {}
    where_parts = []

    if annee is not None:
        where_parts.append("annee = :annee")
        params["annee"] = annee
    if segment:
        where_parts.append("segment_marche = :segment")
        params["segment"] = segment

    where = f"WHERE {' AND '.join(where_parts)}" if where_parts else ""

    sql = f"""
        SELECT arrondissement, arrondissement_nom, annee,
               prix_m2_median, variation_pct, nb_transactions,
               segment_marche, tendance
        FROM mart_marche_immobilier
        {where}
        ORDER BY arrondissement, annee
    """
    with db.engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return {"count": len(rows), "data": [dict(r) for r in rows]}


@router.get("/qualite-vie")
def get_mart_qualite_vie():
    """
    Indicateurs de qualité de vie par arrondissement : population, densité,
    qualité de l'air, nombre d'espaces verts, ratio espaces verts/habitant.
    """
    sql = """
        SELECT arrondissement, arrondissement_nom,
               population, densite_hab_km2,
               indice_qualite_air, niveau_qualite_air,
               nb_espaces_verts, espaces_verts_pour_10k_hab
        FROM mart_qualite_vie
        ORDER BY arrondissement
    """
    with db.engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()
    return {"count": len(rows), "data": [dict(r) for r in rows]}


@router.get("/mobilite")
def get_mart_mobilite():
    """
    Disponibilité Vélib en temps réel agrégée par arrondissement.
    Mise à jour continue par le consumer Kafka (streaming/consumer_to_gold.py).
    """
    sql = """
        SELECT arrondissement, arrondissement_nom,
               nb_stations_actives, velos_disponibles_moyen,
               etat_mobilite, derniere_maj
        FROM mart_mobilite
        ORDER BY arrondissement
    """
    with db.engine.connect() as conn:
        rows = conn.execute(text(sql)).mappings().all()

    data = []
    for r in rows:
        d = dict(r)
        if d.get("derniere_maj"):
            d["derniere_maj"] = d["derniere_maj"].isoformat()
        data.append(d)
    return {"count": len(data), "data": data}
