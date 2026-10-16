"""Read-only audit of the data that Phase 10 (feature engineering) will use.

Run from the backend folder:  python check_feature_inputs.py
It only reads from the database. Nothing is written or changed.
"""
from sqlalchemy import func, select

from database import SessionLocal
from models import (
    EconomicIndicator,
    FinancialStatement,
    News,
    NewsSentiment,
    PriceHistory,
    Stock,
    TechnicalIndicator,
)

US_EXCHANGES = {"NASDAQ", "NYSE"}


def day(value):
    return "-" if value is None else str(value)[:10]


def has_time_of_day(value):
    return bool(value.hour or value.minute or value.second)


with SessionLocal() as db:
    stocks = [
        s
        for s in db.execute(select(Stock).order_by(Stock.symbol)).scalars().all()
        if s.exchange in US_EXCHANGES
    ]

    # ------------------------------------------------------------------
    print("=== 1. PRICES vs TECHNICAL INDICATORS (dates must line up) ===")
    print(f"{'SYMBOL':<7}{'PRICE ROWS':>11} {'FIRST':<11}{'LAST':<11}"
          f"{'IND ROWS':>9} {'IND FIRST':<11}{'PRICES W/O IND':>15}{'IND W/O PRICE':>14}{'TIME-OF-DAY':>12}")
    price_dates_by_stock = {}
    for s in stocks:
        prices = db.execute(
            select(PriceHistory.date).where(PriceHistory.stock_id == s.stock_id)
        ).scalars().all()
        inds = db.execute(
            select(TechnicalIndicator.date).where(TechnicalIndicator.stock_id == s.stock_id)
        ).scalars().all()
        price_days = {d.date() for d in prices}
        ind_days = {d.date() for d in inds}
        price_dates_by_stock[s.stock_id] = price_days
        timed = sum(1 for d in prices if has_time_of_day(d))
        print(
            f"{s.symbol:<7}{len(prices):>11} {day(min(prices, default=None)):<11}"
            f"{day(max(prices, default=None)):<11}{len(inds):>9} "
            f"{day(min(inds, default=None)):<11}{len(price_days - ind_days):>15}"
            f"{len(ind_days - price_days):>14}{timed:>12}"
        )
    print("Expected: 'PRICES W/O IND' about 49 (warm-up), 'IND W/O PRICE' 0, 'TIME-OF-DAY' 0.\n")

    # ------------------------------------------------------------------
    print("=== 2. NEWS COVERAGE (how much of the price history has news?) ===")
    print(f"{'SYMBOL':<7}{'ARTICLES':>9}{'SCORED':>8} {'FIRST ARTICLE':<14}{'LAST ARTICLE':<14}"
          f"{'TRADING DAYS IN SPAN':>21}{'WITH NEWS':>10}{'COVERAGE':>9}{'SHARE OF ALL DAYS':>18}")
    for s in stocks:
        published = db.execute(
            select(News.published_at).where(News.stock_id == s.stock_id)
        ).scalars().all()
        published = [p for p in published if p is not None]
        scored = db.execute(
            select(func.count())
            .select_from(News)
            .join(NewsSentiment, NewsSentiment.news_id == News.news_id)
            .where(News.stock_id == s.stock_id)
        ).scalar_one()
        if not published:
            print(f"{s.symbol:<7}{0:>9}{scored:>8} no news stored")
            continue
        first, last = min(published), max(published)
        news_days = {p.date() for p in published}
        trading_days = price_dates_by_stock[s.stock_id]
        span = [d for d in trading_days if first.date() <= d <= last.date()]
        with_news = sum(1 for d in span if d in news_days)
        coverage = with_news / len(span) if span else 0.0
        share_all = with_news / len(trading_days) if trading_days else 0.0
        print(
            f"{s.symbol:<7}{len(published):>9}{scored:>8} {day(first):<14}{day(last):<14}"
            f"{len(span):>21}{with_news:>10}{coverage:>9.0%}{share_all:>18.0%}"
        )
    print("Dates here are UTC calendar days, so coverage is approximate.\n")

    # ------------------------------------------------------------------
    print("=== 3. ECONOMIC SERIES ===")
    series = db.execute(
        select(
            EconomicIndicator.indicator_name,
            EconomicIndicator.country,
            EconomicIndicator.source,
            func.count(),
            func.min(EconomicIndicator.indicator_date),
            func.max(EconomicIndicator.indicator_date),
        )
        .group_by(
            EconomicIndicator.indicator_name,
            EconomicIndicator.country,
            EconomicIndicator.source,
        )
        .order_by(EconomicIndicator.source, EconomicIndicator.indicator_name)
    ).all()
    for name, country, source, count, first, last in series:
        dates = db.execute(
            select(EconomicIndicator.indicator_date).where(
                EconomicIndicator.indicator_name == name,
                EconomicIndicator.country == country,
                EconomicIndicator.source == source,
            )
        ).scalars().all()
        months = {(d.year, d.month) for d in dates if d is not None}
        expected_months = (last.year - first.year) * 12 + last.month - first.month + 1
        gaps = f"months present {len(months)} of {expected_months}"
        print(f"{str(source):<12}{str(country):<5}{day(first)} to {day(last)}  "
              f"rows={count:<4} {gaps}  | {name}")
    print("For annual series, 'months present' is expected to be small.\n")

    # ------------------------------------------------------------------
    print("=== 4. FINANCIAL STATEMENTS (annual) ===")
    print(f"{'SYMBOL':<7}{'ROWS':>5} {'FIRST REPORT':<14}{'LAST REPORT':<14}")
    for s in stocks:
        count, first, last = db.execute(
            select(
                func.count(),
                func.min(FinancialStatement.report_date),
                func.max(FinancialStatement.report_date),
            ).where(FinancialStatement.stock_id == s.stock_id)
        ).one()
        print(f"{s.symbol:<7}{count:>5} {day(first):<14}{day(last):<14}")
    print("\nAudit finished. Nothing was changed.")