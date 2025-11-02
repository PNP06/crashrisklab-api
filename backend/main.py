from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, validator

# Minimal core imports (stubs with executable defaults)
from .core.policy import policy_from_p, PolicyHint
from .core.model import (
    time_split,
    train_select_and_evaluate,
    predict_today,
    compute_reverse_importances,
)
from .core.data import fetch_ohlcv, build_features, label_crash
from .core.utils import get_logger
from .middleware_observe import observability_middleware
from .middleware_rate_limit import rate_limit_middleware
from starlette.staticfiles import StaticFiles
from .core.validation_temps import seed_all
from sklearn.calibration import calibration_curve
import matplotlib.pyplot as plt


class RunParams(BaseModel):
    symbols: List[str] = Field(..., example=["ETH/USDT", "SOL/USDT"])
    timeframe: str = Field("1d")
    lookback: int = Field(1200, ge=400)
    horizon: int = Field(10, ge=5, le=30)
    crash_drop: float = Field(0.2, ge=0.05, le=0.60)
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
    report["validation"] = "walk_forward" if os.environ.get("WALK_FORWARD","" ).strip() in ("1","true","yes","on") else "holdout"

    logger.info(
        "stage=start params symbols=%s timeframe=%s lookback=%s horizon=%s drop=%s",
        ",".join(params.symbols), params.timeframe, params.lookback, params.horizon, params.crash_drop,
    )

    # Hard cap to keep request < ~5 minutes on Render
    MAX_SECONDS = int(os.environ.get("MAX_RUNTIME_SECONDS", "300"))

    last_report: Dict[str, Any] = report
    for sym in params.symbols:
        st_sym = time.time()
        logger.info("stage=data_load symbol=%s action=fetch_ohlcv", sym)
        # 1) Fetch OHLCV from exchange
        try:
            df = fetch_ohlcv(sym, params.timeframe, params.lookback)
        except Exception as e:
            raise HTTPException(status_code=503, detail={"error": "data_unavailable", "symbol": sym, "reason": str(type(e).__name__)})
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

        # Optional reliability plot export
        try:
            if os.environ.get("EXPORT_PLOTS", "").strip() in ("1","true","yes","on"):
                probs = best_model.predict_proba(X_te.values)[:,1] if not X_te.empty else best_model.predict_proba(X_tr.values)[:,1]
                y_plot = y_te.values if not X_te.empty else y_tr.values
                prob_true, prob_pred = calibration_curve(y_plot, probs, n_bins=10, strategy='uniform')
                Path('outputs').mkdir(parents=True, exist_ok=True)
                out_png = Path('outputs') / f"calibration_{sym.replace('/','_')}.png"
                plt.figure(figsize=(5,4))
                plt.plot(prob_pred, prob_true, 's-', label='model')
                plt.plot([0,1],[0,1],'k--', label='ideal')
                plt.xlabel('Predicted probability')
                plt.ylabel('Observed frequency')
                plt.legend()
                plt.tight_layout()
                plt.savefig(out_png)
                plt.close()
                # attach to report
                report.setdefault('plots', {})[sym] = { 'calibration': f"/outputs/{out_png.name}" }
        except Exception:
            pass

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
        last_report = report

        logger.info(
            "stage=symbol_done symbol=%s total_ms=%s", sym, int((time.time()-st_sym)*1000)
        )

        if time.time() - start_all > MAX_SECONDS:
            logger.warning("stage=timeout_reached seconds=%s stopping_after=%s", MAX_SECONDS, sym)
            break

    logger.info("stage=done total_ms=%s", int((time.time()-start_all)*1000))

    # Store last report in app state for GET /last_report
    try:
        app.state.last_report = last_report
    except Exception:
        pass
    return report


app = FastAPI(title="CrashRiskLab API", version="0.1.0")
app.middleware("http")(observability_middleware)
app.middleware("http")(rate_limit_middleware)
# Outputs static mount: be defensive across Starlette versions
try:
    outdir = Path(os.environ.get("OUTPUTS_DIR", "outputs"))
    outdir.mkdir(parents=True, exist_ok=True)
    app.mount("/outputs", StaticFiles(directory=str(outdir)), name="outputs")
except Exception:
    # If mount fails (older Starlette or FS constraints), continue without static mount
    pass

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


@app.get("/last_report")
def last_report() -> Dict[str, Any]:
    lr = getattr(app.state, "last_report", None)
    if not lr:
        raise HTTPException(status_code=404, detail="No report yet")
    return lr


class ReverseParams(BaseModel):
    symbol: str
    horizon: int = Field(10, ge=5, le=30)
    crash_drop: float = Field(0.2, ge=0.05, le=0.60)
    top_k: int = Field(10, ge=1, le=30)


@app.post("/v1/reverse")
def reverse_endpoint(
    body: ReverseParams,
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
) -> Dict[str, Any]:
    _auth_guard(x_api_key)
    # Minimal reverse using the real pipeline pieces, single symbol flow
    df = fetch_ohlcv(body.symbol, "1d", 1200)
    feats = build_features(df)
    feats["y"] = label_crash(feats["close"], horizon=body.horizon, crash_drop=body.crash_drop)
    data = feats.dropna()
    feature_cols = [c for c in data.columns if c not in ("open", "high", "low", "volume", "y")]
    X_all = data[feature_cols]
    y_all = data["y"].astype(int)
    X_tr, y_tr, X_te, y_te = time_split(X_all, y_all)
    best_name, best_model, _ = train_select_and_evaluate(X_tr, y_tr, X_te, y_te, random_state=42)

    reverse = compute_reverse_importances(best_model, X_tr, y_tr, X_te, top_k=body.top_k)
    return {"features": reverse, "model": best_name, "explain": "Reverse feature importance"}


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)




