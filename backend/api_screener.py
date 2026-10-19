"""Stock screener for the dashboard's "Stock Opportunities" page (Phase 14).

GET /api/stocks/screener

One row per stock that has enough stored prices. Everything is computed from
stored closing prices, so nothing here is a price forecast:
  - volatility: annualised % (std of last 63 daily returns x sqrt(252))
  - risk_level: Low < 20%, Medium 20-35%, High > 35% (same thresholds the page shows)
  - signal: a simple TREND RULE on past prices (price vs its 50-day average and
    the last month's change). It describes what already happened. It is not a
    prediction and can be wrong.
  - expected_return_pct is deliberately not provided: our research found no
    reliable signal in future price direction.
Stocks without enough stored prices (currently the NSE ones) are listed in
"skipped_no_prices" instead of being shown with fake numbers.

This router must be included BEFORE the stocks router in main.py, otherwise
/api/stocks/{symbol} would swallow "/screener".
"""
import math
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import crud
from database import get_db
from models import Stock

router = APIRouter(prefix="/api/stocks", tags=["screener"])

ROWS_NEEDED = 64   # 63 returns for volatility, and >= 50 for the 50-day average
SMA_DAYS = 50
MONTH_DAYS = 21
VOL_DAYS = 63


class ScreenerRow(BaseModel):
    symbol: str
    name: Optional[str]
    exchange: Optional[str]
    sector: Optional[str]
    price: float
    change_pct: Optional[float]
    volatility: Optional[float]
    risk_level: Optional[str]
    signal: str
    signal_reason: str
    as_of: str


class ScreenerOut(BaseModel):
    rows: List[ScreenerRow]
    skipped_no_prices: List[str]
    note: str


def risk_level(vol_pct: Optional[float]) -> Optional[str]:
    if vol_pct is None:
        return None
    return "Low" if vol_pct < 20 else ("Medium" if vol_pct <= 35 else "High")


def analyse(closes: List[float]) -> Optional[dict]:
    """closes: oldest first, at least ROWS_NEEDED values. Returns the computed numbers."""
    if len(closes) < ROWS_NEEDED or any(c is None or c <= 0 for c in closes[-ROWS_NEEDED:]):
        return None
    last = closes[-1]
    change = (last / closes[-2] - 1.0) * 100.0
    sma = sum(closes[-SMA_DAYS:]) / SMA_DAYS
    vs_sma = (last / sma - 1.0) * 100.0
    month = (last / closes[-1 - MONTH_DAYS] - 1.0) * 100.0
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(len(closes) - VOL_DAYS, len(closes))]
    mean = sum(rets) / len(rets)
    sd = math.sqrt(sum((r - mean) ** 2 for r in rets) / (len(rets) - 1))
    vol = sd * math.sqrt(252) * 100.0
    if vs_sma > 0 and month > 0:
        signal = "Positive"
    elif vs_sma < 0 and month < 0:
        signal = "Negative"
    else:
        signal = "Neutral"
    reason = (f"Price is {vs_sma:+.1f}% vs its 50-day average and {month:+.1f}% over the last month. "
              "A trend rule on past prices, not a forecast.")
    return {"price": last, "change": change, "vol": vol, "signal": signal, "reason": reason}


@router.get("/screener", response_model=ScreenerOut)
def screener(db: Session = Depends(get_db)):
    stocks = db.execute(select(Stock).order_by(Stock.symbol)).scalars().all()
    rows: List[ScreenerRow] = []
    skipped: List[str] = []
    for s in stocks:
        hist = crud.get_price_history(db, s.stock_id, limit=ROWS_NEEDED + 6)
        pts = [(h.date, float(h.close_price)) for h in hist if h.close_price is not None]
        res = analyse([c for _, c in pts])
        if res is None:
            skipped.append(s.symbol)
            continue
        rows.append(ScreenerRow(
            symbol=s.symbol,
            name=s.company_name,
            exchange=s.exchange,
            sector=s.sector,
            price=round(res["price"], 2),
            change_pct=round(res["change"], 2),
            volatility=round(res["vol"], 1),
            risk_level=risk_level(res["vol"]),
            signal=res["signal"],
            signal_reason=res["reason"],
            as_of=pts[-1][0].isoformat(),
        ))
    return ScreenerOut(
        rows=rows,
        skipped_no_prices=skipped,
        note=("Signals are simple trend rules on stored past prices, not forecasts, and can be wrong. "
              "Stocks without enough stored prices are listed in skipped_no_prices."),
    )