import time
from collections import deque
from datetime import datetime
from typing import Deque, List, Optional

import requests
from pydantic import BaseModel

from config import settings

TWELVE_DATA_URL = "https://api.twelvedata.com"
FINNHUB_URL = "https://finnhub.io/api/v1"
REQUEST_TIMEOUT = 15  # seconds

# Twelve Data free plan: 8 API credits per minute
TWELVE_DATA_MAX_PER_MINUTE = 8


class MarketDataError(Exception):
    """Raised when a market data provider fails. Messages never contain API keys."""


class Quote(BaseModel):
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    currency: Optional[str] = None
    price: float
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None
    change: Optional[float] = None
    percent_change: Optional[float] = None
    volume: Optional[int] = None
    quote_time: Optional[str] = None
    is_market_open: Optional[bool] = None
    source: str


# ---------- helpers ----------
def _to_float(value) -> Optional[float]:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _to_int(value) -> Optional[int]:
    number = _to_float(value)
    return int(number) if number is not None else None


_twelve_call_times: Deque[float] = deque()


def _wait_for_twelve_data_slot() -> None:
    """Block until we are under 8 calls in the last 60 seconds."""
    while True:
        now = time.monotonic()
        while _twelve_call_times and now - _twelve_call_times[0] >= 60:
            _twelve_call_times.popleft()
        if len(_twelve_call_times) < TWELVE_DATA_MAX_PER_MINUTE:
            _twelve_call_times.append(now)
            return
        wait = 60 - (now - _twelve_call_times[0]) + 0.5
        print(f"  (rate limit pacing: waiting {wait:.0f}s)")
        time.sleep(wait)


def _get_json(url: str, params: dict, provider: str) -> dict:
    """GET request with a timeout. Never lets the API key leak into errors."""
    try:
        response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        # 'from None' hides the original error, which can contain the URL + key
        raise MarketDataError(f"Could not reach {provider} (network error or timeout)") from None

    if response.status_code in (401, 403):
        raise MarketDataError(f"{provider} rejected the request (invalid key or no access to this data)")
    if response.status_code == 429:
        raise MarketDataError(f"{provider} rate limit reached. Wait a minute and try again")
    if response.status_code != 200:
        raise MarketDataError(f"{provider} returned HTTP {response.status_code}")

    try:
        return response.json()
    except ValueError:
        raise MarketDataError(f"{provider} returned an unreadable response") from None


# ---------- Twelve Data (main provider) ----------
def get_quote_twelve_data(symbol: str) -> Quote:
    if not settings.twelve_data_api_key:
        raise MarketDataError("TWELVE_DATA_API_KEY is not set in .env")

    symbol = symbol.strip().upper()
    _wait_for_twelve_data_slot()
    data = _get_json(
        f"{TWELVE_DATA_URL}/quote",
        {"symbol": symbol, "apikey": settings.twelve_data_api_key},
        "Twelve Data",
    )

    # Twelve Data reports problems inside a normal JSON body
    if data.get("status") == "error":
        raise MarketDataError(f"Twelve Data error {data.get('code')}: {data.get('message')}")

    price = _to_float(data.get("close"))
    if price is None:
        raise MarketDataError(f"Twelve Data returned no price for {symbol}")

    return Quote(
        symbol=symbol,
        name=data.get("name"),
        exchange=data.get("exchange"),
        currency=data.get("currency"),
        price=price,
        open=_to_float(data.get("open")),
        high=_to_float(data.get("high")),
        low=_to_float(data.get("low")),
        previous_close=_to_float(data.get("previous_close")),
        change=_to_float(data.get("change")),
        percent_change=_to_float(data.get("percent_change")),
        volume=_to_int(data.get("volume")),
        quote_time=data.get("datetime"),
        is_market_open=data.get("is_market_open"),
        source="Twelve Data",
    )


# ---------- Finnhub (backup provider) ----------
def get_quote_finnhub(symbol: str) -> Quote:
    if not settings.finnhub_api_key:
        raise MarketDataError("FINNHUB_API_KEY is not set in .env")

    symbol = symbol.strip().upper()
    data = _get_json(
        f"{FINNHUB_URL}/quote",
        {"symbol": symbol, "token": settings.finnhub_api_key},
        "Finnhub",
    )

    # Finnhub returns zeros for symbols it does not know
    if not data.get("c"):
        raise MarketDataError(f"Finnhub returned no price for {symbol}")

    return Quote(
        symbol=symbol,
        price=float(data["c"]),
        open=_to_float(data.get("o")),
        high=_to_float(data.get("h")),
        low=_to_float(data.get("l")),
        previous_close=_to_float(data.get("pc")),
        change=_to_float(data.get("d")),
        percent_change=_to_float(data.get("dp")),
        quote_time=str(data.get("t")) if data.get("t") else None,
        source="Finnhub",
    )


# ---------- combined ----------
def get_latest_quote(symbol: str) -> Quote:
    """Try Twelve Data first. If it fails, fall back to Finnhub."""
    try:
        return get_quote_twelve_data(symbol)
    except MarketDataError as first_error:
        print(f"  Twelve Data failed ({first_error}). Trying Finnhub...")
        return get_quote_finnhub(symbol)

    # ---------- historical data ----------
class PriceBar(BaseModel):
    """One daily candle: Open, High, Low, Close, Volume."""
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[int] = None


def _parse_bar_date(text: str) -> datetime:
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise MarketDataError(f"Unexpected date format from Twelve Data: {text}")


def get_daily_history_twelve_data(symbol: str, outputsize: int = 1250) -> List[PriceBar]:
    """Daily candles, oldest first. 1250 trading days is roughly 5 years."""
    if not settings.twelve_data_api_key:
        raise MarketDataError("TWELVE_DATA_API_KEY is not set in .env")

    symbol = symbol.strip().upper()
    _wait_for_twelve_data_slot()
    data = _get_json(
        f"{TWELVE_DATA_URL}/time_series",
        {
            "symbol": symbol,
            "interval": "1day",
            "outputsize": outputsize,
            "apikey": settings.twelve_data_api_key,
        },
        "Twelve Data",
    )

    if data.get("status") == "error":
        raise MarketDataError(f"Twelve Data error {data.get('code')}: {data.get('message')}")

    rows = data.get("values") or []
    if not rows:
        raise MarketDataError(f"Twelve Data returned no history for {symbol}")

    bars = []
    for row in rows:
        open_, high, low, close = (_to_float(row.get(k)) for k in ("open", "high", "low", "close"))
        if None in (open_, high, low, close):
            continue  # skip incomplete rows instead of storing bad data
        bars.append(
            PriceBar(
                date=_parse_bar_date(row["datetime"]),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=_to_int(row.get("volume")),
            )
        )

    bars.sort(key=lambda bar: bar.date)  # Twelve Data returns newest first
    return bars