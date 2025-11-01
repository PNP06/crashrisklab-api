from __future__ import annotations

from typing import List, Literal

import numpy as np
import pandas as pd
import ccxt
import os
from .utils import LOGGER

_CB_STATE: dict[tuple[str, str], dict[str, float]] = {}


def synth_ohlcv(symbol: str, timeframe: Literal["1d", "1h", "4h"] = "1d", lookback: int = 1200) -> pd.DataFrame:
    """Create a deterministic synthetic OHLCV frame for testing.

    - Index: UTC date range of length `lookback`.
    - Columns: open, high, low, close, volume (floats)
    """
    rng = np.random.default_rng(abs(hash((symbol, timeframe))) % (2**32))
    if timeframe == "1d":
        idx = pd.date_range(end=pd.Timestamp.utcnow().normalize(), periods=lookback, freq="D", tz="UTC")
    else:
        # Approximate intraday
        idx = pd.date_range(end=pd.Timestamp.utcnow(), periods=lookback, freq="H", tz="UTC")

    # Random walk for close
    steps = rng.normal(loc=0.0, scale=0.01, size=len(idx))
    close = 100.0 * (1.0 + steps).cumprod()
    high = close * (1.0 + rng.normal(0.002, 0.002, len(idx)).clip(0, 0.01))
    low = close * (1.0 - rng.normal(0.002, 0.002, len(idx)).clip(0, 0.01))
    open_ = close / (1.0 + rng.normal(0.0005, 0.002, len(idx)))
    volume = rng.lognormal(mean=10.0, sigma=0.25, size=len(idx))

    df = pd.DataFrame(
        {
            "open": open_.astype(float),
            "high": high.astype(float),
            "low": low.astype(float),
            "close": close.astype(float),
            "volume": volume.astype(float),
        },
        index=idx,
    )
    return df


def fetch_ohlcv(symbol: str, timeframe: str, lookback: int) -> pd.DataFrame:
    """Fetch OHLCV from Binance via ccxt with enableRateLimit.

    Returns UTC-indexed DataFrame [open, high, low, close, volume] of length up to `lookback`.
    """
    exchange = ccxt.binance({"enableRateLimit": True})
    try:
        timeout_ms = int(os.environ.get("CCXT_TIMEOUT_MS", "15000") or "15000")
        exchange.timeout = timeout_ms
    except Exception:
        pass
    limit = 1000
    tf_ms = exchange.parse_timeframe(timeframe) * 1000

    approx_days = int(lookback * 1.2)
    since_dt = pd.Timestamp.utcnow() - pd.Timedelta(days=approx_days)
    since_ms = int(since_dt.timestamp() * 1000)

    rows: List[List[float]] = []
    key = (symbol.upper(), timeframe)
    state = _CB_STATE.setdefault(key, {"fails": 0.0, "ts": 0.0})
    if state["fails"] >= 5:
        raise RuntimeError(f"circuit-open {symbol} {timeframe}")

    attempts = 0
    while True:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit)
        except Exception as e:
            attempts += 1
            state["fails"] += 1
            back = min(4, attempts)
            LOGGER.warning("ccxt_fetch_fail symbol=%s tf=%s attempt=%s err=%s", symbol, timeframe, attempts, type(e).__name__)
            if attempts >= 3:
                raise
            # exponential backoff (1s,2s,4s)
            cc = back
            import time as _t

            _t.sleep(cc)
            continue
        if not batch:
            break
        rows.extend(batch)
        since_ms = batch[-1][0] + tf_ms
        if len(batch) < limit:
            break
        if len(rows) >= lookback + 2000:
            break
    # reset fails on success
    state["fails"] = 0.0

    if not rows:
        raise RuntimeError(f"No OHLCV for {symbol} {timeframe}")

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])  # type: ignore
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates("timestamp").sort_values("timestamp").set_index("timestamp")
    df = df.tail(lookback)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna()
    return df


def compute_rsi_wilder(close: pd.Series, length: int = 15) -> pd.Series:
    close = close.astype(float)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def label_crash(close: pd.Series, horizon: int = 10, crash_drop: float = 0.20) -> pd.Series:
    close = close.astype(float)
    min_future = close.shift(-1).rolling(window=horizon, min_periods=horizon).min()
    fut_dd = (min_future / close) - 1.0
    y = (fut_dd <= (-crash_drop)).astype(float)
    y[pd.isna(fut_dd)] = np.nan
    return y


def _rolling_annualized_vol(returns: pd.Series, window: int) -> pd.Series:
    return returns.rolling(window=window, min_periods=window).std() * np.sqrt(365)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build interpretable time-t features using only info up to and including t."""
    out = df.copy()
    close = out["close"].astype(float)
    ret = close.pct_change()

    # Returns
    out["ret_1d"] = ret
    out["ret_5d"] = close.pct_change(5)
    out["ret_10d"] = close.pct_change(10)

    # Volatility
    out["vol_20"] = _rolling_annualized_vol(ret, 20)
    out["vol_60"] = _rolling_annualized_vol(ret, 60)

    # Higher moments on returns
    out["skew_20"] = ret.rolling(20, min_periods=20).skew()
    out["kurt_20"] = ret.rolling(20, min_periods=20).kurt()

    # Momentum / overbought
    out["rsi_15"] = compute_rsi_wilder(close, 15)
    out["mom_14"] = close.pct_change(14)

    # Trend / distances
    sma50 = close.rolling(50, min_periods=50).mean()
    sma200 = close.rolling(200, min_periods=200).mean()
    out["dist_sma50"] = (close / sma50) - 1.0
    out["dist_sma200"] = (close / sma200) - 1.0
    out["ma50_above_ma200"] = (sma50 > sma200).astype(float)

    # Drawdown context
    rolling_high_90 = close.rolling(90, min_periods=90).max()
    out["dd_from_90h"] = (close / rolling_high_90) - 1.0

    # Slopes (first difference) of MAs
    out["slope_ma20"] = close.rolling(20, min_periods=20).mean().diff()
    out["slope_ma50"] = sma50.diff()

    return out
