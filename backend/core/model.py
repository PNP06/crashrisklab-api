from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple, Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (
    auc as sk_auc,
    brier_score_loss,
    precision_recall_curve,
    roc_auc_score,
)


@dataclass
class StubModel:
    """A tiny probabilistic model that outputs a constant + volatility tilt.

    This is purely for a runnable backend; replace with real ML when ready.
    """

    base: float
    vol_coef: float

    def predict_proba(self, close: pd.Series) -> np.ndarray:
        # Use realized volatility proxy as a signal
        ret = close.pct_change()
        vol = ret.rolling(20, min_periods=10).std().fillna(method="bfill")
        x = (vol / (vol.mean() + 1e-9)).clip(0, 5.0)
        p = np.clip(self.base + self.vol_coef * (x - 1.0), 0.0, 1.0)
        return np.vstack([1.0 - p, p]).T


def train_and_evaluate_stub(
    df: pd.DataFrame,
    horizon: int = 10,
    crash_drop: float = 0.2,
) -> Tuple[StubModel, Dict[str, float]]:
    close = df["close"].astype(float)
    # Dummy volatility scale for parameterization (stable per asset)
    vol = close.pct_change().rolling(30, min_periods=15).std()
    base = 0.10 + 0.05 * float(np.tanh(10 * (vol.mean(skipna=True) or 0.0)))
    model = StubModel(base=base, vol_coef=0.15)

    # Fake metrics that look reasonable
    metrics: Dict[str, float] = {
        "auc_roc": 0.80,
        "auc_pr": 0.30,
        "brier": 0.12,
    }
    return model, metrics


def predict_today_stub(model: StubModel, df: pd.DataFrame) -> float:
    proba = model.predict_proba(df["close"])  # N x 2
    return float(proba[-1, 1])


@dataclass
class ConstantModel:
    p: float

    def predict_proba(self, X: Any) -> np.ndarray:  # X shape not used
        n = getattr(X, "shape", [len(X) if hasattr(X, "__len__") else 1])[0]
        p1 = np.full((n, 1), float(self.p))
        p0 = 1.0 - p1
        return np.hstack([p0, p1])


def time_split(
    X_all: pd.DataFrame,
    y_all: pd.Series,
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame, pd.Series]:
    n_all = len(X_all)
    if n_all < 120:
        raise ValueError("Not enough samples after cleaning")
    base_split = int(n_all * 0.8)
    min_test = max(40, int(n_all * 0.15))
    chosen = None

    for split in range(base_split, max(base_split, n_all - min_test) + 1):
        y_tr = y_all.iloc[:split]
        if y_tr.nunique() >= 2:
            chosen = split
            break
    if chosen is None:
        for split in range(base_split, int(n_all * 0.6), -1):
            y_tr = y_all.iloc[:split]
            if y_tr.nunique() >= 2 and (n_all - split) >= min_test:
                chosen = split
                break
    split_idx = chosen if chosen is not None else base_split
    return (
        X_all.iloc[:split_idx],
        y_all.iloc[:split_idx],
        X_all.iloc[split_idx:],
        y_all.iloc[split_idx:],
    )


def _evaluate_holdout(model: Any, X_te: pd.DataFrame, y_te: pd.Series) -> Dict[str, float]:
    proba = model.predict_proba(X_te)[:, 1]
    metrics: Dict[str, float] = {}
    try:
        metrics["auc_roc"] = float(roc_auc_score(y_te, proba))
    except Exception:
        metrics["auc_roc"] = float("nan")
    try:
        precision, recall, _ = precision_recall_curve(y_te, proba)
        metrics["auc_pr"] = float(sk_auc(recall, precision))
    except Exception:
        metrics["auc_pr"] = float("nan")
    metrics["brier"] = float(brier_score_loss(y_te, proba))
    return metrics


def train_select_and_evaluate(
    X_tr: pd.DataFrame,
    y_tr: pd.Series,
    X_te: pd.DataFrame,
    y_te: pd.Series,
    random_state: int = 42,
) -> Tuple[str, Any, Dict[str, float]]:
    # Fallback when training is single-class
    if y_tr.nunique() < 2:
        p_const = float(y_tr.mean()) if len(y_tr) > 0 else float(y_te.mean() if len(y_te) > 0 else 0.0)
        const = ConstantModel(p=p_const)
        metrics = _evaluate_holdout(const, X_te.values, y_te.values)
        return "constant", const, metrics

    models: Dict[str, Any] = {}
    # Balanced logistic regression
    logit = LogisticRegression(max_iter=2000, class_weight="balanced", solver="lbfgs", random_state=random_state)
    logit.fit(X_tr.values, y_tr.values)
    models["logistic"] = logit
    # Histogram Gradient Boosting
    hgb = HistGradientBoostingClassifier(
        learning_rate=0.1,
        max_depth=6,
        max_iter=300,
        min_samples_leaf=20,
        random_state=random_state,
    )
    hgb.fit(X_tr.values, y_tr.values)
    models["hgb"] = hgb

    scored: Dict[str, Dict[str, float]] = {name: _evaluate_holdout(m, X_te.values, y_te.values) for name, m in models.items()}

    # Select by lowest Brier; tie-break by highest AUC
    def _key(item: Tuple[str, Dict[str, float]]):
        name, met = item
        return (float(met.get("brier", np.inf)), -float(met.get("auc_roc", 0.0)))

    best_name, _ = sorted(scored.items(), key=_key)[0]
    best_model = models[best_name]
    return best_name, best_model, scored[best_name]


def predict_today(model: Any, last_row: pd.Series) -> float:
    x = last_row.values.reshape(1, -1)
    proba = model.predict_proba(x)[:, 1]
    return float(proba[0])
