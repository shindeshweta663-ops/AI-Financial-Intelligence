import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from pydantic import BaseModel

from config import settings
from market_data import MarketDataError, _get_json

FINNHUB_NEWS_URL = "https://finnhub.io/api/v1/company-news"

# Finnhub returns at most about 250 articles per request (newest first).
# If a request comes back close to that size, older articles were probably
# cut off, so we split the date range in two and ask again.
TRUNCATION_LIMIT = 240
PAUSE_SECONDS = 1.1  # stay inside Finnhub's 60 calls per minute


class NewsItem(BaseModel):
    title: str
    description: Optional[str] = None
    source: Optional[str] = None
    url: str
    published_at: datetime  # UTC, stored without timezone info


def _fetch_range(symbol: str, start: date, end: date) -> List[NewsItem]:
    """One Finnhub request for start..end (inclusive). Newest first, no duplicate URLs."""
    if not settings.finnhub_api_key:
        raise MarketDataError("FINNHUB_API_KEY is not set in .env")

    data = _get_json(
        FINNHUB_NEWS_URL,
        {
            "symbol": symbol,
            "from": start.isoformat(),
            "to": end.isoformat(),
            "token": settings.finnhub_api_key,
        },
        "Finnhub",
    )

    if not isinstance(data, list):
        raise MarketDataError(f"Finnhub returned an unexpected news format for {symbol}")

    items: List[NewsItem] = []
    seen_urls = set()
    for row in data:
        title = (row.get("headline") or "").strip()
        url = (row.get("url") or "").strip()
        timestamp = row.get("datetime")
        if not title or not url or not timestamp or url in seen_urls:
            continue  # skip incomplete or duplicate articles
        seen_urls.add(url)

        published = datetime.fromtimestamp(int(timestamp), tz=timezone.utc).replace(tzinfo=None)
        summary = (row.get("summary") or "").strip()
        items.append(
            NewsItem(
                title=title,
                description=summary or None,
                source=(row.get("source") or None),
                url=url,
                published_at=published,
            )
        )

    items.sort(key=lambda item: item.published_at, reverse=True)
    return items


def get_company_news(symbol: str, days: int = 30) -> List[NewsItem]:
    """Single request for the last `days` days (used by test_news.py)."""
    today = date.today()
    return _fetch_range(symbol.strip().upper(), today - timedelta(days=days), today)


def _fetch_split(symbol: str, start: date, end: date) -> List[NewsItem]:
    """Fetch a range; if it looks truncated, split it in half and fetch both halves."""
    items = _fetch_range(symbol, start, end)
    time.sleep(PAUSE_SECONDS)
    if len(items) >= TRUNCATION_LIMIT and start < end:
        middle = start + (end - start) // 2
        return _fetch_split(symbol, start, middle) + _fetch_split(
            symbol, middle + timedelta(days=1), end
        )
    return items


def get_company_news_history(symbol: str, days: int = 30, window_days: int = 7) -> List[NewsItem]:
    """News for the last `days` days, fetched in small windows so nothing is cut off."""
    symbol = symbol.strip().upper()
    today = date.today()
    first_day = today - timedelta(days=days)

    by_url = {}
    window_end = today
    while window_end >= first_day:
        window_start = max(first_day, window_end - timedelta(days=window_days - 1))
        for item in _fetch_split(symbol, window_start, window_end):
            by_url.setdefault(item.url, item)
        window_end = window_start - timedelta(days=1)

    return sorted(by_url.values(), key=lambda item: item.published_at, reverse=True)
