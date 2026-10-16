from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models import (
    EconomicIndicator,
    FinancialStatement,
    News,
    NewsSentiment,
    PriceHistory,
    Stock,
    TechnicalIndicator,
)


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


# ---------- news ----------
def add_news_items(db: Session, stock_id: int, items: list) -> int:
    """Insert only articles whose URL is not stored yet for this stock. Returns how many were added."""
    statement = select(News.url).where(News.stock_id == stock_id)
    existing = set(db.execute(statement).scalars().all())

    new_rows = []
    for item in items:
        if item.url in existing:
            continue
        existing.add(item.url)  # also protects against duplicates inside `items`
        new_rows.append(
            News(
                stock_id=stock_id,
                title=item.title,
                description=item.description,
                source=item.source[:150] if item.source else None,  # column is String(150)
                url=item.url,
                published_at=item.published_at,  # UTC, no timezone
            )
        )
    db.add_all(new_rows)
    db.commit()
    return len(new_rows)


def count_news(db: Session, stock_id: int) -> int:
    """How many articles are stored for this stock."""
    statement = select(func.count()).select_from(News).where(News.stock_id == stock_id)
    return db.execute(statement).scalar_one()


def get_news(db: Session, stock_id: int, limit: int = 50) -> List[News]:
    """Latest `limit` articles, newest first."""
    statement = (
        select(News)
        .where(News.stock_id == stock_id)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


def get_news_with_sentiment(db: Session, stock_id: int, limit: int = 50) -> list:
    """Latest `limit` articles, newest first, each paired with its sentiment row (or None)."""
    statement = (
        select(News, NewsSentiment)
        .outerjoin(NewsSentiment, NewsSentiment.news_id == News.news_id)
        .where(News.stock_id == stock_id)
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(statement).all())


# ---------- news sentiment ----------
def get_unscored_news(db: Session, limit: int = 200) -> List[News]:
    """Articles that have no sentiment row yet, newest first."""
    statement = (
        select(News)
        .outerjoin(NewsSentiment, NewsSentiment.news_id == News.news_id)
        .where(NewsSentiment.sentiment_id.is_(None))
        .order_by(News.published_at.desc())
        .limit(limit)
    )
    return list(db.execute(statement).scalars().all())


def count_unscored_news(db: Session) -> int:
    """How many articles still need a sentiment score."""
    statement = (
        select(func.count())
        .select_from(News)
        .outerjoin(NewsSentiment, NewsSentiment.news_id == News.news_id)
        .where(NewsSentiment.sentiment_id.is_(None))
    )
    return db.execute(statement).scalar_one()


def add_sentiments(db: Session, scored: list) -> int:
    """Save (news_id, result) pairs into news_sentiment. Returns how many were saved."""
    rows = [
        NewsSentiment(
            news_id=news_id,
            sentiment=result["sentiment"],
            positive_score=result["positive_score"],
            neutral_score=result["neutral_score"],
            negative_score=result["negative_score"],
        )
        for news_id, result in scored
    ]
    db.add_all(rows)
    db.commit()
    return len(rows)


# ---------- scored news (for the sentiment summary endpoint) ----------
def get_scored_news(db: Session, stock_id: int, since: Optional[datetime] = None) -> list:
    """(News, NewsSentiment) pairs for scored articles, newest first.

    `since` is a UTC datetime without timezone, like News.published_at.
    """
    statement = (
        select(News, NewsSentiment)
        .join(NewsSentiment, NewsSentiment.news_id == News.news_id)
        .where(News.stock_id == stock_id)
        .order_by(News.published_at.desc())
    )
    if since is not None:
        statement = statement.where(News.published_at >= since)
    return list(db.execute(statement).all())

# ---------- incremental price update ----------
def upsert_price_bars(db: Session, stock_id: int, bars: list) -> tuple:
    """Insert new bars and correct stored bars whose values differ.

    Returns (inserted, updated). Used by update_data.py so a bar stored
    too early (for example a partial day) is fixed on a later run.
    """
    if not bars:
        return 0, 0
    start = min(bar.date for bar in bars)
    statement = select(PriceHistory).where(
        PriceHistory.stock_id == stock_id, PriceHistory.date >= start
    )
    existing = {row.date: row for row in db.execute(statement).scalars().all()}

    inserted = updated = 0
    for bar in bars:
        row = existing.get(bar.date)
        if row is None:
            db.add(
                PriceHistory(
                    stock_id=stock_id,
                    date=bar.date,
                    open_price=bar.open,
                    high_price=bar.high,
                    low_price=bar.low,
                    close_price=bar.close,
                    volume=bar.volume,
                )
            )
            inserted += 1
            continue

        same = (
            abs(float(row.open_price) - bar.open) < 0.005
            and abs(float(row.high_price) - bar.high) < 0.005
            and abs(float(row.low_price) - bar.low) < 0.005
            and abs(float(row.close_price) - bar.close) < 0.005
            and row.volume == bar.volume
        )
        if not same:
            row.open_price = bar.open
            row.high_price = bar.high
            row.low_price = bar.low
            row.close_price = bar.close
            row.volume = bar.volume
            updated += 1

    db.commit()
    return inserted, updated

# ---------- economic indicators ----------
def add_economic_points(db: Session, points: list) -> tuple:
    """Insert observations whose (name, country, date, source) is not stored yet.

    Never updates or deletes stored rows. Returns (inserted, already_stored, differs),
    where `differs` counts already-stored rows whose value differs from the new one
    (providers sometimes revise values; we report it but keep the stored value).
    """
    if not points:
        return 0, 0, 0

    statement = select(EconomicIndicator).where(
        EconomicIndicator.indicator_name.in_({p.indicator_name for p in points}),
        EconomicIndicator.country.in_({p.country for p in points}),
        EconomicIndicator.source.in_({p.source for p in points}),
    )
    existing = {
        (r.indicator_name, r.country, r.indicator_date, r.source): r.value
        for r in db.execute(statement).scalars().all()
    }

    inserted = already = differs = 0
    for p in points:
        key = (p.indicator_name, p.country, p.date, p.source)
        if key in existing:
            already += 1
            stored = existing[key]
            if stored is None or abs(float(stored) - p.value) > 0.0001:
                differs += 1
            continue
        existing[key] = p.value  # also protects against duplicates inside `points`
        db.add(
            EconomicIndicator(
                indicator_name=p.indicator_name,
                country=p.country,
                indicator_date=p.date,
                value=p.value,
                unit=p.unit,
                source=p.source,
            )
        )
        inserted += 1

    db.commit()
    return inserted, already, differs

def list_economic_series(db: Session) -> list:
    """One row per stored series: (country, name, unit, source, count, first, last)."""
    statement = (
        select(
            EconomicIndicator.country,
            EconomicIndicator.indicator_name,
            EconomicIndicator.unit,
            EconomicIndicator.source,
            func.count(),
            func.min(EconomicIndicator.indicator_date),
            func.max(EconomicIndicator.indicator_date),
        )
        .group_by(
            EconomicIndicator.country,
            EconomicIndicator.indicator_name,
            EconomicIndicator.unit,
            EconomicIndicator.source,
        )
        .order_by(EconomicIndicator.country, EconomicIndicator.indicator_name)
    )
    return list(db.execute(statement).all())


def get_economic_series(
    db: Session,
    country: str,
    indicator_name: str,
    start_year: Optional[int] = None,
    end_year: Optional[int] = None,
) -> List[EconomicIndicator]:
    """Observations of one series, oldest first. Name match ignores upper/lower case."""
    statement = (
        select(EconomicIndicator)
        .where(
            EconomicIndicator.country == country.strip().upper(),
            func.lower(EconomicIndicator.indicator_name) == indicator_name.strip().lower(),
        )
        .order_by(EconomicIndicator.indicator_date)
    )
    if start_year is not None:
        statement = statement.where(EconomicIndicator.indicator_date >= date(start_year, 1, 1))
    if end_year is not None:
        statement = statement.where(EconomicIndicator.indicator_date <= date(end_year, 12, 31))
    return list(db.execute(statement).scalars().all())