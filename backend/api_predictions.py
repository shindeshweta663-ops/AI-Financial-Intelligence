"""Prediction endpoints for the dashboard's "Stock Prediction" page (Phase 15).

GET  /api/predictions/config    -> {"horizons": [5, 21]}
POST /api/predictions/forecast  -> forecast for one stock (login required)
GET  /api/predictions/history   -> the user's saved forecasts (currently always empty)
POST /api/predictions/history   -> not available yet (needs a database change)

HONESTY NOTE. Our research found no reliable signal in future price DIRECTION,
so this does NOT predict a price. What the model can forecast is VOLATILITY
(how big the daily swings are likely to be). The page requires a numeric
"predicted_price", so we return the last close as a central, no-direction
estimate (expected return 0%) and put the real information in the range:
a lognormal range with no drift whose width comes from the forecast
volatility. Nothing here says a price will rise or fall.
"""
import math
from datetime import date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

import crud
from api_volatility import volatility_forecast
from auth import get_current_user
from database import get_db
from vol_rule import HORIZONS

router = APIRouter(prefix="/api/predictions", tags=["predictions"])

Z80 = 1.2816  # one-sided z for an 80% central range


class ConfigOut(BaseModel):
    horizons: List[int]


class ForecastRequest(BaseModel):
    symbol: str
    horizon_days: int


class PathPoint(BaseModel):
    date: str
    price: float
    lower: float
    upper: float


class FactorOut(BaseModel):
    name: str
    impact: str  # "neutral": these describe risk level, not direction
    description: str


class ForecastOut(BaseModel):
    prediction_id: Optional[int] = None
    symbol: str
    horizon_days: int
    as_of: str
    target_date: str
    last_price: float
    predicted_price: float
    expected_return_pct: float
    lower: float
    upper: float
    signal: Optional[str] = None
    confidence: Optional[float] = None
    model: str
    forecast_volatility_pct: float
    recent_volatility_pct: dict
    factors: List[FactorOut]
    forecast_path: List[PathPoint]
    notes: List[str]


class HistoryOut(BaseModel):
    items: list


def vol_to_fraction(v: float) -> float:
    """Annualised volatility as a fraction (0.27 = 27%).

    The volatility module may hand back a fraction or a percent. Real values
    for a stock are about 0.10-1.50 (fraction) or 10-150 (percent), so a
    threshold of 3 separates them safely.
    """
    return v if v <= 3 else v / 100.0


def next_business_days(start: date, n: int) -> List[date]:
    """n weekdays after `start` (public holidays are not handled)."""
    out, d = [], start
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return out


def build_path(last: float, vol: float, as_of: date, horizon: int) -> List[dict]:
    """80% no-drift range for each business day up to the horizon."""
    path = []
    for k, d in enumerate(next_business_days(as_of, horizon), start=1):
        s = vol * math.sqrt(k / 252.0)
        path.append({
            "date": d.isoformat(),
            "price": round(last, 2),
            "lower": round(last * math.exp(-Z80 * s), 2),
            "upper": round(last * math.exp(Z80 * s), 2),
        })
    return path


@router.get("/config", response_model=ConfigOut)
def prediction_config():
    return ConfigOut(horizons=sorted(int(h) for h in HORIZONS))


@router.post("/forecast", response_model=ForecastOut)
def forecast(req: ForecastRequest, db: Session = Depends(get_db), user=Depends(get_current_user)):
    try:
        vf = volatility_forecast(req.symbol, req.horizon_days, db)
    except HTTPException as e:
        # a missing stock/forecast is not a missing endpoint: use 422 so the page shows the reason
        if e.status_code == 404:
            raise HTTPException(status_code=422, detail=e.detail)
        raise

    stock = crud.get_stock_by_symbol(db, req.symbol)
    bars = crud.get_price_history(db, stock.stock_id, limit=1)
    if not bars or bars[-1].close_price is None:
        raise HTTPException(status_code=422, detail=f"No price history stored for {req.symbol.upper()} yet")
    last = float(bars[-1].close_price)

    vol = vol_to_fraction(float(vf.forecast_volatility))
    path = build_path(last, vol, vf.as_of, vf.horizon_days)
    lower, upper = path[-1]["lower"], path[-1]["upper"]

    rec = {k: round(vol_to_fraction(float(v)) * 100, 1) for k, v in vf.recent_volatility.items()}
    factors = [
        FactorOut(
            name="Forecast volatility",
            impact="neutral",
            description=f"{vol * 100:.1f}% a year over the next {vf.horizon_days} trading days. This sets the width of the range.",
        ),
        FactorOut(
            name="Recent volatility",
            impact="neutral",
            description="The stock's own past swings: " + ", ".join(f"{k} {v}%" for k, v in rec.items()) + ".",
        ),
    ]
    if vf.model.typical_error_vol_points is not None:
        factors.append(FactorOut(
            name="Model accuracy",
            impact="neutral",
            description=f"On a test period the volatility forecast missed by about {vf.model.typical_error_vol_points:.1f} volatility points on average.",
        ))

    notes = [
        "This is a volatility-based range, not a price prediction. No direction (up or down) is forecast.",
        f"The central price is the last close. About 80% of outcomes would fall inside the range if there were no drift; this is not guaranteed.",
        "Target date counts weekdays only and ignores public holidays.",
    ] + list(vf.notes)

    return ForecastOut(
        symbol=vf.symbol,
        horizon_days=vf.horizon_days,
        as_of=vf.as_of.isoformat(),
        target_date=path[-1]["date"],
        last_price=round(last, 2),
        predicted_price=round(last, 2),
        expected_return_pct=0.0,
        lower=lower,
        upper=upper,
        model=f"{vf.model.type} (trained {vf.model.last_training_date})",
        forecast_volatility_pct=round(vol * 100, 1),
        recent_volatility_pct=rec,
        factors=factors,
        forecast_path=[PathPoint(**p) for p in path],
        notes=notes,
    )


@router.get("/history", response_model=HistoryOut)
def prediction_history(user=Depends(get_current_user)):
    # Nothing can be saved yet (see POST below), so the honest answer is an empty list.
    return HistoryOut(items=[])


@router.post("/history", status_code=501)
def save_prediction(user=Depends(get_current_user)):
    raise HTTPException(
        status_code=501,
        detail="Saving prediction history needs a database change that has not been approved yet.",
    )