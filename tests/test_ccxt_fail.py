from fastapi.testclient import TestClient
from backend.main import app


def test_ccxt_failure_returns_503(monkeypatch):
    client = TestClient(app)
    from backend.core import data as core_data

    def boom(symbol, timeframe, lookback):
        raise RuntimeError("circuit-open")

    monkeypatch.setattr(core_data, "fetch_ohlcv", boom)

    body = {
        "symbols": ["ETH/USDT"],
        "timeframe": "1d",
        "lookback": 500,
        "horizon": 10,
        "crash_drop": 0.2,
        "mode": "basic",
    }
    r = client.post("/run", json=body)
    assert r.status_code == 503
    js = r.json()
    assert js["detail"]["error"] == "data_unavailable"

