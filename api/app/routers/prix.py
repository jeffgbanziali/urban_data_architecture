from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import IndicateurSocio, PrixArrondissement
from app.security import rate_limit

router = APIRouter(dependencies=[Depends(rate_limit)])


@router.get("/arrondissements", response_model=list[IndicateurSocio], tags=["Référentiel"])
def get_arrondissements(db: Session = Depends(get_db)):
    """Liste des 20 arrondissements avec leurs indicateurs socio-économiques courants."""
    rows = db.execute(text("SELECT * FROM indicateurs_socio ORDER BY arrondissement")).mappings().all()
    if not rows:
        raise HTTPException(status_code=404, detail="Aucun indicateur socio-économique chargé pour le moment.")
    return list(rows)


@router.get("/prix", response_model=list[PrixArrondissement], tags=["Indicateurs"])
def get_prix(annee: Optional[int] = Query(None, description="Filtrer sur une année précise, ex: 2023")):
    """Prix médian au m² par arrondissement, optionnellement filtré par année."""
    from app.db import engine

    query = "SELECT arrondissement, annee, prix_m2_median, variation_pct FROM prix_m2_arrondissement"
    params = {}
    if annee is not None:
        query += " WHERE annee = :annee"
        params["annee"] = annee
    query += " ORDER BY arrondissement, annee"

    with engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()

    if not rows:
        raise HTTPException(status_code=404, detail="Aucune donnée de prix trouvée pour ces critères.")
    return list(rows)
