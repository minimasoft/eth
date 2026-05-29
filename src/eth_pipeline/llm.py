"""
LLM provider abstraction for event extraction.

Defines a ``Protocol``-based interface for LLM providers (``LLMProvider``),
an ``OpenRouterProvider`` that calls the OpenRouter API with structured JSON
output, and a convenience ``extract_events()`` function.

The ``EVENT_EXTRACTION_SCHEMA`` constant holds a strict JSON Schema that
matches the SurrealDB ``event`` table fields (``que_paso``, ``espacio``,
``tiempo``, ``humanos``, ``objetos``) plus a ``references`` array of verbatim
text spans with character offsets.  Every nested object carries
``additionalProperties: false`` for strict-mode compliance with OpenAI- and
OpenRouter-compatible JSON Schema constrained decoding.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JSON Schema for strict-mode structured extraction
# ---------------------------------------------------------------------------

EVENT_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "que_paso": {
                        "type": "string",
                        "description": "Core narrative: what happened (the primary event description)",
                    },
                    "espacio": {
                        "type": "string",
                        "description": "Location or spatial context where the event occurred",
                    },
                    "tiempo": {
                        "type": "string",
                        "description": "Temporal context: when the event occurred (free-form date/time)",
                    },
                    "humanos": {
                        "type": "string",
                        "description": "People or organizations involved in the event",
                    },
                    "objetos": {
                        "type": "string",
                        "description": "Objects, assets, or physical items involved in the event",
                    },
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference_type": {
                                    "type": "string",
                                    "enum": ["espacio", "tiempo", "humanos", "objetos"],
                                    "description": "Which event field this reference supports",
                                },
                                "verbatim_text": {
                                    "type": "string",
                                    "description": "Exact verbatim text as it appears in the source document",
                                },
                                "span_start": {
                                    "type": "integer",
                                    "description": "Character offset (0-based) where the verbatim span begins in the document text",
                                },
                                "span_end": {
                                    "type": "integer",
                                    "description": "Character offset (exclusive) where the verbatim span ends in the document text",
                                },
                            },
                            "required": ["reference_type", "verbatim_text", "span_start", "span_end"],
                            "additionalProperties": False,
                        },
                        "description": "Verbatim text references substantiating each event field",
                    },
                },
                "required": ["que_paso", "references"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "google/gemini-2.0-flash-001"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Protocol for LLM providers that extract structured events from text."""

    async def extract_events(self, text: str) -> dict:
        """Extract structured events from *text*.

        Returns a dict matching ``EVENT_EXTRACTION_SCHEMA`` (top-level key
        ``"events"`` containing a list of event objects with verbatim
        references).
        """
        ...


# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------


