from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # The mode is reported so a UI or operator can see whether AI output is mocked.
    assert body["ai_provider"] in {"mock", "openai", "azure_openai", "gemini"}
    assert body["auth_mode"] in {"demo", "oidc"}


def test_every_api_route_requires_authentication() -> None:
    client = TestClient(app)
    for path in ("/api/v1/courses", "/api/v1/dashboard", "/api/v1/roster", "/api/v1/billing"):
        assert client.get(path).status_code in (401, 403, 422), path
    for path in ("/api/v1/ai/study-buddy", "/api/v1/cohorts", "/api/v1/scorecards"):
        assert client.post(path, json={}).status_code in (401, 403), path
