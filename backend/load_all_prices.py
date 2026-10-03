from crud import add_price_bars, get_price_history, list_stocks
from database import SessionLocal
from market_data import MarketDataError, get_daily_history_twelve_data

US_EXCHANGES = {"NASDAQ", "NYSE"}

with SessionLocal() as db:
    targets = [s for s in list_stocks(db) if s.exchange in US_EXCHANGES]
    print(f"{len(targets)} US stocks found.\n")

    for stock in targets:
        if get_price_history(db, stock.stock_id, limit=1):
            print(f"{stock.symbol:<8} already has data, skipped")
            continue
        try:
            bars = get_daily_history_twelve_data(stock.symbol)
            added = add_price_bars(db, stock.stock_id, bars)
            print(f"{stock.symbol:<8} inserted {added} rows")
        except MarketDataError as error:
            print(f"{stock.symbol:<8} FAILED: {error}")

print("\nDone.")
