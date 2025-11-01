from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

# Minimal core imports (stubs with executable defaults)
from .core.policy import policy_from_p, PolicyHint
from .core.model import (
    time_split,
    train_select_and_evaluate,
    predict_today,
)
from .core.data import fetch_ohlcv, build_features, label_crash
from .core.utils import get_logger


class RunParams(BaseModel):
    symbols: List[str] = Field(..., example=["ETH/USDT", "SOL/USDT"])
    timeframe: str = Field("1d")
    lookback: int = Field(1200, ge=50)
    horizon: int = Field(10, ge=5, le=30)
    crash_drop: float = Field(0.2, gt=0.0, lt=1.0)
    mode: str = Field("basic")

    @validator("symbols")
    def _norm_symbols(cls, v: List[str]) -> List[str]:
        out = [s.strip().upper() for s in v if s and s.strip()]
        if not out:
            raise ValueError("symbols must be non-empty")
        return out


def _auth_guard(x_api_key: Optional[str]) -> None:
    env_key = os.environ.get("API_KEY", "").strip()
    if env_key:
        if not x_api_key or x_api_key.strip() != env_key:
            raise HTTPException(status_code=401, detail="Unauthorized")


def _run_pipeline(params: RunParams) -> Dict[str, Any]:
    """Minimal, testable pipeline using stubbed core functions.

    Returns a report-like dictionary that mirrors the UI project output at high level.
    """
    logger = get_logger("crashrisklab.api")
    debug_env = os.environ.get("DEBUG", "").strip().lower()
    if debug_env in ("1", "true", "yes", "on"):
        logger.setLevel(10)
    start_all = time.time()
    asof_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    report: Dict[str, Any] = {
        "asof_utc": asof_utc,
        "horizon_days": params.horizon,
        "crash_drop": params.crash_drop,
        "timeframe": params.timeframe,
        "mode": params.mode,
        "symbols": {},
        "policy_hint": {},
    }

    logger.info(
        "stage=start params symbols=%s timeframe=%s lookback=%s horizon=%s drop=%s",
        ",".join(params.symbols), params.timeframe, params.lookback, params.horizon, params.crash_drop,
    )

    # Hard cap to keep request < ~5 minutes on Render
    MAX_SECONDS = int(os.environ.get("MAX_RUNTIME_SECONDS", "300"))

    for sym in params.symbols:
        st_sym = time.time()
        logger.info("stage=data_load symbol=%s action=fetch_ohlcv", sym)
        # 1) Fetch OHLCV from exchange
        df = fetch_ohlcv(sym, params.timeframe, params.lookback)
        logger.info("stage=data_loaded symbol=%s rows=%s elapsed_ms=%s", sym, len(df), int((time.time()-st_sym)*1000))

        # 2) Build features and label without leakage (time-t only)
        st_feat = time.time()
        logger.info("stage=features_build symbol=%s", sym)
        feats = build_features(df)
        feats["y"] = label_crash(feats["close"], horizon=params.horizon, crash_drop=params.crash_drop)
        data = feats.dropna()
        feature_cols = [c for c in data.columns if c not in ("open", "high", "low", "volume", "y")]
        X_all = data[feature_cols]
        y_all = data["y"].astype(int)
        if len(X_all) < 120:
            raise HTTPException(status_code=422, detail=f"Insufficient samples for {sym}: {len(X_all)}")
        logger.info("stage=features_ready symbol=%s n=%s elapsed_ms=%s", sym, len(X_all), int((time.time()-st_feat)*1000))

        # 3) Time split train/test
        st_split = time.time()
        logger.info("stage=split symbol=%s", sym)
        X_tr, y_tr, X_te, y_te = time_split(X_all, y_all)
        logger.info(
            "stage=split_ready symbol=%s train=%s test=%s elapsed_ms=%s",
            sym, len(X_tr), len(X_te), int((time.time()-st_split)*1000)
        )

        # 4) Train + evaluate two real models, select best
        st_train = time.time()
        logger.info("stage=model_train symbol=%s", sym)
        best_name, best_model, metrics = train_select_and_evaluate(
            X_tr, y_tr, X_te, y_te, random_state=42
        )
        logger.info(
            "stage=model_ready symbol=%s model=%s auc=%.3f pr=%.3f brier=%.4f elapsed_ms=%s",
            sym, best_name, float(metrics.get("auc_roc", float("nan"))), float(metrics.get("auc_pr", float("nan"))), float(metrics.get("brier", float("nan"))), int((time.time()-st_train)*1000)
        )

        # 5) Predict today (use latest available row from test or train)
        st_pred = time.time()
        latest_source = X_te if not X_te.empty else X_tr
        p_today: float = predict_today(best_model, latest_source.iloc[-1])
        confidence: float = float(max(0.0, min(1.0, 1.0 - float(metrics.get("brier", 0.25)))))
        pol: PolicyHint = policy_from_p(p_today)
        logger.info(
            "stage=policy symbol=%s p_crash=%.4f confidence=%.3f policy=%s elapsed_ms=%s",
            sym, p_today, confidence, pol.label, int((time.time()-st_pred)*1000)
        )

        report["symbols"][sym] = {
            "p_crash": p_today,
            "confidence": confidence,
            "metrics": {
                "auc": float(metrics.get("auc_roc", float("nan"))),
                "prauc": float(metrics.get("auc_pr", float("nan"))),
                "brier": float(metrics.get("brier", 0.25)),
            },
            "model": best_name,
        }
        report["policy_hint"][sym] = pol.label

        logger.info(
            "stage=symbol_done symbol=%s total_ms=%s", sym, int((time.time()-st_sym)*1000)
        )

        if time.time() - start_all > MAX_SECONDS:
            logger.warning("stage=timeout_reached seconds=%s stopping_after=%s", MAX_SECONDS, sym)
            break

    logger.info("stage=done total_ms=%s", int((time.time()-start_all)*1000))

    return report


app = FastAPI(title="CrashRiskLab API", version="0.1.0")

# CORS setup from env
cors_origins = os.environ.get("CORS_ORIGINS", "*")
origins = [o.strip() for o in cors_origins.split(",") if o.strip()] or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/run")
def run_endpoint(
    body: RunParams,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Dict[str, Any]:
    _auth_guard(x_api_key)
    return _run_pipeline(body)


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
