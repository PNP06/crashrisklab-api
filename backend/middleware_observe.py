from __future__ import annotations

import json
import time
import uuid
from typing import Callable

from fastapi import Request, Response


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


async def observability_middleware(request: Request, call_next: Callable) -> Response:
    """Structured JSON logging with correlation id and basic request metrics.

    - Sets request.state.corr_id so downstream can log it.
    - Adds X-Request-ID header on the response.
    - Emits one JSON log line per request with ts, corr_id, path, method, status, duration_ms, size.
    """
    corr_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.corr_id = corr_id
    start = time.time()
    status = 500
    size = 0
    try:
        response: Response = await call_next(request)
        status = response.status_code
        # Might not be available if streaming; best-effort
        body_len = response.headers.get("content-length")
        try:
            size = int(body_len) if body_len is not None else 0
        except Exception:
            size = 0
        response.headers["X-Request-ID"] = corr_id
        return response
    finally:
        duration_ms = int((time.time() - start) * 1000)
        line = {
            "ts": _now_iso(),
            "level": "INFO",
            "corr_id": corr_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "duration_ms": duration_ms,
            "size": size,
        }
        # Print to stdout; platform picks up container logs
        print(json.dumps(line, ensure_ascii=False))

