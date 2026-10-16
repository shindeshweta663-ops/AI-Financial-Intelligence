"""Read-only check of the Phase 10 feature table built from the real database.

Run from the backend folder:
    python check_features.py        (next-day target)
    python check_features.py 5      (5-day target)
It only reads from the database. Nothing is written, saved or changed.
"""
import sys

import numpy as np
import pandas as pd

from crud import get_indicator_history, get_price_history, list_stocks
from database import SessionLocal
from features import FEATURE_COLUMNS, add_target, build_dataset, build_features, make_labeled, split_frame

US_EXCHANGES = {"NASDAQ", "NYSE"}
horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 1
INDICATOR_COLUMNS = ["rsi", "macd", "macd_signal", "ema20", "ema50", "sma20", "volatility"]


def number(value):
    return float(value) if value is not None else np.nan


closes, indicators = {}, {}
with SessionLocal() as db:
    for stock in list_stocks(db):
        if stock.exchange not in US_EXCHANGES:
            continue
        rows = [r for r in get_price_history(db, stock.stock_id, limit=5000) if r.close_price is not None]
        if not rows:
            continue
        closes[stock.symbol] = pd.Series(
            [float(r.close_price) for r in rows],
            index=pd.DatetimeIndex([pd.Timestamp(r.date).normalize() for r in rows]),
        )
        ind_rows = get_indicator_history(db, stock.stock_id, limit=5000)
        indicators[stock.symbol] = pd.DataFrame(
            {c: [number(getattr(r, c)) for r in ind_rows] for c in INDICATOR_COLUMNS},
            index=pd.DatetimeIndex([pd.Timestamp(r.date).normalize() for r in ind_rows]),
        )

print(f"Target horizon: {horizon} trading day(s). Stocks with prices: {len(closes)}\n")

# ------------------------------------------------------------------
print("=== 1. ROWS PER STOCK ===")
print(f"{'SYMBOL':<7}{'PRICE ROWS':>11}{'ALL FEATURES':>13}{'LABELED':>9} {'FIRST LABELED':<14}{'LAST LABELED':<14}")
raw_tables = []
for symbol, close in closes.items():
    raw = build_features(close, indicators.get(symbol))
    raw_tables.append(raw)
    labeled = make_labeled(add_target(raw, close, horizon))
    print(
        f"{symbol:<7}{len(close):>11}{len(raw.dropna()):>13}{len(labeled):>9} "
        f"{str(labeled.index.min())[:10]:<14}{str(labeled.index.max())[:10]:<14}"
    )

# ------------------------------------------------------------------
print("\n=== 2. MISSING VALUES PER FEATURE (all stocks together, before dropping rows) ===")
raw_all = pd.concat(raw_tables)
print(f"Total rows: {len(raw_all)}")
for column in FEATURE_COLUMNS:
    print(f"  {column:<20}{int(raw_all[column].isna().sum()):>7} missing")

# ------------------------------------------------------------------
dataset = build_dataset(closes, indicators, horizon)
print(f"\n=== 3. POOLED DATASET: {len(dataset)} rows x {len(FEATURE_COLUMNS)} features ===")
print(f"Dates {str(dataset['date'].min())[:10]} to {str(dataset['date'].max())[:10]}")
print(f"Missing values left in the dataset: {int(dataset[FEATURE_COLUMNS].isna().sum().sum())}")

print("\nFeature ranges (look for impossible or extreme values):")
print(f"  {'feature':<20}{'min':>10}{'median':>10}{'max':>10}")
for column in FEATURE_COLUMNS:
    s = dataset[column]
    print(f"  {column:<20}{s.min():>10.4f}{s.median():>10.4f}{s.max():>10.4f}")

# ------------------------------------------------------------------
print("\n=== 4. TIME-BASED SPLIT (60% / 20% / 20% of dates, gap = horizon) ===")
parts = split_frame(dataset, 0.6, 0.2, gap=horizon)
majority = 1 if parts["train"]["target_up"].mean() >= 0.5 else 0
print(f"Majority class in the training set: {'UP' if majority else 'DOWN'}")
print(f"{'SET':<7}{'ROWS':>7}{'FIRST DATE':>13}{'LAST DATE':>12}{'SHARE UP':>10}{'ALWAYS-MAJORITY ACCURACY':>26}")
for name in ("train", "val", "test"):
    part = parts[name]
    share_up = part["target_up"].mean()
    baseline = (part["target_up"] == majority).mean()
    print(
        f"{name:<7}{len(part):>7}{str(part['date'].min())[:10]:>13}{str(part['date'].max())[:10]:>12}"
        f"{share_up:>10.1%}{baseline:>26.1%}"
    )
print("\nShare per stock (all dates): "
      + ", ".join(f"{s} {g['target_up'].mean():.0%}" for s, g in dataset.groupby("symbol")))
print("\nCheck finished. Nothing was saved or changed.")