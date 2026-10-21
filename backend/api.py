from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from crud import (
    count_news,
    get_financial_history,
    get_indicator_history,
    get_news_with_sentiment,
    get_price_history,
    get_scored_news,
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


# Dashboard range buttons -> number of latest trading days
HISTORY_RANGES = {"1M": 21, "3M": 63, "6M": 126, "1Y": 252}


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
        description="Number of latest trading days (ignored when range is given)",
    ),
    range_: Optional[str] = Query(
        None,
        alias="range",
        description="1M, 3M, 6M or 1Y (21, 63, 126, 252 trading days). Overrides limit.",
    ),
    db: Session = Depends(get_db),
):
    """Return daily OHLCV prices, oldest first."""

    if range_ is not None:
        days = HISTORY_RANGES.get(range_.strip().upper())
        if days is None:
            raise HTTPException(
                status_code=422,
                detail="range must be one of 1M, 3M, 6M, 1Y",
            )
        limit = days

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


# ============================================================
# COMPANY NEWS (with optional FinBERT sentiment)
# ============================================================

class SentimentOut(BaseModel):
    label: Optional[str] = None
    positive: Optional[float] = None
    neutral: Optional[float] = None
    negative: Optional[float] = None


class NewsArticleOut(BaseModel):
    title: str
    description: Optional[str] = None
    source: Optional[str] = None
    url: str
    published_at: datetime  # UTC
    sentiment: Optional[SentimentOut] = None  # null if not scored yet


class NewsOut(BaseModel):
    symbol: str
    count: int
    total_stored: int
    scored_in_response: int
    data_source: str = "Company news via Finnhub, stored in PostgreSQL"
    time_note: str = "published_at is in UTC."
    note: str = (
        "Articles are returned newest first. Finnhub tags any article that "
        "mentions the company, so some items are only loosely related. "
        "Sentiment comes from the FinBERT model applied to the headline and "
        "description only (not the full article); it is null when an article "
        "has not been scored yet. Headlines are not investment advice."
    )
    articles: List[NewsArticleOut]


def _sentiment_out(row) -> Optional[SentimentOut]:
    """Convert a news_sentiment row to SentimentOut, or None if unscored."""
    if row is None:
        return None
    return SentimentOut(
        label=row.sentiment,
        positive=_num(row.positive_score),
        neutral=_num(row.neutral_score),
        negative=_num(row.negative_score),
    )


@router.get("/{symbol}/news", response_model=NewsOut)
def get_stock_news(
    symbol: str,
    limit: int = Query(20, ge=1, le=200, description="Number of latest articles"),
    db: Session = Depends(get_db),
):
    """Latest stored company news with stored sentiment, newest first."""
    stock = _get_stock_or_404(db, symbol)
    pairs = get_news_with_sentiment(db, stock.stock_id, limit=limit)
    if not pairs:
        raise HTTPException(
            status_code=404,
            detail=f"No news stored for {stock.symbol} yet",
        )
    articles = [
        NewsArticleOut(
            title=news.title,
            description=news.description,
            source=news.source,
            url=news.url,
            published_at=news.published_at,
            sentiment=_sentiment_out(sent),
        )
        for news, sent in pairs
    ]
    return NewsOut(
        symbol=stock.symbol,
        count=len(articles),
        total_stored=count_news(db, stock.stock_id),
        scored_in_response=sum(1 for a in articles if a.sentiment is not None),
        articles=articles,
    )


# ============================================================
# SENTIMENT SUMMARY
# ============================================================

NET_SCORE_THRESHOLD = 0.10  # this project's own labelling rule, NOT part of FinBERT


class SentimentSummaryOut(BaseModel):
    article_count: int
    positive_count: int
    neutral_count: int
    negative_count: int
    avg_positive: Optional[float] = None
    avg_neutral: Optional[float] = None
    avg_negative: Optional[float] = None
    net_score: Optional[float] = None
    overall_label: str


class SentimentDayOut(BaseModel):
    day: date
    article_count: int
    net_score: float


class SentimentSummaryResponse(BaseModel):
    symbol: str
    window_days: int
    summary: SentimentSummaryOut
    daily_trend: List[SentimentDayOut]
    recent_articles: List[NewsArticleOut]
    note: str


def _overall_label(net_score: Optional[float]) -> str:
    if net_score is None:
        return "no data"
    if net_score >= NET_SCORE_THRESHOLD:
        return "positive"
    if net_score <= -NET_SCORE_THRESHOLD:
        return "negative"
    return "neutral"


@router.get("/{symbol}/sentiment", response_model=SentimentSummaryResponse)
def get_stock_sentiment(
    symbol: str,
    days: int = Query(30, ge=1, le=365, description="Look-back window in days"),
    articles: int = Query(5, ge=0, le=50, description="Recent articles to include"),
    db: Session = Depends(get_db),
):
    """Sentiment summary from stored FinBERT scores. No model runs here."""
    stock = _get_stock_or_404(db, symbol)
    since = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    pairs = get_scored_news(db, stock.stock_id, since=since)

    pos_sum = neu_sum = neg_sum = 0.0
    counts = {"positive": 0, "neutral": 0, "negative": 0}
    per_day = defaultdict(list)  # day -> list of (positive - negative)

    for news, sent in pairs:
        p = _num(sent.positive_score) or 0.0
        n = _num(sent.neutral_score) or 0.0
        g = _num(sent.negative_score) or 0.0
        pos_sum += p
        neu_sum += n
        neg_sum += g
        label = (sent.sentiment or "").lower()
        if label in counts:
            counts[label] += 1
        if news.published_at is not None:
            per_day[news.published_at.date()].append(p - g)

    total = len(pairs)
    if total:
        avg_p, avg_n, avg_g = pos_sum / total, neu_sum / total, neg_sum / total
        net = avg_p - avg_g
    else:
        avg_p = avg_n = avg_g = net = None

    summary = SentimentSummaryOut(
        article_count=total,
        positive_count=counts["positive"],
        neutral_count=counts["neutral"],
        negative_count=counts["negative"],
        avg_positive=round(avg_p, 4) if avg_p is not None else None,
        avg_neutral=round(avg_n, 4) if avg_n is not None else None,
        avg_negative=round(avg_g, 4) if avg_g is not None else None,
        net_score=round(net, 4) if net is not None else None,
        overall_label=_overall_label(net),
    )

    trend = [
        SentimentDayOut(day=d, article_count=len(v), net_score=round(sum(v) / len(v), 4))
        for d, v in sorted(per_day.items())
    ]

    recent = [
        NewsArticleOut(
            title=news.title,
            description=news.description,
            source=news.source,
            url=news.url,
            published_at=news.published_at,
            sentiment=_sentiment_out(sent),
        )
        for news, sent in pairs[:articles]
    ]

    return SentimentSummaryResponse(
        symbol=stock.symbol,
        window_days=days,
        summary=summary,
        daily_trend=trend,
        recent_articles=recent,
        note=(
            "Scores come from the FinBERT model applied to news headlines and "
            "descriptions from Finnhub (times in UTC). net_score = average positive "
            "minus average negative. The overall_label thresholds (+/-0.10) are this "
            "project's own rule, not FinBERT's. Only articles fetched so far are "
            "included. This is an analytical signal, not investment advice."
        ),
    )