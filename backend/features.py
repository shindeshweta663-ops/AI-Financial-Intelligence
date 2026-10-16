"""Feature engineering for Phase 10: groups A (returns), B (technical), C (drawdown),
the prediction target, and the date-based train/validation/test split.

Everything here is a pure function: pandas objects in, pandas objects out.
No database access and no API calls, so it can be tested with small examples.

THE ONE RULE: a feature in the row for trading day T may use only information that
was available at the close of day T. The target columns are the only values that
look forward (they use the close of day T + horizon), and they are never features.
"""
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

RETURN_LAGS = 5                     # ret_lag0 (today's return) ... ret_lag4
MOMENTUM_WINDOWS = (5, 10, 21)      # trading days
VOLATILITY_WINDOWS = (5, 21)        # trading days
DRAWDOWN_WINDOW = 63                # trading days (about 3 months)

RETURN_FEATURES = [f"ret_lag{k}" for k in range(RETURN_LAGS)]
MOMENTUM_FEATURES = [f"momentum_{w}" for w in MOMENTUM_WINDOWS]
VOLATILITY_FEATURES = [f"vol_{w}" for w in VOLATILITY_WINDOWS]
DRAWDOWN_FEATURES = ["drawdown"]
TECHNICAL_FEATURES = [
    "rsi",
    "macd_pct",
    "macd_hist_pct",
    "close_vs_sma20",
    "close_vs_ema20",
    "ema20_vs_ema50",
    "volatility_stored",
]

FEATURE_COLUMNS = (
    RETURN_FEATURES
    + MOMENTUM_FEATURES
    + VOLATILITY_FEATURES
    + DRAWDOWN_FEATURES
    + TECHNICAL_FEATURES
)
TARGET_COLUMNS = ["target_return", "target_up"]


def _check_close(close: pd.Series) -> pd.Series:
    if not isinstance(close.index, pd.DatetimeIndex):
        raise ValueError("close must be indexed by dates (a DatetimeIndex)")
    if close.index.has_duplicates or not close.index.is_monotonic_increasing:
        raise ValueError("close dates must be unique and sorted oldest first")
    close = close.astype(float)
    if close.isna().any() or (close <= 0).any():
        raise ValueError("close prices must be positive numbers with no gaps")
    return close


def build_features(
    close: pd.Series,
    indicators: Optional[pd.DataFrame] = None,
    drawdown_window: int = DRAWDOWN_WINDOW,
) -> pd.DataFrame:
    """Feature table with the same dates as `close`. Early rows are NaN (warm-up).

    close       daily closing prices, oldest first, indexed by date.
    indicators  optional table indexed by date with columns rsi, macd, macd_signal,
                ema20, ema50, sma20, volatility (the stored technical indicators).
                Without it the technical features are NaN.
    """
    close = _check_close(close)
    daily = close.pct_change()
    out = pd.DataFrame(index=close.index)

    # --- Group A: returns, momentum, rolling volatility (price only) ---
    for k in range(RETURN_LAGS):
        out[f"ret_lag{k}"] = daily.shift(k)          # lag0 = today's return
    for w in MOMENTUM_WINDOWS:
        out[f"momentum_{w}"] = close / close.shift(w) - 1
    for w in VOLATILITY_WINDOWS:
        out[f"vol_{w}"] = daily.rolling(w, min_periods=w).std()

    # --- Group C: drawdown from the recent peak (price only) ---
    recent_peak = close.rolling(drawdown_window, min_periods=drawdown_window).max()
    out["drawdown"] = close / recent_peak - 1

    # --- Group B: technical indicators, turned into scale-free ratios ---
    for column in TECHNICAL_FEATURES:
        out[column] = np.nan
    if indicators is not None:
        ind = indicators.reindex(close.index).astype(float)
        out["rsi"] = ind["rsi"]
        out["macd_pct"] = ind["macd"] / close
        out["macd_hist_pct"] = (ind["macd"] - ind["macd_signal"]) / close
        out["close_vs_sma20"] = close / ind["sma20"] - 1
        out["close_vs_ema20"] = close / ind["ema20"] - 1
        out["ema20_vs_ema50"] = ind["ema20"] / ind["ema50"] - 1
        out["volatility_stored"] = ind["volatility"]

    return out[FEATURE_COLUMNS]


def add_target(features: pd.DataFrame, close: pd.Series, horizon: int = 1) -> pd.DataFrame:
    """Append the two target columns. These look FORWARD and are never features.

    target_return  close(T + horizon) / close(T) - 1
    target_up      1 if target_return > 0, else 0 (a flat day counts as 0)
    The last `horizon` rows have no future price, so both are NaN there.
    """
    if horizon < 1:
        raise ValueError("horizon must be at least 1 trading day")
    close = _check_close(close)
    future_return = close.shift(-horizon) / close - 1
    out = features.copy()
    out["target_return"] = future_return
    out["target_up"] = (future_return > 0).astype(float).where(future_return.notna())
    return out


def make_labeled(table: pd.DataFrame) -> pd.DataFrame:
    """Drop rows with any missing feature or target (never fill them with 0)."""
    clean = table.dropna(subset=FEATURE_COLUMNS + TARGET_COLUMNS).copy()
    clean["target_up"] = clean["target_up"].astype(int)
    return clean


def build_dataset(
    closes: Dict[str, pd.Series],
    indicators: Dict[str, pd.DataFrame],
    horizon: int = 1,
) -> pd.DataFrame:
    """Pooled table for all stocks: columns date, symbol, features, targets."""
    parts = []
    for symbol, close in closes.items():
        table = add_target(build_features(close, indicators.get(symbol)), close, horizon)
        table = make_labeled(table)
        table.insert(0, "symbol", symbol)
        table.index.name = "date"
        parts.append(table.reset_index())
    if not parts:
        raise ValueError("no stocks given")
    dataset = pd.concat(parts, ignore_index=True)
    return dataset.sort_values(["date", "symbol"]).reset_index(drop=True)


def split_dates(dates, train_frac: float = 0.6, val_frac: float = 0.2, gap: int = 1) -> Tuple:
    """Cut the sorted unique dates into train / validation / test, oldest to newest.

    `gap` dates are skipped between the sets. Use gap = horizon, because the target
    of the last training day uses prices up to `horizon` days later.
    """
    if gap < 0:
        raise ValueError("gap cannot be negative")
    unique = pd.Index(sorted(set(pd.to_datetime(list(dates)))))
    n = len(unique)
    train_end = int(n * train_frac)
    val_end = int(n * (train_frac + val_frac))
    train = unique[:train_end]
    val = unique[train_end + gap:val_end]
    test = unique[val_end + gap:]
    if min(len(train), len(val), len(test)) == 0:
        raise ValueError("not enough dates for this split")
    return train, val, test


def split_frame(dataset: pd.DataFrame, train_frac: float = 0.6, val_frac: float = 0.2, gap: int = 1) -> Dict[str, pd.DataFrame]:
    """Split a pooled dataset by date. Every stock uses the same cut dates."""
    train, val, test = split_dates(dataset["date"], train_frac, val_frac, gap)
    return {
        "train": dataset[dataset["date"].isin(train)],
        "val": dataset[dataset["date"].isin(val)],
        "test": dataset[dataset["date"].isin(test)],
    }