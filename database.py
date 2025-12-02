from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv
import logging

load_dotenv()

# Get database URL from environment variable
# CRITICAL: Never hardcode production credentials. Always use environment variables.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://user:password@localhost:5432/prontivus_clinic"  # Default for local development only
)

# Create async engine
# Determine if we should echo SQL queries (only in development)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ECHO_SQL = (ENVIRONMENT == "development" and DEBUG)

# Connection pool configuration to prevent connection exhaustion
# These settings help prevent intermittent connection failures
POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))  # Number of connections to maintain
MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))  # Additional connections beyond pool_size
POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))  # Seconds to wait for a connection
POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))  # Recycle connections after 1 hour
POOL_PRE_PING = os.getenv("DB_POOL_PRE_PING", "True").lower() == "true"  # Test connections before using

logger = logging.getLogger(__name__)

try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=ECHO_SQL,  # Only echo SQL in development
        future=True,
        pool_pre_ping=POOL_PRE_PING,  # Test connections before using them
        pool_size=POOL_SIZE,  # Number of connections to maintain
        max_overflow=MAX_OVERFLOW,  # Additional connections beyond pool_size
        pool_timeout=POOL_TIMEOUT,  # Seconds to wait for a connection
        pool_recycle=POOL_RECYCLE,  # Recycle connections after this many seconds
        connect_args={
            "server_settings": {
                "application_name": "prontivus_backend",
                "tcp_keepalives_idle": "600",  # Start keepalives after 10 minutes of inactivity
                "tcp_keepalives_interval": "30",  # Send keepalive every 30 seconds
                "tcp_keepalives_count": "3",  # Close connection after 3 failed keepalives
            },
            "command_timeout": 60,  # 60 second timeout for commands
        },
    )
    logger.info(f"Database engine created with pool_size={POOL_SIZE}, max_overflow={MAX_OVERFLOW}")
except Exception as e:
    logger.error(f"Failed to create database engine: {e}", exc_info=True)
    raise

# Create async session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI routes
async def get_db():
    """
    Dependency function to get database session
    Usage in FastAPI routes:
        async def my_route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            # Log database errors for debugging
            logger.error(f"Database error in session: {str(e)}", exc_info=True)
            raise
        finally:
            await session.close()

# Alias for consistency
get_async_session = get_db

