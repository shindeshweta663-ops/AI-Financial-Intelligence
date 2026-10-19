"""Market overview endpoint for the dashboard (Phase 13b).

GET /api/market/overview

We store no official index levels (no S&P 500, no Nifty), so this builds
honest "tracked stocks" indices from the stocks we do store: the average
daily % move of every stock in a market, starting at 100. The names say
so plainly. Using % moves (not prices) means USD and INR stocks are never
mixed. This is a summary of stored data, not a forecast.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

import crud
from database import get_db
from models import Stock

router = APIRouter(prefix="/api/market", tags=["market"])

HISTORY_DAYS = 90  # price rows per stock used for the chart

# exchange -> (group key, display name)
GROUPS = {
    "NASDAQ": ("US", "US stocks (equal-weighted)"),
    "NYSE": ("US", "US stocks (equal-weighted)"),
    "NSE": ("IN", "India stocks (equal-weighted)"),
    "BSE": ("IN", "India stocks (equal-weighted)"),
}


class IndexPoint(BaseModel):
    date: str
    close: float


class IndexOut(BaseModel):
    name: str
    value: Optional[float]
    change_pct: Optional[float]
    stocks: int
    history: List[IndexPoint]


class StatusOut(BaseModel):
    state: str  # "open" or "closed"
    label: str
    as_of: Optional[str]


class MarketOverviewOut(BaseModel):
    status: StatusOut
    indices: List[IndexOut]
    note: str


def _nth_sunday(year: int, month: int, n: int) -> date:
    first = date(year, month, 1)
    offset = (6 - first.weekday()) % 7  # Monday=0 ... Sunday=6
    return first + timedelta(days=offset + 7 * (n - 1))


def us_market_state(now_utc: datetime) -> str:
    """'open' during regular US hours (Mon-Fri 09:30-16:00 New York time).

    New York time is worked out by hand (daylight saving: 2nd Sunday of
    March to 1st Sunday of November) so no timezone database is needed on
    Windows. Public holidays are NOT handled.
    """
    y = now_utc.year
    dst_start = datetime(y, 3, _nth_sunday(y, 3, 2).day, 7, tzinfo=timezone.utc)
    dst_end = datetime(y, 11, _nth_sunday(y, 11, 1).day, 6, tzinfo=timezone.utc)
    offset = -4 if dst_start <= now_utc < dst_end else -5
    ny = now_utc + timedelta(hours=offset)
    if ny.weekday() >= 5:
        return "closed"
    minutes = ny.hour * 60 + ny.minute
    return "open" if 9 * 60 + 30 <= minutes < 16 * 60 else "closed"


def build_index(series: List[List[tuple]]) -> List[tuple]:
    """series = one list of (date, close) per stock, oldest first.

    Returns [(date, level, day_return_pct)] with level starting at 100.
    A date counts only if at least half of the stocks have a return that
    day, so one stale stock cannot distort the line.
    """
    returns: Dict[date, List[float]] = {}
    for rows in series:
        for (_, prev), (d, cur) in zip(rows, rows[1:]):
            if prev and cur:
                returns.setdefault(d, []).append(cur / prev - 1.0)
    need = max(1, (len(series) + 1) // 2)
    out, level = [], 100.0
    for d in sorted(returns):
        if len(returns[d]) < need:
            continue
        r = sum(returns[d]) / len(returns[d])
        level *= 1.0 + r
        out.append((d, level, r * 100.0))
    return out


@router.get("/overview", response_model=MarketOverviewOut)
def market_overview(db: Session = Depends(get_db)):
    stocks = db.execute(select(Stock)).scalars().all()

    by_group: Dict[str, dict] = {}
    latest: Optional[date] = None
    for s in stocks:
        key, name = GROUPS.get(s.exchange, (s.exchange, f"{s.exchange} stocks (equal-weighted)"))
        rows = crud.get_price_history(db, s.stock_id, limit=HISTORY_DAYS + 1)
        pts = [(r.date, float(r.close_price)) for r in rows if r.close_price is not None]
        if len(pts) < 2:
            continue
        g = by_group.setdefault(key, {"name": name, "series": []})
        g["series"].append(pts)
        if latest is None or pts[-1][0] > latest:
            latest = pts[-1][0]

    indices: List[IndexOut] = []
    for key in sorted(by_group, key=lambda k: (k != "US", k)):  # US first
        g = by_group[key]
        built = build_index(g["series"])
        if not built:
            continue
        indices.append(IndexOut(
            name=g["name"],
            value=round(built[-1][1], 2),
            change_pct=round(built[-1][2], 2),
            stocks=len(g["series"]),
            history=[IndexPoint(date=d.isoformat(), close=round(v, 2)) for d, v, _ in built],
        ))

    state = us_market_state(datetime.now(timezone.utc))
    return MarketOverviewOut(
        status=StatusOut(
            state=state,
            label="US market " + state,
            as_of=datetime.combine(latest, datetime.min.time()).isoformat() if latest else None,
        ),
        indices=indices,
        note=("Indices are equal-weighted averages of the stocks this platform tracks, "
              "not official benchmarks. Market hours ignore public holidays."),
    )
