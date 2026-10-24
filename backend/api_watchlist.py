"""Watchlist endpoints (login required).

GET    /api/watchlist           -> {"items": [{symbol, name, exchange, price, change_pct, as_of, added_at}]}
POST   /api/watchlist           body {"symbol": "AAPL"} -> the added item (409 if already there)
DELETE /api/watchlist/{symbol}  -> {"removed": true|false} (safe to repeat)

price is the latest stored close, change_pct the 1-day change between the
last two stored closes (percent), as_of the date of the latest stored close.
These are stored daily prices, not live quotes.
"""
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from auth import get_current_user
from crud import get_price_history, get_stock_by_symbol
from database import get_db
from models import Stock, User, Watchlist

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchItem(BaseModel):
    symbol: str
    name: Optional[str] = None
    exchange: Optional[str] = None
    price: Optional[float] = None
    change_pct: Optional[float] = None
    as_of: Optional[datetime] = None
    added_at: Optional[datetime] = None


class WatchlistOut(BaseModel):
    items: List[WatchItem]


class AddRequest(BaseModel):
    symbol: str


class RemoveOut(BaseModel):
    removed: bool


def _float(value) -> Optional[float]:
    return float(value) if value is not None else None


def _build_item(db: Session, stock: Stock, added_at: Optional[datetime]) -> WatchItem:
    rows = get_price_history(db, stock.stock_id, limit=2)  # oldest first
    price = change = as_of = None
    if rows:
        last = rows[-1]
        price = _float(last.close_price)
        as_of = last.date
        if len(rows) == 2:
            prev = _float(rows[0].close_price)
            if price is not None and prev:
                change = round((price / prev - 1.0) * 100.0, 2)
    return WatchItem(
        symbol=stock.symbol,
        name=stock.company_name,
        exchange=stock.exchange,
        price=price,
        change_pct=change,
        as_of=as_of,
        added_at=added_at,
    )


@router.get("", response_model=WatchlistOut)
def get_watchlist(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The logged-in user's watchlist, newest first."""
    pairs = db.execute(
        select(Watchlist.added_at, Stock)
        .join(Stock, Watchlist.stock_id == Stock.stock_id)
        .where(Watchlist.user_id == user.user_id)
        .order_by(Watchlist.added_at.desc().nulls_last(), Watchlist.watchlist_id.desc())
    ).all()
    return WatchlistOut(items=[_build_item(db, stock, added_at) for added_at, stock in pairs])


@router.post("", response_model=WatchItem, status_code=201)
def add_to_watchlist(
    body: AddRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Add a tracked stock to the logged-in user's watchlist."""
    symbol = body.symbol.strip()
    if not symbol:
        raise HTTPException(status_code=400, detail="Please provide a stock symbol.")
    stock = get_stock_by_symbol(db, symbol)
    if stock is None:
        # 400, not 404: the dashboard reads 404 as "watchlist not available".
        raise HTTPException(status_code=400, detail=f"Stock '{symbol.upper()}' is not tracked.")

    existing = db.scalars(
        select(Watchlist).where(
            Watchlist.user_id == user.user_id,
            Watchlist.stock_id == stock.stock_id,
        )
    ).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="Already in your watchlist.")

    added_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.add(Watchlist(user_id=user.user_id, stock_id=stock.stock_id, added_at=added_at))
    db.commit()
    return _build_item(db, stock, added_at)


@router.delete("/{symbol}", response_model=RemoveOut)
def remove_from_watchlist(
    symbol: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a stock from the watchlist. Repeating it is harmless."""
    stock = get_stock_by_symbol(db, symbol.strip())
    if stock is None:
        return RemoveOut(removed=False)
    result = db.execute(
        delete(Watchlist).where(
            Watchlist.user_id == user.user_id,
            Watchlist.stock_id == stock.stock_id,
        )
    )
    db.commit()
    return RemoveOut(removed=result.rowcount > 0)