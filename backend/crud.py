from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import FinancialStatement, PriceHistory, Stock, TechnicalIndicator


def _clean_symbol(symbol: str) -> str:
    """Symbols are stored in uppercase without spaces, e.g. 'TCS'."""
    return symbol.strip().upper()


def get_stock_by_symbol(db: Session, symbol: str) -> Optional[Stock]:
    """Return the stock with this symbol, or None if it does not exist."""
    statement = select(Stock).where(Stock.symbol == _clean_symbol(symbol))
    return db.execute(statement).scalars().first()


def get_stock_by_id(db: Session, stock_id: int) -> Optional[Stock]:
    """Return the stock with this id, or None."""
    return db.get(Stock, stock_id)


def list_stocks(db: Session, skip: int = 0, limit: int = 100) -> List[Stock]:
    """Return stocks ordered by symbol, with simple paging."""
    statement = select(Stock).order_by(Stock.symbol).offset(skip).limit(limit)
    return list(db.execute(statement).scalars().all())


def search_stocks(db: Session, query: str, limit: int = 10) -> List[Stock]:
    """Search by symbol or company name (case-insensitive, partial match)."""
    pattern = f"%{query.strip()}%"
    statement = (
        select(Stock)
        .where(Stock.symbol.ilike(pattern) | Stock.company_name.ilike(pattern))
        .order_by(Stock.symbol)
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


def create_stock(
    db: Session,
    symbol: str,
    company_name: Optional[str] = None,
    exchange: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
) -> Stock:
    """Insert a new stock. If the symbol already exists, return the existing one."""
    existing = get_stock_by_symbol(db, symbol)
    if existing:
        return existing

    stock = Stock(
        symbol=_clean_symbol(symbol),
        company_name=company_name,
        exchange=exchange,
        sector=sector,
        industry=industry,
    )
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def delete_stock(db: Session, symbol: str) -> bool:
    """Delete a stock by symbol. Returns True if something was deleted."""
    stock = get_stock_by_symbol(db, symbol)
    if not stock:
        return False
    db.delete(stock)
    db.commit()
    return True


# ---------- price history ----------
def get_existing_price_dates(db: Session, stock_id: int) -> set:
    """All dates already stored for this stock."""
    statement = select(PriceHistory.date).where(PriceHistory.stock_id == stock_id)
    return set(db.execute(statement).scalars().all())


def add_price_bars(db: Session, stock_id: int, bars: list) -> int:
    """Insert only the bars whose date is not stored yet. Returns how many were added."""
    existing = get_existing_price_dates(db, stock_id)
    new_rows = [
        PriceHistory(
            stock_id=stock_id,
            date=bar.date,
            open_price=bar.open,
            high_price=bar.high,
            low_price=bar.low,
            close_price=bar.close,
            volume=bar.volume,
        )
        for bar in bars
        if bar.date not in existing
    ]
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)


def get_price_history(db: Session, stock_id: int, limit: int = 365) -> List[PriceHistory]:
    """Latest `limit` rows, returned oldest first."""
    statement = (
        select(PriceHistory)
        .where(PriceHistory.stock_id == stock_id)
        .order_by(PriceHistory.date.desc())
        .limit(limit)
    )
    rows = list(db.execute(statement).scalars().all())
    rows.reverse()
    return rows

# ---------- technical indicators ----------
def add_indicator_rows(db: Session, stock_id: int, records: list) -> int:
    """
    records: list of dicts with keys date, sma20, ema20, ema50, rsi,
    macd, macd_signal, volatility. Inserts only dates not stored yet.
    """
    statement = select(TechnicalIndicator.date).where(TechnicalIndicator.stock_id == stock_id)
    existing = set(db.execute(statement).scalars().all())

    new_rows = [
        TechnicalIndicator(stock_id=stock_id, **record)
        for record in records
        if record["date"] not in existing
    ]
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)


def get_indicator_history(db: Session, stock_id: int, limit: int = 250) -> List[TechnicalIndicator]:
    """Latest `limit` indicator rows, returned oldest first."""
    statement = (
        select(TechnicalIndicator)
        .where(TechnicalIndicator.stock_id == stock_id)
        .order_by(TechnicalIndicator.date.desc())
        .limit(limit)
    )
    rows = list(db.execute(statement).scalars().all())
    rows.reverse()
    return rows


    # ---------- financial statements ----------
def add_financial_rows(db: Session, stock_id: int, records: list) -> int:
    """Insert only report dates not stored yet. Returns how many were added."""
    statement = select(FinancialStatement.report_date).where(
        FinancialStatement.stock_id == stock_id
    )
    existing = set(db.execute(statement).scalars().all())

    new_rows = [
        FinancialStatement(
            stock_id=stock_id,
            report_date=r.report_date,
            revenue=r.revenue,
            net_profit=r.net_profit,
            total_assets=r.total_assets,
            total_debt=r.total_debt,
            eps=r.eps,
            profit_margin=r.profit_margin,
        )
        for r in records
        if r.report_date not in existing
    ]
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)


def get_financial_history(db: Session, stock_id: int, limit: int = 10) -> List[FinancialStatement]:
    """Latest `limit` annual rows, returned oldest first."""
    statement = (
        select(FinancialStatement)
        .where(FinancialStatement.stock_id == stock_id)
        .order_by(FinancialStatement.report_date.desc())
        .limit(limit)
    )
    rows = list(db.execute(statement).scalars().all())
    rows.reverse()
    return rows