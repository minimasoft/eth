"""LLM provider management API.

Providers are stored in the DB; the read-only ``default`` provider always
reflects the environment.  API keys are never returned to clients — only a
masked preview (first 4 chars + '****').
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from eth_pipeline import providers as provider_svc
from eth_pipeline.api.models import (
    ProviderCreate,
    ProviderItem,
    ProviderItemList,
    ProviderTestResult,
)
from eth_pipeline.llm import test_provider

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Providers"])


@router.get("/api/providers", response_model=ProviderItemList)
async def list_providers() -> ProviderItemList:
    try:
        items = await provider_svc.list_providers()
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to list providers: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to query providers.") from exc
    return ProviderItemList(items=items)


@router.post("/api/providers", response_model=ProviderItem, status_code=201)
async def create_provider(input: ProviderCreate) -> ProviderItem:
    try:
        provider = await provider_svc.add_provider(
            name=input.name,
            model=input.model,
            base_url=input.base_url or None,  # type: ignore[arg-type]
            api_key=input.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to add provider: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to store provider.") from exc
    assert provider is not None  # add_provider always returns the created row
    return ProviderItem(**provider)


@router.delete("/api/providers/{provider_id}", status_code=204)
async def delete_provider(provider_id: str) -> None:
    try:
        deleted = await provider_svc.delete_provider(provider_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to delete provider %s: %s", provider_id, exc)
        raise HTTPException(status_code=502, detail="Failed to delete provider.") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Provider not found.")


@router.post("/api/providers/{provider_id}/test", response_model=ProviderTestResult)
async def test_provider_route(provider_id: str) -> ProviderTestResult:
    try:
        provider = await provider_svc.resolve_provider(provider_id)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to resolve provider %s: %s", provider_id, exc)
        raise HTTPException(status_code=502, detail="Failed to query provider.") from exc

    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found.")

    result = await test_provider(
        model=provider["model"],
        api_key=provider.get("api_key") or None,
        base_url=provider["base_url"],
    )
    return ProviderTestResult(**result, provider_id=provider_id)