"""
Database configuration and connections
"""

import asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch

from config.config import get_settings
from api.models.sql import Base

settings = get_settings()

# Cleaned up duplicate imports or unused parts
# SQLAlchemy (PostgreSQL)
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=300,
)

async_session_maker = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

# Use the models' Base to ensure metadata includes all models
Base = Base

# MongoDB
mongodb_client: AsyncIOMotorClient = None
mongodb_db = None

# Redis
redis_client: aioredis.Redis = None

# Elasticsearch
es_client: AsyncElasticsearch = None


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session"""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_mongodb():
    """Get MongoDB database"""
    return mongodb_db


async def get_redis():
    """Get Redis client"""
    return redis_client


async def get_elasticsearch():
    """Get Elasticsearch client"""
    return es_client


async def create_db_and_tables():
    """Initialize databases and create tables"""
    global mongodb_client, mongodb_db, redis_client, es_client
    
    try:
        # Create PostgreSQL tables
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Ensure the default administrator account exists.
        # Kept after SQL table creation and before external services so the admin
        # account is available even if MongoDB/Redis/Elasticsearch are offline.
        from src.services.admin_seed import ensure_default_admin_user
        await ensure_default_admin_user()
        
        # Initialize MongoDB
        mongodb_client = AsyncIOMotorClient(settings.MONGODB_URL)
        mongodb_db = mongodb_client.get_default_database()
        
        # Test MongoDB connection
        await mongodb_db.command("ping")
        print("✅ MongoDB connected successfully")
        
        # Initialize Redis
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True
        )
        
        # Test Redis connection
        await redis_client.ping()
        print("✅ Redis connected successfully")
        
        # Initialize Elasticsearch
        es_client = AsyncElasticsearch(
            [settings.ELASTICSEARCH_URL],
            verify_certs=False
        )
        
        # Test Elasticsearch connection
        if await es_client.ping():
            print("✅ Elasticsearch connected successfully")
        else:
            print("❌ Elasticsearch connection failed")
            
        print("✅ All databases initialized successfully")
        
    except Exception as e:
        print(f"❌ Database initialization error: {e}")
        raise


async def close_db_connections():
    """Close all database connections"""
    global mongodb_client, redis_client, es_client
    
    try:
        # Close PostgreSQL engine
        await engine.dispose()
        print("✅ PostgreSQL connection closed")
        
        # Close MongoDB
        if mongodb_client:
            mongodb_client.close()
            print("✅ MongoDB connection closed")
        
        # Close Redis
        if redis_client:
            await redis_client.close()
            print("✅ Redis connection closed")
        
        # Close Elasticsearch
        if es_client:
            await es_client.close()
            print("✅ Elasticsearch connection closed")
            
    except Exception as e:
        print(f"❌ Error closing database connections: {e}")


# Database health check functions
async def check_postgres_health() -> bool:
    """Check PostgreSQL health"""
    try:
        async with async_session_maker() as session:
            result = await session.execute("SELECT 1")
            return result.scalar() == 1
    except Exception:
        return False


async def check_mongodb_health() -> bool:
    """Check MongoDB health"""
    try:
        if mongodb_db:
            await mongodb_db.command("ping")
            return True
        return False
    except Exception:
        return False


async def check_redis_health() -> bool:
    """Check Redis health"""
    try:
        if redis_client:
            return await redis_client.ping()
        return False
    except Exception:
        return False


async def check_elasticsearch_health() -> bool:
    """Check Elasticsearch health"""
    try:
        if es_client:
            return await es_client.ping()
        return False
    except Exception:
        return False


async def get_all_health_status() -> dict:
    """Get health status of all databases"""
    return {
        "postgresql": await check_postgres_health(),
        "mongodb": await check_mongodb_health(),
        "redis": await check_redis_health(),
        "elasticsearch": await check_elasticsearch_health()
    }