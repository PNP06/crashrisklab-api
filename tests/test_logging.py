from fastapi.testclient import TestClient
from backend.main import app


def test_corr_id_present():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    # X-Request-ID header returned by observability middleware
    assert "X-Request-ID" in r.headers
    assert len(r.headers["X-Request-ID"]) > 0

