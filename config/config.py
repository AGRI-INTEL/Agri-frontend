"""
Application configuration using Pydantic Settings
"""

import os
from functools import lru_cache
from typing import List, Optional, Any, Dict
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings"""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    # Project info
    PROJECT_NAME: str = "AgriIntel360"
    VERSION: str = "1.0.0"
    DESCRIPTION: str = "Plateforme Intelligente de Décision Agricole"
    API_V1_STR: str = "/api/v1"

    # Environment
    ENVIRONMENT: str = Field(default="development")
    DEBUG: bool = Field(default=True)

    @validator("DEBUG", pre=True)
    def validate_debug(cls, v: Any, values: Dict[str, Any]) -> bool:
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes")
        return bool(v)

    # Database URLs
    DATABASE_URL: str = Field(
        default="postgresql://postgres:CHANGE_ME@localhost:5432/agriintel360"
    )
    MONGODB_URL: str = Field(
        default="mongodb://admin:CHANGE_ME@localhost:27017/agriintel360"
    )
    REDIS_URL: str = Field(default="redis://:CHANGE_ME@localhost:6379")
    ELASTICSEARCH_URL: str = Field(default="http://localhost:9200")
    MONGODB_ENABLED: bool = True
    ELASTICSEARCH_ENABLED: bool = True
    CLOUDINARY_ENABLED: bool = False
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None
    CLOUDINARY_UPLOAD_FOLDER: str = "agriintel"

    # JWT Settings
    JWT_SECRET_KEY: str = Field(default="CHANGE_ME_openssl_rand_hex_64")
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Security
    BCRYPT_ROUNDS: int = 12
    ALLOWED_HOSTS: List[str] = ["localhost", "127.0.0.1"]

    @validator("ALLOWED_HOSTS", pre=True)
    def assemble_allowed_hosts(cls, v: Any) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        elif isinstance(v, str):
            return [v]
        raise ValueError(v)

    # Default administrator account
    DEFAULT_ADMIN_EMAIL: str = "admin@agri.com"
    DEFAULT_ADMIN_PASSWORD: str = Field(default="CHANGE_ME")
    DEFAULT_ADMIN_USERNAME: str = "admin"
    DEFAULT_ADMIN_FULL_NAME: str = "Administrateur AgriIntel360"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:8000",
        ]
    )

    @validator("BACKEND_CORS_ORIGINS", pre=True)
    def assemble_cors_origins(cls, v: Any) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, list):
            return v
        elif isinstance(v, str):
            # Handle string that starts with '[' (likely JSON-like format)
            return [v]
        raise ValueError(v)

    # File upload
    MAX_FILE_SIZE_MB: int = 100
    UPLOAD_DIR: str = "uploads"
    ALLOWED_FILE_TYPES: List[str] = [
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/csv",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]

    # External API Keys
    OPENWEATHER_API_KEY: Optional[str] = None
    FAO_API_KEY: Optional[str] = None
    WORLD_BANK_API_KEY: Optional[str] = None
    MAPBOX_ACCESS_TOKEN: Optional[str] = None

    # OAuth
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    MICROSOFT_CLIENT_ID: Optional[str] = None
    MICROSOFT_CLIENT_SECRET: Optional[str] = None

    # AI/ML Keys
    OPENAI_API_KEY: Optional[str] = None
    HUGGINGFACE_API_KEY: Optional[str] = None
    LANGCHAIN_API_KEY: Optional[str] = None

    # OpenRouter (Kimi + DeepSeek)
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_BASE_URL: str = "https://openrouter.ai/api/v1"
    KIMI_MODEL: str = "moonshotai/moonshot-v1-8k"
    DEEPSEEK_MODEL: str = "deepseek/deepseek-chat"
    DEEPSEEK_API_KEY: Optional[str] = None
    DEFAULT_LLM_PROVIDER: str = "kimi"  # "kimi" | "deepseek" | "openai"

    # Frontend URL
    FRONTEND_URL: str = Field(default="http://localhost:3000")

    # Email settings (for fastapi-mail)
    MAIL_USERNAME: Optional[str] = None
    MAIL_PASSWORD: Optional[str] = None
    MAIL_FROM: Optional[str] = None
    MAIL_PORT: int = 587
    MAIL_SERVER: Optional[str] = None
    MAIL_STARTTLS: bool = True
    MAIL_SSL_TLS: bool = False

    # SMTP direct (for notifications service)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_TLS: bool = True

    # SMS/Notifications
    TWILIO_ACCOUNT_SID: Optional[str] = None
    TWILIO_AUTH_TOKEN: Optional[str] = None
    TWILIO_PHONE_NUMBER: Optional[str] = None

    # Firebase Cloud Messaging (push notifications)
    FCM_SERVER_KEY: Optional[str] = None

    # Cache TTL (seconds)
    CACHE_TTL_SHORT: int = 300  # 5 minutes
    CACHE_TTL_MEDIUM: int = 3600  # 1 hour
    CACHE_TTL_LONG: int = 86400  # 24 hours

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/agriintel360.log"

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True

    # Pagination
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # ML Model settings
    ML_MODEL_PATH: str = "ml-models"
    MODEL_UPDATE_INTERVAL_HOURS: int = 24

    # Data processing
    DATA_RETENTION_DAYS: int = 365 * 5  # 5 years
    BATCH_SIZE: int = 1000

    @property
    def database_url_async(self) -> str:
        """Get async database URL"""
        return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

    @property
    def database_url_sync(self) -> str:
        """Get sync database URL for Alembic"""
        return self.DATABASE_URL

    @property
    def is_production(self) -> bool:
        """Check if running in production"""
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development"""
        return self.ENVIRONMENT.lower() == "development"

    def get_external_api_config(self) -> Dict[str, Optional[str]]:
        """Get external API configuration"""
        return {
            "openweather": self.OPENWEATHER_API_KEY,
            "fao": self.FAO_API_KEY,
            "world_bank": self.WORLD_BANK_API_KEY,
            "mapbox": self.MAPBOX_ACCESS_TOKEN,
        }

    def get_ai_config(self) -> Dict[str, Optional[str]]:
        """Get AI/ML configuration"""
        return {
            "openai": self.OPENAI_API_KEY,
            "huggingface": self.HUGGINGFACE_API_KEY,
            "langchain": self.LANGCHAIN_API_KEY,
        }

    @property
    def cloudinary_active(self) -> bool:
        """Check if Cloudinary storage is configured and enabled."""
        return bool(
            self.CLOUDINARY_ENABLED
            and self.CLOUDINARY_CLOUD_NAME
            and self.CLOUDINARY_API_KEY
            and self.CLOUDINARY_API_SECRET
        )


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
