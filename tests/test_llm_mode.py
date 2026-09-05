"""Unit tests for LLM mode helpers (instruct vs thinking sampling).

Pure, host-runnable tests — no DB, no network (see ./test.sh --unit).
"""

from __future__ import annotations

import pytest

from eth_pipeline.llm import (
    INSTRUCT_TEMPERATURE,
    INSTRUCT_TOP_K,
    INSTRUCT_TOP_P,
    OpenRouterProvider,
    resolve_sampling,
    tracking_model_name,
)


class TestResolveSampling:
    def test_thinking_returns_none(self):
        assert resolve_sampling("thinking", None) is None

    def test_thinking_with_provider_cfg_returns_none(self):
        cfg = {"instruct_temperature": 0.2, "instruct_top_p": 0.5, "instruct_top_k": 10}
        assert resolve_sampling("thinking", cfg) is None

    def test_instruct_defaults(self):
        assert resolve_sampling("instruct", None) == {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
        }
        # Defaults match the module constants
        assert resolve_sampling("instruct", None) == {
            "temperature": INSTRUCT_TEMPERATURE,
            "top_p": INSTRUCT_TOP_P,
            "top_k": INSTRUCT_TOP_K,
        }

    def test_instruct_provider_values_win_null_falls_back(self):
        cfg = {"instruct_temperature": 0.3, "instruct_top_p": None, "instruct_top_k": 20}
        assert resolve_sampling("instruct", cfg) == {
            "temperature": 0.3,
            "top_p": 0.9,  # NULL falls back to module default
            "top_k": 20,
        }

    def test_mode_is_case_insensitive(self):
        assert resolve_sampling("  INSTRUCT ", None) == {
            "temperature": 0.7,
            "top_p": 0.9,
            "top_k": 40,
        }
        assert resolve_sampling("Thinking", None) is None

    def test_unknown_mode_raises(self):
        with pytest.raises(ValueError):
            resolve_sampling("greedy", None)


class TestTrackingModelName:
    def test_thinking_unchanged(self):
        assert tracking_model_name("deepseek/v4", "thinking") == "deepseek/v4"

    def test_instruct_appends_suffix(self):
        assert tracking_model_name("deepseek/v4", "instruct") == "deepseek/v4 [I]"

    def test_instruct_case_insensitive(self):
        assert tracking_model_name("deepseek/v4", " Instruct ") == "deepseek/v4 [I]"


def _provider(sampling: dict | None) -> OpenRouterProvider:
    return OpenRouterProvider(api_key="test-key", model="deepseek/v4", sampling=sampling)


class TestBuildV7Payload:
    def test_thinking_payload_unchanged(self):
        payload = _provider(None)._build_v7_payload("texto")
        assert payload["temperature"] == 1.0
        assert payload["top_p"] == 0.95
        assert payload["top_k"] == 20
        assert payload["max_tokens"] == 60000
        assert payload["presence_penalty"] == 0.0

    def test_instruct_payload_uses_sampling(self):
        sampling = {"temperature": 0.3, "top_p": 0.8, "top_k": 20}
        payload = _provider(sampling)._build_v7_payload("texto")
        assert payload["temperature"] == 0.3
        assert payload["top_p"] == 0.8
        assert payload["top_k"] == 20
        # Unchanged knobs stay as-is
        assert payload["max_tokens"] == 60000
        assert payload["presence_penalty"] == 0.0
