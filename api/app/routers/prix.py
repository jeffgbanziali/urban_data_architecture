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


@router.get("/typologie", tags=["Indicateurs"])
def get_typologie(arr: int = Query(..., ge=1, le=20)):
    """Répartition types de logements (Appartement/Maison) et pièces (T1→T5+) par arrondissement."""
    from app.db import engine
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT type_local, nb_pieces_cat, part_pct FROM typologie_logements WHERE arrondissement = :arr"),
                {"arr": arr},
            ).mappings().all()
    except Exception:
        raise HTTPException(status_code=503, detail="Table non disponible — relancez le pipeline Gold.")

    type_local: dict[str, float] = {}
    nb_pieces: dict[str, float] = {}
    for r in rows:
        if r["nb_pieces_cat"] == "all":
            type_local[r["type_local"]] = float(r["part_pct"])
        elif r["type_local"] == "all":
            nb_pieces[r["nb_pieces_cat"]] = float(r["part_pct"])

    return {"arrondissement": arr, "type_local": type_local, "nb_pieces": nb_pieces}
