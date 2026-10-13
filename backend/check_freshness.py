from sqlalchemy import func, select

from database import SessionLocal
from models import News, PriceHistory, Stock, TechnicalIndicator


def day(value) -> str:
    return str(value)[:10] if value else "-"


with SessionLocal() as db:
    print(f"{'SYMBOL':<12}{'LAST PRICE':<14}{'LAST INDICATOR':<16}{'LAST NEWS (UTC)':<16}")
    for stock in db.execute(select(Stock).order_by(Stock.symbol)).scalars():
        sid = stock.stock_id
        price = db.execute(select(func.max(PriceHistory.date)).where(PriceHistory.stock_id == sid)).scalar()
        ind = db.execute(select(func.max(TechnicalIndicator.date)).where(TechnicalIndicator.stock_id == sid)).scalar()
        news = db.execute(select(func.max(News.published_at)).where(News.stock_id == sid)).scalar()
        print(f"{stock.symbol:<12}{day(price):<14}{day(ind):<16}{day(news):<16}")