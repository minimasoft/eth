from __future__ import annotations

import asyncio
import logging
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from eth_pipeline.models.v7_event import Base

logger = logging.getLogger(__name__)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_dsn(alembic_url: str) -> str:
    defaults = {
        "PGUSER": "eth",
        "PGPASSWORD": "eth",
        "PGHOST": "localhost",
        "PGPORT": "5432",
        "PGDATABASE": "eth",
    }
    resolved = alembic_url
    for key, default in defaults.items():
        resolved = resolved.replace(f"${{{key}}}", os.environ.get(key, default))
    return resolved


def run_migrations_offline() -> None:
    url = _resolve_dsn(config.get_main_option("sqlalchemy.url"))
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = _resolve_dsn(config.get_main_option("sqlalchemy.url"))
    connectable = create_async_engine(url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
