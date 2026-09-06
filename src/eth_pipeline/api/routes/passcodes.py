"""Passcode check API (D-03).

Validates a passcode and returns its level.  A wrong passcode yields a
generic 401 with no level information.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from eth_pipeline.passcodes import resolve_level

router = APIRouter(tags=["Passcodes"])


@router.get("/api/passcode/check")
async def check_passcode(passcode: str = Query(...)) -> dict[str, str]:
    level = resolve_level(passcode)
    if level is None:
        raise HTTPException(status_code=401, detail="Invalid passcode.")
    return {"level": level}
