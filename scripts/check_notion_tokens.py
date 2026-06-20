from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.kit.security.fernet_token_cipher import FernetTokenCipher
from src.models.external_connection import ExternalConnectionModel
from src.settings import settings


async def main() -> None:
    cipher = FernetTokenCipher(settings.TOKEN_ENCRYPTION_KEY, key_version=settings.TOKEN_ENCRYPTION_KEY_VERSION)
    engine = create_async_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        connect_args={
            "timeout": settings.DB_CONNECT_TIMEOUT,
            "command_timeout": settings.DB_QUERY_TIMEOUT,
        },
    )
    checked = 0
    invalid: list[str] = []
    legacy: list[str] = []
    try:
        session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as session:
            result = await session.execute(
                select(ExternalConnectionModel).where(ExternalConnectionModel.provider == "notion")
            )
            for connection in result.scalars().all():
                checked += 1
                if not connection.access_token_encrypted.startswith(f"{settings.TOKEN_ENCRYPTION_KEY_VERSION}:"):
                    legacy.append(str(connection.id))
                    continue
                try:
                    cipher.decrypt(connection.access_token_encrypted)
                except ValueError:
                    invalid.append(str(connection.id))
    finally:
        await engine.dispose()

    print(f"checked={checked}")
    print(f"legacy={len(legacy)}")
    print(f"invalid={len(invalid)}")
    if legacy:
        print("legacy_connection_ids=" + ",".join(legacy))
    if invalid:
        print("invalid_connection_ids=" + ",".join(invalid))


if __name__ == "__main__":
    asyncio.run(main())
