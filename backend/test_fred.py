"""FRED client test. Fetches and prints only; nothing is written to PostgreSQL.

Run from the backend folder:  python test_fred.py
The API key is never printed.
"""
import math
import sys

from config import settings
from economic_data import FRED_SERIES, get_fred_series
from market_data import MarketDataError

failures = []

# plausible value ranges, to catch a wrong series or unit
RANGES = {"FEDFUNDS": (0, 25), "DGS10": (0, 20), "CPIAUCSL": (100, 1000)}


def check(ok: bool, message: str) -> None:
    print(("  PASS  " if ok else "  FAIL  ") + message)
    if not ok:
        failures.append(message)


print("=== 0. Key ===")
check(bool(settings.fred_api_key), "FRED_API_KEY is set (value not shown)")
if not settings.fred_api_key:
    sys.exit("Add FRED_API_KEY to .env first, then rerun.")

print("\n=== 1. Every configured series ===")
for country, series_id, name, unit, freq in FRED_SERIES:
    print(f"\n{country}  {series_id}  {name}")
    try:
        result = get_fred_series(country, series_id, name, unit, frequency=freq)
    except MarketDataError as error:
        check(False, f"fetch failed: {error}")
        continue

    pts = result.points
    print(f"  rows_returned={result.reported_total}  kept={len(pts)}  missing_skipped={result.missing_skipped}")
    check(len(pts) > 0, "has observations")
    if not pts:
        continue

    dates = [p.date for p in pts]
    check(dates == sorted(dates) and len(set(dates)) == len(dates), "dates ascending, no duplicates")
    low, high = RANGES[series_id]
    check(all(math.isfinite(p.value) and low <= p.value <= high for p in pts), f"values finite and within {low}-{high}")
    check(len(pts) + result.missing_skipped == result.reported_total, "kept + missing = rows returned")

    for p in pts[:3]:
        print(f"    {p.date}  {p.value:.4f}")
    print("    ...")
    for p in pts[-3:]:
        print(f"    {p.date}  {p.value:.4f}")

print("\n=== 2. Invalid series gives a clean error that does not leak the key ===")
try:
    get_fred_series("USA", "NOT_A_REAL_SERIES", "x", "x")
    check(False, "an invalid series should have raised an error")
except MarketDataError as error:
    check(settings.fred_api_key not in str(error), f"error is clean: {error}")

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED")
    sys.exit(1)
print("All checks passed. Nothing was written to the database.")