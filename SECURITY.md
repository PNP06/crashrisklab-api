# Security

- Authentication: `X-API-Key` header compared against `API_KEY` env (empty → no auth).
- CORS: default `*`, can be set via `CORS_ORIGINS` CSV.
- Rate limit: in-memory token bucket via middleware (default `RATE_LIMIT=30` per minute).
- Secrets: do not log secrets; logs are structured JSON without payload bodies.
- Timeouts: ccxt client timeout via `CCXT_TIMEOUT_MS` (default 15000ms).

