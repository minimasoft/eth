"""DB-backed LLM provider registry.

Providers are stored in the ``llm_provider`` table.  A special read-only
``default`` provider is seeded from the environment: its effective model,
base URL and API key always reflect the current environment at call time
(they are *not* stored as authoritative values).  Additional providers can
be added/deleted via the API; API keys are never returned to clients.
"""

from __future__ import annotations

import logging
import os
import uuid

from eth_pipeline.db import get_db
from eth_pipeline.llm import DEFAULT_MODEL, OPENROUTER_BASE_URL

logger = logging.getLogger(__name__)

DEFAULT_PROVIDER_ID = "default"
DEFAULT_PROVIDER_NAME = "default"


def default_provider_model() -> str:
    """Effective model identifier for the default provider (from env)."""
    return os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)


def default_provider_base_url() -> str:
    return os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL)


def default_provider_api_key() -> str | None:
    return os.environ.get("OPENROUTER_API_KEY") or None


def mask_api_key(key: str | None) -> str | None:
    """Return a masked API key: first 4 chars + '****' (or None if empty)."""
    if not key:
        return None
    key = key.strip()
    if len(key) <= 4:
        return key[0] + "****" if key else None
    return key[:4] + "****"


async def seed_default_provider() -> None:
    """Ensure a read-only 'default' provider row exists (created from env)."""
    try:
        async with get_db() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM llm_provider WHERE is_default = TRUE LIMIT 1"
            )
            if row:
                return
            await conn.execute(
                "INSERT INTO llm_provider (id, name, model, base_url, api_key, is_default) "
                "VALUES ($1, $2, $3, $4, $5, TRUE) "
                "ON CONFLICT (id) DO NOTHING",
                DEFAULT_PROVIDER_ID,
                DEFAULT_PROVIDER_NAME,
                default_provider_model(),
                default_provider_base_url(),
                default_provider_api_key(),
            )
            logger.info("Seeded default LLM provider from environment")
    except Exception as exc:  # DB degraded mode — non-fatal
        logger.warning("Failed to seed default LLM provider: %s", exc)


async def _effective_provider(row: dict) -> dict:
    """Return a provider dict; the default provider always reflects env."""
    is_default = bool(row.get("is_default"))
    if is_default:
        row = dict(row)
        row["model"] = default_provider_model()
        row["base_url"] = default_provider_base_url()
        row["api_key"] = default_provider_api_key()
    return row


async def _row_to_public(row: dict) -> dict:
    """Map a DB row to a public (key-hidden) provider dict."""
    row = await _effective_provider(row)
    return {
        "id": row["id"],
        "name": row["name"],
        "model": row["model"],
        "base_url": row["base_url"],
        "is_default": bool(row["is_default"]),
        "api_key_masked": mask_api_key(row.get("api_key")),
        "created_at": row.get("created_at"),
    }


async def list_providers() -> list[dict]:
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT id, name, model, base_url, api_key, is_default, created_at "
            "FROM llm_provider ORDER BY is_default DESC, name ASC"
        )
    return [await _row_to_public(dict(r)) for r in rows]


async def get_provider(provider_id: str) -> dict | None:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, model, base_url, api_key, is_default, created_at "
            "FROM llm_provider WHERE id = $1",
            provider_id,
        )
    if row is None:
        return None
    return await _row_to_public(dict(row))


async def resolve_provider(provider_id: str) -> dict | None:
    """Return a provider with its working credentials (used by the backend only).

    The default provider resolves model/base_url/api_key from the environment.
    """
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, model, base_url, api_key, is_default FROM llm_provider WHERE id = $1",
            provider_id,
        )
    if row is None:
        return None
    return await _effective_provider(dict(row))


async def resolve_provider_by_name(name: str) -> dict | None:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, model, base_url, api_key, is_default FROM llm_provider WHERE name = $1",
            name,
        )
    if row is None:
        return None
    return await _effective_provider(dict(row))


async def add_provider(name: str, model: str, base_url: str, api_key: str | None = None) -> dict:
    name = (name or "").strip()
    model = (model or "").strip()
    base_url = (base_url or OPENROUTER_BASE_URL).strip()

    if not name:
        raise ValueError("name is required.")
    if not model:
        raise ValueError("model is required.")

    provider_id = str(uuid.uuid4().hex)
    async with get_db() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM llm_provider WHERE name = $1", name
        )
        if existing:
            raise ValueError(f"A provider named '{name}' already exists.")
        await conn.execute(
            "INSERT INTO llm_provider (id, name, model, base_url, api_key, is_default) "
            "VALUES ($1, $2, $3, $4, $5, FALSE)",
            provider_id,
            name,
            model,
            base_url,
            (api_key or "").strip() or None,
        )
    return await get_provider(provider_id)  # type: ignore[return-value]


async def delete_provider(provider_id: str) -> bool:
    """Delete a custom provider. Returns False if it is the default provider."""
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, is_default FROM llm_provider WHERE id = $1", provider_id
        )
        if row is None:
            return False
        if row["is_default"]:
            raise ValueError("The default provider cannot be deleted.")
        await conn.execute(
            "DELETE FROM llm_provider WHERE id = $1", provider_id
        )
    return True