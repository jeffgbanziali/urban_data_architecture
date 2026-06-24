"""
api/app/routers/admin_users.py
---------------------------------
Gestion des comptes utilisateurs, réservée au rôle "admin" :
  - lister tous les comptes (clients, employés, admins) ;
  - créer un compte employé ou admin (l'auto-inscription publique ne permet
    de créer que des comptes client, voir routers/auth.py) ;
  - changer le rôle d'un utilisateur ;
  - activer/désactiver un compte (sans suppression, pour garder l'historique).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.auth import hash_password, require_role
from app import db
from app.schemas import UserActiveUpdate, UserOut, UserRegister, UserRoleUpdate

router = APIRouter(prefix="/admin/users", tags=["Administration"])


@router.get("", response_model=list[UserOut])
def list_users(current_user: dict = Depends(require_role("admin"))):
    with db.engine.connect() as conn:
        rows = conn.execute(text("SELECT id, email, full_name, role, is_active FROM users ORDER BY created_at DESC")).mappings().all()
    return list(rows)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_staff_user(payload: UserRegister, role: str, current_user: dict = Depends(require_role("admin"))):
    """Permet à un admin de créer directement un compte employé ou admin."""
    if role not in ("employe", "admin", "client"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rôle invalide.")

    with db.engine.connect() as conn:
        existing = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": payload.email}).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email.")

        result = conn.execute(
            text(
                "INSERT INTO users (email, hashed_password, full_name, role) "
                "VALUES (:email, :hashed, :full_name, :role) RETURNING id, email, full_name, role, is_active"
            ),
            {"email": payload.email, "hashed": hash_password(payload.password), "full_name": payload.full_name, "role": role},
        )
        row = result.mappings().first()
        conn.commit()
        return row


@router.patch("/{user_id}/role", response_model=UserOut)
def update_role(user_id: int, payload: UserRoleUpdate, current_user: dict = Depends(require_role("admin"))):
    if user_id == current_user["id"] and payload.role != "admin":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vous ne pouvez pas retirer votre propre rôle admin.")

    with db.engine.connect() as conn:
        result = conn.execute(
            text("UPDATE users SET role = :role WHERE id = :id RETURNING id, email, full_name, role, is_active"),
            {"role": payload.role, "id": user_id},
        )
        row = result.mappings().first()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    return row


@router.patch("/{user_id}/active", response_model=UserOut)
def update_active(user_id: int, payload: UserActiveUpdate, current_user: dict = Depends(require_role("admin"))):
    if user_id == current_user["id"] and not payload.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Vous ne pouvez pas désactiver votre propre compte.")

    with db.engine.connect() as conn:
        result = conn.execute(
            text("UPDATE users SET is_active = :is_active WHERE id = :id RETURNING id, email, full_name, role, is_active"),
            {"is_active": payload.is_active, "id": user_id},
        )
        row = result.mappings().first()
        conn.commit()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Utilisateur introuvable.")
    return row
