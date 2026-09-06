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
        "instruct_temperature": row.get("instruct_temperature"),
        "instruct_top_p": row.get("instruct_top_p"),
        "instruct_top_k": row.get("instruct_top_k"),
        "created_at": row.get("created_at"),
    }


async def list_providers() -> list[dict]:
    async with get_db() as conn:
        rows = await conn.fetch(
            "SELECT id, name, model, base_url, api_key, is_default, "
            "instruct_temperature, instruct_top_p, instruct_top_k, created_at "
            "FROM llm_provider ORDER BY is_default DESC, name ASC"
        )
    return [await _row_to_public(dict(r)) for r in rows]


async def get_provider(provider_id: str) -> dict | None:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, model, base_url, api_key, is_default, "
            "instruct_temperature, instruct_top_p, instruct_top_k, created_at "
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
            "SELECT id, name, model, base_url, api_key, is_default, "
            "instruct_temperature, instruct_top_p, instruct_top_k FROM llm_provider WHERE id = $1",
            provider_id,
        )
    if row is None:
        return None
    return await _effective_provider(dict(row))


async def resolve_provider_by_name(name: str) -> dict | None:
    async with get_db() as conn:
        row = await conn.fetchrow(
            "SELECT id, name, model, base_url, api_key, is_default, "
            "instruct_temperature, instruct_top_p, instruct_top_k FROM llm_provider WHERE name = $1",
            name,
        )
    if row is None:
        return None
    return await _effective_provider(dict(row))


async def add_provider(
    name: str,
    model: str,
    base_url: str,
    api_key: str | None = None,
    instruct_temperature: float | None = None,
    instruct_top_p: float | None = None,
    instruct_top_k: int | None = None,
) -> dict:
    name = (name or "").strip()
    model = (model or "").strip()
    base_url = (base_url or OPENROUTER_BASE_URL).strip()

    if not name:
        raise ValueError("name is required.")
    if not model:
        raise ValueError("model is required.")

    # Instruct sampling validation (T-SK4-02): range-check client-supplied
    # values before they reach the DB. None = use module defaults.
    if instruct_temperature is not None and not (0 <= instruct_temperature <= 2):
        raise ValueError("instruct_temperature must be between 0 and 2.")
    if instruct_top_p is not None and not (0 <= instruct_top_p <= 1):
        raise ValueError("instruct_top_p must be between 0 and 1.")
    if instruct_top_k is not None and instruct_top_k < 1:
        raise ValueError("instruct_top_k must be >= 1.")

    provider_id = str(uuid.uuid4().hex)
    async with get_db() as conn:
        existing = await conn.fetchrow(
            "SELECT id FROM llm_provider WHERE name = $1", name
        )
        if existing:
            raise ValueError(f"A provider named '{name}' already exists.")
        await conn.execute(
            "INSERT INTO llm_provider (id, name, model, base_url, api_key, is_default, "
            "instruct_temperature, instruct_top_p, instruct_top_k) "
            "VALUES ($1, $2, $3, $4, $5, FALSE, $6, $7, $8)",
            provider_id,
            name,
            model,
            base_url,
            (api_key or "").strip() or None,
            instruct_temperature,
            instruct_top_p,
            instruct_top_k,
        )
        # Assign a timeline color right after the provider INSERT succeeds.
        # Failure here must never fail provider creation (assign_free_color
        # already tolerates insert errors; this also guards a pre-0006 DB).
        try:
            await assign_free_color(conn, provider_id)
        except Exception as exc:  # DB degraded mode — non-fatal
            logger.warning(
                "Color assignment skipped for provider %s: %s", provider_id, exc
            )
    return await get_provider(provider_id)  # type: ignore[return-value]


async def assign_free_color(conn, provider_id: str) -> int | None:
    """Assign the lowest free color_index (0..19) to a provider.

    Inserts a ``model_color`` row and returns the assigned index.  If all
    20 palette slots are taken, falls back to a shared slot based on the
    current row count modulo 20.  Returns None if the assignment could not
    be recorded (the caller decides whether that is fatal).
    """
    taken = await conn.fetch("SELECT color_index FROM model_color")
    used = {r["color_index"] for r in taken}
    color_index: int | None = None
    for candidate in range(20):
        if candidate not in used:
            color_index = candidate
            break
    if color_index is None:
        count = await conn.fetchval("SELECT COUNT(*) FROM model_color")
        color_index = count % 20
    try:
        await conn.execute(
            "INSERT INTO model_color (id, provider_id, color_index) "
            "VALUES ($1, $2, $3)",
            uuid.uuid4().hex,
            provider_id,
            color_index,
        )
        return color_index
    except Exception as exc:
        logger.warning(
            "Failed to assign color to provider %s: %s", provider_id, exc
        )
        return None


async def delete_provider(provider_id: str) -> bool:
    """Delete a custom provider. Returns False if it is the default provider.

    No explicit model_color cleanup is needed here: the FK
    (model_color.provider_id → llm_provider.id ON DELETE CASCADE) frees the
    color row automatically. Do not "fix" this by deleting colors manually.
    """
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