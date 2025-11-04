from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment variable
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://prontivus_clinic_user:awysfvJWF0oFBmG7zJDCirqw238MjrmT@dpg-d441bemuk2gs739jnde0-a.oregon-postgres.render.com/prontivus_clinic"
)

# Create async engine
# Determine if we should echo SQL queries (only in development)
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"
ECHO_SQL = (ENVIRONMENT == "development" and DEBUG)

engine = create_async_engine(
    DATABASE_URL,
    echo=ECHO_SQL,  # Only echo SQL in development
    future=True,
    pool_pre_ping=True,
)

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
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Alias for consistency
get_async_session = get_db

