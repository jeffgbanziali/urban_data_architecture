from typing import Optional

from pydantic import BaseModel, Field


class PrixArrondissement(BaseModel):
    arrondissement: int = Field(..., ge=1, le=20)
    annee: int
    prix_m2_median: float
    variation_pct: Optional[float] = None


class IndicateurSocio(BaseModel):
    arrondissement: int = Field(..., ge=1, le=20)
    # Source : INSEE (communes_insee — data.gouv.fr)
    population: Optional[int] = None
    densite_hab_km2: Optional[int] = None
    # Source : WAQI via DAG realtime_stream (peut être None si pas encore de mesure)
    indice_qualite_air: Optional[float] = None
    # Source : OpenData Paris géocodé (API BAN + point-in-polygon)
    nb_espaces_verts: Optional[int] = None


class TimelinePoint(BaseModel):
    annee: int
    prix_m2_median: float
    variation_pct: Optional[float] = None


class ComparaisonArrondissement(BaseModel):
    arrondissement: int
    timeline: list[TimelinePoint]
    indicateurs: Optional[IndicateurSocio] = None


class ComparaisonResponse(BaseModel):
    arr1: ComparaisonArrondissement
    arr2: ComparaisonArrondissement


class TransactionTempsReel(BaseModel):
    arrondissement: int
    prix_m2: float
    surface_m2: Optional[float] = None
    horodatage: str


# ---------------------------------------------------------------------------
# Authentification & utilisateurs
# ---------------------------------------------------------------------------
class UserRegister(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    full_name: str


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    full_name: str


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    role: str
    is_active: bool


class UserRoleUpdate(BaseModel):
    role: str = Field(..., pattern="^(client|employe|admin)$")


class UserActiveUpdate(BaseModel):
    is_active: bool


# ---------------------------------------------------------------------------
# Biens immobiliers
# ---------------------------------------------------------------------------
class BienCreate(BaseModel):
    titre: str
    description: Optional[str] = None
    arrondissement: int = Field(..., ge=1, le=20)
    type_bien: str = Field(..., pattern="^(Studio|T2|T3|T4|T5\\+|Maison)$")
    prix: float = Field(..., gt=0)
    surface_m2: float = Field(..., gt=0)
    photo_url: Optional[str] = None
    statut: str = Field("disponible", pattern="^(disponible|sous_offre|vendu)$")
    # Attributs variables (ex. {"etage": 3, "ascenseur": true, "jardin_m2": 80}).
    # Stockés en colonne JSONB dans PostgreSQL — flexibilité sans MongoDB.
    caracteristiques: Optional[dict] = Field(default_factory=dict)


class BienUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    arrondissement: Optional[int] = Field(None, ge=1, le=20)
    type_bien: Optional[str] = Field(None, pattern="^(Studio|T2|T3|T4|T5\\+|Maison)$")
    prix: Optional[float] = Field(None, gt=0)
    surface_m2: Optional[float] = Field(None, gt=0)
    photo_url: Optional[str] = None
    statut: Optional[str] = Field(None, pattern="^(disponible|sous_offre|vendu)$")
    caracteristiques: Optional[dict] = None


class BienOut(BaseModel):
    id: int
    titre: str
    description: Optional[str] = None
    arrondissement: int
    type_bien: str
    prix: float
    surface_m2: float
    photo_url: Optional[str] = None
    statut: str
    employe_id: Optional[int] = None
    caracteristiques: Optional[dict] = None


class FavoriOut(BaseModel):
    bien_id: int
