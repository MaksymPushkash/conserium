from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.config import settings
from src.infrastructure.database.services.topic_backfill import SQLAlchemyTopicBackfill


async def main() -> None:
    args = parse_args()
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.DB_CONNECT_TIMEOUT,
            "command_timeout": settings.DB_QUERY_TIMEOUT,
        },
    )
    try:
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            result = await SQLAlchemyTopicBackfill(session).rebuild_missing_topics(limit=args.limit)
            await session.commit()
            print(f"scanned_documents={result.scanned_documents}")
            print(f"updated_documents={result.updated_documents}")
    finally:
        await engine.dispose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill stored topics from existing document tags.")
    parser.add_argument("--limit", type=int, default=1000)
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main())
