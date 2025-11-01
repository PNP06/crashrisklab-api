from fastapi.testclient import TestClient
from backend.main import app


def test_rate_limit(monkeypatch):
    client = TestClient(app)
    # Temporarily set a very low rate limit
    monkeypatch.setenv("RATE_LIMIT", "2")
    hits = []
    for _ in range(3):
        r = client.get("/health")
        hits.append(r.status_code)
    # Expect one of the calls to be 429
    assert 429 in hits

