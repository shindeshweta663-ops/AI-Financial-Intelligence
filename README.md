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
| 9 | Risk analysis | Done |
| 10-12 | Feature engineering, direction baseline, volatility forecast | Done (see "Machine learning findings") |
| 15 | Authentication: register, login, logout, session cookie | Done (frontend pages not yet connected) |
| 13+ | SHAP, LSTM comparison, portfolio, deployment | Planned |

## Tech Stack

Python, FastAPI, SQLAlchemy 2.x, PostgreSQL, pandas/numpy, scikit-learn,
XGBoost, FinBERT (transformers + torch, CPU), bcrypt and PyJWT
(authentication). Planned: LSTM, SHAP.

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
3. Set `JWT_SECRET` in `.env` to a long random value (32+ characters). One way
   to make one: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
   Keep it private and do not share it.
4. Run every Python script from the `backend` folder.

### Environment variables

| Name | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `TWELVE_DATA_API_KEY` | Daily prices |
| `FINNHUB_API_KEY` | News, quotes, reported financials |
| `FRED_API_KEY` | Federal Reserve economic data (free key) |
| `SEC_USER_AGENT` | Identification string for SEC requests |
| `NEWS_API_KEY` | Optional, currently unused |
| `JWT_SECRET` | Signs login cookies. Required for login: a long random value (32+ characters). Never commit it. |
| `COOKIE_SECURE` | `true` when served over HTTPS (production). `false` for local http (default). |

Run `python check_keys.py` to confirm keys are set (it never prints them).

## Run the API

```powershell
cd backend
uvicorn main:app --reload
```

Interactive docs: http://127.0.0.1:8000/docs

The `frontend` folder is served from the same server at
http://127.0.0.1:8000/app/.

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
| GET | `/api/stocks/{symbol}/risk` | Historical risk measures: volatility, drawdown, VaR/CVaR, Sharpe, Sortino (optional `window`, `var_level`) |
| GET | `/api/stocks/{symbol}/volatility-forecast` | Forecast of annualized volatility over the next 5 or 21 trading days (`horizon=5` or `21`), US stocks only |
| GET | `/api/economic/indicators` | Catalog of stored economic series |
| GET | `/api/economic/data` | One series (`country`, `indicator`, optional `start_year`, `end_year`) |
| POST | `/api/auth/register` | Create an account (name, email, password of 8+ characters) and log in |
| POST | `/api/auth/login` | Log in (`remember: true` keeps the session 30 days instead of 1 day) |
| GET | `/api/auth/me` | Current user and subscription info (requires login) |
| POST | `/api/auth/logout` | End the session |
| POST | `/api/auth/change-password` | Change password (requires login) |
| GET | `/api/stocks/search` | Search stocks by symbol or company name (`q`, optional `limit`); returns `{"results": [{symbol, name, exchange}]}` |
| GET | `/api/stocks/{symbol}/history` | Daily price history (`range=1M`, `3M`, `6M` or `1Y`, or `limit` for a number of trading days) |

**Authentication notes.** Passwords are stored only as bcrypt hashes. A successful login sets a signed token in an HttpOnly cookie named `fn_session`. The `frontend` folder is served at http://127.0.0.1:8000/app/ so the pages and the API share one address. The subscription `plan` is derived (`premium` only when the stored status is `active`); there is no plan column yet. Not yet implemented: forgot-password and login rate limiting. `change-password` has not been tested end to end.

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
| `check_risk_independent.py` | Read-only loop-based recomputation of the risk measures, compared with `risk.py` |
| `check_feature_inputs.py` | Read-only audit of the data available for feature engineering |
| `check_features.py`, `check_vol_baselines.py` | Read-only checks of the feature tables and of simple volatility baselines |
| `train_xgb.py`, `train_vol_xgb.py` | Experiments: XGBoost for direction and for volatility (models saved to `models/`, not tracked in git) |
| `walk_forward_vol.py [21]` | Robustness check: expanding-window comparison of XGBoost, the linear rule and a constant (5-day by default) |
| `fit_vol_rule.py [5\|21]` | Fit the linear volatility rule on the stored data and save `models/linear_vol_h5.json` / `linear_vol_h21.json` |
| `test_worldbank.py`, `test_fred.py` | Provider tests (need network) |
| `test_risk.py`, `test_features.py`, `test_vol_features.py` | Tests that use no database or network |

Loaders are safe to rerun: they insert only rows that are missing.

## Machine learning findings

All of this is analysis of past data. Nothing here is a guarantee, and none
of it is investment advice.

**Setup.** 10 US stocks, daily data from 2021 to 2026. Features for day T use
only information available at the close of day T. Train, validation and test
sets are split by date (60/20/20) with a gap equal to the forecast horizon,
the same cut dates for every stock, and no shuffling.

