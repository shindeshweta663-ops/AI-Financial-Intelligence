from crud import create_stock, get_stock_by_symbol, list_stocks
from database import SessionLocal

# (symbol, company_name, exchange, sector, industry)
STOCKS = [
    # ---------- US stocks ----------
    ("AAPL", "Apple Inc.", "NASDAQ", "Technology", "Consumer Electronics"),
    ("MSFT", "Microsoft Corporation", "NASDAQ", "Technology", "Software"),
    ("GOOGL", "Alphabet Inc.", "NASDAQ", "Communication Services", "Internet Content & Information"),
    ("AMZN", "Amazon.com Inc.", "NASDAQ", "Consumer Cyclical", "Internet Retail"),
    ("NVDA", "NVIDIA Corporation", "NASDAQ", "Technology", "Semiconductors"),
    ("TSLA", "Tesla Inc.", "NASDAQ", "Consumer Cyclical", "Auto Manufacturers"),
    ("JPM", "JPMorgan Chase & Co.", "NYSE", "Financial Services", "Banks"),
    ("JNJ", "Johnson & Johnson", "NYSE", "Healthcare", "Drug Manufacturers"),
    ("XOM", "Exxon Mobil Corporation", "NYSE", "Energy", "Oil & Gas Integrated"),
    ("WMT", "Walmart Inc.", "NYSE", "Consumer Defensive", "Discount Stores"),
    # ---------- Indian NSE stocks ----------
    ("TCS", "Tata Consultancy Services Ltd", "NSE", "Technology", "IT Services"),
    ("RELIANCE", "Reliance Industries Ltd", "NSE", "Energy", "Oil & Gas Refining & Marketing"),
    ("HDFCBANK", "HDFC Bank Ltd", "NSE", "Financial Services", "Banks"),
    ("ICICIBANK", "ICICI Bank Ltd", "NSE", "Financial Services", "Banks"),
    ("SBIN", "State Bank of India", "NSE", "Financial Services", "Banks"),
    ("ITC", "ITC Ltd", "NSE", "Consumer Defensive", "Tobacco & FMCG"),
    ("BHARTIARTL", "Bharti Airtel Ltd", "NSE", "Communication Services", "Telecom Services"),
    ("HCLTECH", "HCL Technologies Ltd", "NSE", "Technology", "IT Services"),
]

created = 0
skipped = 0

with SessionLocal() as db:
    for symbol, name, exchange, sector, industry in STOCKS:
        if get_stock_by_symbol(db, symbol):
            skipped += 1
            continue
        create_stock(db, symbol, name, exchange, sector, industry)
        created += 1

    print(f"Created: {created}   Already existed: {skipped}\n")
    print(f"{'ID':<5}{'SYMBOL':<12}{'EXCHANGE':<10}{'COMPANY'}")
    for stock in list_stocks(db):
        print(f"{stock.stock_id:<5}{stock.symbol:<12}{stock.exchange:<10}{stock.company_name}")