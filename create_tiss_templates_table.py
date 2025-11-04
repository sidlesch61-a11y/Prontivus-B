"""
Script para criar a tabela tiss_templates manualmente
Execute este script quando o banco de dados estiver disponível
"""

import asyncio
from sqlalchemy import text
from database import get_async_session

async def create_tiss_templates_table():
    """Cria a tabela tiss_templates no banco de dados"""
    
    from database import AsyncSessionLocal
    
    async with AsyncSessionLocal() as db:
        try:
            # Verifica se a tabela já existe
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'tiss_templates'
                );
            """)
            result = await db.execute(check_table)
            table_exists = result.scalar()
            
            if table_exists:
                print("✅ Tabela 'tiss_templates' já existe!")
                return
            
            # Cria o tipo ENUM se não existir
            create_enum = text("""
                DO $$ BEGIN
                    CREATE TYPE tisstemplatecategory AS ENUM ('consultation', 'procedure', 'exam', 'emergency', 'custom');
                EXCEPTION
                    WHEN duplicate_object THEN null;
                END $$;
            """)
            await db.execute(create_enum)
            await db.commit()
            print("✅ Tipo ENUM 'tisstemplatecategory' criado ou já existe")
            
            # Cria a tabela
            create_table = text("""
                CREATE TABLE IF NOT EXISTS tiss_templates (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(200) NOT NULL,
                    description TEXT,
                    category tisstemplatecategory NOT NULL,
                    xml_template TEXT NOT NULL,
                    variables JSONB,
                    is_default BOOLEAN NOT NULL DEFAULT FALSE,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    clinic_id INTEGER NOT NULL REFERENCES clinics(id),
                    created_by_id INTEGER REFERENCES users(id),
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE
                );
            """)
            await db.execute(create_table)
            await db.commit()
            print("✅ Tabela 'tiss_templates' criada com sucesso!")
            
            # Cria os índices
            create_indexes = [
                text("CREATE INDEX IF NOT EXISTS ix_tiss_templates_id ON tiss_templates(id);"),
                text("CREATE INDEX IF NOT EXISTS ix_tiss_templates_name ON tiss_templates(name);"),
                text("CREATE INDEX IF NOT EXISTS ix_tiss_templates_clinic_id ON tiss_templates(clinic_id);"),
            ]
            
            for index_sql in create_indexes:
                await db.execute(index_sql)
            
            await db.commit()
            print("✅ Índices criados com sucesso!")
            
            print("\n🎉 Migration concluída! A tabela 'tiss_templates' está pronta para uso.")
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Erro ao criar tabela: {e}")
            raise

if __name__ == "__main__":
    print("🚀 Iniciando criação da tabela tiss_templates...")
    print("-" * 60)
    try:
        asyncio.run(create_tiss_templates_table())
    except Exception as e:
        print(f"\n❌ Erro durante a execução: {e}")
        print("\n💡 Verifique:")
        print("   1. Se o PostgreSQL está rodando")
        print("   2. Se as credenciais em config.py estão corretas")
        print("   3. Se o banco de dados existe")
        exit(1)

