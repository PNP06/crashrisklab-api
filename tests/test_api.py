from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json().get('status') == 'ok'

def test_run_offline_monkeypatch(monkeypatch):
    # Monkeypatch fetch_ohlcv to avoid network
    from backend.core import data as core_data
    def fake_fetch(symbol, timeframe, lookback):
        return core_data.synth_ohlcv(symbol, timeframe, lookback)
    monkeypatch.setattr(core_data, 'fetch_ohlcv', fake_fetch)

    body = {
        'symbols': ['ETH/USDT', 'SOL/USDT'],
        'timeframe': '1d',
        'lookback': 500,
        'horizon': 10,
        'crash_drop': 0.2,
        'mode': 'basic'
    }
    r = client.post('/run', json=body)
    assert r.status_code == 200
    js = r.json()
    assert 'symbols' in js and isinstance(js['symbols'], dict)
