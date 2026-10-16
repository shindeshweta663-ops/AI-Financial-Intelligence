"""Read-only price quality check, run before risk analysis.

Looks for gaps, duplicate dates, non-positive closes and suspicious one-day moves
(an unadjusted stock split shows up as a very large one-day drop).
"""
import pandas as pd

from crud import get_price_history, list_stocks
from database import SessionLocal

US_EXCHANGES = {"NASDAQ", "NYSE"}

with SessionLocal() as db:
    print(f"{'SYMBOL':<8}{'ROWS':<7}{'FIRST':<12}{'LAST':<12}{'GAP(d)':<8}{'DUPES':<7}{'<=0':<5}{'|MOVE|>20%':<12}LARGEST MOVE")
    for stock in list_stocks(db):
        if stock.exchange not in US_EXCHANGES:
            continue
        rows = get_price_history(db, stock.stock_id, limit=5000)
        if not rows:
            print(f"{stock.symbol:<8}no prices")
            continue

        close = pd.Series(
            [float(r.close_price) for r in rows],
            index=pd.to_datetime([r.date for r in rows]),
        ).sort_index()
        returns = close.pct_change().dropna()

        max_gap = int(close.index.to_series().diff().dt.days.max())
        dupes = int(close.index.duplicated().sum())
        non_positive = int((close <= 0).sum())
        big = int((returns.abs() > 0.20).sum())
        day = returns.abs().idxmax()
        largest = f"{returns[day] * 100:+.1f}% on {str(day)[:10]}"

        print(f"{stock.symbol:<8}{len(close):<7}{str(close.index[0])[:10]:<12}{str(close.index[-1])[:10]:<12}"
              f"{max_gap:<8}{dupes:<7}{non_positive:<5}{big:<12}{largest}")