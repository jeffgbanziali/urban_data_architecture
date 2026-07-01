import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text

from app.auth import get_current_user, require_role
from app import db, mongo_client
from app.schemas import BienCreate, BienOut, BienUpdate

log = logging.getLogger(__name__)

router = APIRouter(prefix="/biens", tags=["Biens immobiliers"])


@router.get("", response_model=list[BienOut])
def list_biens(
    arrondissement: Optional[int] = Query(None, ge=1, le=20),
    type_bien: Optional[str] = Query(None),
    statut: Optional[str] = Query(None),
    prix_max: Optional[float] = Query(None, gt=0),
):
    """Liste publique des biens, avec filtres optionnels (vitrine de l'agence)."""
    query = "SELECT * FROM biens WHERE 1=1"
    params: dict = {}
    if arrondissement is not None:
        query += " AND arrondissement = :arrondissement"
        params["arrondissement"] = arrondissement
    if type_bien is not None:
        query += " AND type_bien = :type_bien"
        params["type_bien"] = type_bien
    if statut is not None:
        query += " AND statut = :statut"
        params["statut"] = statut
    if prix_max is not None:
        query += " AND prix <= :prix_max"
        params["prix_max"] = prix_max
    query += " ORDER BY created_at DESC"

    with db.engine.connect() as conn:
        rows = conn.execute(text(query), params).mappings().all()
    return [_row_to_bien(r) for r in rows]


@router.get("/{bien_id}", response_model=BienOut)
def get_bien(bien_id: int):
    with db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM biens WHERE id = :id"), {"id": bien_id}
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bien introuvable.")
    return _row_to_bien(row)


@router.get("/{bien_id}/caracteristiques", tags=["Biens immobiliers"])
def get_caracteristiques(bien_id: int):
    """
    Retourne les caractéristiques libres d'un bien (colonne JSONB).
    Ces attributs sont variables selon le type de bien :
      Studio → {"etage": 3, "ascenseur": true}
      Maison → {"jardin_m2": 80, "garage": true, "nb_niveaux": 2}
    Retourne {} si aucune caractéristique n'a encore été renseignée.
    """
    with db.engine.connect() as conn:
        row = conn.execute(
            text("SELECT caracteristiques FROM biens WHERE id = :id"), {"id": bien_id}
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bien introuvable.")
    return row["caracteristiques"] or {}


async def _upsert_mongo(bien_id: int, type_bien: str, caracteristiques: dict) -> None:
    mdb = mongo_client.get_mongo_db()
    if mdb is None:
        return
    try:
        await mdb.biens_caracteristiques.update_one(
            {"bien_id": bien_id},
            {"$set": {"bien_id": bien_id, "type_bien": type_bien, **caracteristiques}},
            upsert=True,
        )
    except Exception as exc:
        log.warning("MongoDB write failed for bien %s: %s", bien_id, exc)


@router.post("", response_model=BienOut, status_code=status.HTTP_201_CREATED)
async def create_bien(
    payload: BienCreate,
    current_user: dict = Depends(require_role("employe", "admin")),
):
    data = payload.model_dump(exclude={"caracteristiques"})
    caracteristiques_json = json.dumps(payload.caracteristiques or {})

    with db.engine.connect() as conn:
        result = conn.execute(
            text(
                "INSERT INTO biens "
                "(titre, description, arrondissement, type_bien, prix, surface_m2, "
                " photo_url, statut, employe_id, caracteristiques) "
                "VALUES (:titre, :description, :arrondissement, :type_bien, :prix, :surface_m2, "
                "        :photo_url, :statut, :employe_id, :caracteristiques::jsonb) "
                "RETURNING *"
            ),
            {**data, "employe_id": current_user["id"], "caracteristiques": caracteristiques_json},
        )
        row = result.mappings().first()
        conn.commit()

    bien = _row_to_bien(row)
    await _upsert_mongo(bien["id"], bien["type_bien"], bien.get("caracteristiques") or {})
    return bien


@router.put("/{bien_id}", response_model=BienOut)
async def update_bien(
    bien_id: int,
    payload: BienUpdate,
    current_user: dict = Depends(require_role("employe", "admin")),
):
    data = {k: v for k, v in payload.model_dump(exclude={"caracteristiques"}).items() if v is not None}

    if not data and payload.caracteristiques is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Aucune modification fournie.")

    with db.engine.connect() as conn:
        existing = conn.execute(
            text("SELECT id FROM biens WHERE id = :id"), {"id": bien_id}
        ).mappings().first()
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bien introuvable.")

        # Construction dynamique du SET clause
        set_parts = [f"{col} = :{col}" for col in data]
        if payload.caracteristiques is not None:
            set_parts.append("caracteristiques = :caracteristiques::jsonb")
            data["caracteristiques"] = json.dumps(payload.caracteristiques)

        set_parts.append("updated_at = now()")
        data["id"] = bien_id

        result = conn.execute(
            text(f"UPDATE biens SET {', '.join(set_parts)} WHERE id = :id RETURNING *"),
            data,
        )
        row = result.mappings().first()
        conn.commit()

    bien = _row_to_bien(row)
    await _upsert_mongo(bien["id"], bien["type_bien"], bien.get("caracteristiques") or {})
    return bien


@router.delete("/{bien_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bien(bien_id: int, current_user: dict = Depends(require_role("admin"))):
    with db.engine.connect() as conn:
        result = conn.execute(text("DELETE FROM biens WHERE id = :id"), {"id": bien_id})
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bien introuvable.")


def _row_to_bien(row) -> dict:
    """Convertit une ligne SQL en dict compatible BienOut (JSONB → dict Python)."""
    d = dict(row)
    carac = d.get("caracteristiques")
    if isinstance(carac, str):
        try:
            d["caracteristiques"] = json.loads(carac)
        except (ValueError, TypeError):
            d["caracteristiques"] = {}
    return d
