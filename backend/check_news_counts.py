from sqlalchemy import text

from database import engine

QUERIES = {
    "Rows in news": "SELECT COUNT(*) FROM news",
    "Rows in news_sentiment": "SELECT COUNT(*) FROM news_sentiment",
    "Distinct news_id in news_sentiment": "SELECT COUNT(DISTINCT news_id) FROM news_sentiment",
    "Distinct stock_id in news": "SELECT COUNT(DISTINCT stock_id) FROM news",
}

with engine.connect() as conn:
    for label, sql in QUERIES.items():
        value = conn.execute(text(sql)).scalar()
        print(f"{label}: {value}")