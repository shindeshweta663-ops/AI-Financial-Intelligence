"""Daily price history from Yahoo Finance (via the yfinance package) for the
exchanges Twelve Data's free plan does not cover (NSE, BSE).

Why this exists: Twelve Data answers "available starting with the Grow or
Venture plan" for NSE tickers. Yahoo's data is free but UNOFFICIAL, so it can
change or fail without notice. Prices for these stocks therefore come from a
different source than the US stocks; say so in the README.

Returns the same PriceBar objects as get_daily_history_twelve_data, so the rest
of the project does not change.
"""
import math
from datetime import datetime, timedelta, timezone
from typing import List

from market_data import MarketDataError, PriceBar

# exchange stored in our stocks table -> Yahoo ticker suffix
YF_SUFFIX = {"NSE": ".NS", "BSE": ".BO"}


def _clean(value):
    """float or None (NaN, missing and zero-or-negative prices are rejected)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def frame_to_bars(frame) -> List[PriceBar]:
    """Turn a yfinance table (Open/High/Low/Close/Volume, one row per day) into PriceBars, oldest first."""
    bars = []
    for stamp, row in frame.iterrows():
        open_, high, low, close = (_clean(row.get(k)) for k in ("Open", "High", "Low", "Close"))
        if None in (open_, high, low, close):
            continue  # skip incomplete rows instead of storing bad data
        volume = row.get("Volume")
        try:
            volume = int(volume) if volume is not None and math.isfinite(float(volume)) else None
        except (TypeError, ValueError):
            volume = None
        bars.append(PriceBar(
            date=datetime(stamp.year, stamp.month, stamp.day),  # midnight, no timezone, like the US rows
            open=open_, high=high, low=low, close=close, volume=volume,
        ))
    bars.sort(key=lambda bar: bar.date)
    return bars


def get_daily_history_yfinance(symbol: str, exchange: str, period: str = "5y") -> List[PriceBar]:
    """Daily candles, oldest first (about 5 years). Split-adjusted, not dividend-adjusted."""
    suffix = YF_SUFFIX.get(exchange)
    if suffix is None:
        raise MarketDataError(f"No Yahoo ticker rule for exchange {exchange}")
    ticker = symbol.strip().upper() + suffix
    try:
        import yfinance as yf  # imported here so the project still starts without it
        frame = yf.Ticker(ticker).history(period=period, interval="1d", auto_adjust=False, actions=False)
    except Exception as error:  # yfinance raises many kinds of errors
        raise MarketDataError(f"Yahoo Finance failed for {ticker}: {str(error)[:150]}") from None
    if frame is None or frame.empty:
        raise MarketDataError(f"Yahoo Finance returned no history for {ticker}")
    bars = frame_to_bars(frame)
        # drop today's bar (India time): it may still be in progress, and stored rows are never updated
    today = datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
    bars = [bar for bar in bars if bar.date.date() < today]
    if not bars:
        raise MarketDataError(f"Yahoo Finance returned only incomplete rows for {ticker}")
    return bars