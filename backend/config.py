import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Project root = one folder above backend/
BASE_DIR = Path(__file__).resolve().parent.parent

# Load the .env file from the project root
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    # App info
    app_name: str = "AI Financial Intelligence API"
    app_version: str = "0.1.0"

    # Database
    database_url: str = os.getenv("DATABASE_URL", "")

    # External API keys (used in later steps)
    twelve_data_api_key: str = os.getenv("TWELVE_DATA_API_KEY", "")
    finnhub_api_key: str = os.getenv("FINNHUB_API_KEY", "")
    news_api_key: str = os.getenv("NEWS_API_KEY", "")
    fred_api_key: str = os.getenv("FRED_API_KEY", "")


settings = Settings()

# Fail early with a clear message if the database is not configured
if not settings.database_url:
    raise ValueError(
        "DATABASE_URL is missing. Add it to the .env file in the project root."
    )