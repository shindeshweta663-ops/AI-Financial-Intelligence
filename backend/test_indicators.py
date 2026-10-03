import sys

import pandas as pd

from crud import get_price_history, get_stock_by_symbol
from database import SessionLocal
from indicators import compute_indicators

symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

with SessionLocal() as db:
    stock = get_stock_by_symbol(db, symbol)
    if not stock:
        sys.exit(f"{symbol} is not in the stocks table.")
    rows = get_price_history(db, stock.stock_id, limit=1500)

if not rows:
    sys.exit(f"No stored prices for {symbol}. Run load_prices.py first.")

close = pd.Series(
    [float(r.close_price) for r in rows],
    index=pd.to_datetime([r.date for r in rows]),
)
ind = compute_indicators(close)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)

print(f"{symbol}: {len(ind)} rows\n")
print("Latest 5 rows:")
print(ind.tail(5).round(2))

# ---------- sanity checks ----------
print("\nSanity checks:")
valid_rsi = ind["rsi"].dropna()
print("  RSI always between 0 and 100:", bool(valid_rsi.between(0, 100).all()))

manual_sma = close.iloc[-20:].mean()
print("  SMA20 matches a manual average:", abs(ind["sma20"].iloc[-1] - manual_sma) < 1e-9)

macd_diff = (ind["macd"] - ind["macd_signal"]).dropna()
print("  MACD and signal both calculated:", len(macd_diff) > 0)

print("  First row with all indicators:", ind.dropna().index[0].date())
print("  Rows without full indicators (warm-up):", len(ind) - len(ind.dropna()))