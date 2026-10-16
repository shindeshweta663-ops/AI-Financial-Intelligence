"""Economic data clients: World Bank (no key) and FRED (needs FRED_API_KEY in .env).

Nothing in this file touches the database. It only fetches and validates data.
Missing observations are skipped, never stored as 0.
"""
import time
from datetime import date
from typing import List, Optional

from pydantic import BaseModel

from config import settings
from market_data import MarketDataError, _get_json

WORLD_BANK_URL = "https://api.worldbank.org/v2"
WORLD_BANK_SOURCE = "World Bank"
WORLD_BANK_PAGE_SIZE = 100
WORLD_BANK_MAX_PAGES = 20          # safety stop, these series need 1 page
WORLD_BANK_PAUSE_SECONDS = 0.3     # polite pause between pages


class EconomicPoint(BaseModel):
    indicator_code: str
    indicator_name: str
    country: str          # ISO3, e.g. USA
    date: date            # the period the value describes
    value: float
    unit: str
    source: str


class SeriesFetch(BaseModel):
    points: List[EconomicPoint]
    pages: int
    reported_total: int       # rows the provider returned, including empty ones
    missing_skipped: int      # rows with no value (not stored)
    missing_dates: List[str] = []   # dates with no value (FRED only)


# (country ISO3, World Bank code, stored name, unit)
WORLD_BANK_SERIES = [
    ("USA", "NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)", "% per year"),
    ("USA", "FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)", "% per year"),
    ("USA", "SL.UEM.TOTL.ZS", "Unemployment rate (% of labor force)", "% of labor force"),
    ("IND", "NY.GDP.MKTP.KD.ZG", "GDP growth (annual %)", "% per year"),
    ("IND", "FP.CPI.TOTL.ZG", "Inflation, consumer prices (annual %)", "% per year"),
]


def _split_world_bank_response(data) -> tuple:
    """Return (meta, rows). World Bank answers with [meta, rows] or [{'message': ...}]."""
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        raise MarketDataError("World Bank returned an unexpected response")
    meta = data[0]
    if "message" in meta:
        raise MarketDataError("World Bank rejected the request (check country or indicator code)")
    rows = data[1] if len(data) > 1 and data[1] else []
    return meta, rows


def _get_json_with_retry(url: str, params: dict, provider: str, attempts: int = 3, pause: float = 2.0):
    """Call _get_json, retrying transient failures. Waits 2s, then 4s between attempts.

    The final error is raised unchanged, so it still never contains a URL or key.
    """
    last_error = None
    for attempt in range(attempts):
        try:
            return _get_json(url, params, provider)
        except MarketDataError as error:
            last_error = error
            if attempt < attempts - 1:
                time.sleep(pause * (attempt + 1))
    raise last_error


def get_world_bank_series(
    country: str,
    code: str,
    name: str,
    unit: str,
    start_year: int = 2000,
    end_year: Optional[int] = None,
    page_size: int = WORLD_BANK_PAGE_SIZE,
) -> SeriesFetch:
    """Fetch one country/indicator series, following all pages, oldest first."""
    end_year = end_year or date.today().year
    url = f"{WORLD_BANK_URL}/country/{country}/indicator/{code}"

    points = {}
    missing = 0
    page = 1
    while True:
        data = _get_json_with_retry(
            url,
            {"format": "json", "date": f"{start_year}:{end_year}", "per_page": page_size, "page": page},
            "World Bank",
        )
        meta, rows = _split_world_bank_response(data)
        pages = int(meta.get("pages", 1))
        total = int(meta.get("total", 0))

        for row in rows:
            returned_country = row.get("countryiso3code")
            if returned_country and returned_country != country:
                raise MarketDataError("World Bank returned data for an unexpected country")
            if row.get("value") is None:
                missing += 1
                continue
            try:
                year = int(row["date"])
                value = float(row["value"])
            except (KeyError, TypeError, ValueError):
                raise MarketDataError("World Bank returned a row that could not be read") from None
            points[date(year, 12, 31)] = EconomicPoint(
                indicator_code=code,
                indicator_name=name,
                country=country,
                date=date(year, 12, 31),
                value=value,
                unit=unit,
                source=WORLD_BANK_SOURCE,
            )

        if page >= pages:
            break
        if page >= WORLD_BANK_MAX_PAGES:
            raise MarketDataError("World Bank returned more pages than expected")
        page += 1
        time.sleep(WORLD_BANK_PAUSE_SECONDS)

    ordered = [points[d] for d in sorted(points)]
    return SeriesFetch(points=ordered, pages=pages, reported_total=total, missing_skipped=missing)


# ======================= FRED (needs FRED_API_KEY in .env) =======================
FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
FRED_SOURCE = "FRED"
# Official limit not confirmed by me. Waiting 2 s between calls is about 30/min,
# below the lowest figure I saw quoted (40/min).
FRED_MIN_INTERVAL_SECONDS = 2.0

# (country, FRED series id, stored name, unit, frequency override or None)
FRED_SERIES = [
    ("USA", "FEDFUNDS", "Federal funds effective rate (%)", "% per year", None),
    ("USA", "DGS10", "10-year Treasury yield, monthly average (%)", "% per year", "m"),
    ("USA", "CPIAUCSL", "CPI all urban consumers, seasonally adjusted (index 1982-84=100)", "index", None),
]

_last_fred_call = 0.0


def _wait_for_fred_slot() -> None:
    global _last_fred_call
    wait = FRED_MIN_INTERVAL_SECONDS - (time.monotonic() - _last_fred_call)
    if wait > 0:
        time.sleep(wait)
    _last_fred_call = time.monotonic()


def get_fred_series(
    country: str,
    series_id: str,
    name: str,
    unit: str,
    start_date: str = "2000-01-01",
    frequency: Optional[str] = None,
) -> SeriesFetch:
    """Fetch one FRED series, oldest first. Missing values ('.') are skipped, never stored as 0."""
    if not settings.fred_api_key:
        raise MarketDataError("FRED_API_KEY is not set in .env")

    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "observation_start": start_date,
    }
    if frequency:
        params["frequency"] = frequency  # server-side aggregation (default method: average)

    _wait_for_fred_slot()
    data = _get_json_with_retry(FRED_URL, params, "FRED")

    if not isinstance(data, dict) or not isinstance(data.get("observations"), list):
        raise MarketDataError("FRED returned an unexpected response")

    points = {}
    missing = 0
    missing_dates = []
    for row in data["observations"]:
        raw = row.get("value")
        if raw in (None, "", "."):
            missing += 1
            if row.get("date"):
                missing_dates.append(str(row["date"]))
            continue
        try:
            day = date.fromisoformat(row["date"])
            value = float(raw)
        except (KeyError, TypeError, ValueError):
            raise MarketDataError("FRED returned a row that could not be read") from None
        points[day] = EconomicPoint(
            indicator_code=series_id,
            indicator_name=name,
            country=country,
            date=day,
            value=value,
            unit=unit,
            source=FRED_SOURCE,
        )

    ordered = [points[d] for d in sorted(points)]
    return SeriesFetch(
        points=ordered,
        pages=1,
        reported_total=len(data["observations"]),  # rows FRED returned, including empty ones
        missing_skipped=missing,
        missing_dates=missing_dates,
    )