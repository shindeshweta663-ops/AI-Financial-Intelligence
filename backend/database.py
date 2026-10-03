import os
from typing import Generator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not found in .env file")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# ADDED: session factory (one session per request)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


# ADDED: parent class for all models (Step 4)
class Base(DeclarativeBase):
    pass


# ADDED: FastAPI dependency, opens a session and always closes it
def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# YOUR ORIGINAL TEST, now only runs with: python database.py
if __name__ == "__main__":
    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT 1"))
            print("PostgreSQL connection successful!")
            print("Database test result:", result.scalar())

    except Exception as e:
        print("PostgreSQL connection failed!")
        print("Error:", e)