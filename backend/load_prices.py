import sys

from crud import add_price_bars, get_price_history, get_stock_by_symbol
from database import SessionLocal
from market_data import MarketDataError, get_daily_history_twelve_data

symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"

with SessionLocal() as db:
    stock = get_stock_by_symbol(db, symbol)
    if not stock:
        print(f"{symbol} is not in the stocks table. Add it first (seed_stocks.py).")
        sys.exit(1)

    print(f"Fetching daily history for {stock.symbol} from Twelve Data...")
    try:
        bars = get_daily_history_twelve_data(stock.symbol)
    except MarketDataError as error:
        print("FAILED:", error)
        sys.exit(1)

    print(f"Downloaded {len(bars)} daily bars ({bars[0].date.date()} to {bars[-1].date.date()})")
    added = add_price_bars(db, stock.stock_id, bars)
    print(f"Inserted {added} new rows ({len(bars) - added} were already stored)")

    stored = get_price_history(db, stock.stock_id, limit=3)
    print("\nLatest 3 stored rows:")
    for row in stored:
        print(f"  {row.date.date()}  O={row.open_price}  H={row.high_price}  "
              f"L={row.low_price}  C={row.close_price}  V={row.volume}")