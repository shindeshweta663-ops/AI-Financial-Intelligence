"""Walk-forward check of the volatility forecasters (constant, linear rule, XGBoost).

Run from the backend folder:
    python walk_forward_vol.py          (5-day horizon, the primary one)
    python walk_forward_vol.py 21       (21-day horizon)
It only reads from the database. Nothing is written or saved.

How it works: the dates are cut into FOLDS consecutive test blocks. For each block
every model is trained ONLY on dates before it (minus a gap of `horizon` dates, so
no training target overlaps the block), then scored on the block. The training
window grows with each fold. XGBoost stops early using the last 20% of its own
training window, never the test block. Nothing is tuned between folds.

Important: the folds include periods already seen in the single-split test, so
this is a robustness check, NOT a fresh untouched test.
"""
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor

from check_vol_baselines import annual_pct, log_of
from train_vol_xgb import HAR_COLUMNS, XGB_VOL_SETTINGS, compare_models
from vol_features import VOL_FEATURE_COLUMNS, build_vol_dataset

FOLDS = 6
MIN_TRAIN_FRACTION = 0.4      # the first fold trains on the oldest 40% of dates
INNER_VAL_FRACTION = 0.2      # last 20% of each training window is used for early stopping


def make_folds(dates, horizon, folds=FOLDS, min_train=MIN_TRAIN_FRACTION):
    """List of (train_dates, test_dates). Test blocks are consecutive and never overlap."""
    dates = list(dates)
    n = len(dates)
    start = int(n * min_train)
    size = (n - start) // folds
    if size < 20 or start - horizon < 100:
        raise ValueError("not enough dates for this many folds")
    result = []
    for k in range(folds):
        t0 = start + k * size
        t1 = n if k == folds - 1 else t0 + size
        result.append((dates[: t0 - horizon], dates[t0:t1]))
    return result


def run_fold(dataset, train_dates, test_dates, horizon):
    """Fit all models on train_dates, predict test_dates. Returns (frame, best_iteration)."""
    train = dataset[dataset["date"].isin(train_dates)]
    test = dataset[dataset["date"].isin(test_dates)]

    m = len(train_dates)
    split = int(m * (1 - INNER_VAL_FRACTION))
    fit = dataset[dataset["date"].isin(train_dates[: split - horizon])]
    inner = dataset[dataset["date"].isin(train_dates[split:])]

    har = LinearRegression().fit(
        np.column_stack([log_of(train[c]) for c in HAR_COLUMNS]), train["target_log_vol"]
    )
    model = XGBRegressor(**XGB_VOL_SETTINGS)
    model.fit(
        fit[VOL_FEATURE_COLUMNS], fit["target_log_vol"],
        eval_set=[(inner[VOL_FEATURE_COLUMNS], inner["target_log_vol"])],
        verbose=False,
    )

    out = test[["date", "symbol", "target_log_vol", "target_vol"]].copy()
    out["p_const"] = float(train["target_log_vol"].mean())
    out["p_har"] = har.predict(np.column_stack([log_of(test[c]) for c in HAR_COLUMNS]))
    out["p_xgb"] = model.predict(test[VOL_FEATURE_COLUMNS])
    return out, int(model.best_iteration)


def relative_change(frame, new, old):
    """Change in mean squared error of `new` versus `old` (negative = new is better)."""
    y = frame["target_log_vol"].to_numpy()
    se_new = np.mean((y - frame[new].to_numpy()) ** 2)
    se_old = np.mean((y - frame[old].to_numpy()) ** 2)
    return (se_new - se_old) / se_old


def mae_points(frame, column):
    return annual_pct(float(np.mean(np.abs(np.exp(frame[column].to_numpy()) - frame["target_vol"].to_numpy()))))


def verdict(c):
    return "better" if c["high"] < 0 else "worse" if c["low"] > 0 else "no clear difference"


