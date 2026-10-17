"""The linear volatility rule, as a small reusable module (fit, save, load, forecast).

Rule (the same model as 'linear on log 5/21/63-day vol' in check_vol_baselines.py):

    log(next-h-day volatility) = a + b1*log(vol_5) + b2*log(vol_21) + b3*log(vol_63)

Volatilities are in DAILY units, like vol_features.py. The result is a typical
(median-style) forecast, not a guarantee. Multiply by sqrt(252) to annualize.
"""
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from vol_features import MIN_VOL, TRADING_DAYS

RULE_INPUTS = ["vol_5", "vol_21", "vol_63"]
HORIZONS = (5, 21)
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


def rule_path(horizon: int) -> Path:
    return MODELS_DIR / f"linear_vol_h{horizon}.json"


def _logs(values) -> np.ndarray:
    return np.log(np.maximum(np.asarray(values, dtype=float), MIN_VOL))


def fit_rule(dataset: pd.DataFrame, horizon: int) -> dict:
    """Fit on every labeled row of `dataset` (from build_vol_dataset) and return the rule."""
    missing = [c for c in RULE_INPUTS + ["target_log_vol", "date"] if c not in dataset.columns]
    if missing:
        raise ValueError(f"dataset is missing columns: {missing}")
    if dataset[RULE_INPUTS + ["target_log_vol"]].isna().any().any():
        raise ValueError("dataset has missing values in the rule inputs or target")
    x = np.column_stack([_logs(dataset[c]) for c in RULE_INPUTS])
    model = LinearRegression().fit(x, dataset["target_log_vol"].to_numpy(dtype=float))
    return {
        "type": "linear rule on log vol_5, vol_21, vol_63",
        "horizon_days": int(horizon),
        "inputs": RULE_INPUTS,
        "intercept": float(model.intercept_),
        "coefficients": [float(c) for c in model.coef_],
        "min_vol": MIN_VOL,
        "fitted_rows": int(len(dataset)),
        "first_training_date": str(dataset["date"].min())[:10],
        "last_training_date": str(dataset["date"].max())[:10],
    }


def save_rule(rule: dict) -> Path:
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    path = rule_path(rule["horizon_days"])
    path.write_text(json.dumps(rule, indent=2), encoding="utf-8")
    return path


def load_rule(horizon: int) -> dict:
    path = rule_path(horizon)
    if not path.exists():
        raise FileNotFoundError(f"{path.name} not found. Run: python fit_vol_rule.py {horizon}")
    return json.loads(path.read_text(encoding="utf-8"))


def forecast_daily_vol(rule: dict, vol_5: float, vol_21: float, vol_63: float) -> float:
    """Forecast of the next-h-day realized volatility, in daily units."""
    values = [vol_5, vol_21, vol_63]
    if any(v is None or not math.isfinite(v) for v in values):
        raise ValueError("vol_5, vol_21 and vol_63 must all be finite numbers")
    log_pred = rule["intercept"] + float(np.dot(rule["coefficients"], _logs(values)))
    return float(np.exp(log_pred))


def annualize(daily_vol: float) -> float:
    return daily_vol * math.sqrt(TRADING_DAYS)