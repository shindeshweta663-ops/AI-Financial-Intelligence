"""Phase 10, volatility version: extra features and the forward-volatility target.

New module. It reuses features.py and does not change it.

TARGET: the realized volatility of the NEXT `horizon` trading days:
    target_vol     = sqrt( mean( r(T+1)^2 ... r(T+horizon)^2 ) )   (daily units)
    target_log_vol = log(target_vol)                              (what the models predict)
where r(t) = close(t) / close(t-1) - 1. It uses only returns AFTER day T.
Multiply target_vol by sqrt(252) to get an annualized figure.

THE ONE RULE (same as features.py): features in the row for day T use only
information available at the close of day T. The targets are the only columns
that look forward, and they are never features.
"""
from typing import Dict, Optional

import numpy as np
import pandas as pd

from features import FEATURE_COLUMNS, _check_close, build_features

VOL_EXTRA_FEATURES = ["abs_ret_lag0", "abs_ret_lag1", "abs_ret_lag2", "vol_63"]
VOL_FEATURE_COLUMNS = FEATURE_COLUMNS + VOL_EXTRA_FEATURES
VOL_TARGET_COLUMNS = ["target_vol", "target_log_vol"]

MIN_VOL = 1e-6          # avoids log(0) if every future return were exactly zero
TRADING_DAYS = 252


def build_vol_features(close: pd.Series, indicators: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Groups A-C plus a few volatility-specific features. Early rows are NaN (warm-up)."""
    base = build_features(close, indicators)
    close = _check_close(close)
    daily = close.pct_change()

    out = base.copy()
    for k in range(3):
        out[f"abs_ret_lag{k}"] = daily.abs().shift(k)             # lag0 = today
    out["vol_63"] = daily.rolling(63, min_periods=63).std()       # about 3 months
    return out[VOL_FEATURE_COLUMNS]


def add_vol_target(features: pd.DataFrame, close: pd.Series, horizon: int = 5) -> pd.DataFrame:
    """Append target_vol and target_log_vol. These look FORWARD and are never features.

    For row T the window is the returns of days T+1 ... T+horizon, so today's own
    return r(T) is NOT part of the target. The last `horizon` rows have no target.
    """
    if horizon < 2:
        raise ValueError("horizon must be at least 2 trading days")
    close = _check_close(close)
    returns = close.pct_change().to_numpy()
    n = len(returns)

    target = np.full(n, np.nan)
    for t in range(n - horizon):
        window = returns[t + 1: t + 1 + horizon]       # strictly after day t
        if not np.isnan(window).any():
            target[t] = np.sqrt(np.mean(window ** 2))

    out = features.copy()
    out["target_vol"] = pd.Series(target, index=close.index)
    out["target_log_vol"] = np.log(np.maximum(out["target_vol"], MIN_VOL)).where(out["target_vol"].notna())
    return out


def make_vol_labeled(table: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with any missing feature or target (never fill them with 0)."""
    return table.dropna(subset=VOL_FEATURE_COLUMNS + VOL_TARGET_COLUMNS).copy()


def build_vol_dataset(
    closes: Dict[str, pd.Series],
    indicators: Dict[str, pd.DataFrame],
    horizon: int = 5,
) -> pd.DataFrame:
    """Pooled table for all stocks: columns date, symbol, features, volatility targets."""
    parts = []
    for symbol, close in closes.items():
        table = add_vol_target(build_vol_features(close, indicators.get(symbol)), close, horizon)
        table = make_vol_labeled(table)
        table.insert(0, "symbol", symbol)
        table.index.name = "date"
        parts.append(table.reset_index())
    if not parts:
        raise ValueError("no stocks given")
    dataset = pd.concat(parts, ignore_index=True)
    return dataset.sort_values(["date", "symbol"]).reset_index(drop=True)