from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from crud import (
    get_financial_history,
    get_indicator_history,
    get_price_history,
    get_stock_by_symbol,
    list_stocks,
    search_stocks,
)
from database import get_db
from market_data import MarketDataError, Quote, get_latest_quote


router = APIRouter(
    prefix="/api/stocks",
    tags=["Stocks"],
)


# ============================================================
# RESPONSE MODELS
# ============================================================

class StockOut(BaseModel):
    symbol: str
    company_name: Optional[str] = None
    exchange: Optional[str] = None
    sector: Optional[str] = None
    industry: Optional[str] = None


class PriceBarOut(BaseModel):
    date: datetime
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    close: Optional[float] = None
    volume: Optional[int] = None


class StockDetailOut(BaseModel):
    stock: StockOut
    latest_price: Optional[PriceBarOut] = None
    data_source: str = "Stored daily prices (PostgreSQL)"


class HistoryOut(BaseModel):
    symbol: str
    count: int
    data_source: str = "Stored daily prices (PostgreSQL)"
    prices: List[PriceBarOut]


class IndicatorPointOut(BaseModel):
    date: datetime
    sma20: Optional[float] = None
    ema20: Optional[float] = None
    ema50: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    volatility: Optional[float] = None


class TechnicalOut(BaseModel):
    symbol: str
    count: int
    data_type: str = "Calculated from stored daily closing prices"
    note: str = (
        "Indicators describe past prices. They are not predictions "
        "or investment advice. Volatility is annualized, in percent."
    )
    indicators: List[IndicatorPointOut]


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def _num(value) -> Optional[float]:
    """Convert database numeric values to float."""
    return float(value) if value is not None else None


def _stock_out(stock) -> StockOut:
    """Convert a database Stock object to StockOut."""
    return StockOut(
        symbol=stock.symbol,
        company_name=stock.company_name,
        exchange=stock.exchange,
        sector=stock.sector,
        industry=stock.industry,
    )


def _bar_out(row) -> PriceBarOut:
    """Convert a database price row to PriceBarOut."""
    return PriceBarOut(
        date=row.date,
        open=_num(row.open_price),
        high=_num(row.high_price),
        low=_num(row.low_price),
        close=_num(row.close_price),
        volume=row.volume,
    )


def _get_stock_or_404(db: Session, symbol: str):
    """Find a stock by symbol or return HTTP 404."""
    stock = get_stock_by_symbol(db, symbol)

    if not stock:
        raise HTTPException(
            status_code=404,
            detail=f"Stock '{symbol.upper()}' is not tracked",
        )

    return stock


# ============================================================
# STOCK ENDPOINTS
# ============================================================

@router.get(
    "",
    response_model=List[StockOut],
)
def get_stocks(
    q: Optional[str] = Query(
        None,
        description="Search by symbol or company name",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=500,
    ),
    db: Session = Depends(get_db),
):
    """List tracked stocks or search them using ?q=."""

    stocks = (
        search_stocks(db, q, limit)
        if q
        else list_stocks(db, limit=limit)
    )

    return [_stock_out(stock) for stock in stocks]


@router.get(
    "/{symbol}",
    response_model=StockDetailOut,
)
def get_stock(
    symbol: str,
    db: Session = Depends(get_db),
):
    """Return stock details and latest stored daily price."""

    stock = _get_stock_or_404(db, symbol)

    rows = get_price_history(
        db,
        stock.stock_id,
        limit=1,
    )

    return StockDetailOut(
        stock=_stock_out(stock),
        latest_price=_bar_out(rows[-1]) if rows else None,
    )


@router.get(
    "/{symbol}/history",
    response_model=HistoryOut,
)
def get_stock_history(
    symbol: str,
    limit: int = Query(
        365,
        ge=1,
        le=1500,
        description="Number of latest trading days",
    ),
    db: Session = Depends(get_db),
):
    """Return daily OHLCV prices, oldest first."""

    stock = _get_stock_or_404(db, symbol)

    rows = get_price_history(
        db,
        stock.stock_id,
        limit=limit,
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No price history stored for {stock.symbol} yet",
        )

    return HistoryOut(
        symbol=stock.symbol,
        count=len(rows),
        prices=[_bar_out(row) for row in rows],
    )


# ============================================================
# LIVE QUOTE ENDPOINT
# ============================================================

@router.get(
    "/{symbol}/quote",
    response_model=Quote,
)
def get_stock_quote(
    symbol: str,
    db: Session = Depends(get_db),
):
    """
    Get a LIVE stock quote.

    Twelve Data is used as the primary source.
    Finnhub can be used as a backup depending on market_data.py.
    """

    stock = _get_stock_or_404(db, symbol)

    try:
        return get_latest_quote(stock.symbol)

    except MarketDataError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        )


# ============================================================
# TECHNICAL INDICATORS
# ============================================================

@router.get(
    "/{symbol}/technical",
    response_model=TechnicalOut,
)
def get_stock_technical(
    symbol: str,
    limit: int = Query(
        250,
        ge=1,
        le=1500,
        description="Number of latest trading days",
    ),
    db: Session = Depends(get_db),
):
    """
    Return stored technical indicators.

    Indicators:
    - SMA20
    - EMA20
    - EMA50
    - RSI(14)
    - MACD(12,26,9)
    - 20-day volatility
    """

    stock = _get_stock_or_404(db, symbol)

    rows = get_indicator_history(
        db,
        stock.stock_id,
        limit=limit,
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No indicators stored for {stock.symbol} yet",
        )

    return TechnicalOut(
        symbol=stock.symbol,
        count=len(rows),
        indicators=[
            IndicatorPointOut(
                date=row.date,
                sma20=_num(row.sma20),
                ema20=_num(row.ema20),
                ema50=_num(row.ema50),
                rsi=_num(row.rsi),
                macd=_num(row.macd),
                macd_signal=_num(row.macd_signal),
                volatility=_num(row.volatility),
            )
            for row in rows
        ],
    )


# ============================================================
# COMPANY FINANCIALS
# ============================================================

class FinancialPointOut(BaseModel):
    report_date: date
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    eps: Optional[float] = None
    profit_margin: Optional[float] = None


class FinancialsOut(BaseModel):
    symbol: str
    count: int
    currency: str = "USD"
    data_type: str = "Reported annual figures (10-K filings) via Finnhub"
    note: str = (
        "Figures are as reported by the company. profit_margin is calculated "
        "as net_profit / revenue x 100 (percent). total_debt is an approximation "
        "of interest-bearing borrowings from the main balance sheet lines. "
        "Empty values mean the item was not found, not zero."
    )
    statements: List[FinancialPointOut]


@router.get("/{symbol}/financials", response_model=FinancialsOut)
def get_stock_financials(
    symbol: str,
    limit: int = Query(10, ge=1, le=30, description="Number of latest annual reports"),
    db: Session = Depends(get_db),
):
    """Annual financial statement summary, oldest first."""
    stock = _get_stock_or_404(db, symbol)
    rows = get_financial_history(db, stock.stock_id, limit=limit)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No financial statements stored for {stock.symbol} yet",
        )
    return FinancialsOut(
        symbol=stock.symbol,
        count=len(rows),
        statements=[
            FinancialPointOut(
                report_date=r.report_date,
                revenue=_num(r.revenue),
                net_profit=_num(r.net_profit),
                total_assets=_num(r.total_assets),
                total_debt=_num(r.total_debt),
                eps=_num(r.eps),
                profit_margin=_num(r.profit_margin),
            )
            for r in rows
        ],
    )