"""GET /api/stocks/search?q= : find stocks by symbol or company name.

Returns {"results": [{"symbol", "name", "exchange"}, ...]}, the shape the
dashboard search box reads. Matches that start with the typed text come first.
"""
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from database import get_db
from models import Stock

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


class SearchItem(BaseModel):
    symbol: str
    name: Optional[str]
    exchange: Optional[str]


class SearchResponse(BaseModel):
    results: List[SearchItem]


def _escape_like(text: str) -> str:
    """Make %, _ and \\ in the typed text match literally."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search", response_model=SearchResponse)
def search_stocks(
    q: str = Query(..., min_length=1, max_length=50, description="Symbol or company name"),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    text = q.strip()
    if not text:
        return SearchResponse(results=[])
    safe = _escape_like(text)
    starts = safe + "%"
    contains = "%" + safe + "%"

    # 0 = exact symbol, 1 = symbol starts with, 2 = name starts with, 3 = anything else
    rank = case(
        (func.upper(Stock.symbol) == text.upper(), 0),
        (Stock.symbol.ilike(starts, escape="\\"), 1),
        (Stock.company_name.ilike(starts, escape="\\"), 2),
        else_=3,
    )
    rows = db.execute(
        select(Stock.symbol, Stock.company_name, Stock.exchange)
        .where(
            Stock.symbol.is_not(None),
            or_(
                Stock.symbol.ilike(contains, escape="\\"),
                Stock.company_name.ilike(contains, escape="\\"),
            ),
        )
        .order_by(rank, Stock.symbol)
        .limit(limit)
    ).all()
    return SearchResponse(
        results=[SearchItem(symbol=r.symbol, name=r.company_name, exchange=r.exchange) for r in rows]
    )
