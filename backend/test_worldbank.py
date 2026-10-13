"""World Bank client test. Fetches and prints only; nothing is written to PostgreSQL.

Run from the backend folder:  python test_worldbank.py
"""
import math
import sys

from economic_data import WORLD_BANK_SERIES, get_world_bank_series
from market_data import MarketDataError

failures = []


def check(ok: bool, message: str) -> None:
    print(("  PASS  " if ok else "  FAIL  ") + message)
    if not ok:
        failures.append(message)


print("=== 1. Every configured series ===")
results = {}
for country, code, name, unit in WORLD_BANK_SERIES:
    print(f"\n{country}  {code}  {name}")
    try:
        result = get_world_bank_series(country, code, name, unit)
    except MarketDataError as error:
        check(False, f"fetch failed: {error}")
        continue

    results[(country, code)] = result
    pts = result.points
    print(f"  pages={result.pages}  provider_total={result.reported_total}  "
          f"kept={len(pts)}  missing_skipped={result.missing_skipped}")
    check(len(pts) > 0, "has observations")
    if not pts:
        continue

    dates = [p.date for p in pts]
    check(dates == sorted(dates) and len(set(dates)) == len(dates), "dates ascending, no duplicates")
    check(all(math.isfinite(p.value) and abs(p.value) < 1e12 for p in pts), "values finite and fit NUMERIC(18,4)")
    check(len(pts) + result.missing_skipped == result.reported_total, "kept + missing = provider total")

    shown = pts if len(pts) <= 6 else pts[:3]
    for p in shown:
        print(f"    {p.date}  {p.value:.4f}")
    if len(pts) > 6:
        print("    ...")
        for p in pts[-3:]:
            print(f"    {p.date}  {p.value:.4f}")

print("\n=== 2. Pagination (same series with a tiny page size) ===")
full = results.get(("USA", "NY.GDP.MKTP.KD.ZG"))
try:
    small = get_world_bank_series("USA", "NY.GDP.MKTP.KD.ZG", "x", "x", page_size=5)
    print(f"  page_size=5 needed {small.pages} page(s)")
    check(small.pages > 1, "more than one page was followed")
    if full:
        same = [(p.date, p.value) for p in small.points] == [(p.date, p.value) for p in full.points]
        check(same, "paged result is identical to the single-page result")
except MarketDataError as error:
    check(False, f"pagination test failed: {error}")

print("\n=== 3. Invalid indicator code gives a clean error ===")
try:
    get_world_bank_series("USA", "NOT.A.REAL.CODE", "x", "x")
    check(False, "an invalid code should have raised an error")
except MarketDataError as error:
    check(True, f"clear error: {error}")

print()
if failures:
    print(f"{len(failures)} CHECK(S) FAILED")
    sys.exit(1)
print("All checks passed. Nothing was written to the database.")