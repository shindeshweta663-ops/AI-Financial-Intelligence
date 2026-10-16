"""Historical risk measures from daily closing prices.

Pure calculation: no database and no network. Every number describes the PAST
window that was passed in. They are analytical measures, not predictions or
guarantees. Results are fractions (0.10 = 10%).
"""
from typing import Optional

import numpy as np
import pandas as pd

TRADING_DAYS = 252
MIN_RETURNS = 60
FLAT_TOLERANCE = 1e-10   # a std or downside deviation below this counts as zero


class RiskInputError(ValueError):
    """The price data cannot be used for risk calculations."""


def _clean_close(close) -> pd.Series:
    if not isinstance(close, pd.Series) or not isinstance(close.index, pd.DatetimeIndex):
        raise RiskInputError("close must be a pandas Series with a date index")
    close = close.astype(float)
    if close.isna().any() or not np.isfinite(close).all() or (close <= 0).any():
        raise RiskInputError("close prices must be finite and positive")
    if close.index.has_duplicates or not close.index.is_monotonic_increasing:
        raise RiskInputError("dates must be unique and in ascending order")
    return close


def _align_risk_free(rf_pct: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """Annual risk-free rate (percent) -> annual fraction on each trading day.

    Each day uses the latest rate dated on or before it; days before the first
    rate use the first rate.
    """
    rf_pct = rf_pct.sort_index()
    combined = rf_pct.reindex(rf_pct.index.union(index)).ffill().bfill()
    return combined.reindex(index) / 100.0


def compute_risk(
    close: pd.Series,
    risk_free_pct: Optional[pd.Series] = None,
    var_level: float = 0.95,
    min_returns: int = MIN_RETURNS,
) -> dict:
    """Return historical risk measures for one price series."""
    close = _clean_close(close)
    if not 0 < var_level < 1:
        raise RiskInputError("var_level must be between 0 and 1")

    returns = close.pct_change().dropna()
    n = len(returns)
    if n < min_returns:
        raise RiskInputError(f"Need at least {min_returns} daily returns, got {n}")

    years = n / TRADING_DAYS
    total_return = float(close.iloc[-1] / close.iloc[0] - 1.0)
    annualized_return = float((1.0 + total_return) ** (1.0 / years) - 1.0)
    annualized_vol = float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS))

    # drawdown: fall from the highest close so far
    drawdown = close / close.cummax() - 1.0
    max_dd = float(drawdown.min())
    peak_date = trough_date = recovery_date = None
    if max_dd < 0:
        trough = drawdown.idxmin()
        peak = close.loc[:trough].idxmax()
        after = close.loc[trough:]
        recovered = after[after >= close.loc[peak]]
        peak_date, trough_date = peak.date(), trough.date()
        recovery_date = recovered.index[0].date() if len(recovered) else None

    # historical value at risk and expected shortfall (reported as positive losses)
    cut = float(np.quantile(returns.to_numpy(), 1.0 - var_level))
    var = -cut
    cvar = -float(returns[returns <= cut].mean())

    # Sharpe and Sortino on daily excess returns over the risk-free rate
    risk_free_used = False
    avg_rf = None
    rf_daily = pd.Series(0.0, index=returns.index)
    if risk_free_pct is not None and len(risk_free_pct.dropna()) > 0:
        annual = _align_risk_free(risk_free_pct.dropna(), returns.index)
        rf_daily = annual / TRADING_DAYS
        avg_rf = float(annual.mean())
        risk_free_used = True

    excess = returns - rf_daily
    mean_excess = float(excess.mean())
    std_excess = float(excess.std(ddof=1))
    downside_dev = float(np.sqrt((np.minimum(excess, 0.0) ** 2).mean()))
    sharpe = mean_excess / std_excess * np.sqrt(TRADING_DAYS) if std_excess > FLAT_TOLERANCE else None
    sortino = mean_excess / downside_dev * np.sqrt(TRADING_DAYS) if downside_dev > FLAT_TOLERANCE else None

    return {
        "start_date": close.index[0].date(),
        "end_date": close.index[-1].date(),
        "returns_used": n,
        "total_return": total_return,
        "annualized_return": annualized_return,
        "annualized_volatility": annualized_vol,
        "max_drawdown": max_dd,
        "max_drawdown_peak_date": peak_date,
        "max_drawdown_trough_date": trough_date,
        "max_drawdown_recovery_date": recovery_date,
        "current_drawdown": float(drawdown.iloc[-1]),
        "var_level": var_level,
        "var": float(var),
        "cvar": float(cvar),
        "sharpe_ratio": None if sharpe is None else float(sharpe),
        "sortino_ratio": None if sortino is None else float(sortino),
        "risk_free_used": risk_free_used,
        "avg_risk_free_annual": avg_rf,
    }