class OpenRouterProvider:
    """LLM provider that calls the OpenRouter ``/v1/chat/completions`` API.

    Uses ``httpx.AsyncClient`` per-call (created and closed inside
    ``extract_events``).  The API response is parsed as JSON and validated
    implicitly against ``EVENT_EXTRACTION_SCHEMA`` via the
    ``response_format`` parameter (OpenRouter relays this to the upstream
    model as strict JSON Schema constrained decoding).

    Parameters
    ----------
    api_key:
        OpenRouter API key.
    model:
        Model identifier (e.g. ``"google/gemini-2.0-flash-001"``).
    base_url:
        Base URL for the OpenRouter API.  Defaults to
        ``OPENROUTER_BASE_URL``.

    Raises
    ------
    ValueError
        If *api_key* is empty or ``None``.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        base_url: str = OPENROUTER_BASE_URL,
    ) -> None:
        resolved_key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not resolved_key:
            msg = (
                "OPENROUTER_API_KEY is not set. "
                "Pass api_key explicitly or set the OPENROUTER_API_KEY environment variable."
            )
            raise ValueError(msg)

        self._api_key: str = resolved_key
        self._model: str = model
        self._base_url: str = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def extract_events(self, text: str) -> dict:
        """Call OpenRouter and return parsed JSON matching the extraction schema.

        Parameters
        ----------
        text:
            Raw document text (typically Spanish legal/court document text).

        Returns
        -------
        dict
            Parsed JSON response body matching ``EVENT_EXTRACTION_SCHEMA``.
        """
        payload = self._build_payload(text)

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self._base_url}/v1/chat/completions",
                    headers=self._headers(),
                    json=payload,
                    timeout=120.0,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:500]
                msg = f"OpenRouter API returned HTTP {status}: {body}"
                logger.error("LLM API error [status=%d] [model=%s]", status, self._model)
                raise RuntimeError(msg) from exc
            except httpx.TimeoutException as exc:
                msg = f"OpenRouter API timed out after 120s (model={self._model})"
                logger.error("LLM API timeout [model=%s]", self._model)
                raise TimeoutError(msg) from exc
            except json.JSONDecodeError as exc:
                body = response.text[:500] if response else "(no response)"
                msg = f"OpenRouter returned invalid JSON: {body}"
                logger.error("LLM API invalid JSON [model=%s]", self._model)
                raise RuntimeError(msg) from exc

        return self._parse_choice(data)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, text: str) -> dict:
        return {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Eres un asistente especializado en extraer eventos estructurados "
                        "de documentos legales y judiciales en español. "
                        "Analiza el texto proporcionado e identifica todos los eventos descritos. "
                        "Para cada evento, extrae:\n"
                        "- que_paso: la acción o suceso principal (obligatorio)\n"
                        "- espacio: dónde ocurrió (si está explícito)\n"
                        "- tiempo: cuándo ocurrió (fecha, hora o referencia temporal)\n"
                        "- humanos: personas, organizaciones o entidades involucradas\n"
                        "- objetos: objetos, bienes o activos mencionados\n"
                        "- references: fragmentos textuales literales que respaldan cada campo, "
                        "con tipo de referencia, texto exacto y offsets de caracteres (0-based, exclusive end)\n\n"
                        "Los tipos de referencia pueden ser: espacio, tiempo, humanos, objetos.\n"
                        "Debes incluir al menos una referencia para que_paso (con reference_type 'humanos').\n"
                        "Responde ÚNICAMENTE con el JSON estructurado, sin texto adicional."
                    ),
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "event_extraction",
                    "strict": True,
                    "schema": EVENT_EXTRACTION_SCHEMA,
                },
            },
        }

    @staticmethod
    def _parse_choice(data: dict) -> dict:
        """Extract the parsed JSON content from the OpenAI-format response."""
        choices = data.get("choices", [])
        if not choices:
            msg = f"OpenRouter returned no choices: {json.dumps(data, indent=2)[:500]}"
            logger.error("LLM API empty choices")
            raise RuntimeError(msg)

        content = choices[0].get("message", {}).get("content", "")
        if not content:
            msg = "OpenRouter returned empty content in the first choice"
            logger.error("LLM API empty content")
            raise RuntimeError(msg)

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.error("LLM API response not valid JSON [content=%s]", content[:200])
            msg = f"Model returned non-JSON content: {content[:200]}"
            raise RuntimeError(msg) from exc


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------


async def extract_events(text: str, provider: LLMProvider | None = None) -> dict:
    """Extract structured events from *text* using the given or default provider.

    If *provider* is ``None``, creates an ``OpenRouterProvider`` using the
    ``OPENROUTER_API_KEY`` and ``OPENROUTER_MODEL`` (optional) environment
    variables.

    Parameters
    ----------
    text:
        Raw document text to analyse.
    provider:
        Optional ``LLMProvider`` instance.  Uses ``OpenRouterProvider`` with
        env-var defaults when ``None``.

    Returns
    -------
    dict
        Parsed JSON matching ``EVENT_EXTRACTION_SCHEMA``.
    """
    if provider is not None:
        return await provider.extract_events(text)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        msg = (
            "OPENROUTER_API_KEY is not set. "
            "Either pass a provider explicitly or set the OPENROUTER_API_KEY environment variable."
        )
        raise ValueError(msg)

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    default_provider = OpenRouterProvider(api_key=api_key, model=model)
    return await default_provider.extract_events(text)
