"""Local Flutter Web CORS policy, without camera or network access."""
from fastapi.testclient import TestClient

from src.api.app import create_app


def test_local_origins_can_read_monitoring_endpoints():
    with TestClient(create_app()) as client:
        for origin in ("http://localhost:53201", "http://localhost:54321",
                       "http://127.0.0.1:54321"):
            for path in ("/api/falls", "/api/system/status", "/api/health"):
                response = client.get(path, headers={"Origin": origin})
                assert response.status_code == 200
                assert response.headers["access-control-allow-origin"] == origin
                assert "Origin" in response.headers["vary"]
                assert "access-control-allow-credentials" not in response.headers


def test_json_post_preflight_allows_local_origin_only():
    with TestClient(create_app()) as client:
        for origin, allowed in (("http://localhost:53201", True),
                                ("https://example.com", False),
                                ("http://localhost.evil.example:53201", False),
                                ("http://127.0.0.1.evil.example:53201", False)):
            response = client.options("/api/falls/example/acknowledge", headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            })
            assert response.status_code == (200 if allowed else 400)
            if allowed:
                assert response.headers["access-control-allow-origin"] == origin
                assert "POST" in response.headers["access-control-allow-methods"]
                assert "content-type" in response.headers["access-control-allow-headers"].lower()
            else:
                assert "access-control-allow-origin" not in response.headers
                response = client.get("/api/health", headers={"Origin": origin})
                assert "access-control-allow-origin" not in response.headers