**1. Direction (next-day or 5-day up/down): no usable signal.** An
"always predict up" baseline scores 51.7% (1-day) and 53.4% (5-day) on the
test period. XGBoost stopped after one tree and predicted "up" for every row,
with ROC-AUC 0.48 to 0.50 (no better than chance). Because there is no edge,
there is no price-direction prediction endpoint and no SHAP explanation for
that model.

**2. Volatility (how large the next days' price swings are): forecastable.**
The target is the realized volatility of the next 5 (primary) or 21 trading
days, predicted in log space.

| Horizon | Constant guess | Linear rule (test R2 / MAE) | XGBoost (test R2 / MAE) |
|---|---|---|---|
| 5 days | R2 -0.002, MAE 10.22 | R2 0.138, MAE 9.55 | R2 0.126, MAE 9.63 |
| 21 days | | R2 0.228, MAE 6.98 | R2 0.222, MAE 7.17 |

MAE is in annualized volatility percentage points. The linear rule uses only
the log of the 5-day, 21-day and 63-day realized volatility.

**3. Why the linear rule is served, not XGBoost.** A decision rule was fixed
before looking at the results: serve XGBoost only if the pooled interval for
"XGBoost vs linear rule" is entirely below zero AND XGBoost wins at least 4 of
6 walk-forward folds. Results (squared error change, 95% interval from a block
bootstrap by date):

- 21 days: -3.0% (-9.4% to +2.5%), includes zero, XGBoost won 4 of 6 folds.
- 5 days: -2.8% (-5.7% to -0.3%), XGBoost won only 3 of 6 folds.

Neither horizon met both conditions, so the simpler, more stable linear rule
is served. It beat the constant guess in all 6 folds at both horizons. The
walk-forward folds include periods already seen in the single-split test, so
they are a robustness check, not a fresh untouched test. Targets of
neighbouring days overlap, so small differences should not be over-read.

**4. Inputs that are NOT used, and why.**

- *News sentiment*: stored news covers only 2026-09-06 to 2026-10-13 (about
  25 trading days, roughly 2% of the price history), so it cannot be a
  training feature. It is available through the `/sentiment` endpoint.
- *Macro-economic series*: only about 60 monthly values per stock in the
  training period, and the dates are the period covered, not the publication
  date. World Bank annual values are published late.
- *Financial statements*: about 5 annual reports per stock in the period and
  no filing date stored.

**5. Using the forecast.** `/volatility-forecast` returns the forecast, the
stock's own recent 5/21/63-day volatility for context, the as-of date, and the
typical error measured on the test period (about 9.6 volatility points for 5
days and 7.0 for 21 days). Treat it as a rough level of risk, not a precise
number. The forecast is a typical (median-style) value. The final coefficients
are fitted on all labeled rows, so no untouched test set exists for that final
fit; the reported errors come from the earlier test split. The forecast is as
of the latest stored price, so refresh the data (`update_data.py ALL`) before
relying on it.

## Data notes and limitations

- **Prices**: Twelve Data free plan, US stocks only (8 requests/min, 800/day).
  Stored prices pass basic quality checks and appear split-adjusted.
- **News**: Finnhub free plan, US companies only.
- **NSE / Indian stocks**: no verified free data source yet, so none stored
  and no forecasts for them.
- **Sentiment**: FinBERT scores each article. The overall label uses the
  project's own thresholds (net score beyond +/-0.10), not a FinBERT rule.
- **Risk**: computed from the stored split-adjusted closing prices, so the
  figures are historical measures, not predictions or guarantees. Sharpe and
  Sortino use the stored FRED federal funds rate as the risk-free rate (each
  day uses the latest monthly value on or before it). Beta is not included
  because no market index is stored. The default window is 756 returns.
  The independent cross-check script confirms the implementation matches a
  loop-based recomputation, not that the conventions match any particular
  finance website.
- **Economic data**: dates are the period covered, not the publication date.
  World Bank annual values are dated Dec 31, FRED monthly values the first of
  the month. Machine-learning features must apply a publication lag to avoid
  using information that was not yet public. Missing values are stored as
  absent, never as 0. Stored values are never overwritten, so later revisions
  by the source are not picked up.
- **FRED rate limit**: not verified. The client waits 2 seconds between calls.
- **Users table**: `models.py` now maps the extra subscription and payment
  columns (`subscription_status`, `start_date`, `expiry_date`,
  `payment_status`, `payment_id`). There is no plan-name column, so the plan
  returned by `/api/auth/me` is derived.
- `economic_indicators` has no database UNIQUE constraint; duplicates are
  prevented in code.