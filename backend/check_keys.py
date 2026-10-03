from config import settings

keys = {
    "TWELVE_DATA_API_KEY": settings.twelve_data_api_key,
    "FINNHUB_API_KEY": settings.finnhub_api_key,
    "NEWS_API_KEY": settings.news_api_key,
    "FRED_API_KEY": settings.fred_api_key,
}

for name, value in keys.items():
    if not value:
        status = "MISSING"
    elif value.startswith("your_"):
        status = "STILL A PLACEHOLDER"
    else:
        status = f"set ({len(value)} characters)"
    print(f"{name:<22} {status}")