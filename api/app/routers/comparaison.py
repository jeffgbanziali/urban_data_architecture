"""
api/app/routers/comparaison.py
---------------------------------
Endpoints de comparaison et de timeline, utilisés par le mode "comparaison
arrondissement A vs B" et la timeline animée du dashboard.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from app import db
from app.schemas import ComparaisonArrondissement, ComparaisonResponse, IndicateurSocio, TimelinePoint
from app.security import rate_limit

router = APIRouter(dependencies=[Depends(rate_limit)])


def _build_arrondissement_payload(arr: int) -> ComparaisonArrondissement:
    with db.engine.connect() as conn:
        timeline_rows = conn.execute(
            text(
                "SELECT annee, prix_m2_median, variation_pct FROM prix_m2_arrondissement "
                "WHERE arrondissement = :arr ORDER BY annee"
            ),
            {"arr": arr},
        ).mappings().all()
        indic_row = conn.execute(
            text("SELECT * FROM indicateurs_socio WHERE arrondissement = :arr"),
            {"arr": arr},
        ).mappings().first()

    if not timeline_rows:
        raise HTTPException(status_code=404, detail=f"Aucune donnée de prix pour l'arrondissement {arr}.")

    return ComparaisonArrondissement(
        arrondissement=arr,
        timeline=[TimelinePoint(**row) for row in timeline_rows],
        indicateurs=IndicateurSocio(**indic_row) if indic_row else None,
    )


@router.get("/comparaison", response_model=ComparaisonResponse, tags=["Comparaison"])
def comparer_arrondissements(
    arr1: int = Query(..., ge=1, le=20),
    arr2: int = Query(..., ge=1, le=20),
):
    """Compare deux arrondissements (timeline des prix + indicateurs socio)."""
    if arr1 == arr2:
        raise HTTPException(status_code=400, detail="Veuillez choisir deux arrondissements différents.")
    return ComparaisonResponse(
        arr1=_build_arrondissement_payload(arr1),
        arr2=_build_arrondissement_payload(arr2),
    )


@router.get("/timeline", response_model=list[TimelinePoint], tags=["Indicateurs"])
def get_timeline(arr: int = Query(..., ge=1, le=20, description="Numéro de l'arrondissement (1-20)")):
    """Évolution du prix médian au m² dans le temps pour un arrondissement donné."""
    payload = _build_arrondissement_payload(arr)
    return payload.timeline
