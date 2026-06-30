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
