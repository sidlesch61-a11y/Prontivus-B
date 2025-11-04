"""
Seed financial data for testing
"""
import asyncio
from decimal import Decimal
from sqlalchemy import select
from database import get_async_session
from app.models import ServiceItem, ServiceCategory, Clinic, User, UserRole

async def seed_financial_data():
    """Seed the database with sample financial data"""
    async for db in get_async_session():
        try:
            # Get the first clinic
            clinic_query = select(Clinic).limit(1)
            clinic_result = await db.execute(clinic_query)
            clinic = clinic_result.scalar_one_or_none()
            
            if not clinic:
                print("No clinic found. Please create a clinic first.")
                return
            
            # Check if service items already exist
            existing_items = await db.execute(select(ServiceItem).filter(ServiceItem.clinic_id == clinic.id))
            if existing_items.scalars().first():
                print("Service items already exist. Skipping seed.")
                return
            
            # Create sample service items
            service_items = [
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Consulta Médica - Clínica Geral",
                    description="Consulta médica de clínica geral",
                    code="0301010010",
                    price=Decimal("150.00"),
                    category=ServiceCategory.CONSULTATION,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Consulta Médica - Cardiologia",
                    description="Consulta médica especializada em cardiologia",
                    code="0301010020",
                    price=Decimal("250.00"),
                    category=ServiceCategory.CONSULTATION,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Eletrocardiograma",
                    description="Exame de eletrocardiograma",
                    code="40301001",
                    price=Decimal("80.00"),
                    category=ServiceCategory.EXAM,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Hemograma Completo",
                    description="Exame de hemograma completo",
                    code="40301002",
                    price=Decimal("45.00"),
                    category=ServiceCategory.EXAM,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Raio-X de Tórax",
                    description="Exame radiológico de tórax",
                    code="40301003",
                    price=Decimal("120.00"),
                    category=ServiceCategory.EXAM,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Ultrassonografia Abdominal",
                    description="Exame de ultrassonografia abdominal",
                    code="40301004",
                    price=Decimal("200.00"),
                    category=ServiceCategory.EXAM,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Curativo Simples",
                    description="Aplicação de curativo simples",
                    code="0301010030",
                    price=Decimal("25.00"),
                    category=ServiceCategory.PROCEDURE,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Sutura Simples",
                    description="Sutura de ferimento simples",
                    code="0301010040",
                    price=Decimal("80.00"),
                    category=ServiceCategory.PROCEDURE,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Vacina Antitetânica",
                    description="Aplicação de vacina antitetânica",
                    code="0301010050",
                    price=Decimal("35.00"),
                    category=ServiceCategory.MEDICATION,
                    is_active=True
                ),
                ServiceItem(
                    clinic_id=clinic.id,
                    name="Atestado Médico",
                    description="Emissão de atestado médico",
                    code="0301010060",
                    price=Decimal("30.00"),
                    category=ServiceCategory.OTHER,
                    is_active=True
                )
            ]
            
            # Add all service items
            for item in service_items:
                db.add(item)
            
            await db.commit()
            print(f"✅ Created {len(service_items)} service items for clinic: {clinic.name}")
            
        except Exception as e:
            print(f"❌ Error seeding financial data: {e}")
            await db.rollback()
        finally:
            break

if __name__ == "__main__":
    asyncio.run(seed_financial_data())
