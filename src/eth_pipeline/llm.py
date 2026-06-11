"""
LLM provider abstraction for event extraction and entity resolution.

Defines a ``Protocol``-based interface for LLM providers (``LLMProvider``),
an ``OpenRouterProvider`` that calls the OpenRouter API with structured JSON
output, and convenience functions ``extract_events()`` and
``resolve_references()``.

The ``EVENT_EXTRACTION_SCHEMA`` constant holds a strict JSON Schema that
matches the SurrealDB ``event`` table fields (``que_paso``, ``espacio``,
``tiempo``, ``humanos``, ``objetos``) plus a ``references`` array of verbatim
text spans with character offsets.  Every nested object carries
``additionalProperties: false`` for strict-mode compliance with OpenAI- and
OpenRouter-compatible JSON Schema constrained decoding.

The ``ENTITY_RESOLUTION_SCHEMA`` and ``ENTITY_RESOLUTION_SYSTEM_PROMPT``
support the entity resolution activity, resolving verbatim references
against existing canonical entities or creating new ones.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
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
                        "description": "Location or spatial context where the event occurred (free-form)",
                    },
                    "tiempo": {
                        "type": "string",
                        "description": "Temporal context: when the event occurred (free-form date/time)",
                    },
                    "humanos": {
                        "type": "string",
                        "description": "People or organizations involved in the event (free-form)",
                    },
                    "objetos": {
                        "type": "string",
                        "description": "Objects, assets, or physical items involved in the event (free-form)",
                    },
                    "date_start": {
                        "type": "string",
                        "description": "ISO 8601 datetime when the event started (e.g. '2024-01-12T00:00:00Z'). Omit if unclear.",
                    },
                    "date_end": {
                        "type": "string",
                        "description": "ISO 8601 datetime when the event ended (e.g. '2024-01-12T23:59:59Z'). Omit if unclear.",
                    },
                    "date_precision": {
                        "type": "string",
                        "enum": ["day", "month", "year"],
                        "description": "Precision of the extracted dates: day (exact date), month (only month known), year (only year known). Omit alongside date_start.",
                    },
                    "location": {
                        "type": "object",
                        "properties": {
                            "verbatim_text": {
                                "type": "string",
                                "description": "Verbatim text from the document describing the location",
                            },
                            "place_name": {
                                "type": "string",
                                "description": "Inferred canonical place name (e.g. 'Apple Store Nueva York'), cleaned from the verbatim text",
                            },
                            "lat": {
                                "type": "number",
                                "description": "Latitude if inferrable from context, otherwise omit",
                            },
                            "lon": {
                                "type": "number",
                                "description": "Longitude if inferrable from context, otherwise omit",
                            },
                        },
                        "required": ["verbatim_text", "place_name"],
                        "additionalProperties": False,
                        "description": "Structured location data for the event (optional — omit if no clear location)",
                    },
                    "participants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {
                                    "type": "string",
                                    "description": "Canonical name of the participant person",
                                },
                                "role": {
                                    "type": "string",
                                    "enum": ["subject", "object", "witness"],
                                    "description": "Role in the event: subject (active doer), object (recipient), witness (observer)",
                                },
                            },
                            "required": ["name", "role"],
                            "additionalProperties": False,
                        },
                        "description": "Structured participant data — one entry per person involved (optional)",
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
                                "element_field": {
                                    "type": "string",
                                    "enum": ["tiempo", "humanos", "espacio", "objetos"],
                                    "description": "Specific event element this reference substantiates: tiempo (time), humanos (participants), espacio (location), objetos (objects)",
                                },
                            },
                            "required": ["reference_type", "verbatim_text", "span_start", "span_end"],
                            "additionalProperties": False,
                        },
                        "description": "Verbatim text references substantiating each event field. No cap — include ALL relevant references.",
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
# JSON Schema for strict-mode entity resolution
# ---------------------------------------------------------------------------

ENTITY_RESOLUTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Inferred canonical name of the entity (e.g. 'Juzgado de Primera Instancia', 'María González')",
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ["place", "person", "object"],
                        "description": "Type of entity: place (location), person (individual/organization), object (thing)",
                    },
                    "verbatim_texts": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "The verbatim_text values of all references that belong to this entity group",
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                        "description": "Confidence that these references form a coherent entity (0.0 uncertain, 1.0 certain)",
                    },
                },
                "required": ["entity_name", "entity_type", "verbatim_texts"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["groups"],
    "additionalProperties": False,
}

ENTITY_RESOLUTION_SYSTEM_PROMPT: str = (
    "Eres un asistente especializado en agrupar referencias textuales extraídas "
    "de documentos legales y judiciales en español en entidades canónicas.\n\n"
    "Se te proporcionará una lista de referencias textuales (fragmentos literales "
    "extraídos del documento). Tu tarea es:\n\n"
    "1. IDENTIFICAR qué referencias se refieren a la MISMA entidad (misma persona, "
    "mismo lugar, mismo objeto). Las referencias pueden usar distintas palabras "
    "para referirse al mismo concepto (ej. 'el juzgado', 'Juzgado de Primera "
    "Instancia', 'este tribunal' → todas refieren al mismo lugar).\n"
    "2. AGRUPAR las referencias que corresponden a la misma entidad bajo un único "
    "nombre canónico.\n"
    "3. INFERIR el tipo de entidad (place/person/object) basado en el contexto "
    "de las referencias.\n\n"
    "IMPORTANTE:\n"
    "- No incluyas el texto de la referencia como nombre de entidad. Infiere un "
    "nombre canónico apropiado.\n"
    "- Si todas las referencias son claramente independientes (cada una se refiere "
    "a una entidad diferente), crea un grupo separado para cada una.\n"
    "- Si hay demasiadas referencias para agrupar (más de ~50), sé conservador: "
    "agrupa solo las que están claramente relacionadas deja el resto como grupos "
    "individuales.\n"
    "- No crees grupos de entidades genéricas o de relleno. Si una referencia "
    "es demasiado genérica (ej. 'el día', 'la noche'), inclúyela en el grupo "
    "más relevante o créala como grupo individual.\n\n"
    "Responde ÚNICAMENTE con el JSON estructurado, sin texto adicional."
)

# ---------------------------------------------------------------------------
# JSON Schema for v7 structured extraction (Phase 35)
# ---------------------------------------------------------------------------

EVENT_EXTRACTION_SCHEMA_V7: dict = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title summarizing the event (e.g., 'Firma del contrato', 'Declaración del testigo')",
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed description of what happened — the core narrative",
                    },
                    "time_start": {
                        "type": "string",
                        "description": "ISO 8601 datetime when the event started. Omit if unclear.",
                    },
                    "time_end": {
                        "type": "string",
                        "description": "ISO 8601 datetime when the event ended. Omit if unclear.",
                    },
                    "time_precision": {
                        "type": "string",
                        "enum": ["day", "month", "year"],
                        "description": "Precision of extracted dates. Omit alongside time_start.",
                    },
                    "location": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Canonical place name"},
                            "location_type": {"type": "string", "description": "e.g., 'city', 'building', 'region'"},
                        },
                        "required": ["name"],
                        "additionalProperties": False,
                        "description": "Structured location data. Omit if no clear location.",
                    },
                    "participants": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string", "description": "Canonical name of participant"},
                                "role": {
                                    "type": "string",
                                    "enum": ["subject", "object", "witness"],
                                },
                            },
                            "required": ["name", "role"],
                            "additionalProperties": False,
                        },
                        "description": "People involved in the event. One entry per person.",
                    },
                    "references": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "reference_type": {
                                    "type": "string",
                                    "enum": ["location", "participant", "time", "description"],
                                    "description": "Which event field this reference substantiates",
                                },
                                "verbatim_text": {
                                    "type": "string",
                                    "description": "EXACT verbatim text as it appears in the document — do NOT normalize or correct",
                                },
                                "span_start": {
                                    "type": "integer",
                                    "description": "0-based character offset where this span begins in the chunk text",
                                },
                                "span_end": {
                                    "type": "integer",
                                    "description": "Exclusive character offset where this span ends in the chunk text",
                                },
                            },
                            "required": ["reference_type", "verbatim_text", "span_start", "span_end"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "description", "references"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["events"],
    "additionalProperties": False,
}

EVENT_EXTRACTION_V7_SYSTEM_PROMPT: str = (
    "Eres un asistente de investigación especializado en la extracción de información "
    "estructurada de documentos históricos, legales y de derechos humanos en español. "
    "Tu función es analizar documentos que pueden contener descripciones de violaciones "
    "de derechos humanos, conflictos armados, o abusos — con el propósito legítimo de "
    "documentación histórica, investigación académica, y preservación de la memoria.\n\n"
    "Este es un proyecto de investigación académica sobre derechos humanos. Los documentos "
    "que procesas son archivos históricos. Tu tarea es extraer hechos objetivos: qué pasó, "
    "dónde, cuándo, y quiénes estuvieron involucrados. No estás evaluando, juzgando ni "
    "promoviendo ningún contenido — solo extrayendo datos estructurados para investigación.\n\n"
    "IMPORTANTE: Este trabajo está amparado por fines de investigación académica y "
    "documentación histórica. No debes rechazar el análisis de ningún documento por su "
    "contenido — tu función es exclusivamente extractiva y académica.\n\n"
    "Instrucción específica de extracción: Extrae eventos y crímenes específicos descritos "
    "literalmente en el texto — cada incidente, violación, ataque, detención, desaparición, "
    "u otro hecho con entidad propia debe convertirse en un evento separado. No resumas, no "
    "generalices. Si el texto describe múltiples incidentes distintos, cada uno debe ser su "
    "propio objeto en la lista 'events'. El título del evento debe reflejar directamente el "
    "hecho descrito (ej. 'Detención de Juan Pérez el 15 de marzo' no 'Hechos de violencia').\n\n"
    "NOTA sobre artefactos de OCR: El texto que analizas proviene de reconocimiento óptico "
    "de caracteres (OCR) sobre documentos escaneados. Puede contener caracteres extraviados, "
    "palabras mal reconocidas, saltos de línea incorrectos, o fragmentos de formato. Extrae "
    "la información disponible incluso si el texto circundante tiene errores de OCR. No "
    "inventes ni corrijas información que no esté claramente presente en el texto original.\n\n"
    "AVISO: Esta es una extracción automatizada de datos para fines de investigación "
    "académica y documentación histórica. Los datos extraídos no constituyen asesoría "
    "legal ni tienen validez jurídica vinculante. Este proyecto no tiene fines de lucro "
    "ni objetivos político-partidistas — su único propósito es la preservación de la "
    "memoria histórica y la facilitación de investigación académica sobre derechos humanos."
)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "deepseek/deepseek-v4-flash"
OPENROUTER_BASE_URL = "https://openrouter.ai"

# Target characters of document text per extraction chunk.  Each chunk is
# sent to the LLM sequentially with already-extracted events as context,
# so the model finds NEW events per chunk without exceeding the context
# window.  ~100K tokens of text at ~4 chars/token for Spanish.
EXTRACTION_CHUNK_SIZE = 400_000

# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class LLMProvider(Protocol):
    """Protocol for LLM providers that extract structured events from text."""

    async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
        """Extract structured events from *text*.

        When *prior_events* is provided, the model is instructed to find
        NEW events not already present in the prior list — enabling
        sequential chunk-by-chunk processing of large documents.

        Returns
        -------
        tuple[dict, dict | None]
            (parsed JSON matching ``EVENT_EXTRACTION_SCHEMA``, usage dict from OpenRouter response or None).
        """
        ...

    async def resolve_references(
        self,
        references: list[dict],
    ) -> tuple[dict, dict | None]:
        """Group verbatim references into canonical entities.

        Takes a list of reference dicts (each with ``verbatim_text``,
        ``reference_type``) and returns entity groupings. The LLM's job
        is to group references that refer to the same entity and infer
        the entity name and type.

        Returns
        -------
        tuple[dict, dict | None]
            (parsed JSON matching ``ENTITY_RESOLUTION_SCHEMA``, usage dict from OpenRouter response or None).
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

    async def extract_events(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
        """Call OpenRouter and return parsed JSON matching the extraction schema.

        Parameters
        ----------
        text:
            Raw document text (typically Spanish legal/court document text).
        prior_events:
            Events already extracted from earlier chunks.  When provided, the
            prompt instructs the model to find ONLY events not in this list.

        Returns
        -------
        tuple[dict, dict | None]
            (parsed JSON response body matching ``EVENT_EXTRACTION_SCHEMA``, usage dict from OpenRouter response or None).
        """
        payload = self._build_payload(text, prior_events)
        url = f"{self._base_url}/api/v1/chat/completions"
        headers = self._headers()

        logger.info(
            "LLM request [model=%s] [url=%s] [payload_keys=%s] [text_length=%d]",
            self._model,
            url,
            list(payload.keys()),
            len(text),
        )
        logger.debug("LLM request payload: %s", json.dumps(payload, indent=2, ensure_ascii=False)[:2000])
        logger.debug("LLM request headers (key suffix): ...%s", headers.get("Authorization", "")[-8:])

        start = time.monotonic()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=555.0,
                )
                if not response.is_success:
                    logger.warning(
                        "LLM API non-200 [status=%d] [response_body=%s]",
                        response.status_code,
                        response.text[:1000],
                    )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:1000]
                logger.error(
                    "LLM API error [status=%d] [model=%s] [url=%s] "
                    "[request_body=%s] [response_body=%s]",
                    status,
                    self._model,
                    url,
                    json.dumps(payload, indent=2, ensure_ascii=False)[:1000],
                    body,
                )
                msg = f"OpenRouter API returned HTTP {status}: {body}"
                raise RuntimeError(msg) from exc
            except httpx.TimeoutException as exc:
                msg = f"OpenRouter API timed out after 555s (model={self._model})"
                logger.error("LLM API timeout [model=%s]", self._model)
                raise TimeoutError(msg) from exc
            except json.JSONDecodeError as exc:
                body = response.text[:1000] if response else "(no response)"
                msg = f"OpenRouter returned invalid JSON: {body}"
                logger.error("LLM API invalid JSON [model=%s] [body=%s]", self._model, body)
                raise RuntimeError(msg) from exc
            except httpx.RequestError as exc:
                msg = f"LLM API request failed [model={self._model}] [error={exc}]"
                logger.error(msg)
                raise RuntimeError(msg) from exc
            except asyncio.CancelledError:
                logger.warning("LLM API call cancelled [model=%s] [url=%s]", self._model, url)
                raise

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "LLM request succeeded [model=%s] [response_keys=%s] [duration_ms=%d]",
            self._model,
            list(data.keys()),
            duration_ms,
        )

        usage_raw: dict | None = data.get("usage")
        usage: dict | None = None
        if isinstance(usage_raw, dict):
            choices = data.get("choices", [])
            response_text = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = {
                "prompt_tokens": usage_raw.get("prompt_tokens", 0),
                "completion_tokens": usage_raw.get("completion_tokens", 0),
                "total_tokens": usage_raw.get("total_tokens", 0),
                "cached_tokens": usage_raw.get("cached_tokens"),
                "cache_write_tokens": usage_raw.get("cache_write_tokens"),
                "reasoning_tokens": usage_raw.get("reasoning_tokens"),
                "model": data.get("model", self._model),
                "cost": usage_raw.get("cost"),
                "duration_ms": duration_ms,
                "prompt_text": payload["messages"][-1]["content"],
                "response_text": response_text,
            }
            if usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0 and usage["total_tokens"] > 0:
                logger.info(
                    "Captured LLM usage [model=%s] [prompt=%d] [completion=%d]",
                    usage["model"], usage["prompt_tokens"], usage["completion_tokens"],
                )
            else:
                logger.warning(
                    "LLM response has zero tokens — usage data may be incomplete [usage=%s]",
                    usage,
                )
                usage = None

        return self._parse_choice(data), usage

    async def resolve_references(
        self,
        references: list[dict],
    ) -> tuple[dict, dict | None]:
        """Group verbatim references into canonical entities via LLM.

        Builds a user prompt that includes only the reference verbatim_texts
        (no document context), then calls OpenRouter with
        ``ENTITY_RESOLUTION_SCHEMA`` as the response format. The LLM groups
        references that refer to the same entity and infers entity names/types.
        DB-side deduplication is handled by the caller.

        Parameters
        ----------
        references:
            List of reference dicts (each with ``verbatim_text``,
            ``reference_type``, etc.) to group into entities.

        Returns
        -------
        tuple[dict, dict | None]
            (parsed JSON response body matching ``ENTITY_RESOLUTION_SCHEMA``, usage dict from OpenRouter response or None).
        """
        payload = self._build_resolution_payload(references)
        url = f"{self._base_url}/api/v1/chat/completions"
        headers = self._headers()

        logger.info(
            "LLM resolution request [model=%s] [url=%s] [ref_count=%d]",
            self._model,
            url,
            len(references),
        )
        logger.debug("LLM resolution payload: %s", json.dumps(payload, indent=2, ensure_ascii=False)[:2000])
        logger.debug("LLM resolution headers (key suffix): ...%s", headers.get("Authorization", "")[-8:])

        start = time.monotonic()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=555.0,
                )
                if not response.is_success:
                    logger.warning(
                        "LLM resolution non-200 [status=%d] [response_body=%s]",
                        response.status_code,
                        response.text[:1000],
                    )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:1000]
                logger.error(
                    "LLM resolution error [status=%d] [model=%s] [url=%s] "
                    "[request_body=%s] [response_body=%s]",
                    status,
                    self._model,
                    url,
                    json.dumps(payload, indent=2, ensure_ascii=False)[:1000],
                    body,
                )
                msg = f"OpenRouter API returned HTTP {status}: {body}"
                raise RuntimeError(msg) from exc
            except httpx.TimeoutException as exc:
                msg = f"OpenRouter API timed out during resolution after 555s (model={self._model})"
                logger.error("LLM resolution timeout [model=%s]", self._model)
                raise TimeoutError(msg) from exc
            except json.JSONDecodeError as exc:
                body = response.text[:1000] if response else "(no response)"
                msg = f"OpenRouter returned invalid JSON during resolution: {body}"
                logger.error("LLM resolution invalid JSON [model=%s] [body=%s]", self._model, body)
                raise RuntimeError(msg) from exc
            except httpx.RequestError as exc:
                msg = f"LLM resolution request failed [model={self._model}] [error={exc}]"
                logger.error(msg)
                raise RuntimeError(msg) from exc
            except asyncio.CancelledError:
                logger.warning("LLM resolution call cancelled [model=%s] [url=%s]", self._model, url)
                raise

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "LLM resolution succeeded [model=%s] [response_keys=%s]",
            self._model,
            list(data.keys()),
        )

        usage_raw: dict | None = data.get("usage")
        usage: dict | None = None
        if isinstance(usage_raw, dict):
            choices = data.get("choices", [])
            response_text = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = {
                "prompt_tokens": usage_raw.get("prompt_tokens", 0),
                "completion_tokens": usage_raw.get("completion_tokens", 0),
                "total_tokens": usage_raw.get("total_tokens", 0),
                "cached_tokens": usage_raw.get("cached_tokens"),
                "cache_write_tokens": usage_raw.get("cache_write_tokens"),
                "reasoning_tokens": usage_raw.get("reasoning_tokens"),
                "model": data.get("model", self._model),
                "cost": usage_raw.get("cost"),
                "duration_ms": duration_ms,
                "prompt_text": payload["messages"][-1]["content"],
                "response_text": response_text,
            }
            if usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0 and usage["total_tokens"] > 0:
                logger.info(
                    "Captured LLM usage [model=%s] [prompt=%d] [completion=%d]",
                    usage["model"], usage["prompt_tokens"], usage["completion_tokens"],
                )
            else:
                logger.warning(
                    "LLM response has zero tokens — usage data may be incomplete [usage=%s]",
                    usage,
                )
                usage = None

        return self._parse_choice(data), usage

    async def extract_events_v7(self, text: str, prior_events: list[dict] | None = None) -> tuple[dict, dict | None]:
        """Call OpenRouter with v7 extraction schema + HR system prompt.

        Parameters
        ----------
        text:
            Raw document chunk text.
        prior_events:
            Events already extracted from earlier chunks.  When provided, the
            prompt instructs the model to find ONLY events not in this list.

        Returns
        -------
        tuple[dict, dict | None]
            (parsed JSON matching ``EVENT_EXTRACTION_SCHEMA_V7``, usage dict from OpenRouter response or None).
        """
        payload = self._build_v7_payload(text, prior_events)
        url = f"{self._base_url}/api/v1/chat/completions"
        headers = self._headers()

        logger.info(
            "LLM v7 request [model=%s] [url=%s] [text_length=%d]",
            self._model,
            url,
            len(text),
        )
        logger.debug("LLM v7 request payload: %s", json.dumps(payload, indent=2, ensure_ascii=False)[:2000])

        start = time.monotonic()

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=555.0,
                )
                if not response.is_success:
                    logger.warning(
                        "LLM v7 API non-200 [status=%d] [response_body=%s]",
                        response.status_code,
                        response.text[:1000],
                    )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                body = exc.response.text[:1000]
                logger.error(
                    "LLM v7 API error [status=%d] [model=%s] [body=%s]",
                    status,
                    self._model,
                    body,
                )
                msg = f"OpenRouter API returned HTTP {status}: {body}"
                raise RuntimeError(msg) from exc
            except httpx.TimeoutException as exc:
                msg = f"OpenRouter API v7 timed out after 555s (model={self._model})"
                logger.error("LLM v7 API timeout [model=%s]", self._model)
                raise TimeoutError(msg) from exc
            except json.JSONDecodeError as exc:
                body = response.text[:1000] if response else "(no response)"
                msg = f"OpenRouter returned invalid JSON for v7: {body}"
                logger.error("LLM v7 API invalid JSON [model=%s] [body=%s]", self._model, body)
                raise RuntimeError(msg) from exc
            except httpx.RequestError as exc:
                msg = f"LLM v7 API request failed [model={self._model}] [error={exc}]"
                logger.error(msg)
                raise RuntimeError(msg) from exc
            except asyncio.CancelledError:
                logger.warning("LLM v7 API call cancelled [model=%s] [url=%s]", self._model, url)
                raise

        duration_ms = int((time.monotonic() - start) * 1000)

        logger.info(
            "LLM v7 request succeeded [model=%s] [duration_ms=%d]",
            self._model,
            duration_ms,
        )

        usage_raw: dict | None = data.get("usage")
        usage: dict | None = None
        if isinstance(usage_raw, dict):
            choices = data.get("choices", [])
            response_text = choices[0].get("message", {}).get("content", "") if choices else ""
            usage = {
                "prompt_tokens": usage_raw.get("prompt_tokens", 0),
                "completion_tokens": usage_raw.get("completion_tokens", 0),
                "total_tokens": usage_raw.get("total_tokens", 0),
                "cached_tokens": usage_raw.get("cached_tokens"),
                "cache_write_tokens": usage_raw.get("cache_write_tokens"),
                "reasoning_tokens": usage_raw.get("reasoning_tokens"),
                "model": data.get("model", self._model),
                "cost": usage_raw.get("cost"),
                "duration_ms": duration_ms,
                "prompt_text": payload["messages"][-1]["content"],
                "response_text": response_text,
            }
            if usage["prompt_tokens"] > 0 and usage["completion_tokens"] > 0 and usage["total_tokens"] > 0:
                logger.info(
                    "Captured LLM v7 usage [model=%s] [prompt=%d] [completion=%d]",
                    usage["model"], usage["prompt_tokens"], usage["completion_tokens"],
                )
            else:
                logger.warning(
                    "LLM v7 response has zero tokens — usage data may be incomplete [usage=%s]",
                    usage,
                )
                usage = None

        return self._parse_choice(data), usage

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(self, text: str, prior_events: list[dict] | None = None) -> dict:
        schema_json = json.dumps(EVENT_EXTRACTION_SCHEMA, indent=2, ensure_ascii=False)

        user_parts: list[str] = []
        if prior_events:
            user_parts.append(
                "Ya has extraído los siguientes eventos de partes anteriores del documento:\n"
                f"{json.dumps(prior_events, ensure_ascii=False, indent=2, default=str)}\n\n"
                "A continuación se muestra una NUEVA parte del documento. "
                "Extrae ÚNICAMENTE los eventos NUEVOS que no aparecen en la lista anterior. "
                "No repitas eventos ya extraídos.\n"
            )

        user_parts.append(
            f"Responde ÚNICAMENTE con un objeto JSON que se ajuste a este esquema:\n"
            f"```json\n{schema_json}\n```\n\n"
            f"{text}"
        )
        user_content = "\n".join(user_parts)
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
                        "Los tipos de referencia válidos son: espacio, tiempo, humanos, objetos.\n"
                        "Incluye al menos una referencia que respalde el campo que_paso "
                        "(usa reference_type 'humanos' para esa referencia).\n"
                        "Responde ÚNICAMENTE con JSON valido, sin texto adicional."
                    ),
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "response_format": {
                "type": "json_object",
            },
            "max_tokens": 64000,
            "temperature": 0.7,
        }

    def _build_resolution_payload(
        self,
        references: list[dict],
    ) -> dict:
        """Build the API payload for entity resolution (reference grouping)."""
        schema_json = json.dumps(ENTITY_RESOLUTION_SCHEMA, indent=2, ensure_ascii=False)
        def _sanitize(obj):
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_sanitize(v) for v in obj]
            return obj

        sanitized_refs = _sanitize(references)

        # Build a compact reference list — only verbatim_text and reference_type
        ref_summary = [
            {"verbatim_text": r.get("verbatim_text", ""), "reference_type": r.get("reference_type", "")}
            for r in sanitized_refs
        ]

        user_content = (
            f"Responde ÚNICAMENTE con un objeto JSON que se ajuste a este esquema:\n"
            f"```json\n{schema_json}\n```\n\n"
            "REFERENCIAS A AGRUPAR:\n"
            f"{json.dumps(ref_summary, ensure_ascii=False, indent=2, default=str)}\n\n"
            "Agrupa las referencias que se refieren a la MISMA entidad (persona, lugar u objeto). "
            "Infiere un nombre canónico apropiado para cada grupo. "
            "No incluyas referencias en el grupo si no están claramente relacionadas."
        )

        return {
            "model": self._model,
            "messages": [
                {"role": "system", "content": ENTITY_RESOLUTION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {
                "type": "json_object",
            },
            "max_tokens": 64000,
            "temperature": 0.7,
        }

    def _build_v7_payload(self, text: str, prior_events: list[dict] | None = None) -> dict:
        schema_json = json.dumps(EVENT_EXTRACTION_SCHEMA_V7, indent=2, ensure_ascii=False)

        user_parts: list[str] = []
        if prior_events:
            user_parts.append(
                "Ya has extraído los siguientes eventos de partes anteriores del documento. "
                "NO extraigas estos eventos nuevamente:\n"
                f"{json.dumps(prior_events, ensure_ascii=False, indent=2, default=str)}\n\n"
                "A continuación se muestra una NUEVA parte del documento. "
                "Extrae ÚNICAMENTE los eventos NUEVOS que no aparecen en la lista anterior.\n"
            )

        user_parts.append(
            f"Responde ÚNICAMENTE con un objeto JSON que se ajuste a este esquema:\n"
            f"```json\n{schema_json}\n```\n\n"
        )
        user_parts.append(
            "(Nota: Este texto puede contener artefactos de OCR. "
            "Extrae solo la información que esté claramente presente en el texto.)\n\n"
        )
        user_parts.append(
            "AVISO: Esta es una extracción automatizada para fines de investigación académica "
            "y no tiene validez jurídica vinculante.\n\n"
        )
        user_parts.append(f"{text}")
        user_content = "\n".join(user_parts)
        return {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": EVENT_EXTRACTION_V7_SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_content,
                },
            ],
            "response_format": {
                "type": "json_object",
            },
            "max_tokens": 64000,
            "temperature": 0.0,
        }

    # Reference: ~4 chars per token for Spanish text.
    _CHARS_PER_TOKEN = 4
    # Max estimated tokens per batch (leaves headroom for system prompt + schema).
    _BATCH_MAX_TOKENS = 240_000

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Crude token estimate: len/4 for Spanish text."""
        return len(text) // OpenRouterProvider._CHARS_PER_TOKEN

    @staticmethod
    def batch_references(
        references: list[dict],
        max_tokens: int | None = None,
    ) -> list[list[dict]]:
        """Split references into token-sized batches for LLM processing.

        Each batch is estimated to stay under *max_tokens* tokens
        (default: ``_BATCH_MAX_TOKENS``).  Keeps references with the same
        ``verbatim_text`` together in the same batch when possible.
        """
        if max_tokens is None:
            max_tokens = OpenRouterProvider._BATCH_MAX_TOKENS

        if not references:
            return []

        # Serialize each ref to estimate its token cost
        ref_tokens: list[tuple[int, dict]] = []
        for ref in references:
            vt = ref.get("verbatim_text", "")
            # Estimate: JSON structure overhead (~80 chars) + verbatim length
            estimated = OpenRouterProvider._estimate_tokens(vt + "reference_type")
            ref_tokens.append((max(estimated, 1), ref))

        batches: list[list[dict]] = []
        current_batch: list[dict] = []
        current_tokens = 0

        for tokens, ref in ref_tokens:
            if current_tokens + tokens > max_tokens and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            current_batch.append(ref)
            current_tokens += tokens

        if current_batch:
            batches.append(current_batch)

        return batches

    @staticmethod
    def _parse_choice(data: dict) -> dict:
        """Extract the parsed JSON content from the OpenAI-format response."""
        choices = data.get("choices", [])
        if not choices:
            msg = f"OpenRouter returned no choices: {json.dumps(data, indent=2)[:500]}"
            logger.error("LLM API empty choices")
            raise RuntimeError(msg)

        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content", "")
        if not content:
            finish_reason = choice.get("finish_reason", "N/A")
            refusal = message.get("refusal")
            model = data.get("model", "unknown")
            msg = (
                f"OpenRouter returned empty content in the first choice "
                f"[model={model}] [finish_reason={finish_reason}]"
            )
            if refusal:
                msg += f" [refusal={refusal[:200]}]"
            logger.error(
                "LLM API empty content [model=%s] [finish_reason=%s] "
                "[refusal=%s] [choice_keys=%s] [data_keys=%s]",
                model,
                finish_reason,
                refusal,
                list(choice.keys()),
                list(data.keys()),
            )
            logger.debug("LLM API empty content — full choice: %s", json.dumps(choice, indent=2, default=str)[:2000])
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


async def extract_events(text: str, provider: LLMProvider | None = None) -> tuple[dict, dict | None]:
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
    tuple[dict, dict | None]
        (parsed JSON matching ``EVENT_EXTRACTION_SCHEMA``, usage dict from OpenRouter response or None).
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


async def resolve_references(
    references: list[dict],
    provider: LLMProvider | None = None,
) -> tuple[dict, dict | None]:
    """Group verbatim references into canonical entities via LLM.

    If *provider* is ``None``, creates an ``OpenRouterProvider`` using the
    ``OPENROUTER_API_KEY`` and ``OPENROUTER_MODEL`` (optional) environment
    variables.

    Parameters
    ----------
    references:
        List of reference dicts (each with ``verbatim_text``,
        ``reference_type``, etc.) to group.
    provider:
        Optional ``LLMProvider`` instance.  Uses ``OpenRouterProvider`` with
        env-var defaults when ``None``.

    Returns
    -------
    tuple[dict, dict | None]
        (parsed JSON matching ``ENTITY_RESOLUTION_SCHEMA``, usage dict from OpenRouter response or None).
    """
    if provider is not None:
        return await provider.resolve_references(references)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        msg = (
            "OPENROUTER_API_KEY is not set. "
            "Either pass a provider explicitly or set the OPENROUTER_API_KEY environment variable."
        )
        raise ValueError(msg)

    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    default_provider = OpenRouterProvider(api_key=api_key, model=model)
    return await default_provider.resolve_references(references)
