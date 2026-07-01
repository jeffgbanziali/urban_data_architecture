from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.auth import require_role
from app import db
from app.schemas import BienOut

router = APIRouter(prefix="/favoris", tags=["Favoris"])


@router.get("", response_model=list[BienOut])
def list_my_favoris(current_user: dict = Depends(require_role("client"))):
    with db.engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT b.* FROM biens b "
                "JOIN favoris f ON f.bien_id = b.id "
                "WHERE f.client_id = :client_id ORDER BY f.created_at DESC"
            ),
            {"client_id": current_user["id"]},
        ).mappings().all()
    return list(rows)


@router.post("/{bien_id}", status_code=status.HTTP_201_CREATED)
def add_favori(bien_id: int, current_user: dict = Depends(require_role("client"))):
    with db.engine.connect() as conn:
        bien = conn.execute(text("SELECT id FROM biens WHERE id = :id"), {"id": bien_id}).first()
        if not bien:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bien introuvable.")
        conn.execute(
            text("INSERT INTO favoris (client_id, bien_id) VALUES (:client_id, :bien_id) ON CONFLICT DO NOTHING"),
            {"client_id": current_user["id"], "bien_id": bien_id},
        )
        conn.commit()
    return {"message": "Ajouté aux favoris."}


@router.delete("/{bien_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_favori(bien_id: int, current_user: dict = Depends(require_role("client"))):
    with db.engine.connect() as conn:
        conn.execute(
            text("DELETE FROM favoris WHERE client_id = :client_id AND bien_id = :bien_id"),
            {"client_id": current_user["id"], "bien_id": bien_id},
        )
        conn.commit()
