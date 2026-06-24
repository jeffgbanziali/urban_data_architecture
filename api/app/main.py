"""
api/app/main.py
-----------------
Point d'entrée FastAPI : sécurité, CORS, routeurs métier, /health et /docs.
"""
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.routers import admin_pipeline, admin_users, auth, biens, comparaison, favoris, geo, marts, prix, realtime_ws

FRONTEND_ORIGIN = os.environ.get("FRONTEND_ORIGIN", "*")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Ajoute les en-têtes de sécurité HTTP recommandés sur toutes les réponses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # CSP volontairement omis : le /docs Swagger injecte des scripts inline
        # qui nécessiteraient un 'unsafe-inline' — activer en production après audit.
        return response


app = FastAPI(
    title="Urban Immo / Urban Data Explorer API",
    description="""
API de l'agence immobilière Urban Immo — Urban Data Explorer.

## Authentification (C2.1)

JWT signé HS256 via `POST /auth/login`. Inclure le token dans l'en-tête :
`Authorization: Bearer <token>`

Trois rôles applicatifs :
| Rôle | Droits |
|---|---|
| **public** | Lecture des biens, prix, indicateurs, GeoJSON |
| **client** | + favoris personnels |
| **employe** | + création et modification de biens |
| **admin** | + gestion des comptes, suppression de biens, endpoints pipeline |

## Sécurité

- Authentification : JWT HS256, expiration 24 h
- Mots de passe : bcrypt (coût 12)
- En-têtes HTTP : X-Content-Type-Options, X-Frame-Options, X-XSS-Protection, Referrer-Policy
- Quota : 60 req/min par IP (reverse-proxy Nginx en production)
- Taille maximale du corps de requête : 1 MB

## Data Marts analytiques

Vues matérialisées rafraîchies après chaque run pipeline :
- `GET /marts/marche` — prix, variations, segmentation (premium / intermédiaire / accessible)
- `GET /marts/qualite-vie` — population, qualité de l'air, espaces verts
- `GET /marts/mobilite` — état Vélib en temps réel par arrondissement

## Sources de données

Toutes réelles, aucune valeur inventée :
- **DVF** (data.gouv.fr) — prix immobiliers 2021-2025
- **INSEE communes** (data.gouv.fr) — population et densité
- **WAQI / Airparif** — qualité de l'air temps réel
- **OpenData Paris** — espaces verts géocodés, Vélib disponibilité temps réel
""",
    version="2.1.0",
)

# Sécurité : en-têtes HTTP sur toutes les réponses
app.add_middleware(SecurityHeadersMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

app.include_router(auth.router)
app.include_router(prix.router)
app.include_router(comparaison.router)
app.include_router(realtime_ws.router)
app.include_router(biens.router)
app.include_router(favoris.router)
app.include_router(admin_users.router)
app.include_router(admin_pipeline.router)
app.include_router(geo.router)
app.include_router(marts.router)


@app.get("/health", tags=["Système"])
def health():
    return {"status": "ok"}


@app.get("/", tags=["Système"])
def root():
    return {
        "message": "Urban Immo / Urban Data Explorer API v2.1",
        "docs": "/docs",
        "endpoints": [
            "/auth/register", "/auth/login", "/auth/me",
            "/biens", "/favoris", "/admin/users",
            "/arrondissements", "/prix", "/comparaison", "/timeline", "/typologie",
            "/geo/arrondissements",
            "/marts/marche", "/marts/qualite-vie", "/marts/mobilite",
            "/ws/realtime",
        ],
    }
