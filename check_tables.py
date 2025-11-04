import asyncio
from database import get_async_session
from sqlalchemy import text

async def check_tables():
    async for db in get_async_session():
        try:
            result = await db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"))
            tables = result.fetchall()
            print('Existing tables:')
            for table in tables:
                print(f'  - {table[0]}')
        except Exception as e:
            print(f'Error: {e}')
        finally:
            break

if __name__ == "__main__":
    asyncio.run(check_tables())