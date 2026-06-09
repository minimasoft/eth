"""Unit and integration tests for v7 event extraction activity."""

from __future__ import annotations

import logging
import os
from unittest.mock import AsyncMock, patch

import pytest

logger = logging.getLogger(__name__)


class TestExtractionV7:

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_degraded(self) -> None:
        """Activity returns degraded result when OPENROUTER_API_KEY is not set."""
        from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity

        with patch.dict(os.environ, {}, clear=True):
            result = await extract_events_v7_activity("doc-001", 0, "some text")
        assert result == {"error": "OPENROUTER_API_KEY not set", "events": []}

    @pytest.mark.asyncio
    async def test_returns_structured_events_v7_schema(self) -> None:
        """Activity returns events matching v7 schema shape from a mocked provider."""
        from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity

        mock_events = {
            "events": [
                {
                    "title": "Firma del contrato",
                    "description": "Las partes firmaron el acuerdo",
                    "time_start": "2024-01-01T00:00:00Z",
                    "time_end": None,
                    "time_precision": "day",
                    "location": {
                        "name": "Buenos Aires",
                        "location_type": "city",
                    },
                    "participants": [
                        {"name": "Juan Pérez", "role": "subject"},
                        {"name": "María García", "role": "witness"},
                    ],
                    "references": [
                        {
                            "reference_type": "location",
                            "verbatim_text": "en la ciudad de Buenos Aires",
                            "span_start": 0,
                            "span_end": 30,
                        },
                    ],
                }
            ]
        }
        mock_usage = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "duration_ms": 2000,
            "prompt_text": "test prompt",
            "response_text": "test response",
        }

        mock_provider = AsyncMock()
        mock_provider.extract_events_v7.return_value = (mock_events, mock_usage)

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch(
                "eth_pipeline.activities.extract_events_v7.OpenRouterProvider",
                return_value=mock_provider,
            ):
                with patch("eth_pipeline.activities.extract_events_v7.record_llm_usage"):
                    with patch("eth_pipeline.activities.extract_events_v7.record_llm_call_log"):
                        result = await extract_events_v7_activity("doc-002", 1, "document text")

        assert "events" in result
        assert result["events"][0]["title"] == "Firma del contrato"
        assert result["events"][0]["description"] == "Las partes firmaron el acuerdo"
        assert result["events"][0]["location"]["name"] == "Buenos Aires"
        assert result["events"][0]["participants"][0]["name"] == "Juan Pérez"
        assert result["events"][0]["references"][0]["verbatim_text"] == "en la ciudad de Buenos Aires"

    @pytest.mark.asyncio
    async def test_refusal_detection(self) -> None:
        """Mocked provider raising RuntimeError with 'refusal' returns degraded result."""
        from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity

        mock_provider = AsyncMock()
        mock_provider.extract_events_v7.side_effect = RuntimeError(
            "content refusal: safety filter triggered"
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch(
                "eth_pipeline.activities.extract_events_v7.OpenRouterProvider",
                return_value=mock_provider,
            ):
                result = await extract_events_v7_activity("doc-003", 0, "sensitive text")

        assert result["events"] == []
        assert result["refused"] is True
        assert "refusal_reason" in result
        assert "safety filter" in result["refusal_reason"]

    @pytest.mark.asyncio
    async def test_non_json_content_degraded(self) -> None:
        """Mocked provider returning non-JSON content returns degraded result."""
        from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity

        mock_provider = AsyncMock()
        mock_provider.extract_events_v7.side_effect = RuntimeError(
            "Model returned non-JSON content: plain text"
        )

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch(
                "eth_pipeline.activities.extract_events_v7.OpenRouterProvider",
                return_value=mock_provider,
            ):
                result = await extract_events_v7_activity("doc-004", 0, "some text")

        assert result["events"] == []
        assert result["refused"] is True
        assert "plain text" in result["refusal_reason"]

    @pytest.mark.asyncio
    async def test_records_llm_usage_on_success(self) -> None:
        """Activity calls record_llm_usage with step_name='extract_events_v7'."""
        from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity

        mock_events = {"events": [{"title": "Test", "description": "Test desc", "references": []}]}
        mock_usage = {
            "prompt_tokens": 50,
            "completion_tokens": 25,
            "total_tokens": 75,
            "duration_ms": 1000,
            "prompt_text": "test",
            "response_text": "test",
        }

        mock_provider = AsyncMock()
        mock_provider.extract_events_v7.return_value = (mock_events, mock_usage)

        mock_record_usage = AsyncMock()
        mock_record_call_log = AsyncMock()

        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "sk-test"}):
            with patch(
                "eth_pipeline.activities.extract_events_v7.OpenRouterProvider",
                return_value=mock_provider,
            ):
                with patch(
                    "eth_pipeline.activities.extract_events_v7.record_llm_usage",
                    mock_record_usage,
                ):
                    with patch(
                        "eth_pipeline.activities.extract_events_v7.record_llm_call_log",
                        mock_record_call_log,
                    ):
                        result = await extract_events_v7_activity(
                            "doc-005", 2, "test text"
                        )

        assert "events" in result
        mock_record_usage.assert_called_once()
        call_kwargs = mock_record_usage.call_args.kwargs
        assert call_kwargs["step_name"] == "extract_events_v7"
        assert call_kwargs["chunk_index"] == 2
        mock_record_call_log.assert_called_once()
        log_kwargs = mock_record_call_log.call_args.kwargs
        assert log_kwargs["activity_type"] == "extract_events_v7"

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_no_refusals_on_corpus(self) -> None:
        """Run extraction against real Spanish documents — verify zero refusals."""
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            pytest.skip("OPENROUTER_API_KEY not set")

        from eth_pipeline.activities.extract_events_v7 import extract_events_v7_activity

        test_data_dir = os.path.join(os.path.dirname(__file__), "..", "test_data")
        if not os.path.isdir(test_data_dir):
            test_data_dir = "test_data"

        import glob
        txt_files = sorted(glob.glob(os.path.join(test_data_dir, "*.txt")))
        if not txt_files:
            pytest.skip("No test_data/*.txt files found for refusal spike")

        total_chunks = 0
        refusal_count = 0
        for txt_path in txt_files[:10]:
            try:
                with open(txt_path, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception:
                continue

            chunk_size = 5000
            chunks = [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]
            for idx, chunk in enumerate(chunks[:3]):
                result = await extract_events_v7_activity(
                    f"corpus-{os.path.basename(txt_path)}", idx, chunk
                )
                total_chunks += 1
                if result.get("refused"):
                    refusal_count += 1
                    logger.warning(
                        "REFUSAL DETECTED: file=%s chunk=%d reason=%s",
                        txt_path, idx, result.get("refusal_reason", "unknown"),
                    )

        refusal_rate = refusal_count / total_chunks if total_chunks > 0 else 0
        assert refusal_rate < 0.05, (
            f"Refusal rate {refusal_rate:.1%} exceeds 5% threshold "
            f"({refusal_count}/{total_chunks} chunks refused)"
        )
