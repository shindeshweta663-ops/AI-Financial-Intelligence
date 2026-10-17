"""Forecast of the stock's realized volatility over the next 5 or 21 trading days.

Uses the saved linear rule (models/linear_vol_h5.json, linear_vol_h21.json) and the
SAME feature code as training (vol_features.build_vol_features).
A forecast of risk level, not a price prediction and not a guarantee.
"""
import math
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from crud import get_stock_by_symbol
from database import get_db
from ml_data import US_EXCHANGES, load_stock_inputs
from vol_features import build_vol_features
from vol_rule import HORIZONS, annualize, forecast_daily_vol, load_rule

router = APIRouter(prefix="/api/stocks", tags=["Volatility Forecast"])

STALE_AFTER_DAYS = 5


class ModelInfo(BaseModel):
    type: str
    last_training_date: str
    test_r2: Optional[float] = None
    typical_error_vol_points: Optional[float] = None


class VolatilityForecastResponse(BaseModel):
    symbol: str
    as_of: date
    horizon_days: int
    forecast_volatility: float
    recent_volatility: Dict[str, float]
    model: ModelInfo
    notes: List[str]


@router.get("/{symbol}/volatility-forecast", response_model=VolatilityForecastResponse)
def volatility_forecast(
    symbol: str,
    horizon: int = Query(5, description="Trading days ahead: 5 or 21"),
    db: Session = Depends(get_db),
):
    if horizon not in HORIZONS:
        raise HTTPException(status_code=422, detail=f"horizon must be one of {list(HORIZONS)}")

    stock = get_stock_by_symbol(db, symbol)
    if stock is None:
        raise HTTPException(status_code=404, detail=f"Stock '{symbol.upper()}' is not tracked")
    if stock.exchange not in US_EXCHANGES:
        raise HTTPException(
            status_code=404,
            detail=f"No forecast for {stock.symbol}: the model was fitted on US stocks only",
        )

    inputs = load_stock_inputs(db, stock)
    if inputs is None:
        raise HTTPException(status_code=404, detail=f"No price history stored for {stock.symbol} yet")

    try:
        rule = load_rule(horizon)
    except FileNotFoundError:
        raise HTTPException(status_code=503, detail="Forecast model file is not available on the server")

    close, indicators = inputs
    latest = build_vol_features(close, indicators).iloc[-1]
    vols = {name: float(latest[name]) for name in ("vol_5", "vol_21", "vol_63")}
    if any(not math.isfinite(v) for v in vols.values()):
        raise HTTPException(status_code=422, detail=f"Not enough price history for {stock.symbol} to build the inputs")

    daily = forecast_daily_vol(rule, vols["vol_5"], vols["vol_21"], vols["vol_63"])
    as_of = close.index[-1].date()

    notes = [
        f"Forecast of the typical size of daily price swings (annualized) over the {horizon} trading days after {as_of}.",
        "It describes risk level. It is not a price prediction, not a guarantee and not financial advice.",
        "Annualized with 252 trading days. The recent figures are the stock's own past volatility over 5, 21 and 63 days.",
        "Typical error is the average miss measured on a held-out test period, in annualized volatility percentage points.",
    ]
    age = (date.today() - as_of).days
    if age > STALE_AFTER_DAYS:
        notes.append(f"The latest stored price is {age} days old, so this forecast may be out of date.")

    return VolatilityForecastResponse(
        symbol=stock.symbol,
        as_of=as_of,
        horizon_days=horizon,
        forecast_volatility=annualize(daily),
        recent_volatility={
            "5d": annualize(vols["vol_5"]),
            "21d": annualize(vols["vol_21"]),
            "63d": annualize(vols["vol_63"]),
        },
        model=ModelInfo(
            type=rule["type"],
            last_training_date=rule["last_training_date"],
            test_r2=rule.get("test_r2"),
            typical_error_vol_points=rule.get("test_mae_vol_points"),
        ),
        notes=notes,
    )