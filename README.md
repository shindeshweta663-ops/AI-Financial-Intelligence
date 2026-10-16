# AI-Powered Financial Intelligence & Investment Analytics Platform

A FastAPI + PostgreSQL backend that stores market data, news sentiment and
macro-economic indicators, and serves them through a REST API. A separate
frontend consumes this API.

> Educational/analytical project. Nothing here is investment advice, and no
> output is a prediction or guarantee of future results.

## Current Status

| Phase | Area | Status |
|---|---|---|
| 1-5 | FastAPI, models, CRUD, price data, technical indicators, financials | Done |
| 6 | Financial news (Finnhub) | Done |
| 7 | FinBERT news sentiment | Done |
| 8 | Economic indicators (World Bank, FRED) | Done |
| 9 | Risk analysis | In progress (calculations written and unit-tested; API endpoint next) |
| 10+ | Feature engineering, ML models, auth, portfolio, deployment | Planned |

## Tech Stack

Python, FastAPI, SQLAlchemy 2.x, PostgreSQL, pandas/numpy, FinBERT
(transformers + torch, CPU). Planned: XGBoost, LSTM, SHAP.

## Setup (Windows / PowerShell)

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r ..\requirements.txt
```

1. Create a PostgreSQL database named `financial_intelligence`.
2. Copy `.env.example` to `.env` in the project root and fill in real values.
   Never commit `.env`.
3. Run every Python script from the `backend` folder.

### Environment variables

| Name | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `TWELVE_DATA_API_KEY` | Daily prices |
| `FINNHUB_API_KEY` | News, quotes, reported financials |
| `FRED_API_KEY` | Federal Reserve economic data (free key) |
| `SEC_USER_AGENT` | Identification string for SEC requests |
| `NEWS_API_KEY` | Optional, currently unused |

Run `python check_keys.py` to confirm keys are set (it never prints them).

## Run the API

```powershell
cd backend
uvicorn main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/stocks` | List stored stocks |
| GET | `/api/stocks/{symbol}` | One stock |
| GET | `/api/stocks/{symbol}/history` | Daily price history |
| GET | `/api/stocks/{symbol}/quote` | Latest quote |
| GET | `/api/stocks/{symbol}/technical` | Technical indicators |
| GET | `/api/stocks/{symbol}/financials` | Reported financials |
| GET | `/api/stocks/{symbol}/news` | Stored news with FinBERT scores |
| GET | `/api/stocks/{symbol}/sentiment` | Aggregated sentiment, daily trend, recent articles |
| GET | `/api/economic/indicators` | Catalog of stored economic series |
| GET | `/api/economic/data` | One series (`country`, `indicator`, optional `start_year`, `end_year`) |

## Data scripts

| Script | Purpose |
|---|---|
| `update_data.py AAPL` or `ALL` | Refresh prices, indicators, news and sentiment (US stocks) |
| `score_news.py` | Score unscored news with FinBERT |
| `load_economic.py [--dry-run]` | Load World Bank indicators |
| `load_fred.py [--dry-run]` | Load FRED indicators |
| `check_freshness.py` | Show how recent stored data is |
| `check_indicator_consistency.py` | Compare stored indicators with recomputed ones |
| `check_price_quality.py` | Read-only price sanity checks |
| `check_economic.py` | Summary of the economic table, duplicate count |
| `test_worldbank.py`, `test_fred.py`, `test_risk.py` | Tests (the first two need network, the last needs nothing) |

Loaders are safe to rerun: they insert only rows that are missing.

## Data notes and limitations

- **Prices**: Twelve Data free plan, US stocks only (8 requests/min, 800/day).
  Stored prices pass basic quality checks and appear split-adjusted.
- **News**: Finnhub free plan, US companies only.
- **NSE / Indian stocks**: no verified free data source yet, so none stored.
- **Sentiment**: FinBERT scores each article. The overall label uses the
  project's own thresholds (net score beyond +/-0.10), not a FinBERT rule.
- **Economic data**: dates are the period covered, not the publication date.
  World Bank annual values are dated Dec 31, FRED monthly values the first of
  the month. Machine-learning features must apply a publication lag to avoid
  using information that was not yet public. Missing values are stored as
  absent, never as 0. Stored values are never overwritten, so later revisions
  by the source are not picked up.
- **FRED rate limit**: not verified. The client waits 2 seconds between calls.
- **Known schema gap**: the `users` table has extra columns (expiry_date,
  payment_id, payment_status, start_date, subscription_status) not mapped in
  `models.py`. To be resolved before authentication work.
- `economic_indicators` has no database UNIQUE constraint; duplicates are
  prevented in code.