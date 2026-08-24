"""Apply SQLite migrations: `python migrate.py` (used by `make migrate`)."""
import asyncio

from app import db


async def main() -> None:
    await db.connect()
    applied = await db.run_migrations()
    print(f"applied migrations: {applied or 'none (up to date)'}")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
