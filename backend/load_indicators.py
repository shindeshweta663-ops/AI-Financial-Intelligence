import sys

import pandas as pd

from crud import add_indicator_rows, get_price_history, get_stock_by_symbol, list_stocks
from database import SessionLocal
from indicators import compute_indicators

COLUMNS = ["sma20", "ema20", "ema50", "rsi", "macd", "macd_signal", "volatility"]


def load_for_stock(db, stock) -> str:
    rows = get_price_history(db, stock.stock_id, limit=5000)
    if not rows:
        return "no prices stored, skipped"

    close = pd.Series(
        [float(r.close_price) for r in rows],
        index=pd.to_datetime([r.date for r in rows]),
    )
    ind = compute_indicators(close).dropna()  # drop warm-up rows

    records = [
        {"date": ts.to_pydatetime(), **{c: float(row[c]) for c in COLUMNS}}
        for ts, row in ind.iterrows()
    ]
    added = add_indicator_rows(db, stock.stock_id, records)
    return f"calculated {len(records)} rows, inserted {added} new"


with SessionLocal() as db:
    if len(sys.argv) > 1:
        stock = get_stock_by_symbol(db, sys.argv[1])
        if not stock:
            sys.exit(f"{sys.argv[1]} is not in the stocks table.")
        stocks = [stock]
    else:
        stocks = list_stocks(db)

    for stock in stocks:
        print(f"{stock.symbol:<12} {load_for_stock(db, stock)}")

print("\nDone.")