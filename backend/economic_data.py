"""Economic data clients. World Bank now, FRED later.

Nothing in this file touches the database. It only fetches and validates data.
Missing observations are skipped, never stored as 0.
"""
import time
from datetime import date
from typing import List, Optional

from pydantic import BaseModel

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
    date: date            # the period the value describes (annual: Dec 31)
    value: float
    unit: str
    source: str


class SeriesFetch(BaseModel):
    points: List[EconomicPoint]
    pages: int
    reported_total: int       # rows the provider says exist, including empty ones
    missing_skipped: int      # rows with no value (not stored)


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
        data = _get_json(
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