"""Tests for features.py. They need no database and no network.

Run from the backend folder:  python test_features.py
"""
import math

import numpy as np
import pandas as pd

from features import (
    FEATURE_COLUMNS,
    TARGET_COLUMNS,
    add_target,
    build_dataset,
    build_features,
    make_labeled,
    split_dates,
    split_frame,
)
from indicators import compute_indicators

passed = 0


def check(name, condition):
    global passed
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    passed += 1
    print(f"PASS  {name}")


def close_to(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-12)


# ---------------------------------------------------------------
# 1. Hand-worked example: 10 days, every expected value computed by hand
# ---------------------------------------------------------------
prices = [100, 102, 101, 105, 107, 106, 110, 108, 112, 115]
days = pd.bdate_range("2026-01-05", periods=10)
close = pd.Series(prices, index=days, dtype=float)

f = add_target(build_features(close, None, drawdown_window=3), close, horizon=1)

check("ret_lag0 on day 4 = 105/101 - 1", close_to(f["ret_lag0"].iloc[3], 105 / 101 - 1))
check("ret_lag1 on day 4 = 101/102 - 1", close_to(f["ret_lag1"].iloc[3], 101 / 102 - 1))
check("ret_lag2 on day 4 = 102/100 - 1", close_to(f["ret_lag2"].iloc[3], 102 / 100 - 1))
check("momentum_5 on day 6 = 106/100 - 1", close_to(f["momentum_5"].iloc[5], 106 / 100 - 1))
check("drawdown (3-day) on day 3 = 101/102 - 1", close_to(f["drawdown"].iloc[2], 101 / 102 - 1))
check("drawdown is 0 on a new 3-day high (day 4)", close_to(f["drawdown"].iloc[3], 0.0))
check("target_return on day 4 = 107/105 - 1", close_to(f["target_return"].iloc[3], 107 / 105 - 1))
check("target_up is 1 when tomorrow is higher (day 4)", f["target_up"].iloc[3] == 1)
check("target_up is 0 when tomorrow is lower (day 5)", f["target_up"].iloc[4] == 0)
check("last day has no target", math.isnan(f["target_return"].iloc[-1]) and math.isnan(f["target_up"].iloc[-1]))
check("technical features are NaN without indicators", f["rsi"].isna().all())

flat = pd.Series([10, 10, 10, 11], index=pd.bdate_range("2026-02-02", periods=4), dtype=float)
check("a flat next day counts as DOWN (0)", add_target(build_features(flat, None, 3), flat)["target_up"].iloc[0] == 0)

h5 = add_target(build_features(close, None, 3), close, horizon=5)
check("5-day target on day 1 = 106/100 - 1", close_to(h5["target_return"].iloc[0], 106 / 100 - 1))
check("5-day target on day 5 = 115/107 - 1", close_to(h5["target_return"].iloc[4], 115 / 107 - 1))
check("5-day target is missing for the last 5 days", h5["target_return"].iloc[5:].isna().all())

# ---------------------------------------------------------------
# 2. Leak test: change every price AFTER day T, rebuild, compare rows up to T
# ---------------------------------------------------------------
rng = np.random.default_rng(7)
n_days, T = 400, 300
index = pd.bdate_range("2024-01-01", periods=n_days)
walk = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n_days))), index=index)

features_original = build_features(walk, compute_indicators(walk))

tampered = walk.copy()
tampered.iloc[T + 1:] = tampered.iloc[T + 1:].to_numpy() * rng.uniform(3, 9, n_days - T - 1)
features_tampered = build_features(tampered, compute_indicators(tampered))

same_up_to_T = np.allclose(
    features_original.iloc[: T + 1].to_numpy(),
    features_tampered.iloc[: T + 1].to_numpy(),
    equal_nan=True,
    rtol=1e-9,
    atol=1e-12,
)
check("features up to day T are identical after changing later prices", same_up_to_T)

differs_after_T = not np.allclose(
    features_original.iloc[T + 1:].to_numpy(),
    features_tampered.iloc[T + 1:].to_numpy(),
    equal_nan=True,
)
check("the tampering really changed later rows (the test is sensitive)", differs_after_T)

target_original = add_target(features_original, walk)["target_return"].iloc[T]
target_tampered = add_target(features_tampered, tampered)["target_return"].iloc[T]
check("the TARGET on day T does change (it is meant to look forward)", not close_to(target_original, target_tampered))

# Negative control: a deliberately leaky feature must FAIL the same test
leaky_original = walk.shift(-1) / walk - 1
leaky_tampered = tampered.shift(-1) / tampered - 1
check("a leaky feature is caught by the same test", not close_to(leaky_original.iloc[T], leaky_tampered.iloc[T]))

# ---------------------------------------------------------------
# 3. Dataset and split
# ---------------------------------------------------------------
second = pd.Series(50 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, 350))), index=pd.bdate_range("2024-03-01", periods=350))
closes = {"AAA": walk, "BBB": second}
inds = {"AAA": compute_indicators(walk), "BBB": compute_indicators(second)}
data = build_dataset(closes, inds, horizon=1)

check("dataset has date, symbol, all features and both targets",
      list(data.columns) == ["date", "symbol"] + FEATURE_COLUMNS + TARGET_COLUMNS)
check("dataset has no missing values", not data.isna().any().any())
check("target_up contains only 0 and 1", set(data["target_up"].unique()) <= {0, 1})
check("dataset is sorted by date", data["date"].is_monotonic_increasing)
check("symbol is not one of the feature columns", "symbol" not in FEATURE_COLUMNS)
check("the last day of each stock is dropped (no future price)",
      data[data["symbol"] == "AAA"]["date"].max() < walk.index[-1])

parts = split_frame(data, 0.6, 0.2, gap=1)
check("every date lies in exactly one set",
      len(set(parts["train"]["date"]) & set(parts["val"]["date"])) == 0
      and len(set(parts["val"]["date"]) & set(parts["test"]["date"])) == 0
      and len(set(parts["train"]["date"]) & set(parts["test"]["date"])) == 0)
check("train is older than validation, validation older than test",
      parts["train"]["date"].max() < parts["val"]["date"].min()
      and parts["val"]["date"].max() < parts["test"]["date"].min())

all_dates = sorted(data["date"].unique())
train_d, val_d, test_d = split_dates(all_dates, 0.6, 0.2, gap=1)
dates_between = [d for d in all_dates if train_d.max() < d < val_d.min()]
check("exactly one date is skipped between train and validation", len(dates_between) == 1)
check("the split sizes are roughly 60 / 20 / 20", abs(len(train_d) / len(all_dates) - 0.6) < 0.02)

d5 = split_dates(all_dates, 0.6, 0.2, gap=5)
check("a 5-day gap skips 5 dates between train and validation",
      len([d for d in all_dates if d5[0].max() < d < d5[1].min()]) == 5)

print(f"\nAll {passed} checks passed.")