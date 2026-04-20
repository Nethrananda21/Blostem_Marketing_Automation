import asyncio
from sqlalchemy import text
from apps.api.app.database import engine


async def reset():
    async with engine.begin() as conn:
        # Get all table names in this DB
        result = await conn.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        )
        tables = [row[0] for row in result]
        print("Tables found:", tables)

        # Disable FK constraints temporarily, wipe everything, re-enable
        await conn.execute(text("SET session_replication_role = replica"))
        for t in tables:
            await conn.execute(text(f"TRUNCATE TABLE \"{t}\" CASCADE"))
            print(f"  Cleared: {t}")
        await conn.execute(text("SET session_replication_role = DEFAULT"))

    print("\nAll data cleared successfully.")


asyncio.run(reset())
