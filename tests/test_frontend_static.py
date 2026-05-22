from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import app, _should_serve_spa

client = TestClient(app)

_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
_HAS_BUILD = (_DIST / "index.html").is_file()


def test_api_routes_not_spa():
    assert _should_serve_spa("/api/v1/health") is False
    assert _should_serve_spa("/docs") is False
    assert _should_serve_spa("/openapi.json") is False
    assert _should_serve_spa("/assets/index-abc.js") is False


def test_spa_paths_allowed():
    assert _should_serve_spa("/") is True
    assert _should_serve_spa("/some-client-route") is True


def test_health_api():
    res = client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_openapi_and_docs():
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200


@pytest.mark.skipif(not _HAS_BUILD, reason="frontend/dist not built")
def test_serves_built_index():
    res = client.get("/")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
    assert "Crypto Research Agent" in res.text


@pytest.mark.skipif(not _HAS_BUILD, reason="frontend/dist not built")
def test_spa_fallback_returns_index():
    res = client.get("/wallet-connect-placeholder")
    assert res.status_code == 200
    assert "text/html" in res.headers.get("content-type", "")
