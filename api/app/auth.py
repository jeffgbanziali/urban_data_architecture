"""
api/app/auth.py
------------------
Authentification par JWT et contrôle d'accès basé sur les rôles
(client / employe / admin).

Choix techniques :
  - Hash des mots de passe avec `bcrypt` directement (plutôt que passlib, qui
    a des soucis de compatibilité avec les versions récentes de bcrypt) :
    plus simple, moins de dépendances, même garantie de sécurité.
  - JWT signés HS256 via PyJWT, avec expiration courte configurable
    (JWT_EXPIRE_MINUTES, 8h par défaut — une journée de travail).
  - `get_current_user` décode le token et recharge l'utilisateur depuis la
    base à chaque requête (pas seulement depuis le contenu du token), pour
    qu'une désactivation de compte par un admin soit immédiatement effective.
  - `require_role(...)` est un facteur de dépendances FastAPI réutilisable
    pour protéger un endpoint à une liste de rôles autorisés.

Gère l'authentification JWT et le contrôle d'accès pour les 3 profils utilisateurs.
"""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import text

from app import db

JWT_SECRET = os.environ.get("JWT_SECRET", "change-this-secret-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "480"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(user_id: int, email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "email": email, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expirée, veuillez vous reconnecter.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token invalide.")


def get_current_user(token: str = Depends(oauth2_scheme)) -> dict:
    if token is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification requise.")

    payload = decode_access_token(token)
    with db.engine.connect() as conn:
        user = conn.execute(
            text("SELECT id, email, full_name, role, is_active FROM users WHERE id = :id"),
            {"id": int(payload["sub"])},
        ).mappings().first()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Utilisateur introuvable.")
    if not user["is_active"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Compte désactivé. Contactez un administrateur.")

    return dict(user)


def require_role(*allowed_roles: str):
    """Fabrique une dépendance FastAPI qui n'autorise que les rôles donnés."""

    def dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user["role"] not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Accès réservé aux rôles : {', '.join(allowed_roles)}.",
            )
        return current_user

    return dependency
