"""Phase 11/12 (volatility version): XGBoost forecast of log realized volatility.

Run from the backend folder:
    python train_vol_xgb.py          (5-day horizon, the primary one)
    python train_vol_xgb.py 21       (21-day horizon)

Rules this script follows:
  * time-based split by date (no shuffling), same cut dates for every stock
  * the validation set is used only for early stopping
  * the TEST set is used once, to report the final numbers
  * NEVER change settings because of test results. Tune on validation only.
The model forecasts how volatile a stock is likely to be. It does not predict
price direction, and its forecasts are estimates, not guarantees.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from xgboost import XGBRegressor

from check_vol_baselines import annual_pct, log_of, score
from features import split_frame
from vol_features import VOL_FEATURE_COLUMNS

XGB_VOL_SETTINGS = dict(
    n_estimators=800,
    learning_rate=0.03,
    max_depth=3,            # shallow trees: the data is noisy
    min_child_weight=50,    # every leaf must rest on many rows
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    objective="reg:squarederror",
    eval_metric="rmse",
    early_stopping_rounds=50,
    random_state=42,
    n_jobs=-1,
)

HAR_COLUMNS = ["vol_5", "vol_21", "vol_63"]


def block_bootstrap_interval(values, block=20, n_boot=2000, seed=0):
    """Mean of `values` with a 95% interval from a moving-block bootstrap.

    Blocks keep neighbouring days together, so the overlap between neighbouring
    targets is respected. Returns (mean, low, high).
    """
    values = np.asarray(values, dtype=float)
    n = len(values)
    block = max(1, min(block, n))
    n_blocks = math.ceil(n / block)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
    means = np.empty(n_boot)
    for i in range(n_boot):
        sample = np.concatenate([values[s: s + block] for s in starts[i]])[:n]
        means[i] = sample.mean()
    low, high = np.percentile(means, [2.5, 97.5])
    return float(values.mean()), float(low), float(high)


def compare_models(part, pred_new, pred_old):
    """Relative change in squared error of the new model vs the old one, by date.

    Negative means the new model is better. Squared errors are averaged per DATE
    first (all stocks that day), then bootstrapped in blocks of days.
    """
    y = part["target_log_vol"].to_numpy()
    diff = (y - pred_new) ** 2 - (y - pred_old) ** 2
    per_date = pd.Series(diff).groupby(part["date"].to_numpy()).mean()
    old_mse = float(np.mean((y - pred_old) ** 2))
    mean, low, high = block_bootstrap_interval(per_date.to_numpy())
    return {"relative": mean / old_mse, "low": low / old_mse, "high": high / old_mse, "dates": len(per_date)}


def run_vol_experiment(dataset, horizon, model_dir=None, quiet=False):
    """Train, evaluate and compare. Saves the model if model_dir is given."""
    say = (lambda *a, **k: None) if quiet else print

    parts = split_frame(dataset, 0.6, 0.2, gap=horizon)
    train, val, test = parts["train"], parts["val"], parts["test"]
    x_train, y_train = train[VOL_FEATURE_COLUMNS], train["target_log_vol"]
    x_val, y_val = val[VOL_FEATURE_COLUMNS], val["target_log_vol"]
    x_test = test[VOL_FEATURE_COLUMNS]

    # ---- baselines (fitted on the training set only) ----
    train_mean = float(y_train.mean())
    har = LinearRegression().fit(np.column_stack([log_of(train[c]) for c in HAR_COLUMNS]), y_train)

    def har_predict(part):
        return har.predict(np.column_stack([log_of(part[c]) for c in HAR_COLUMNS]))

    # ---- XGBoost: validation is used only to decide when to stop ----
    model = XGBRegressor(**XGB_VOL_SETTINGS)
    model.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)

    results = {"best_iteration": int(model.best_iteration)}
    say(f"Horizon: {horizon} trading days. Features: {len(VOL_FEATURE_COLUMNS)}. "
        f"Rows  train {len(train)}  val {len(val)}  test {len(test)}")
    say(f"XGBoost stopped at tree {results['best_iteration']} of at most {XGB_VOL_SETTINGS['n_estimators']}.\n")

    for name, part, x_part in (("val", val, x_val), ("test", test, x_test)):
        y_log = part["target_log_vol"].to_numpy()
        y_vol = part["target_vol"].to_numpy()
        preds = {
            "training mean (constant)": np.full(len(part), train_mean),
            "linear on log 5/21/63-day vol": har_predict(part),
            "XGBoost": model.predict(x_part),
        }
        results[name] = {label: score(y_log, p, y_vol) for label, p in preds.items()}
        results[name]["xgb_vs_linear"] = compare_models(part, preds["XGBoost"], preds["linear on log 5/21/63-day vol"])
        results[name]["xgb_vs_constant"] = compare_models(part, preds["XGBoost"], preds["training mean (constant)"])

        title = ("VALIDATION (used for early stopping, slightly optimistic for XGBoost)"
                 if name == "val" else "TEST (evaluated once, the honest comparison)")
        say(f"=== {title} ===")
        say(f"{'model':<32}{'MAE(log)':>9}{'RMSE(log)':>10}{'R2':>8}{'MAE vol pts':>13}")
        for label in preds:
            m = results[name][label]
            say(f"{label:<32}{m['mae_log']:>9.3f}{m['rmse_log']:>10.3f}{m['r2']:>8.3f}{m['mae_vol_pts']:>13.2f}")
        for key, text in (("xgb_vs_linear", "XGBoost vs linear rule"), ("xgb_vs_constant", "XGBoost vs constant")):
            c = results[name][key]
            verdict = ("better" if c["high"] < 0 else "worse" if c["low"] > 0 else "no clear difference")
            say(f"{text}: squared error {c['relative'] * 100:+.1f}% "
                f"(95% interval {c['low'] * 100:+.1f}% to {c['high'] * 100:+.1f}%, {c['dates']} dates) -> {verdict}")
        say("")

    gain = model.get_booster().get_score(importance_type="gain")
    total_gain = sum(gain.values()) or 1.0
    importance = {c: gain.get(c, 0.0) / total_gain for c in VOL_FEATURE_COLUMNS}
    results["importance"] = dict(sorted(importance.items(), key=lambda kv: -kv[1]))
    say("=== XGBoost feature importance (share of total gain) ===")
    for feature, share in list(results["importance"].items())[:8]:
        say(f"  {feature:<20}{share:>7.1%}")

    # ---- per-stock test errors ----
    pred_xgb = model.predict(x_test)
    pred_har = har_predict(test)
    view = pd.DataFrame({
        "symbol": test["symbol"].to_numpy(),
        "xgb": np.abs(np.exp(pred_xgb) - test["target_vol"].to_numpy()),
        "linear": np.abs(np.exp(pred_har) - test["target_vol"].to_numpy()),
        "const": np.abs(np.exp(train_mean) - test["target_vol"].to_numpy()),
    })
    say("\n=== PER-STOCK TEST ERROR (annualized vol points: XGBoost / linear / constant) ===")
    per_stock = {}
    for symbol, g in view.groupby("symbol"):
        per_stock[symbol] = {k: annual_pct(float(g[k].mean())) for k in ("xgb", "linear", "const")}
        v = per_stock[symbol]
        say(f"  {symbol:<6}{v['xgb']:>6.1f} / {v['linear']:>5.1f} / {v['const']:>5.1f}")
    results["per_stock_test"] = per_stock

    if model_dir is not None:
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / f"xgb_logvol_h{horizon}.json"
        meta_path = model_dir / f"xgb_logvol_h{horizon}_meta.json"
        model.save_model(str(model_path))
        meta = {
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "task": f"log of the realized daily volatility over the next {horizon} trading days",
            "feature_columns": VOL_FEATURE_COLUMNS,
            "horizon": horizon,
            "xgboost_settings": XGB_VOL_SETTINGS,
            "best_iteration": results["best_iteration"],
            "train_dates": [str(train["date"].min())[:10], str(train["date"].max())[:10]],
            "val_dates": [str(val["date"].min())[:10], str(val["date"].max())[:10]],
            "test_dates": [str(test["date"].min())[:10], str(test["date"].max())[:10]],
            "metrics": {k: results[k] for k in ("val", "test")},
            "note": "Test metrics are from a single evaluation. A volatility forecast, not a price prediction and not a guarantee.",
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        say(f"\nSaved: {model_path.name} and {meta_path.name} in {model_dir}")

    return results


def main():
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    from config import BASE_DIR
    from database import SessionLocal
    from ml_data import load_price_inputs
    from vol_features import build_vol_dataset

    with SessionLocal() as db:
        closes, indicators = load_price_inputs(db)
    dataset = build_vol_dataset(closes, indicators, horizon)
    print(f"Dataset: {len(dataset)} rows, {dataset['symbol'].nunique()} stocks, "
          f"{str(dataset['date'].min())[:10]} to {str(dataset['date'].max())[:10]}\n")
    run_vol_experiment(dataset, horizon, model_dir=BASE_DIR / "models")
    print("\nReminder: do not change settings because of the test numbers above.")


if __name__ == "__main__":
    main()