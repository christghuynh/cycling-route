"""Create the database schema. Run once per environment.

Long-lived deployments create tables at startup, but serverless ones should not do schema work
on every cold start, so they set CREATE_TABLES_ON_STARTUP=false and run this instead:

    cd backend
    DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" python -m scripts.init_db
"""

import asyncio
import sys

from app.core.config import get_settings
from app.db.database import create_engine, create_tables


async def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        await create_tables(engine)
    finally:
        await engine.dispose()
    host = settings.database_url.split("@")[-1].split("/")[0]
    print(f"Schema is ready on {host}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:  # noqa: BLE001 - a CLI should fail with a readable message
        print(f"Could not create the schema: {exc}", file=sys.stderr)
        sys.exit(1)
