import pandas as pd

from crud import get_indicator_history, get_price_history, list_stocks
from database import SessionLocal
from indicators import compute_indicators

COLUMNS = ["sma20", "ema20", "ema50", "rsi", "macd", "macd_signal", "volatility"]
TOLERANCE = 0.001  # stored values have about 4 decimals
US_EXCHANGES = {"NASDAQ", "NYSE"}


def to_float(value) -> float:
    return float(value) if value is not None else float("nan")


with SessionLocal() as db:
    print(f"{'SYMBOL':<8}{'COMPARED':<10}{'DIFFERENT':<11}{'MISSING':<9}{'FIRST DIFFERENCE':<18}{'LARGEST DIFF'}")
    for stock in list_stocks(db):
        if stock.exchange not in US_EXCHANGES:
            continue

        prices = get_price_history(db, stock.stock_id, limit=5000)
        close = pd.Series(
            [float(r.close_price) for r in prices],
            index=pd.to_datetime([r.date for r in prices]),
        )
        fresh = compute_indicators(close).dropna()

        rows = get_indicator_history(db, stock.stock_id, limit=5000)
        stored = pd.DataFrame(
            [{"date": r.date, **{c: to_float(getattr(r, c)) for c in COLUMNS}} for r in rows]
        )
        if stored.empty:
            print(f"{stock.symbol:<8}no stored indicators")
            continue
        stored.index = pd.to_datetime(stored["date"])

        common = stored.index.intersection(fresh.index)
        missing = len(fresh.index.difference(stored.index))
        diff = (stored.loc[common, COLUMNS] - fresh.loc[common, COLUMNS]).abs()
        bad = (diff > TOLERANCE).any(axis=1)
        first = str(bad[bad].index[0])[:10] if bad.any() else "-"
        largest = f"{diff.max().max():.4f}"
        print(f"{stock.symbol:<8}{len(common):<10}{int(bad.sum()):<11}{missing:<9}{first:<18}{largest}")