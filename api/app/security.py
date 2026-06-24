"""
api/app/security.py
---------------------
Sécurisation minimale mais réelle de l'API :
  - Clé API obligatoire sur les endpoints sensibles (header X-API-Key),
    vérifiée via une comparaison en temps constant (`secrets.compare_digest`)
    pour limiter le risque de timing attack.
  - CORS restreint au domaine du dashboard (configuré dans main.py).
  - Limitation de débit basique en mémoire (fenêtre glissante par IP) pour
    éviter un usage abusif de l'API publique de lecture.

Limite : le rate-limiting est en mémoire (par instance). Une mise à l'échelle
horizontale nécessiterait un store partagé (Redis).
"""
import os
import secrets
import time
from collections import defaultdict

from fastapi import Header, HTTPException, Request, status

API_KEY = os.environ.get("API_KEY", "demo-key-change-me")

_rate_limit_window_s = 60
_rate_limit_max_requests = 120
_request_log: dict[str, list[float]] = defaultdict(list)


def verify_api_key(x_api_key: str = Header(default=None)):
    """Dépendance FastAPI : exige une clé API valide pour les endpoints protégés."""
    if x_api_key is None or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Clé API manquante ou invalide.")
    return True


def rate_limit(request: Request):
    """Dépendance FastAPI : limite le nombre de requêtes par IP sur une fenêtre glissante."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    history = _request_log[client_ip]
    history[:] = [t for t in history if now - t < _rate_limit_window_s]

    if len(history) >= _rate_limit_max_requests:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Trop de requêtes, réessayez plus tard.")

    history.append(now)
    return True
