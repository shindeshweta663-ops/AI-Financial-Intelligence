"""Load the stored prices and indicators from PostgreSQL and build the ML dataset.

Read-only. Used by the training scripts so the loading code lives in one place.
"""
import numpy as np
import pandas as pd

from crud import get_indicator_history, get_price_history, list_stocks
from database import SessionLocal
from features import build_dataset

US_EXCHANGES = {"NASDAQ", "NYSE"}
INDICATOR_COLUMNS = ["rsi", "macd", "macd_signal", "ema20", "ema50", "sma20", "volatility"]


def _number(value):
    return float(value) if value is not None else np.nan


def load_price_inputs(db):
    """Return (closes, indicators): dicts keyed by symbol, for stocks that have prices."""
    closes, indicators = {}, {}
    for stock in list_stocks(db):
        if stock.exchange not in US_EXCHANGES:
            continue
        rows = [r for r in get_price_history(db, stock.stock_id, limit=5000) if r.close_price is not None]
        if not rows:
            continue
        closes[stock.symbol] = pd.Series(
            [float(r.close_price) for r in rows],
            index=pd.DatetimeIndex([pd.Timestamp(r.date).normalize() for r in rows]),
        )
        ind_rows = get_indicator_history(db, stock.stock_id, limit=5000)
        indicators[stock.symbol] = pd.DataFrame(
            {c: [_number(getattr(r, c)) for r in ind_rows] for c in INDICATOR_COLUMNS},
            index=pd.DatetimeIndex([pd.Timestamp(r.date).normalize() for r in ind_rows]),
        )
    return closes, indicators


def load_dataset(horizon: int = 1) -> pd.DataFrame:
    """Pooled feature table (groups A-C) with targets for all US stocks."""
    with SessionLocal() as db:
        closes, indicators = load_price_inputs(db)
    return build_dataset(closes, indicators, horizon)