"""Passcode-based permission levels for mutating and read endpoints.

The app is exposed via a Cloudflare tunnel, so every data-returning
endpoint is gated by passcodes.  Levels:

- ``A``: add providers, send documents
- ``B``: deletes (level A never satisfies B)
- ``C``: read level — required by ALL data-returning GET endpoints
  (documents, events, geo, providers, comparisons); asked once by the
  UI and reused for every read fetch

Only liveness/bootstrap endpoints stay open: ``GET /health`` (docker
healthcheck) and ``GET /api/passcode/check`` (lets the UI validate a C
code before any read is possible).

Passcodes come from the environment (``PASSCODE_A``/``PASSCODE_B``/
``PASSCODE_C``) with hardcoded fallback defaults.  All comparisons are
constant-time and a wrong passcode never reveals level information.
"""

from __future__ import annotations

import functools
import hmac
import inspect
import logging
import os
from typing import Any, Callable, TypeVar

from fastapi import HTTPException, Query

logger = logging.getLogger(__name__)

#: Known permission levels.
LEVELS = ("A", "B", "C")

#: Generic detail shared by every rejection — never leaks level information.
PASSCODE_REQUIRED_DETAIL = "Passcode required."

F = TypeVar("F", bound=Callable[..., Any])


def _expected(level: str) -> str:
    """Read the expected passcode for ``level`` at verify time (not import time)."""
    if level == "A":
        return os.environ.get("PASSCODE_A", "AAAAA")
    if level == "B":
        return os.environ.get("PASSCODE_B", "BBBBB")
    if level == "C":
        return os.environ.get("PASSCODE_C", "CCCCC")
    raise ValueError(f"Unknown passcode level: {level}")


def verify_passcode(code: str, level: str) -> bool:
    """Constant-time check of ``code`` against the expected value for ``level``."""
    if level not in LEVELS:
        return False
    expected = _expected(level)
    return hmac.compare_digest(code.encode("utf-8"), expected.encode("utf-8"))


def resolve_level(code: str) -> str | None:
    """Return the level ("A"/"B"/"C") whose passcode matches ``code``, else None.

    Never raises and never reveals which level a near-miss belonged to.
    """
    for level in LEVELS:
        if verify_passcode(code, level):
            return level
    return None


def require_passcode(level: str) -> Callable[[F], F]:
    """Route decorator enforcing a ``passcode`` query param of the given level.

    The wrapper's signature exposes ``passcode: str = Query(...)`` so FastAPI
    injects it and OpenAPI shows it as an obligatory parameter.  A missing or
    wrong passcode yields a uniform generic 403 — a code valid for another
    level is rejected identically (no level leakage).
    """

    def decorator(func: F) -> F:
        try:
            # Resolve string annotations (from __future__ import annotations)
            # against the ORIGINAL module globals, so FastAPI sees real types.
            sig = inspect.signature(func, eval_str=True)
        except Exception:  # noqa: BLE001 — fall back to raw annotations
            sig = inspect.signature(func)

        passcode_param = inspect.Parameter(
            "passcode",
            inspect.Parameter.KEYWORD_ONLY,
            default=Query(...),
            annotation=str,
        )
        params = [*sig.parameters.values(), passcode_param]

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            code = kwargs.pop("passcode", "") or ""
            if not code or not verify_passcode(code, level):
                raise HTTPException(status_code=403, detail=PASSCODE_REQUIRED_DETAIL)
            return await func(*args, **kwargs)

        wrapper.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
        return wrapper  # type: ignore[return-value]

    return decorator
