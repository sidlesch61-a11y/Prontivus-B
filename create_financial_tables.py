import asyncio
from database import engine
from app.models.financial import ServiceItem, Invoice, InvoiceLine
from app.models import Base

async def create_financial_tables():
    """Create financial tables directly using SQLAlchemy"""
    async with engine.begin() as conn:
        # Create all tables
        await conn.run_sync(Base.metadata.create_all)
        print("✅ Financial tables created successfully!")

if __name__ == "__main__":
    asyncio.run(create_financial_tables())
