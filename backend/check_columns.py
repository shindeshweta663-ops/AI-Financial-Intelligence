from sqlalchemy import inspect

from database import engine

inspector = inspect(engine)

for table in ("stocks", "news", "news_sentiment"):
    print(f"\n{table}")
    for col in inspector.get_columns(table):
        print(f"  {col['name']}  ({col['type']})")