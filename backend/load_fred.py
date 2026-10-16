"""Load FRED economic series into PostgreSQL.

Run from the backend folder:
    python load_fred.py --dry-run     fetch and print, write nothing
    python load_fred.py               fetch and store new observations

Safe to re-run: stored observations are never changed or deleted.
Needs FRED_API_KEY in .env (never printed).
"""
import sys

from crud import add_economic_points
from database import SessionLocal
from economic_data import FRED_SERIES, get_fred_series
from market_data import MarketDataError


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    failures = []
    print("DRY RUN: nothing will be written\n" if dry_run else "Loading FRED series\n")

    with SessionLocal() as db:
        for country, series_id, name, unit, frequency in FRED_SERIES:
            label = f"{series_id}  {name}"
            try:
                result = get_fred_series(country, series_id, name, unit, frequency=frequency)
                pts = result.points
                span = f"{pts[0].date}..{pts[-1].date}" if pts else "none"
                missing = ", ".join(result.missing_dates) if result.missing_dates else "none"
                if dry_run:
                    print(f"{label}\n  fetched {len(pts)} ({span}), missing dates: {missing}")
                else:
                    inserted, already, differs = add_economic_points(db, pts)
                    print(f"{label}\n  fetched {len(pts)} ({span}), missing dates: {missing}\n"
                          f"  inserted {inserted}, already stored {already}, differing from stored {differs}")
            except MarketDataError as error:
                failures.append(f"{series_id}: {error}")
            except Exception as error:
                db.rollback()
                failures.append(f"{series_id}: {type(error).__name__}: {str(error)[:150]}")

    print()
    if failures:
        print(f"FINISHED WITH {len(failures)} FAILURE(S):")
        for failure in failures:
            print("  -", failure)
        sys.exit(1)
    print("All series finished without errors.")


if __name__ == "__main__":
    main()