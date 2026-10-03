import datetime as dt
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# =========================================================
# USERS
# =========================================================
class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[Optional[str]] = mapped_column(String(100))
    email: Mapped[Optional[str]] = mapped_column(String(150))
    password_hash: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)

    portfolio_items: Mapped[List["Portfolio"]] = relationship(back_populates="user")
    watchlist_items: Mapped[List["Watchlist"]] = relationship(back_populates="user")
    transactions: Mapped[List["PortfolioTransaction"]] = relationship(back_populates="user")


# =========================================================
# STOCKS
# =========================================================
class Stock(Base):
    __tablename__ = "stocks"

    stock_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[Optional[str]] = mapped_column(String(20))
    company_name: Mapped[Optional[str]] = mapped_column(String(150))
    exchange: Mapped[Optional[str]] = mapped_column(String(50))
    sector: Mapped[Optional[str]] = mapped_column(String(100))
    industry: Mapped[Optional[str]] = mapped_column(String(100))

    price_history: Mapped[List["PriceHistory"]] = relationship(back_populates="stock")
    technical_indicators: Mapped[List["TechnicalIndicator"]] = relationship(back_populates="stock")
    financial_statements: Mapped[List["FinancialStatement"]] = relationship(back_populates="stock")
    news_items: Mapped[List["News"]] = relationship(back_populates="stock")
    predictions: Mapped[List["Prediction"]] = relationship(back_populates="stock")


# =========================================================
# MARKET DATA
# =========================================================
class PriceHistory(Base):
    __tablename__ = "price_history"

    price_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    open_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    high_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    low_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    close_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    volume: Mapped[Optional[int]] = mapped_column(BigInteger)

    stock: Mapped["Stock"] = relationship(back_populates="price_history")


class TechnicalIndicator(Base):
    __tablename__ = "technical_indicators"

    indicator_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    rsi: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    macd: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    macd_signal: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))
    ema20: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    ema50: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    sma20: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    volatility: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    stock: Mapped["Stock"] = relationship(back_populates="technical_indicators")


class FinancialStatement(Base):
    __tablename__ = "financial_statements"

    financial_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    report_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    net_profit: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    total_assets: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    total_debt: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2))
    eps: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 4))
    profit_margin: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4))

    stock: Mapped["Stock"] = relationship(back_populates="financial_statements")


# =========================================================
# NEWS + SENTIMENT
# =========================================================
class News(Base):
    __tablename__ = "news"

    news_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    title: Mapped[Optional[str]] = mapped_column(Text)
    description: Mapped[Optional[str]] = mapped_column(Text)
    source: Mapped[Optional[str]] = mapped_column(String(150))
    url: Mapped[Optional[str]] = mapped_column(Text)
    published_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)

    stock: Mapped["Stock"] = relationship(back_populates="news_items")
    sentiments: Mapped[List["NewsSentiment"]] = relationship(back_populates="news")


class NewsSentiment(Base):
    __tablename__ = "news_sentiment"

    sentiment_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    news_id: Mapped[Optional[int]] = mapped_column(ForeignKey("news.news_id"))
    sentiment: Mapped[Optional[str]] = mapped_column(String(20))
    positive_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    neutral_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))
    negative_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))

    news: Mapped["News"] = relationship(back_populates="sentiments")


# =========================================================
# ECONOMIC DATA (not linked to a single stock)
# =========================================================
class EconomicIndicator(Base):
    __tablename__ = "economic_indicators"

    economic_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    indicator_name: Mapped[Optional[str]] = mapped_column(String(150))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    indicator_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    value: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 4))
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    source: Mapped[Optional[str]] = mapped_column(String(100))


# =========================================================
# PREDICTIONS (model output, not market data)
# =========================================================
class Prediction(Base):
    __tablename__ = "predictions"

    prediction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    model_name: Mapped[Optional[str]] = mapped_column(String(50))
    prediction_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)
    predicted_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    predicted_direction: Mapped[Optional[str]] = mapped_column(String(20))
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 4))

    stock: Mapped["Stock"] = relationship(back_populates="predictions")


# =========================================================
# USER-SPECIFIC TABLES
# =========================================================
class Portfolio(Base):
    __tablename__ = "portfolio"

    portfolio_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    average_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    created_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="portfolio_items")
    stock: Mapped["Stock"] = relationship()


class Watchlist(Base):
    __tablename__ = "watchlist"

    watchlist_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    added_at: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="watchlist_items")
    stock: Mapped["Stock"] = relationship()


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transactions"

    transaction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.user_id"))
    stock_id: Mapped[Optional[int]] = mapped_column(ForeignKey("stocks.stock_id"))
    transaction_type: Mapped[Optional[str]] = mapped_column(String(10))
    quantity: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 4))
    price: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    transaction_date: Mapped[Optional[dt.datetime]] = mapped_column(DateTime)

    user: Mapped["User"] = relationship(back_populates="transactions")
    stock: Mapped["Stock"] = relationship()