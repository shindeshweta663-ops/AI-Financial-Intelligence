"""Tests for vol_features.py. They need no database and no network.

Run from the backend folder:  python test_vol_features.py
"""
import math

import numpy as np
import pandas as pd

from features import split_dates, split_frame
from indicators import compute_indicators
from vol_features import (
    VOL_FEATURE_COLUMNS,
    VOL_TARGET_COLUMNS,
    add_vol_target,
    build_vol_dataset,
    build_vol_features,
)

passed = 0


def check(name, condition):
    global passed
    if not condition:
        raise AssertionError(f"FAILED: {name}")
    passed += 1
    print(f"PASS  {name}")


def close_to(a, b):
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-15)


# ---------------------------------------------------------------
# 1. Hand-worked example
# ---------------------------------------------------------------
prices = [100, 102, 101, 105, 107, 106]
days = pd.bdate_range("2026-01-05", periods=6)
close = pd.Series(prices, index=days, dtype=float)
r = [None, 102 / 100 - 1, 101 / 102 - 1, 105 / 101 - 1, 107 / 105 - 1, 106 / 107 - 1]   # r[i] = return of day i

f = add_vol_target(build_vol_features(close), close, horizon=2)

expected_day0 = math.sqrt((r[1] ** 2 + r[2] ** 2) / 2)
expected_day1 = math.sqrt((r[2] ** 2 + r[3] ** 2) / 2)
expected_day3 = math.sqrt((r[4] ** 2 + r[5] ** 2) / 2)
check("target on day 1 = sqrt(mean(r2^2, r3^2)) [returns of days 2 and 3]", close_to(f["target_vol"].iloc[0], expected_day0))
check("target on day 2 = sqrt(mean(r3^2, r4^2))", close_to(f["target_vol"].iloc[1], expected_day1))
check("target on day 4 = sqrt(mean(r5^2, r6^2))", close_to(f["target_vol"].iloc[3], expected_day3))
wrong_with_today = math.sqrt((r[1] ** 2 + r[2] ** 2 + r[3] ** 2) / 3)
check("today's own return is NOT part of its target", not close_to(f["target_vol"].iloc[1], wrong_with_today))
check("the last 2 days have no target", f["target_vol"].iloc[-2:].isna().all() and f["target_vol"].iloc[:-2].notna().all())
check("target_log_vol = log(target_vol)", close_to(f["target_log_vol"].iloc[0], math.log(expected_day0)))
check("annualizing multiplies by sqrt(252)", close_to(expected_day0 * math.sqrt(252), math.sqrt(252) * f["target_vol"].iloc[0]))

# ---------------------------------------------------------------
# 2. Leak tests
# ---------------------------------------------------------------
rng = np.random.default_rng(5)
n_days, T = 400, 300
index = pd.bdate_range("2024-01-01", periods=n_days)
walk = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0003, 0.012, n_days))), index=index)

original = build_vol_features(walk, compute_indicators(walk))

tampered = walk.copy()
tampered.iloc[T + 1:] = tampered.iloc[T + 1:].to_numpy() * rng.uniform(3, 9, n_days - T - 1)
after = build_vol_features(tampered, compute_indicators(tampered))

check("features up to day T are identical after changing later prices",
      np.allclose(original.iloc[: T + 1].to_numpy(), after.iloc[: T + 1].to_numpy(), equal_nan=True, rtol=1e-9, atol=1e-12))
check("the tampering really changed later rows (the test is sensitive)",
      not np.allclose(original.iloc[T + 1:].to_numpy(), after.iloc[T + 1:].to_numpy(), equal_nan=True))

target_a = add_vol_target(original, walk, 5)["target_vol"].iloc[T]
target_b = add_vol_target(after, tampered, 5)["target_vol"].iloc[T]
check("the TARGET on day T does change (it is meant to look forward)", not close_to(target_a, target_b))

# Changing prices BEFORE day T must not change the target at T
past_changed = walk.copy()
past_changed.iloc[:T] = past_changed.iloc[:T].to_numpy() * 1.7
target_c = add_vol_target(build_vol_features(past_changed), past_changed, 5)["target_vol"].iloc[T]
check("the target on day T does not depend on earlier prices", close_to(target_a, target_c))

# Negative control: forward volatility used as a FEATURE would be caught by the same test
leaky_a = add_vol_target(original, walk, 5)["target_vol"]
leaky_b = add_vol_target(after, tampered, 5)["target_vol"]
check("a leaky (forward-looking) feature is caught by the same test", not close_to(leaky_a.iloc[T], leaky_b.iloc[T]))

# ---------------------------------------------------------------
# 3. Dataset and split
# ---------------------------------------------------------------
second = pd.Series(50 * np.exp(np.cumsum(rng.normal(0.0002, 0.015, 350))), index=pd.bdate_range("2024-03-01", periods=350))
closes = {"AAA": walk, "BBB": second}
inds = {"AAA": compute_indicators(walk), "BBB": compute_indicators(second)}
data = build_vol_dataset(closes, inds, horizon=5)

check("dataset columns are date, symbol, features, targets",
      list(data.columns) == ["date", "symbol"] + VOL_FEATURE_COLUMNS + VOL_TARGET_COLUMNS)
check("dataset has no missing values", not data.isna().any().any())
check("targets are positive and finite", bool((data["target_vol"] > 0).all()) and np.isfinite(data["target_log_vol"]).all())
check("feature names are unique and contain no target", len(set(VOL_FEATURE_COLUMNS)) == len(VOL_FEATURE_COLUMNS)
      and not set(VOL_FEATURE_COLUMNS) & set(VOL_TARGET_COLUMNS) and "symbol" not in VOL_FEATURE_COLUMNS)
check("dataset is sorted by date", data["date"].is_monotonic_increasing)
check("the last 5 days of each stock are dropped",
      data[data["symbol"] == "AAA"]["date"].max() <= walk.index[-6])

parts = split_frame(data, 0.6, 0.2, gap=5)
check("train is older than validation, validation older than test",
      parts["train"]["date"].max() < parts["val"]["date"].min() and parts["val"]["date"].max() < parts["test"]["date"].min())
all_dates = sorted(data["date"].unique())
tr, va, te = split_dates(all_dates, 0.6, 0.2, gap=5)
check("5 dates are skipped between train and validation", len([d for d in all_dates if tr.max() < d < va.min()]) == 5)
check("the last training target ends before validation starts",
      all_dates.index(va.min()) - all_dates.index(tr.max()) > 5)

try:
    add_vol_target(build_vol_features(walk), walk, horizon=1)
    check("horizon 1 is rejected", False)
except ValueError:
    check("horizon 1 is rejected", True)

print(f"\nAll {passed} checks passed.")
