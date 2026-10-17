"""Fit the linear volatility rule on the stored data and save it to models/.

Run from the backend folder:
    python fit_vol_rule.py          (5-day and 21-day)
    python fit_vol_rule.py 5        (only the 5-day horizon)

Reads the database. Writes only models/linear_vol_h5.json and/or h21.json
(overwriting an earlier fit of the same horizon).
"""
import sys

from check_vol_baselines import run_baselines
from database import SessionLocal
from ml_data import load_price_inputs
from vol_features import build_vol_dataset
from vol_rule import HORIZONS, fit_rule, save_rule

# Test-set results reported earlier for this rule: (R2, MAE in annualized vol points)
REPORTED = {5: (0.138, 9.55), 21: (0.228, 6.98)}
LINEAR = "linear on log 5/21/63-day vol"


def main():
    horizons = [int(sys.argv[1])] if len(sys.argv) > 1 else list(HORIZONS)
    for h in horizons:
        if h not in HORIZONS:
            raise SystemExit(f"horizon must be one of {HORIZONS}")

    with SessionLocal() as db:
        closes, indicators = load_price_inputs(db)

    for h in horizons:
        dataset = build_vol_dataset(closes, indicators, h)
        print("=" * 70)
        print(f"Horizon {h} days: {len(dataset)} labeled rows, {dataset['symbol'].nunique()} stocks, "
              f"{str(dataset['date'].min())[:10]} to {str(dataset['date'].max())[:10]}")

        # 1. Reproduction check: fit on the TRAINING split only, score the TEST split.
        test = run_baselines(dataset, h, quiet=True)["test"][LINEAR]
        rep_r2, rep_mae = REPORTED[h]
        ok = abs(test["r2"] - rep_r2) <= 0.001 and abs(test["mae_vol_pts"] - rep_mae) <= 0.01
        print(f"Reproduction check (train-only fit, test split): R2 {test['r2']:.3f} (reported {rep_r2}), "
              f"MAE {test['mae_vol_pts']:.2f} points (reported {rep_mae})  ->  "
              f"{'MATCH' if ok else 'DIFFERENT (see note below)'}")

        # 2. Final fit on all labeled rows, and save.
        rule = fit_rule(dataset, h)
        rule["test_r2"] = round(float(test["r2"]), 4)
        rule["test_mae_vol_points"] = round(float(test["mae_vol_pts"]), 2)
        rule["test_note"] = ("Measured on the 60/20/20 date split with a train-only fit, before the final refit "
                             "on all rows. The refit has no untouched test set.")
        path = save_rule(rule)
        names = ["log vol_5", "log vol_21", "log vol_63"]
        print(f"Final fit on all {rule['fitted_rows']} rows ({rule['first_training_date']} to {rule['last_training_date']})")
        print(f"  intercept {rule['intercept']:+.4f}")
        for name, coef in zip(names, rule["coefficients"]):
            print(f"  {name:<11}{coef:+.4f}")
        print(f"  sum of coefficients {sum(rule['coefficients']):.3f}")
        print(f"Saved: {path}")
        if not ok:
            print("NOTE: the reproduction check differs. If the database was updated since the earlier run, "
                  "small differences are expected; otherwise send me this output.")
    print("\nDone. Only the models/linear_vol_h*.json files were written.")


if __name__ == "__main__":
    main()