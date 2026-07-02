"""
AgriIntel360 - SQL Models registration and extension
"""

# Import Base first
from api.models.sql.base import Base

# Import all models to register them with Base.metadata
from api.models.sql.user import User
from api.models.sql.files import (
    FileShare, FileAttachment, FileFolder, FileFolderItem, FilePermission, FileActivity
)
from api.models.sql.community import (
    Group, Post, Comment, Reaction, GroupInvitation, GroupJoinRequest
)
from api.models.sql.actors import (
    Actor, ProducteurVegetal, EleveurAnimal, PecheurHalieutique, ExploitantForestier,
    Role, Permission, UserRole, extend_user_model
)
from api.models.sql.agricultural import (
    StagingProduction, StagingWeather, StagingEconomic, MalaboYieldIndicator,
    Country, Crop, Production, Alert
)
from api.models.sql.messaging import (
    Conversation, ConversationParticipant, PrivateMessage
)
from api.models.sql.api_keys import ApiKey
from api.models.sql.indicators import (
    IndicateurValeur, IndicateurVegetal, IndicateurAnimal, IndicateurHalieutique,
    IndicateurForestier, DefinitionIndicateur, SeuilIndicateur, VueIndicateursAgregees
)

from api.models.sql.price_alert import PriceAlert, PriceAlertCondition

# Extend the User model with additional relationships and RBAC methods
extend_user_model()
