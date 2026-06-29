"""
Database configuration and connections
"""

import asyncio
import logging
from typing import AsyncGenerator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import inspect as sa_inspect, text
from sqlalchemy.orm import declarative_base
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aioredis
from elasticsearch import AsyncElasticsearch

from config.config import get_settings
from api.models.sql import Base

settings = get_settings()
logger = logging.getLogger(__name__)

# Cleaned up duplicate imports or unused parts
# SQLAlchemy (PostgreSQL)
engine = create_async_engine(
    settings.database_url_async,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={"timeout": 5},
    pool_timeout=5,
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

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


async def _add_missing_columns() -> None:
    """Ensure every column declared on a model exists in the live database.

    ``Base.metadata.create_all`` only creates tables that are missing; it does not
    add new columns to tables that already exist. This routine inspects the
    database schema, compares it against ``Base.metadata`` and issues
    ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS`` statements for the missing ones
    so the application stays in sync with model definitions across redeployments.
    """

    def _sync_add_missing_columns(sync_conn) -> None:
        def _resolve_default(column) -> str:
            if column.server_default is not None and hasattr(column.server_default, "arg"):
                arg = column.server_default.arg
                if isinstance(arg, str):
                    stripped = arg.strip()
                    if stripped.startswith(":"):
                        return ""
                    if "(" in stripped or stripped.startswith("'"):
                        return f" DEFAULT {stripped}"
                    if stripped.upper() in ("TRUE", "FALSE"):
                        return f" DEFAULT {stripped}"
                    if stripped.lstrip("-").replace(".", "", 1).isdigit():
                        return f" DEFAULT {stripped}"
                    return f" DEFAULT '{stripped}'"
                if hasattr(arg, "compile"):
                    compiled = arg.compile(
                        dialect=sync_conn.dialect,
                        compile_kwargs={"literal_binds": True},
                    )
                    return f" DEFAULT {compiled}"
                return f" DEFAULT {arg}"
            if column.default is not None:
                val = column.default.arg if hasattr(column.default, 'arg') else column.default
                if val is None:
                    return ""
                if isinstance(val, bool):
                    return f" DEFAULT {'TRUE' if val else 'FALSE'}"
                if isinstance(val, int):
                    return f" DEFAULT {val}"
                if isinstance(val, str):
                    return f" DEFAULT '{val}'"
            if not column.nullable:
                coltype = str(column.type).lower()
                if "boolean" in coltype or "bool" in coltype:
                    return " DEFAULT FALSE"
                if "integer" in coltype or "int" in coltype or "numeric" in coltype or "float" in coltype or "double" in coltype:
                    return " DEFAULT 0"
                if "varchar" in coltype or "text" in coltype or "char" in coltype:
                    return " DEFAULT ''"
            return ""

        inspector = sa_inspect(sync_conn)
        for table_name, table in Base.metadata.tables.items():
            if not inspector.has_table(table_name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table_name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                col_type = column.type.compile(dialect=sync_conn.dialect)
                nullable = "NULL" if column.nullable else "NOT NULL"
                default_clause = _resolve_default(column)
                quoted_name = f'"{column.name}"'
                stmt = (
                    f'ALTER TABLE "{table_name}" '
                    f"ADD COLUMN IF NOT EXISTS {quoted_name} {col_type}{default_clause} {nullable}"
                )
                logger.info(
                    "Schema sync: adding missing column %s.%s", table_name, column.name
                )
                try:
                    sync_conn.execute(text("SAVEPOINT _col_sync"))
                    sync_conn.execute(text(stmt))
                    sync_conn.execute(text("RELEASE SAVEPOINT _col_sync"))
                except Exception as col_exc:
                    sync_conn.execute(text("ROLLBACK TO SAVEPOINT _col_sync"))
                    logger.warning(
                        "Schema sync: could not add column %s.%s: %s",
                        table_name, column.name, col_exc,
                    )

    async with engine.begin() as conn:
        await conn.run_sync(_sync_add_missing_columns)


async def _run_alembic_upgrade() -> None:
    """Apply any pending Alembic migrations at startup.

    Wrapped in its own helper so it can be called from ``create_db_and_tables``
    without leaking the Alembic dependency into the rest of the module.
    """
    try:
        from alembic import command
        from alembic.config import Config as AlembicConfig

        cfg = AlembicConfig("alembic.ini")
        cfg.set_main_option("script_location", "migrations")
        # configparser treats % as an interpolation prefix; escape it so literal
        # percent-encoded chars in the password (e.g. %3F, %24) are preserved.
        cfg.set_main_option("sqlalchemy.url", settings.database_url_sync.replace("%", "%%"))

        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, command.upgrade, cfg, "head"),
                timeout=30.0,
            )
            logger.info("Alembic migrations applied successfully")
        except asyncio.TimeoutError:
            logger.warning("Alembic upgrade timed out (>30s) — skipping")
    except Exception as exc:  # pragma: no cover - defensive guard
        # Migrations are best-effort: the programmatic column check below will
        # cover the most common case (new columns on existing tables) so the
        # app can still boot even if Alembic cannot be invoked (e.g. when the
        # backend is started outside the project root).
        logger.warning("Alembic upgrade skipped: %s", exc)


