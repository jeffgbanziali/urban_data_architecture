"""
api/app/routers/auth.py
--------------------------
Endpoints d'authentification.

  - POST /auth/register : auto-inscription, réservée au rôle "client"
    (un employé ou un administrateur est créé par un administrateur via
    /admin/users, jamais par auto-inscription — séparation des privilèges).
  - POST /auth/login : authentifie par email/mot de passe, retourne un JWT.
  - GET  /auth/me : profil de l'utilisateur courant (vérifie la validité du token).
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app import db
from app.schemas import Token, UserLogin, UserOut, UserRegister

router = APIRouter(prefix="/auth", tags=["Authentification"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegister):
    with db.engine.connect() as conn:
        existing = conn.execute(text("SELECT id FROM users WHERE email = :email"), {"email": payload.email}).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Un compte existe déjà avec cet email.")

        result = conn.execute(
            text(
                "INSERT INTO users (email, hashed_password, full_name, role) "
                "VALUES (:email, :hashed, :full_name, 'client') RETURNING id, email, full_name, role"
            ),
            {"email": payload.email, "hashed": hash_password(payload.password), "full_name": payload.full_name},
        )
        user = result.mappings().first()
        conn.commit()

    token = create_access_token(user["id"], user["email"], user["role"])
    return Token(access_token=token, role=user["role"], full_name=user["full_name"])


@router.post("/login", response_model=Token)
def login(payload: UserLogin):
    with db.engine.connect() as conn:
        user = conn.execute(
            text("SELECT id, email, hashed_password, full_name, role, is_active FROM users WHERE email = :email"),
            {"email": payload.email},
        ).mappings().first()

    if user is None or not verify_password(payload.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Email ou mot de passe incorrect.")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé. Contactez un administrateur.")

    token = create_access_token(user["id"], user["email"], user["role"])
    return Token(access_token=token, role=user["role"], full_name=user["full_name"])


@router.get("/me", response_model=UserOut)
def me(current_user: dict = Depends(get_current_user)):
    return current_user
