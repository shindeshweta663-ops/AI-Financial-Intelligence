from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from crud import get_economic_series, list_economic_series
from database import get_db

router = APIRouter(prefix="/api/economic", tags=["Economic"])


class SeriesInfoOut(BaseModel):
    country: str
    indicator: str
    unit: Optional[str] = None
    source: Optional[str] = None
    observations: int
    first_date: Optional[date] = None
    last_date: Optional[date] = None


class CatalogOut(BaseModel):
    count: int
    note: str = (
        "Use the exact 'country' and 'indicator' values below with /api/economic/data. "
        "Only series loaded into the database are listed."
    )
    series: List[SeriesInfoOut]


class ObservationOut(BaseModel):
    date: date
    value: float


class SeriesOut(BaseModel):
    country: str
    indicator: str
    unit: Optional[str] = None
    source: Optional[str] = None
    frequency: str
    count: int
    note: str = (
        "Annual values are dated Dec 31 of the year they describe; monthly values are "
        "dated the first day of the month they describe. Dates mark the period covered, "
        "not the publication date: providers publish later and may revise values. "
        "These are reported statistics, not forecasts or investment advice."
    )
    observations: List[ObservationOut]


def _frequency(first_two_dates: list) -> str:
    """Infer 'monthly' or 'annual' from the spacing of the first two observations."""
    if len(first_two_dates) < 2:
        return "unknown"
    gap = (first_two_dates[1] - first_two_dates[0]).days
    if gap <= 32:
        return "monthly"
    if gap >= 360:
        return "annual"
    return "other"


@router.get("/indicators", response_model=CatalogOut)
def list_indicators(db: Session = Depends(get_db)):
    """List the economic series stored in the database."""
    rows = list_economic_series(db)
    return CatalogOut(
        count=len(rows),
        series=[
            SeriesInfoOut(
                country=country,
                indicator=name,
                unit=unit,
                source=source,
                observations=n,
                first_date=first,
                last_date=last,
            )
            for country, name, unit, source, n, first, last in rows
        ],
    )


@router.get("/data", response_model=SeriesOut)
def get_series(
    country: str = Query(..., min_length=2, max_length=3, description="ISO3 code, e.g. USA or IND"),
    indicator: str = Query(..., min_length=3, max_length=150, description="Exact name from /api/economic/indicators"),
    start_year: Optional[int] = Query(None, ge=1900, le=2100),
    end_year: Optional[int] = Query(None, ge=1900, le=2100),
    db: Session = Depends(get_db),
):
    """One economic series, oldest first, with optional year filters."""
    if start_year is not None and end_year is not None and start_year > end_year:
        raise HTTPException(status_code=422, detail="start_year must not be after end_year")

    rows = get_economic_series(db, country, indicator, start_year, end_year)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No data for that country, indicator and period. "
                   "See /api/economic/indicators for the available series.",
        )
    first = rows[0]
    return SeriesOut(
        country=first.country,
        indicator=first.indicator_name,
        unit=first.unit,
        source=first.source,
        frequency=_frequency([r.indicator_date for r in rows[:2]]),
        count=len(rows),
        observations=[
            ObservationOut(date=r.indicator_date, value=float(r.value))
            for r in rows
            if r.value is not None
        ],
    )