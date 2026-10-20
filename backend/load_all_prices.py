from crud import add_price_bars, get_price_history, list_stocks
from database import SessionLocal
from market_data import MarketDataError, get_daily_history_twelve_data
from market_data_yf import YF_SUFFIX, get_daily_history_yfinance

US_EXCHANGES = {"NASDAQ", "NYSE"}   # Twelve Data (free plan covers these)
# NSE / BSE come from Yahoo Finance, because Twelve Data's free plan does not cover them.

with SessionLocal() as db:
    targets = [s for s in list_stocks(db) if s.exchange in US_EXCHANGES or s.exchange in YF_SUFFIX]
    print(f"{len(targets)} stocks found.\n")

    for stock in targets:
        if get_price_history(db, stock.stock_id, limit=1):
            print(f"{stock.symbol:<10} already has data, skipped")
            continue
        try:
            if stock.exchange in US_EXCHANGES:
                bars = get_daily_history_twelve_data(stock.symbol)
            else:
                bars = get_daily_history_yfinance(stock.symbol, stock.exchange)
            added = add_price_bars(db, stock.stock_id, bars)
            print(f"{stock.symbol:<10} inserted {added} rows")
        except MarketDataError as error:
            print(f"{stock.symbol:<10} FAILED: {error}")

print("\nDone.")