import sys

import requests

from config import settings

URL = "https://finnhub.io/api/v1/stock/financials-reported"
TIMEOUT = 30

# Only show line items whose name contains one of these words (keeps output short)
KEYWORDS = ("revenue", "sales", "netincome", "profit", "earningspershare",
            "assets", "debt", "borrowing", "notespayable", "commercialpaper")

symbol = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()

try:
    response = requests.get(
        URL,
        params={"symbol": symbol, "freq": "annual", "token": settings.finnhub_api_key},
        timeout=TIMEOUT,
    )
except requests.RequestException:
    sys.exit("Network error or timeout.")

print(f"{symbol}: HTTP {response.status_code}")
if response.status_code != 200:
    sys.exit("Endpoint not available for this symbol or key.")

filings = response.json().get("data", [])
print(f"Annual filings returned: {len(filings)}")
if not filings:
    sys.exit("No filings returned.")

print("Fields in each filing:", sorted(k for k in filings[0] if k != "report"))
print("Filing dates (newest first):",
      [f.get("endDate", "")[:10] for f in sorted(filings, key=lambda f: f.get("endDate", ""), reverse=True)[:4]])

latest = max(filings, key=lambda f: f.get("endDate", ""))
print(f"\nLatest filing: form={latest.get('form')} year={latest.get('year')} "
      f"period={str(latest.get('startDate'))[:10]} to {str(latest.get('endDate'))[:10]}\n")

for section, title in (("ic", "INCOME STATEMENT"), ("bs", "BALANCE SHEET")):
    items = latest.get("report", {}).get(section, [])
    print(f"--- {title}: {len(items)} items, showing matches ---")
    for item in items:
        concept = str(item.get("concept", ""))
        if any(word in concept.lower() for word in KEYWORDS):
            print(f"  {concept:<70} {item.get('value')}")
    print()