async def create_db_and_tables():
    """Initialize databases and create tables"""
    global mongodb_client, mongodb_db, redis_client, es_client

    try:
        # Apply any pending Alembic migrations first so the schema is always
        # aligned with ``migrations/versions``. This is the canonical way to
        # update the database, but it is followed by a defensive column check
        # (see ``_add_missing_columns``) in case Alembic cannot run for any
        # reason (e.g. running the app from outside the project root).
        await _run_alembic_upgrade()

        # Create PostgreSQL tables (only creates missing tables, not missing
        # columns on existing ones).
        async with engine.begin() as conn:
            try:
                await conn.run_sync(Base.metadata.create_all)
            except IntegrityError as ie:
                # Ignore duplicate enum type creation errors when the database
                # already contains the type and the rest of the schema is present.
                if "pg_type_typname_nsp_index" in str(ie.orig):
                    logger.warning("SQLAlchemy enum type already exists; continuing database initialization.")
                else:
                    raise

        # Ensure every column declared on a model also exists in the database.
        # This is the safety net that resolves the ``column users.cover_url
        # does not exist`` error raised when a new column is added to a model
        # but the table was created by an older migration.
        await _add_missing_columns()

        # Ensure the default administrator account exists.
        # Kept after SQL table creation and before external services so the admin
        # account is available even if MongoDB/Redis/Elasticsearch are offline.
        from src.services.admin_seed import ensure_default_admin_user

        await ensure_default_admin_user()

        # Initialize MongoDB if enabled
        if settings.MONGODB_ENABLED and settings.MONGODB_URL:
            try:
                mongodb_client = AsyncIOMotorClient(settings.MONGODB_URL)
                mongodb_db = mongodb_client.get_default_database()
                await mongodb_db.command("ping")
                print("✅ MongoDB connected successfully")
            except Exception as mongo_exc:
                print("⚠️ MongoDB initialization skipped or failed: %s", mongo_exc)
                mongodb_client = None
                mongodb_db = None
        else:
            print("⚠️ MongoDB is disabled or no URL configured; skipping MongoDB initialization.")

        # Initialize Redis (non-fatal — app runs without Redis)
        if settings.REDIS_URL:
            try:
                redis_client = aioredis.from_url(
                    settings.REDIS_URL, encoding="utf-8", decode_responses=True
                )
                await redis_client.ping()
                print("✅ Redis connected successfully")
            except Exception as redis_exc:
                print("⚠️ Redis initialization skipped or failed: %s", redis_exc)
                redis_client = None
        else:
            print("⚠️ Redis URL not configured; continuing without Redis.")

        # Initialize Elasticsearch if enabled
        if settings.ELASTICSEARCH_ENABLED and settings.ELASTICSEARCH_URL:
            try:
                es_client = AsyncElasticsearch(
                    [settings.ELASTICSEARCH_URL]
                )

                if await es_client.ping():
                    print("✅ Elasticsearch connected successfully")
                else:
                    print("❌ Elasticsearch connection failed")
                    es_client = None
            except Exception as es_exc:
                print("⚠️ Elasticsearch initialization skipped or failed: %s", es_exc)
                es_client = None
        else:
            print("⚠️ Elasticsearch is disabled or no URL configured; skipping Elasticsearch initialization.")

        print("✅ All databases initialized successfully")

    except Exception as e:
        print("⚠️ Database initialization error (non-fatal): %s", e)


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
            result = await session.execute(text("SELECT 1"))
            return result.scalar() == 1
    except Exception:
        return False


async def check_mongodb_health() -> bool:
    """Check MongoDB health"""
    try:
        if mongodb_client is not None:
            await mongodb_client.admin.command("ping")
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
        "elasticsearch": await check_elasticsearch_health(),
    }
