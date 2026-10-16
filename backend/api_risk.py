"""Historical risk measures for one stock, computed from stored daily closes."""
from datetime import date
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from crud import get_economic_series, get_price_history, get_stock_by_symbol
from database import get_db
from risk import RiskInputError, compute_risk

router = APIRouter(prefix="/api/stocks", tags=["Risk"])

RISK_FREE_COUNTRY = "USA"
RISK_FREE_INDICATOR = "Federal funds effective rate (%)"


class RiskResponse(BaseModel):
    symbol: str
    start_date: date
    end_date: date
    returns_used: int
    total_return: float
    annualized_return: float
    annualized_volatility: float
    max_drawdown: float
    max_drawdown_peak_date: Optional[date] = None
    max_drawdown_trough_date: Optional[date] = None
    max_drawdown_recovery_date: Optional[date] = None
    current_drawdown: float
    var_level: float
    var: float
    cvar: float
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    risk_free_used: bool
    avg_risk_free_annual: Optional[float] = None
    notes: list


@router.get("/{symbol}/risk", response_model=RiskResponse)
def stock_risk(
    symbol: str,
    window: int = Query(756, ge=60, le=2500, description="Number of most recent daily returns to use"),
    var_level: float = Query(0.95, gt=0.5, lt=1.0, description="Confidence level for VaR / CVaR"),
    db: Session = Depends(get_db),
):
    stock = get_stock_by_symbol(db, symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' is not tracked")

    prices = get_price_history(db, stock.stock_id, limit=window + 1)
    if not prices:
        raise HTTPException(status_code=404, detail=f"No price history stored for {stock.symbol} yet")

    close = pd.Series(
        [float(r.close_price) for r in prices],
        index=pd.to_datetime([r.date for r in prices]),
    )

    rf_rows = get_economic_series(db, RISK_FREE_COUNTRY, RISK_FREE_INDICATOR)
    risk_free = None
    if rf_rows:
        risk_free = pd.Series(
            [float(r.value) for r in rf_rows],
            index=pd.to_datetime([r.indicator_date for r in rf_rows]),
        )

    try:
        result = compute_risk(close, risk_free_pct=risk_free, var_level=var_level)
    except RiskInputError as error:
        raise HTTPException(status_code=422, detail=str(error))

    notes = [
        "Historical measures of the past window shown. They are not predictions or guarantees.",
        "All figures are fractions (0.10 = 10%). Volatility and returns are annualized with 252 trading days.",
        f"VaR and CVaR are the daily loss at the {int(round(var_level * 100))}% historical level, reported as positive numbers.",
        "Prices are the stored, split-adjusted closes.",
    ]
    if result["risk_free_used"]:
        notes.append(
            "Sharpe and Sortino use the monthly US federal funds rate stored from FRED as the risk-free rate, "
            "applied to each day from the latest monthly value on or before it."
        )
    else:
        notes.append("No risk-free rate is stored, so Sharpe and Sortino use 0%.")
    notes.append("Beta is not included because no market index is stored.")

    return RiskResponse(symbol=stock.symbol, notes=notes, **result)