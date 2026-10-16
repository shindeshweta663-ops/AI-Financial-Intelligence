"""Load World Bank economic indicators into PostgreSQL.

Run from the backend folder:
    python load_economic.py --dry-run     fetch and print, write nothing
    python load_economic.py               fetch and store new observations

Safe to re-run: stored observations are never changed or deleted.
"""
import sys
import time

from crud import add_economic_points
from database import SessionLocal
from economic_data import WORLD_BANK_SERIES, get_world_bank_series
from market_data import MarketDataError


def main() -> None:
    dry_run = "--dry-run" in sys.argv[1:]
    failures = []
    print("DRY RUN: nothing will be written\n" if dry_run else "Loading World Bank series\n")

    with SessionLocal() as db:
        for country, code, name, unit in WORLD_BANK_SERIES:
            label = f"{country}  {name}"
            try:
                result = get_world_bank_series(country, code, name, unit)
                pts = result.points
                span = f"{pts[0].date.year}-{pts[-1].date.year}" if pts else "none"
                if dry_run:
                    print(f"{label}: fetched {len(pts)} ({span}), missing skipped {result.missing_skipped}")
                else:
                    inserted, already, differs = add_economic_points(db, pts)
                    print(f"{label}: fetched {len(pts)} ({span}), inserted {inserted}, "
                          f"already stored {already}, differing from stored {differs}")
            except MarketDataError as error:
                failures.append(f"{label}: {error}")
            except Exception as error:
                db.rollback()
                failures.append(f"{label}: {type(error).__name__}: {str(error)[:150]}")
            time.sleep(0.5)

    print()
    if failures:
        print(f"FINISHED WITH {len(failures)} FAILURE(S):")
        for failure in failures:
            print("  -", failure)
        sys.exit(1)
    print("All series finished without errors.")


if __name__ == "__main__":
    main()