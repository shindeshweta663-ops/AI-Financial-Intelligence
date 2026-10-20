"""Incremental update: prices -> indicators -> news -> FinBERT sentiment.

Run from the backend folder:
    python update_data.py AAPL          one stock
    python update_data.py AAPL MSFT     several stocks
    python update_data.py ALL           every covered stock in the database

Safe to re-run. It never deletes anything, skips unfinished trading days,
and reports a failure instead of pretending a failed provider call worked.
Prices and indicators: US stocks (NASDAQ/NYSE) via Twelve Data, Indian stocks
(NSE/BSE) via Yahoo Finance. News and sentiment: US stocks only, because the
news search is by ticker and a short Indian ticker could match another company.
"""
import sys
import time
from datetime import datetime, time as dtime, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from crud import (
    add_indicator_rows,
    add_news_items,
    add_sentiments,
    count_unscored_news,
    get_news,
    get_price_history,
    get_stock_by_symbol,
    get_unscored_news,
    list_stocks,
    upsert_price_bars,
)
from database import SessionLocal
from indicators import compute_indicators
from market_data import MarketDataError, get_daily_history_twelve_data
from market_data_yf import YF_SUFFIX, get_daily_history_yfinance
from news_service import get_company_news_history

US_EXCHANGES = {"NASDAQ", "NYSE"}
COVERED_EXCHANGES = US_EXCHANGES | set(YF_SUFFIX)  # prices and indicators; news stays US-only
NEW_YORK = ZoneInfo("America/New_York")
COLUMNS = ["sma20", "ema20", "ema50", "rsi", "macd", "macd_signal", "volatility"]
SCORE_BATCH = 64


def is_complete_day(bar_date: datetime) -> bool:
    """False for a US trading day that is still in progress (its bar is partial)."""
    now = datetime.now(NEW_YORK)
    day = bar_date.date()
    if day < now.date():
        return True
    if day > now.date():
        return False
    return now.time() >= dtime(16, 30)  # after the close, with time to settle


def update_prices(db, stock) -> tuple:
    latest = get_price_history(db, stock.stock_id, limit=1)
    gap_days = (datetime.now() - latest[-1].date).days if latest else None
    long_gap = gap_days is None or gap_days > 35

    if stock.exchange in YF_SUFFIX:
        # the Yahoo loader already drops today's unfinished bar (India time)
        bars = get_daily_history_yfinance(stock.symbol, stock.exchange, period="5y" if long_gap else "3mo")
        complete = bars
    else:
        bars = get_daily_history_twelve_data(stock.symbol, outputsize=1250 if long_gap else 30)
        complete = [b for b in bars if is_complete_day(b.date)]
    inserted, updated = upsert_price_bars(db, stock.stock_id, complete)
    return len(bars), inserted, updated, len(bars) - len(complete)


def update_indicators(db, stock) -> int:
    rows = [
        r for r in get_price_history(db, stock.stock_id, limit=5000)
        if stock.exchange in YF_SUFFIX or is_complete_day(r.date)
    ]
    if not rows:
        return 0
    close = pd.Series(
        [float(r.close_price) for r in rows],
        index=pd.to_datetime([r.date for r in rows]),
    )
    ind = compute_indicators(close).dropna()  # drop warm-up rows
    records = [
        {"date": ts.to_pydatetime(), **{c: float(row[c]) for c in COLUMNS}}
        for ts, row in ind.iterrows()
    ]
    return add_indicator_rows(db, stock.stock_id, records)


def update_news(db, stock) -> tuple:
    if stock.exchange not in US_EXCHANGES:
        return None  # news search is by ticker, which could match another company for Indian stocks
    latest = get_news(db, stock.stock_id, limit=1)
    if latest:
        now_utc = datetime.now(timezone.utc).replace(tzinfo=None)
        gap = (now_utc - latest[0].published_at).days
        days = min(max(gap + 2, 3), 365)  # 2 days of overlap, duplicates are skipped
    else:
        days = 30
    items = get_company_news_history(stock.symbol, days=days)
    return days, len(items), add_news_items(db, stock.stock_id, items)


def score_new_articles(db) -> int:
    waiting = count_unscored_news(db)
    if waiting == 0:
        return 0
    from sentiment import build_text, score_texts  # slow import, only when needed

    done = 0
    while True:
        rows = get_unscored_news(db, limit=SCORE_BATCH)
        if not rows:
            break
        results = score_texts([build_text(r.title, r.description) for r in rows])
        added = add_sentiments(db, [(r.news_id, res) for r, res in zip(rows, results)])
        if added == 0:
            break
        done += added
        print(f"  scored {done}/{waiting}")
    return done


def run_step(db, stock, label, fn, failures):
    try:
        return fn()
    except MarketDataError as error:
        failures.append(f"{stock.symbol} {label}: {error}")
    except Exception as error:
        db.rollback()
        failures.append(f"{stock.symbol} {label}: {type(error).__name__}: {str(error)[:150]}")
    return None


def pick_stocks(db, names) -> list:
    if names == ["ALL"]:
        return [s for s in list_stocks(db) if s.exchange in COVERED_EXCHANGES]
    stocks = []
    for name in names:
        stock = get_stock_by_symbol(db, name)
        if not stock:
            print(f"{name}: not in the stocks table, skipped")
        elif stock.exchange not in COVERED_EXCHANGES:
            print(f"{name}: exchange {stock.exchange} is not covered by this updater, skipped")
        else:
            stocks.append(stock)
    return stocks


def main() -> None:
    names = [a.upper() for a in sys.argv[1:]]
    if not names:
        sys.exit("Usage: python update_data.py AAPL [MSFT ...]   or   python update_data.py ALL")

    failures = []
    with SessionLocal() as db:
        for stock in pick_stocks(db, names):
            print(f"\n{stock.symbol}")

            r = run_step(db, stock, "prices", lambda: update_prices(db, stock), failures)
            if r:
                fetched, inserted, updated, skipped = r
                print(f"  prices:     fetched {fetched}, inserted {inserted}, "
                      f"corrected {updated}, skipped {skipped} unfinished day(s)")

            r = run_step(db, stock, "indicators", lambda: update_indicators(db, stock), failures)
            if r is not None:
                print(f"  indicators: inserted {r}")

            if stock.exchange in US_EXCHANGES:
                r = run_step(db, stock, "news", lambda: update_news(db, stock), failures)
                if r:
                    days, fetched, inserted = r
                    print(f"  news:       looked back {days} days, fetched {fetched}, inserted {inserted}")
            else:
                print("  news:       skipped (news search is by ticker, so only US stocks are covered)")

            time.sleep(1)

        try:
            print(f"\nSentiment: scored {score_new_articles(db)} new article(s)")
        except Exception as error:
            db.rollback()
            failures.append(f"scoring: {type(error).__name__}: {str(error)[:150]}")

    print()
    if failures:
        print(f"FINISHED WITH {len(failures)} FAILURE(S). These datasets are NOT fully updated:")
        for failure in failures:
            print("  -", failure)
        sys.exit(1)
    print("All steps finished without errors.")


if __name__ == "__main__":
    main()