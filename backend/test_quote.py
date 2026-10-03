from market_data import MarketDataError, get_quote_finnhub, get_quote_twelve_data

SYMBOL = "AAPL"

for label, fetch in [("Twelve Data", get_quote_twelve_data), ("Finnhub", get_quote_finnhub)]:
    print(f"--- {label}: {SYMBOL} ---")
    try:
        quote = fetch(SYMBOL)
        print(quote.model_dump_json(indent=2))
    except MarketDataError as error:
        print("FAILED:", error)
    print()