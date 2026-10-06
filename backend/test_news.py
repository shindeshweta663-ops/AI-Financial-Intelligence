import sys

from market_data import MarketDataError
from news_service import get_company_news

symbol = sys.argv[1] if len(sys.argv) > 1 else "AAPL"
days = int(sys.argv[2]) if len(sys.argv) > 2 else 7

try:
    items = get_company_news(symbol, days=days)
except MarketDataError as error:
    sys.exit(f"FAILED: {error}")

print(f"{symbol}: {len(items)} articles in the last {days} days")
if items:
    print(f"Newest: {items[0].published_at} UTC | Oldest: {items[-1].published_at} UTC")
    sources = sorted({i.source for i in items if i.source})
    print(f"Sources ({len(sources)}): {', '.join(sources[:8])}")
    with_summary = sum(1 for i in items if i.description)
    print(f"Articles with a summary: {with_summary} of {len(items)}\n")
    print("Latest 5 headlines:")
    for item in items[:5]:
        print(f"  {item.published_at:%Y-%m-%d %H:%M}  [{item.source}]  {item.title[:90]}")