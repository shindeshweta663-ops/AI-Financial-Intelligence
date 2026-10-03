import os

import requests

from config import settings  # importing config also loads the .env file

TIMEOUT = 20
SYMBOL = "AAPL"
FINNHUB = "https://finnhub.io/api/v1"


def fetch(url, params=None, headers=None):
    """Return (status_code, parsed_json_or_None). Never prints URLs, so keys stay hidden."""
    try:
        response = requests.get(url, params=params, headers=headers, timeout=TIMEOUT)
    except requests.RequestException:
        return None, None
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


def show(label, status, note=""):
    print(f"{label:<34} HTTP {status}   {note}")


# ---------- Finnhub ----------
token = {"symbol": SYMBOL, "token": settings.finnhub_api_key}
print("=== Finnhub (free key) ===")

status, body = fetch(f"{FINNHUB}/stock/profile2", token)
note = ""
if status == 200 and body:
    note = f"name={body.get('name')} | industry={body.get('finnhubIndustry')} | exchange={body.get('exchange')}"
show("/stock/profile2", status, note)

status, body = fetch(f"{FINNHUB}/stock/metric", {**token, "metric": "all"})
note = ""
if status == 200 and body:
    metric = body.get("metric", {})
    note = (f"{len(metric)} metrics | epsTTM={metric.get('epsTTM')} | "
            f"netMargin={metric.get('netProfitMarginTTM')}")
show("/stock/metric", status, note)

status, body = fetch(f"{FINNHUB}/stock/earnings", token)
note = ""
if status == 200 and isinstance(body, list):
    note = f"{len(body)} quarters" + (f" | latest period={body[0].get('period')}" if body else "")
show("/stock/earnings", status, note)

status, body = fetch(f"{FINNHUB}/stock/financials-reported", token)
note = "usable" if status == 200 and body and body.get("data") else "no statement data"
show("/stock/financials-reported", status, note)

status, body = fetch(f"{FINNHUB}/stock/financials", {**token, "statement": "ic", "freq": "annual"})
note = "usable" if status == 200 and body and body.get("financials") else "no statement data"
show("/stock/financials (income stmt)", status, note)

# ---------- SEC EDGAR ----------
print("\n=== SEC EDGAR (no API key) ===")
user_agent = os.getenv("SEC_USER_AGENT", "")
if not user_agent or "example.com" in user_agent:
    print("SEC_USER_AGENT is missing or still the example email. Fix .env and run again.")
else:
    url = "https://data.sec.gov/api/xbrl/companyconcept/CIK0000320193/us-gaap/NetIncomeLoss.json"
    status, body = fetch(url, headers={"User-Agent": user_agent})
    note = ""
    if status == 200 and body:
        facts = body.get("units", {}).get("USD", [])
        annual = [f for f in facts if f.get("form") == "10-K" and f.get("fp") == "FY"]
        if annual:
            last = annual[-1]
            note = f"{len(annual)} annual values | latest period ends {last.get('end')} | net income={last.get('val')}"
        else:
            note = f"{len(facts)} values, no annual 10-K rows found"
    show("AAPL net income (companyconcept)", status, note)

print("\nProbe finished. Nothing was stored.")