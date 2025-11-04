"""Verifica se a tabela tiss_templates foi criada corretamente"""

import asyncio
from sqlalchemy import text
from database import AsyncSessionLocal

async def verify_table():
    async with AsyncSessionLocal() as db:
        try:
            # Verifica se a tabela existe
            result = await db.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'tiss_templates'
                );
            """))
            exists = result.scalar()
            
            if exists:
                print("✅ Tabela 'tiss_templates' existe!")
                
                # Conta templates
                count_result = await db.execute(text("SELECT COUNT(*) FROM tiss_templates"))
                count = count_result.scalar()
                print(f"✅ Total de templates: {count}")
                
                # Verifica estrutura
                columns_result = await db.execute(text("""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = 'tiss_templates'
                    ORDER BY ordinal_position;
                """))
                columns = columns_result.fetchall()
                print("\n📋 Estrutura da tabela:")
                for col in columns:
                    print(f"   - {col[0]}: {col[1]}")
                
                return True
            else:
                print("❌ Tabela 'tiss_templates' NÃO existe!")
                return False
        except Exception as e:
            print(f"❌ Erro ao verificar: {e}")
            return False

if __name__ == "__main__":
    asyncio.run(verify_table())

