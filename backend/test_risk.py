"""Tests for risk.py using small series whose answers can be worked out by hand.

Run from the backend folder:  python test_risk.py
No database or network is used.
"""
import math
import sys

import numpy as np
import pandas as pd

from risk import RiskInputError, compute_risk

failures = []


def check(ok: bool, message: str) -> None:
    print(("  PASS  " if ok else "  FAIL  ") + message)
    if not ok:
        failures.append(message)


def close_from_returns(returns) -> pd.Series:
    values = 100.0 * np.concatenate([[1.0], np.cumprod(1.0 + np.asarray(returns, dtype=float))])
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))


def short_series(values) -> pd.Series:
    return pd.Series(values, index=pd.bdate_range("2024-01-01", periods=len(values)))


print("=== 1. Steady growth of 0.1% per day ===")
r = compute_risk(close_from_returns([0.001] * 100))
check(r["returns_used"] == 100, "100 returns used")
check(abs(r["annualized_return"] - (1.001 ** 252 - 1)) < 1e-9, "annualized return = 1.001^252 - 1")
check(r["annualized_volatility"] < 1e-10, "volatility is zero")
check(abs(r["max_drawdown"]) < 1e-12 and r["max_drawdown_trough_date"] is None, "no drawdown, no dates")
check(r["sharpe_ratio"] is None and r["sortino_ratio"] is None, "Sharpe and Sortino undefined with zero risk")

print("\n=== 2. Drawdown with recovery: 100, 120, 90, 100, 130 ===")
s = short_series([100, 120, 90, 100, 130])
r = compute_risk(s, min_returns=3)
check(abs(r["total_return"] - 0.30) < 1e-12, "total return = 30%")
check(abs(r["max_drawdown"] - (-0.25)) < 1e-12, "max drawdown = 90/120 - 1 = -25%")
check(r["max_drawdown_peak_date"] == s.index[1].date(), "peak is the 120 day")
check(r["max_drawdown_trough_date"] == s.index[2].date(), "trough is the 90 day")
check(r["max_drawdown_recovery_date"] == s.index[4].date(), "recovered on the 130 day")
check(abs(r["current_drawdown"]) < 1e-12, "currently at a new high")

print("\n=== 3. Drawdown not yet recovered: 100, 120, 90, 100 ===")
r = compute_risk(short_series([100, 120, 90, 100]), min_returns=3)
check(r["max_drawdown_recovery_date"] is None, "no recovery date")
check(abs(r["current_drawdown"] - (100 / 120 - 1)) < 1e-12, "current drawdown = 100/120 - 1")

print("\n=== 4. VaR and CVaR on evenly spaced returns from -2% to +2% ===")
r = compute_risk(close_from_returns(np.linspace(-0.02, 0.02, 100)))
check(abs(r["var"] - 0.018) < 1e-9, "95% VaR = 1.8%")
check(abs(r["cvar"] - (0.02 - 2 * 0.04 / 99)) < 1e-9, "95% CVaR = mean of the worst 5 days")

print("\n=== 5. Sharpe and Sortino with a 2.52% risk-free rate ===")
returns = [0.01, -0.005] * 50
close = close_from_returns(returns)
rf = pd.Series([2.52], index=[close.index[0]])
r = compute_risk(close, risk_free_pct=rf)
expected_sharpe = 0.0024 / (0.0075 * math.sqrt(100 / 99)) * math.sqrt(252)
expected_sortino = 0.0024 / (0.0051 * math.sqrt(0.5)) * math.sqrt(252)
check(r["risk_free_used"] and abs(r["avg_risk_free_annual"] - 0.0252) < 1e-12, "risk-free rate used (2.52%)")
check(abs(r["sharpe_ratio"] - expected_sharpe) < 1e-6, f"Sharpe = {expected_sharpe:.4f}")
check(abs(r["sortino_ratio"] - expected_sortino) < 1e-6, f"Sortino = {expected_sortino:.4f}")

r = compute_risk(close)
expected_no_rf = 0.0025 / (0.0075 * math.sqrt(100 / 99)) * math.sqrt(252)
check(not r["risk_free_used"] and abs(r["sharpe_ratio"] - expected_no_rf) < 1e-6, "without a rate, Sharpe uses 0%")

print("\n=== 6. Bad input is rejected with a clear error ===")
for label, bad in [
    ("too few returns", close_from_returns([0.01] * 10)),
    ("non-positive close", short_series([100, 0, 100, 100, 100])),
    ("unsorted dates", short_series([100, 101, 102, 103, 104]).iloc[::-1]),
    ("not a date index", pd.Series([100.0, 101.0, 102.0, 103.0, 104.0])),
]:
    try:
        compute_risk(bad, min_returns=3) if label != "too few returns" else compute_risk(bad)
        check(False, f"{label} should have raised an error")
    except RiskInputError as error:
        check(True, f"{label}: {error}")

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED")
    sys.exit(1)
print("All checks passed. No database or network was used.")