import datetime
import os
import sys
from pathlib import Path

import bcrypt
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("JWT_SECRET", "test-secret")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))

DDL = """
CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email VARCHAR(255) UNIQUE NOT NULL, hashed_password VARCHAR(255) NOT NULL, full_name VARCHAR(255) NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'client', is_active BOOLEAN NOT NULL DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE biens (id INTEGER PRIMARY KEY AUTOINCREMENT, titre VARCHAR(255) NOT NULL, description TEXT, arrondissement INTEGER NOT NULL, type_bien VARCHAR(30) NOT NULL, prix REAL NOT NULL, surface_m2 REAL NOT NULL, photo_url TEXT, statut VARCHAR(20) NOT NULL DEFAULT 'disponible', employe_id INTEGER, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE favoris (client_id INTEGER NOT NULL, bien_id INTEGER NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (client_id, bien_id));
CREATE TABLE prix_m2_arrondissement (arrondissement INTEGER, annee INTEGER, prix_m2_median REAL, variation_pct REAL, PRIMARY KEY(arrondissement, annee));
CREATE TABLE indicateurs_socio (arrondissement INTEGER PRIMARY KEY, population INTEGER, densite_hab_km2 INTEGER, indice_qualite_air REAL, nb_espaces_verts INTEGER);
CREATE TABLE qualite_air_temps_reel (id INTEGER PRIMARY KEY AUTOINCREMENT, arrondissement INTEGER, indice_qualite_air REAL, horodatage TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE disponibilite_velib_temps_reel (id INTEGER PRIMARY KEY AUTOINCREMENT, arrondissement INTEGER, station_code TEXT, station_nom TEXT, velos_disponibles INTEGER, bornes_libres INTEGER, horodatage TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


@pytest.fixture()
def client():
    """Crée une app FastAPI branchée sur une base SQLite isolée pour chaque test."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def register_now(dbapi_conn, _):
        dbapi_conn.create_function("now", 0, lambda: datetime.datetime.utcnow().isoformat())

    with engine.begin() as conn:
        for stmt in DDL.strip().split(";"):
            if stmt.strip():
                conn.execute(text(stmt))
        conn.execute(text(
            "INSERT INTO indicateurs_socio (arrondissement, population, densite_hab_km2, indice_qualite_air, nb_espaces_verts) "
            "VALUES (1,16000,8500,60,3)"
        ))
        conn.execute(text(
            "INSERT INTO prix_m2_arrondissement (arrondissement, annee, prix_m2_median, variation_pct) "
            "VALUES (1,2024,13700,2.1)"
        ))
        admin_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
        conn.execute(
            text("INSERT INTO users (email, hashed_password, full_name, role) VALUES ('admin@test.fr', :h, 'Admin', 'admin')"),
            {"h": admin_hash},
        )

    import app.db as db_module
    db_module.engine = engine
    db_module.SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    import app.auth as auth_module
    auth_module.engine = engine

    from fastapi.testclient import TestClient
    from app.main import app as fastapi_app

    return TestClient(fastapi_app)


@pytest.fixture()
def admin_token(client):
    r = client.post("/auth/login", json={"email": "admin@test.fr", "password": "admin123"})
    assert r.status_code == 200
    return r.json()["access_token"]


@pytest.fixture()
def client_token(client):
    r = client.post("/auth/register", json={"email": "test@client.fr", "password": "secret123", "full_name": "Test Client"})
    assert r.status_code == 201
    return r.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_and_me(client, client_token):
    r = client.get("/auth/me", headers=auth_header(client_token))
    assert r.status_code == 200
    assert r.json()["role"] == "client"


def test_wrong_password_rejected(client):
    r = client.post("/auth/login", json={"email": "admin@test.fr", "password": "WRONG"})
    assert r.status_code == 401


def test_client_cannot_create_bien(client, client_token):
    r = client.post(
        "/biens",
        json={"titre": "Test", "arrondissement": 1, "type_bien": "T2", "prix": 100000, "surface_m2": 40},
        headers=auth_header(client_token),
    )
    assert r.status_code == 403


def test_admin_can_create_update_delete_bien(client, admin_token):
    r = client.post(
        "/biens",
        json={"titre": "Appart Test", "arrondissement": 1, "type_bien": "T2", "prix": 300000, "surface_m2": 40},
        headers=auth_header(admin_token),
    )
    assert r.status_code == 201
    bien_id = r.json()["id"]

    r = client.put(f"/biens/{bien_id}", json={"statut": "sous_offre"}, headers=auth_header(admin_token))
    assert r.status_code == 200
    assert r.json()["statut"] == "sous_offre"

    r = client.delete(f"/biens/{bien_id}", headers=auth_header(admin_token))
    assert r.status_code == 204


def test_public_can_list_biens(client, admin_token):
    client.post(
        "/biens",
        json={"titre": "Public Test", "arrondissement": 5, "type_bien": "Studio", "prix": 200000, "surface_m2": 22},
        headers=auth_header(admin_token),
    )
    r = client.get("/biens")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_client_favoris_flow(client, admin_token, client_token):
    r = client.post(
        "/biens",
        json={"titre": "Favori Test", "arrondissement": 3, "type_bien": "T3", "prix": 400000, "surface_m2": 60},
        headers=auth_header(admin_token),
    )
    bien_id = r.json()["id"]

    r = client.post(f"/favoris/{bien_id}", headers=auth_header(client_token))
    assert r.status_code == 201

    r = client.get("/favoris", headers=auth_header(client_token))
    assert len(r.json()) == 1

    r = client.delete(f"/favoris/{bien_id}", headers=auth_header(client_token))
    assert r.status_code == 204

    r = client.get("/favoris", headers=auth_header(client_token))
    assert len(r.json()) == 0


def test_admin_only_user_management(client, admin_token, client_token):
    r = client.get("/admin/users", headers=auth_header(client_token))
    assert r.status_code == 403

    r = client.get("/admin/users", headers=auth_header(admin_token))
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_admin_cannot_deactivate_self(client, admin_token):
    r = client.get("/auth/me", headers=auth_header(admin_token))
    admin_id = r.json()["id"]
    r = client.patch(f"/admin/users/{admin_id}/active", json={"is_active": False}, headers=auth_header(admin_token))
    assert r.status_code == 400


def test_existing_data_endpoints_still_work(client):
    r = client.get("/arrondissements")
    assert r.status_code == 200
    r = client.get("/prix?annee=2024")
    assert r.status_code == 200
    r = client.get("/timeline?arr=1")
    assert r.status_code == 200
    r = client.get("/comparaison?arr1=1&arr2=1")
    assert r.status_code == 400  # mêmes arrondissements refusés


def test_geo_arrondissements_fallback_without_minio(client):
    """Sans MinIO disponible (cas de ce test), l'endpoint doit replier sur la
    géométrie de référence plutôt que de planter (résilience, C1.4)."""
    r = client.get("/geo/arrondissements")
    assert r.status_code == 200
    data = r.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 20
    assert data["features"][0]["geometry"]["type"] == "Polygon"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
