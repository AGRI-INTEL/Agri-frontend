"""
Schemas Pydantic pour les acteurs agricoles
"""

from typing import Optional, List, Any
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from enum import Enum

class SousSecteursEnum(str, Enum):
    VEGETAL = "vegetal"
    ANIMAL = "animal"
    HALIEUTIQUE = "halieutique"
    FORESTIER = "forestier"

class ActorRoleEnum(str, Enum):
    PRODUCTEUR_INDIVIDUEL = "producteur_individuel"
    EXPLOITATION_FAMILIALE = "exploitation_familiale"
    COOPERATIVE_AGRICOLE = "cooperative_agricole"
    TRANSFORMATEUR_ARTISANAL = "transformateur_artisanal"
    TRANSFORMATEUR_SEMI_INDUSTRIEL = "transformateur_semi_industriel"
    COLLECTEUR = "collecteur"
    COMMERCANT = "commercant"
    # ... (other roles can be added as needed or use string)

class ActorBase(BaseModel):
    nom: str
    prenom: Optional[str] = None
    nom_organisation: Optional[str] = None
    sous_secteur: SousSecteursEnum
    role: str
    telephone: Optional[str] = None
    email: Optional[EmailStr] = None
    adresse: Optional[str] = None
    pays: str = "Sénégal"
    region: Optional[str] = None
    departement: Optional[str] = None
    commune: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    age: Optional[int] = None
    genre: Optional[str] = None
    is_active: bool = True
    metadonnees_specifiques: Optional[dict] = None

class ActorCreate(ActorBase):
    pass

class ActorUpdate(BaseModel):
    nom: Optional[str] = None
    prenom: Optional[str] = None
    nom_organisation: Optional[str] = None
    sous_secteur: Optional[SousSecteursEnum] = None
    role: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[EmailStr] = None
    adresse: Optional[str] = None
    pays: Optional[str] = None
    region: Optional[str] = None
    departement: Optional[str] = None
    commune: Optional[str] = None
    village: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    is_active: Optional[bool] = None

class ActorResponse(ActorBase):
    id: UUID
    is_verified: bool
    created_at: datetime
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class ActorListResponse(BaseModel):
    data: List[ActorResponse]
    total: int
    page: int
    per_page: int
    pages: int
