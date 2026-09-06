"""Unit tests for passcode permissions (eth_pipeline.passcodes).

Pure unit tests — no DB, no stateful fixtures.  The decorator and the check
endpoint are exercised through a small in-memory FastAPI app (no dev-DB
contact).
"""

from __future__ import annotations

import importlib

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


# ---------------------------------------------------------------------------
# Read enforcement (260906-kj0): every data-returning GET requires level C
# ---------------------------------------------------------------------------

def _read_app() -> FastAPI:
    app = FastAPI()

    @app.get("/r/things")
    @require_passcode("C")
    async def list_things() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/r/things/{thing_id}")
    @require_passcode("C")
    async def get_thing(thing_id: str) -> dict[str, str]:
        if thing_id == "missing":
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Thing not found.")
        return {"ok": "true"}

    return app


class TestRequirePasscodeReads:
    """T-KJ0-01: C-on-reads contract (mirror of the mutating-endpoint tests)."""

    def test_missing_passcode_422(self) -> None:
        client = TestClient(_read_app())
        assert client.get("/r/things").status_code == 422

    def test_empty_passcode_generic_403(self) -> None:
        client = TestClient(_read_app())
        response = client.get("/r/things", params={"passcode": ""})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}

    def test_wrong_passcode_generic_403(self) -> None:
        client = TestClient(_read_app())
        response = client.get("/r/things", params={"passcode": "nope"})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}

    def test_level_a_does_not_satisfy_c(self) -> None:
        client = TestClient(_read_app())
        response = client.get("/r/things", params={"passcode": "AAAAA"})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}

    def test_level_b_does_not_satisfy_c(self) -> None:
        client = TestClient(_read_app())
        response = client.get("/r/things", params={"passcode": "BBBBB"})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}

    def test_valid_c_passes(self) -> None:
        client = TestClient(_read_app())
        response = client.get("/r/things", params={"passcode": "CCCCC"})
        assert response.status_code == 200

    def test_mocked_db_miss_still_proves_decorator_passed(self) -> None:
        """A 404 from the handler proves the C decorator let the request through."""
        client = TestClient(_read_app())
        response = client.get("/r/things/missing", params={"passcode": "CCCCC"})
        assert response.status_code == 404


#: (route module, path) for every data-returning GET endpoint that must be
#: gated with require_passcode("C").
READ_ENDPOINTS: list[tuple[str, str]] = [
    ("eth_pipeline.api.routes.documents", "/"),
    ("eth_pipeline.api.routes.documents", "/documents"),
    ("eth_pipeline.api.routes.documents", "/documents/{document_id}"),
    ("eth_pipeline.api.routes.documents", "/documents/{document_id}/chunks/{part_index}"),
    ("eth_pipeline.api.routes.documents", "/documents/{document_id}/logs"),
    ("eth_pipeline.api.routes.documents", "/documents/{document_id}/llm-calls"),
    ("eth_pipeline.api.routes.documents", "/documents/{document_id}/tokens"),
    ("eth_pipeline.api.routes.events_v2", "/events"),
    ("eth_pipeline.api.routes.events_v2", "/events/{event_id}"),
    ("eth_pipeline.api.routes.geo", "/geo/events"),
    ("eth_pipeline.api.routes.providers", "/api/providers"),
    ("eth_pipeline.api.routes.comparisons", "/comparisons/{source_id}"),
]

#: Endpoints that must stay reachable WITHOUT any passcode.
#: (/api/passcode/check takes its own ``passcode`` param by design, so it is
#: verified behaviorally below rather than structurally.)
OPEN_ENDPOINTS: list[tuple[str, str]] = [
    ("eth_pipeline.api.routes.documents", "/health"),
]


def _find_route(module_name: str, path: str) -> object:
    module = importlib.import_module(module_name)
    for route in module.router.routes:
        if getattr(route, "path", None) == path and "GET" in getattr(route, "methods", set()):
            return route
    raise AssertionError(f"GET {path} not found in {module_name}")


def _passcode_query_param(route: object) -> object | None:
    for param in route.dependant.query_params:  # type: ignore[attr-defined]
        if param.name == "passcode":
            return param
    return None


class TestReadEndpointsDecorated:
    """Structural checks: the real routers carry the C gate on all reads."""

    def test_every_read_endpoint_requires_passcode(self) -> None:
        for module_name, path in READ_ENDPOINTS:
            route = _find_route(module_name, path)
            param = _passcode_query_param(route)
            assert param is not None, f"GET {path} ({module_name}) lacks passcode param"
            assert param.field_info.is_required(), f"GET {path} passcode param not required"

    def test_health_and_check_stay_open(self) -> None:
        for module_name, path in OPEN_ENDPOINTS:
            route = _find_route(module_name, path)
            assert _passcode_query_param(route) is None, f"GET {path} must stay open"

    def test_real_app_enforces_read_gate(self) -> None:
        """Behavioral spot-check on the real app (rejections happen before DB)."""
        from eth_pipeline.api import app as real_app

        client = TestClient(real_app)
        assert client.get("/documents").status_code == 422
        response = client.get("/documents", params={"passcode": ""})
        assert response.status_code == 403
        assert response.json() == {"detail": "Passcode required."}
        response = client.get("/documents", params={"passcode": "AAAAA"})
        assert response.status_code == 403  # A is not C
        assert client.get("/health").status_code == 200

    def test_passcode_check_stays_open(self) -> None:
        """The bootstrap validation endpoint works without any prior gate."""
        from eth_pipeline.api import app as real_app

        client = TestClient(real_app)
        response = client.get("/api/passcode/check", params={"passcode": "CCCCC"})
        assert response.status_code == 200
        assert response.json() == {"level": "C"}
