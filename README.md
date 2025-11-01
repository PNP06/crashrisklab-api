# CrashRiskLab API (stub)

Minimal FastAPI backend that mimics the CrashRiskLab report generation with executable stubs. Useful to integrate a UI or test pipelines without market/network dependencies.

## Run local

- Python 3.11+
- Install deps:

```
pip install -r requirements.txt
```

- Launch server:

```
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

- Optional env vars:
- `API_KEY` (default empty): if set, requests must include header `X-API-Key: <API_KEY>`
- `CORS_ORIGINS` (default `*`): comma-separated origins for CORS

## Endpoints

- `GET /health` → `{ "status": "ok" }`
- `POST /run` body example:

```
{
  "symbols": ["ETH/USDT", "SOL/USDT"],
  "timeframe": "1d",
  "lookback": 1200,
  "horizon": 10,
  "crash_drop": 0.2,
  "mode": "basic"
}
```

Returns a minimal `report.json`-like payload with per-symbol `p_crash`, `confidence`, `metrics`, and `policy_hint`.

## Docker

Build:

```
docker build -t crashrisklab-api ./crashrisklab-api
```

Run:

```
docker run --rm -p 8000:8000 -e API_KEY=secret -e CORS_ORIGINS=* crashrisklab-api
```

Then call:

```
curl -H "X-API-Key: secret" http://localhost:8000/health
```

