"""Read-only summary of the economic_indicators table."""
from sqlalchemy import func, select

from database import SessionLocal
from models import EconomicIndicator as E

with SessionLocal() as db:
    rows = db.execute(
        select(E.country, E.indicator_name, E.source, func.count(),
               func.min(E.indicator_date), func.max(E.indicator_date))
        .group_by(E.country, E.indicator_name, E.source)
        .order_by(E.country, E.indicator_name)
    ).all()

    print(f"{'COUNTRY':<9}{'INDICATOR':<42}{'SOURCE':<13}{'ROWS':<6}{'FIRST':<12}LAST")
    for country, name, source, n, first, last in rows:
        print(f"{country:<9}{name:<42}{source:<13}{n:<6}{str(first):<12}{last}")

    total = db.execute(select(func.count()).select_from(E)).scalar_one()
    duplicate_keys = db.execute(
        select(func.count()).select_from(
            select(E.indicator_name, E.country, E.indicator_date, E.source)
            .group_by(E.indicator_name, E.country, E.indicator_date, E.source)
            .having(func.count() > 1)
            .subquery()
        )
    ).scalar_one()
    print(f"\nTotal rows: {total}   Duplicate observations: {duplicate_keys}")