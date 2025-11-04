"""
Script para criar a tabela user_settings no banco de dados
Execute: python create_user_settings_table.py
"""
import asyncio
from sqlalchemy import text
from database import AsyncSessionLocal


async def create_user_settings_table():
    """Cria a tabela user_settings no banco de dados"""
    
    async with AsyncSessionLocal() as db:
        try:
            print("🔍 Verificando se a tabela 'user_settings' já existe...")
            
            # Check if table exists
            check_table = text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'user_settings'
                );
            """)
            
            result = await db.execute(check_table)
            table_exists = result.scalar()
            
            if table_exists:
                print("⚠️  A tabela 'user_settings' já existe!")
                return
            
            print("📝 Criando a tabela 'user_settings'...")
            
            # Create table
            create_table = text("""
                CREATE TABLE user_settings (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL UNIQUE,
                    phone VARCHAR(20),
                    notifications JSONB NOT NULL DEFAULT '{}',
                    privacy JSONB NOT NULL DEFAULT '{}',
                    appearance JSONB NOT NULL DEFAULT '{}',
                    security JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP WITH TIME ZONE,
                    CONSTRAINT fk_user_settings_user 
                        FOREIGN KEY (user_id) 
                        REFERENCES users(id) 
                        ON DELETE CASCADE
                );
            """)
            
            await db.execute(create_table)
            
            # Create index on user_id
            create_index = text("""
                CREATE INDEX IF NOT EXISTS ix_user_settings_user_id ON user_settings(user_id);
            """)
            
            await db.execute(create_index)
            
            await db.commit()
            
            print("\n✅ Tabela 'user_settings' criada com sucesso!")
            print("\n📋 Estrutura da tabela:")
            print("   - id: SERIAL PRIMARY KEY")
            print("   - user_id: INTEGER UNIQUE (FK para users)")
            print("   - phone: VARCHAR(20)")
            print("   - notifications: JSONB")
            print("   - privacy: JSONB")
            print("   - appearance: JSONB")
            print("   - security: JSONB")
            print("   - created_at: TIMESTAMP WITH TIME ZONE")
            print("   - updated_at: TIMESTAMP WITH TIME ZONE")
            print("\n🎉 Migration concluída! A tabela 'user_settings' está pronta para uso.")
            
        except Exception as e:
            await db.rollback()
            print(f"❌ Erro ao criar tabela: {e}")
            raise


if __name__ == "__main__":
    print("🚀 Iniciando criação da tabela user_settings...")
    print("-" * 60)
    try:
        asyncio.run(create_user_settings_table())
    except Exception as e:
        print(f"\n❌ Erro durante a execução: {e}")
        print("\n💡 Verifique:")
        print("   1. Se o PostgreSQL está rodando")
        print("   2. Se as credenciais em config.py estão corretas")
        print("   3. Se o banco de dados existe")
        exit(1)

