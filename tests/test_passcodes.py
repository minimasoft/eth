"""Unit tests for passcode permissions (eth_pipeline.passcodes).

Pure unit tests — no DB, no stateful fixtures.  The decorator and the check
endpoint are exercised through a small in-memory FastAPI app (no dev-DB
contact).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from eth_pipeline.passcodes import resolve_level, require_passcode, verify_passcode

PASSCODE_VARS = ("PASSCODE_A", "PASSCODE_B", "PASSCODE_C")


@pytest.fixture(autouse=True)
def _clean_passcode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PASSCODE_VARS:
        monkeypatch.delenv(name, raising=False)


def _app() -> FastAPI:
    app = FastAPI()

    @app.post("/t/thing", status_code=201)
    @require_passcode("A")
    async def create_thing() -> dict[str, str]:
        return {"ok": "true"}

    @app.delete("/t/thing")
    @require_passcode("B")
    async def delete_thing() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/api/passcode/check")
    async def check(passcode: str) -> dict[str, str]:
        level = resolve_level(passcode)
        if level is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Invalid passcode.")
        return {"level": level}

    return app


class TestResolveLevel:
    def test_defaults_resolve_to_a_b_c(self) -> None:
        assert resolve_level("AAAAA") == "A"
        assert resolve_level("BBBBB") == "B"
        assert resolve_level("CCCCC") == "C"

    def test_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PASSCODE_A", "ZZZZZ")
        assert resolve_level("AAAAA") is None
        assert resolve_level("ZZZZZ") == "A"

    def test_wrong_passcode_returns_none(self) -> None:
        assert resolve_level("nope") is None
        assert resolve_level("") is None

    def test_verify_passcode(self) -> None:
        assert verify_passcode("BBBBB", "B") is True
        assert verify_passcode("AAAAA", "B") is False
        assert verify_passcode("AAAAA", "Z") is False

    def test_level_a_does_not_satisfy_b(self) -> None:
        """T-JD7-05: an A-holder must not pass the B decorator."""
        client = TestClient(_app())
        response = client.delete("/t/thing", params={"passcode": "AAAAA"})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}


class TestRequirePasscodeDecorator:
    def test_correct_passcode_passes(self) -> None:
        client = TestClient(_app())
        response = client.post("/t/thing", params={"passcode": "AAAAA"}, json={})
        assert response.status_code == 201

    def test_wrong_passcode_generic_403(self) -> None:
        client = TestClient(_app())
        response = client.post("/t/thing", params={"passcode": "BBBBB"}, json={})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}

    def test_empty_passcode_generic_403(self) -> None:
        client = TestClient(_app())
        response = client.post("/t/thing", params={"passcode": ""}, json={})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}

    def test_passcode_is_required_query_param(self) -> None:
        """The wrapper signature exposes passcode as an obligatory query param."""
        client = TestClient(_app())
        response = client.post("/t/thing", json={})
        assert response.status_code == 422  # FastAPI validation: param required

        schema = _app().openapi()
        param = schema["paths"]["/t/thing"]["post"]["parameters"][0]
        assert param["name"] == "passcode"
        assert param["required"] is True
        assert param["in"] == "query"


class TestCheckEndpoint:
    def test_correct_code_returns_level(self) -> None:
        client = TestClient(_app())
        response = client.get("/api/passcode/check", params={"passcode": "CCCCC"})
        assert response.status_code == 200
        assert response.json() == {"level": "C"}

    def test_wrong_code_401_without_level_info(self) -> None:
        client = TestClient(_app())
        response = client.get("/api/passcode/check", params={"passcode": "nope"})
        assert response.status_code == 401
        body = response.json()
        assert body == {"detail": "Invalid passcode."}
        assert "level" not in body
