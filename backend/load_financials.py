import sys
import time

from crud import add_financial_rows, get_financial_history, get_stock_by_symbol, list_stocks
from database import SessionLocal
from financials import get_annual_financials
from market_data import MarketDataError

US_EXCHANGES = {"NASDAQ", "NYSE"}


def billions(value):
    return "n/a" if value is None else f"{float(value) / 1e9:,.2f}B"


with SessionLocal() as db:
    if len(sys.argv) > 1:
        stock = get_stock_by_symbol(db, sys.argv[1])
        if not stock:
            sys.exit(f"{sys.argv[1]} is not in the stocks table.")
        stocks = [stock]
    else:
        stocks = [s for s in list_stocks(db) if s.exchange in US_EXCHANGES]

    for stock in stocks:
        try:
            records = get_annual_financials(stock.symbol)
        except MarketDataError as error:
            print(f"{stock.symbol:<8} FAILED: {error}")
            continue

        added = add_financial_rows(db, stock.stock_id, records)
        latest = get_financial_history(db, stock.stock_id, limit=1)[-1]
        print(f"{stock.symbol:<8} {len(records)} annual rows, inserted {added} new")
        print(
            f"         latest {latest.report_date}: revenue={billions(latest.revenue)} "
            f"net={billions(latest.net_profit)} assets={billions(latest.total_assets)} "
            f"debt={billions(latest.total_debt)} eps={latest.eps} margin={latest.profit_margin}%"
        )
        time.sleep(1.2)  # stay well inside Finnhub's 60 calls/minute

print("\nDone.")