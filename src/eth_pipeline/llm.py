"""
LLM provider abstraction for v7 event extraction.

Defines an ``OpenRouterProvider`` that calls the OpenRouter API with
structured JSON output, and convenience function ``extract_events_v7()``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time


import httpx

logger = logging.getLogger(__name__)

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
                        "description": "ISO 8601 datetime when the event started. -03:00 Buenos Aires timezone bye default. Approximate best as possible",
                    },
                    "time_end": {
                        "type": "string",
                        "description": "ISO 8601 datetime when the event ended. -03:00 Buenos Aires timezone by default. Approximate best as possible",
                    },
                    "time_precision": {
                        "type": "string",
                        "enum": ["day", "month", "year"],
                        "description": "Precision of extracted dates.",
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
    "CRITICO - Marcas de tiempo: El campo time_start (y time_end cuando aplique) "
    "es el dato MAS IMPORTANTE de cada evento. Sin una marca de tiempo --aunque sea "
    "aproximada-- un evento no es admisible. Eventos sin ningun tiempo (ni siquiera "
    "un ano) NO deben ser extraidos como eventos. Si el texto menciona un rango de "
    "fechas (ej. entre marzo y junio de 1976), usa la fecha mas temprana como "
    "time_start y la mas tardia como time_end. Si solo hay un ano, usa "
    "AAAA-01-01 como time_start con time_precision=year. Si el texto incluye "
    "una ubicacion y una marca de tiempo en la misma oracion, debes crear TANTO la "
    "referencia de lugar como la referencia de tiempo -- no extraer solo una. Las "
    "marcas de tiempo permiten ordenar los eventos cronicamente; incluso un "
    "tiempo difuso (ej. solo un ano) es mejor que ninguno.\n\n"
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

DEFAULT_MODEL = "deepseek/deepseek-v4-flash-0731"
OPENROUTER_BASE_URL = "https://openrouter.ai"


def chat_completions_url(base_url: str) -> str:
    """Build the chat-completions endpoint for a provider base URL.

    Accepts OpenRouter-style bases (``https://openrouter.ai``) as well as
    OpenAI-compatible servers that already include the version path
    (``http://host:8080/v1``, ``http://host:11434/api/v1``).
    """
    base = base_url.rstrip("/")
    if base.endswith("/api/v1"):
        return f"{base}/chat/completions"
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/api/v1/chat/completions"

# Target characters of document text per extraction chunk.  Each chunk is
# sent to the LLM sequentially with already-extracted events as context,
# so the model finds NEW events per chunk without exceeding the context
# window.  ~100K tokens of text at ~4 chars/token for Spanish.
EXTRACTION_CHUNK_SIZE = 400_000

# ---------------------------------------------------------------------------
# OpenRouter provider
# ---------------------------------------------------------------------------


class OpenRouterProvider:
    """LLM provider that calls the OpenRouter ``/v1/chat/completions`` API.

    Uses ``httpx.AsyncClient`` per-call (created and closed inside
    ``extract_events_v7``).  The API response is parsed as JSON and validated
    implicitly against ``EVENT_EXTRACTION_SCHEMA_V7`` via the
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
        url = chat_completions_url(self._base_url)
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
                    timeout=1440.0,
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
                msg = f"OpenRouter API v7 timed out after 999s (model={self._model})"
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

    def _build_v7_payload(self, text: str, prior_events: list[dict] | None = None) -> dict:
        schema_json = json.dumps(EVENT_EXTRACTION_SCHEMA_V7, indent=2, ensure_ascii=False)

        user_parts: list[str] = []
        if prior_events:
            user_parts.append(
                "Ya has extraído los siguientes eventos de partes anteriores del documento. "
                "NO extraigas estos eventos nuevamente:\n"
                f"{json.dumps(prior_events, ensure_ascii=False, indent=2, default=str)}\n\n"
                "A continuación se muestra una NUEVA parte del documento. "
                "Extrae ÚNICAMENTE los eventos NUEVOS que no aparecen en la lista anterior y no repitas los viejos en la respuesta.\n"
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
# Provider self-test (used by GET/POST providers test endpoints)
# ---------------------------------------------------------------------------

OPENROUTER_TEST_PROMPT = 'say "cuba soberana"'
OPENROUTER_TEST_EXPECTED = "cuba soberana"


async def test_provider(model: str, api_key: str | None, base_url: str = OPENROUTER_BASE_URL) -> dict:
    """Send the ``cuba soberana`` echo prompt and verify the exact answer.

    Returns a dict with ``ok``, ``answer``, ``normalized``, ``expected``,
    ``model`` and ``error`` (when the call fails).  Raises ``ValueError`` if
    *api_key* is missing.
    """
    if not api_key:
        return {
            "ok": False,
            "error": "No API key configured for this provider.",
            "model": model,
        }

    base = base_url.rstrip("/")
    url = chat_completions_url(base)

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": OPENROUTER_TEST_PROMPT}],
        "max_tokens": 1024,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()
            data = response.json()
    except Exception as exc:  # noqa: BLE001 — surface as result, not exception
        logger.warning("providers/test request failed [model=%s] [error=%s]", model, exc)
        return {"ok": False, "error": f"Request failed: {exc}", "model": model}

    content = ""
    try:
        choices = data.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "") or ""
    except Exception:  # noqa: BLE001
        content = ""

    normalized = content.strip().strip('"').strip().lower()
    expected = OPENROUTER_TEST_EXPECTED
    ok = normalized == expected

    logger.info(
        "providers/test result [model=%s] [ok=%s] [answer=%r]",
        model,
        ok,
        content[:200],
    )
    return {
        "ok": ok,
        "answer": content,
        "normalized": normalized,
        "expected": expected,
        "model": data.get("model", model),
        "error": None if ok else "La respuesta no es exacta.",
    }