def run_walk_forward(dataset, horizon, quiet=False):
    say = (lambda *a, **k: None) if quiet else print
    dates = sorted(dataset["date"].unique())
    folds = make_folds(dates, horizon)

    say(f"Horizon: {horizon} trading days. {len(folds)} expanding folds, first fold trains on the oldest "
        f"{int(MIN_TRAIN_FRACTION * 100)}% of dates.\n")
    say(f"{'fold':<5}{'test period':<25}{'dates':>6}{'trees':>6}"
        f"{'MAE const':>10}{'MAE lin':>9}{'MAE xgb':>9}{'xgb vs lin':>12}{'lin vs const':>14}")

    frames, rows = [], []
    for k, (train_dates, test_dates) in enumerate(folds, start=1):
        frame, trees = run_fold(dataset, train_dates, test_dates, horizon)
        frame["fold"] = k
        frames.append(frame)
        row = {
            "xgb_vs_lin": relative_change(frame, "p_xgb", "p_har"),
            "lin_vs_const": relative_change(frame, "p_har", "p_const"),
        }
        rows.append(row)
        period = f"{str(test_dates[0])[:10]} to {str(test_dates[-1])[:10]}"
        say(f"{k:<5}{period:<25}{len(test_dates):>6}{trees:>6}"
            f"{mae_points(frame, 'p_const'):>10.2f}{mae_points(frame, 'p_har'):>9.2f}{mae_points(frame, 'p_xgb'):>9.2f}"
            f"{row['xgb_vs_lin'] * 100:>+11.1f}%{row['lin_vs_const'] * 100:>+13.1f}%")

    everything = pd.concat(frames, ignore_index=True)
    pooled = {
        "xgb_vs_lin": compare_models(everything, everything["p_xgb"].to_numpy(), everything["p_har"].to_numpy()),
        "xgb_vs_const": compare_models(everything, everything["p_xgb"].to_numpy(), everything["p_const"].to_numpy()),
        "lin_vs_const": compare_models(everything, everything["p_har"].to_numpy(), everything["p_const"].to_numpy()),
    }
    xgb_better_folds = sum(1 for r in rows if r["xgb_vs_lin"] < 0)
    lin_better_folds = sum(1 for r in rows if r["lin_vs_const"] < 0)

    say("\n=== ALL FOLDS TOGETHER (squared error change, 95% interval from a block bootstrap by date) ===")
    for key, text in (("xgb_vs_lin", "XGBoost vs linear rule"), ("xgb_vs_const", "XGBoost vs constant"),
                      ("lin_vs_const", "Linear rule vs constant")):
        c = pooled[key]
        say(f"{text:<26}{c['relative'] * 100:>+7.1f}%  ({c['low'] * 100:+.1f}% to {c['high'] * 100:+.1f}%, "
            f"{c['dates']} dates) -> {verdict(c)}")
    say(f"\nXGBoost beat the linear rule in {xgb_better_folds} of {len(rows)} folds.")
    say(f"The linear rule beat the constant in {lin_better_folds} of {len(rows)} folds.")
    say("\nThe folds include periods already seen in the single-split test, so this checks robustness;")
    say("it is not a fresh untouched test. Neighbouring targets overlap, so treat small gaps with care.")
    return {"folds": rows, "pooled": pooled, "xgb_better_folds": xgb_better_folds}


def main():
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    from database import SessionLocal
    from ml_data import load_price_inputs

    with SessionLocal() as db:
        closes, indicators = load_price_inputs(db)
    dataset = build_vol_dataset(closes, indicators, horizon)
    print(f"Dataset: {len(dataset)} rows, {dataset['symbol'].nunique()} stocks, "
          f"{str(dataset['date'].min())[:10]} to {str(dataset['date'].max())[:10]}\n")
    run_walk_forward(dataset, horizon)
    print("\nCheck finished. Nothing was saved or changed.")


if __name__ == "__main__":
    main()