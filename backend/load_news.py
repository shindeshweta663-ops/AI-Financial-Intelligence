import sys

from crud import add_news_items, count_news, get_stock_by_symbol, list_stocks
from database import SessionLocal
from market_data import MarketDataError
from news_service import get_company_news_history

US_EXCHANGES = {"NASDAQ", "NYSE"}  # Finnhub's free news covers US companies

# Usage:  python load_news.py AAPL 30     (one stock, last 30 days)
#         python load_news.py ALL 30      (all US stocks)
target = sys.argv[1].upper() if len(sys.argv) > 1 else "AAPL"
days = int(sys.argv[2]) if len(sys.argv) > 2 else 30

with SessionLocal() as db:
    if target == "ALL":
        stocks = [s for s in list_stocks(db) if s.exchange in US_EXCHANGES]
    else:
        stock = get_stock_by_symbol(db, target)
        if not stock:
            sys.exit(f"{target} is not in the stocks table.")
        stocks = [stock]

    for stock in stocks:
        try:
            items = get_company_news_history(stock.symbol, days=days)
        except MarketDataError as error:
            print(f"{stock.symbol:<8} FAILED: {error}")
            continue

        added = add_news_items(db, stock.stock_id, items)
        total = count_news(db, stock.stock_id)
        print(f"{stock.symbol:<8} fetched {len(items)}, inserted {added} new, stored total {total}")

print("\nDone.")