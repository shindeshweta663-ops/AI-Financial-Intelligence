"""Read-only check: how well do SIMPLE rules forecast the next days' volatility?

Run from the backend folder:
    python check_vol_baselines.py          (5-day horizon, then 21-day)
    python check_vol_baselines.py 5        (only the 5-day horizon)
It only reads from the database. Nothing is written or saved.

These baselines are the bar any machine-learning model has to clear.
Volatility is predicted in LOG space (target_log_vol). R-squared is the usual
sklearn r2_score against the mean of the set being scored, so it can be negative.
"""
import math
import sys

import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

from features import split_frame
from vol_features import MIN_VOL, TRADING_DAYS, build_vol_dataset


def log_of(series):
    return np.log(np.maximum(series.to_numpy(dtype=float), MIN_VOL))


def annual_pct(daily_vol):
    return daily_vol * math.sqrt(TRADING_DAYS) * 100


def score(y_log, pred_log, y_vol):
    """Errors in log space, plus the average miss in annualized-volatility points."""
    return {
        "mae_log": mean_absolute_error(y_log, pred_log),
        "rmse_log": math.sqrt(mean_squared_error(y_log, pred_log)),
        "r2": r2_score(y_log, pred_log),
        "mae_vol_pts": annual_pct(float(np.mean(np.abs(np.exp(pred_log) - y_vol)))),
    }


def run_baselines(dataset, horizon, quiet=False):
    """Fit the baselines on the training set only and score validation and test."""
    say = (lambda *a, **k: None) if quiet else print
    parts = split_frame(dataset, 0.6, 0.2, gap=horizon)
    train, val, test = parts["train"], parts["val"], parts["test"]

    har_columns = ["vol_5", "vol_21", "vol_63"]
    har = LinearRegression().fit(
        np.column_stack([log_of(train[c]) for c in har_columns]), train["target_log_vol"]
    )
    train_mean = float(train["target_log_vol"].mean())

    def predictions(part):
        return {
            "training mean (constant)": np.full(len(part), train_mean),
            "persistence: 5-day vol": log_of(part["vol_5"]),
            "persistence: 21-day vol": log_of(part["vol_21"]),
            "linear on log 5/21/63-day vol": har.predict(np.column_stack([log_of(part[c]) for c in har_columns])),
        }

    results = {}
    say(f"Horizon: {horizon} trading days. Target: realized volatility of the next {horizon} days.")
    say(f"Rows  train {len(train)}  val {len(val)}  test {len(test)}")
    say(f"Target in annualized %, training set: 10th {annual_pct(train['target_vol'].quantile(0.1)):.1f}  "
        f"median {annual_pct(train['target_vol'].median()):.1f}  90th {annual_pct(train['target_vol'].quantile(0.9)):.1f}\n")

    for name, part in (("val", val), ("test", test)):
        results[name] = {}
        say(f"=== {name.upper()} ===")
        say(f"{'baseline':<32}{'MAE(log)':>9}{'RMSE(log)':>10}{'R2':>8}{'MAE vol pts':>13}")
        for label, pred in predictions(part).items():
            m = score(part["target_log_vol"].to_numpy(), pred, part["target_vol"].to_numpy())
            results[name][label] = m
            say(f"{label:<32}{m['mae_log']:>9.3f}{m['rmse_log']:>10.3f}{m['r2']:>8.3f}{m['mae_vol_pts']:>13.2f}")
        say("")
    say(f"Targets of neighbouring days overlap (each uses {horizon} returns), so there are far fewer "
        f"independent observations than rows, and small differences are not meaningful.")
    say("'MAE vol pts' = average miss in annualized volatility percentage points.\n")
    return results


def main():
    horizons = [int(sys.argv[1])] if len(sys.argv) > 1 else [5, 21]
    from database import SessionLocal
    from ml_data import load_price_inputs

    with SessionLocal() as db:
        closes, indicators = load_price_inputs(db)
    for horizon in horizons:
        dataset = build_vol_dataset(closes, indicators, horizon)
        print("=" * 78)
        print(f"Dataset: {len(dataset)} rows, {dataset['symbol'].nunique()} stocks, "
              f"{str(dataset['date'].min())[:10]} to {str(dataset['date'].max())[:10]}")
        run_baselines(dataset, horizon)
    print("Check finished. Nothing was saved or changed.")


if __name__ == "__main__":
    main()