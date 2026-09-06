"""Routing tests: top-level entry points land somewhere useful.

``GET /`` redirects to the web UI (``/ui``) and ``GET /api`` redirects to
the API reference (FastAPI's Swagger UI at ``/docs``).  Every pre-existing
data endpoint keeps its exact path and behavior.

Pure unit tests — the real app is imported and exercised through TestClient
without a context manager (lifespan never runs, no DB contact), mirroring
the pattern in tests/test_passcodes.py.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from eth_pipeline.api import app as real_app

    return TestClient(real_app)


# ---------------------------------------------------------------------------
# Redirects
# ---------------------------------------------------------------------------


class TestRootRedirect:
    def test_root_redirects_to_ui(self) -> None:
        response = _client().get("/", follow_redirects=False)
        assert response.status_code in (301, 302, 307, 308)
        assert response.headers["location"] == "/ui"

    def test_root_redirect_open_no_passcode(self) -> None:
        """The redirect itself must not be passcode-gated."""
        response = _client().get("/", follow_redirects=False)
        assert response.status_code != 403
        assert response.status_code != 422


class TestApiRedirect:
    def test_api_redirects_to_docs(self) -> None:
        response = _client().get("/api", follow_redirects=False)
        assert response.status_code in (301, 302, 307, 308)
        assert response.headers["location"] == "/docs"

    def test_api_redirect_open_no_passcode(self) -> None:
        response = _client().get("/api", follow_redirects=False)
        assert response.status_code != 403
        assert response.status_code != 422


# ---------------------------------------------------------------------------
# Regression: data endpoints unchanged
# ---------------------------------------------------------------------------


class TestDataEndpointsUnchanged:
    def test_documents_still_gated_and_present(self) -> None:
        """422 = route present with its required passcode param (not shadowed)."""
        response = _client().get("/documents")
        assert response.status_code == 422

    def test_api_providers_still_gated_and_present(self) -> None:
        """Exact-path /api route must not shadow /api/providers."""
        response = _client().get("/api/providers")
        assert response.status_code == 422

    def test_passcode_check_unchanged(self) -> None:
        """Wrong passcode still yields the generic 401 (route intact)."""
        response = _client().get("/api/passcode/check", params={"passcode": "nope"})
        assert response.status_code == 401
        assert response.json() == {"detail": "Invalid passcode."}

    def test_health_stays_open(self) -> None:
        assert _client().get("/health").status_code == 200

    def test_docs_stay_open(self) -> None:
        assert _client().get("/docs").status_code == 200
