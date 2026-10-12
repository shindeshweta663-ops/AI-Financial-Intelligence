from sqlalchemy import text

from database import engine

SQL = """
SELECT s.symbol,
       COUNT(n.news_id) AS articles,
       COUNT(ns.news_id) AS scored,
       COUNT(n.news_id) - COUNT(ns.news_id) AS unscored
FROM stocks s
LEFT JOIN news n ON n.stock_id = s.stock_id
LEFT JOIN news_sentiment ns ON ns.news_id = n.news_id
GROUP BY s.symbol
ORDER BY s.symbol
"""

with engine.connect() as conn:
    rows = conn.execute(text(SQL)).all()

print(f"{'SYMBOL':<8}{'ARTICLES':>10}{'SCORED':>10}{'UNSCORED':>10}")
for symbol, articles, scored, unscored in rows:
    print(f"{symbol:<8}{articles:>10}{scored:>10}{unscored:>10}")
print(f"\nStocks listed: {len(rows)}")