"""Phase 11/12: first XGBoost model for next-day direction, features A-C only.

Run from the backend folder:
    python train_xgb.py          (next-day direction)
    python train_xgb.py 5        (5-day direction)

Rules this script follows:
  * time-based split by date (no shuffling), same cut dates for every stock
  * the validation set is used only for early stopping
  * the TEST set is used once, to report the final numbers
  * NEVER change settings because of test results. Tune on validation only,
    otherwise the test set stops being an honest check.
Predictions are statistical estimates from past data. They are not guarantees.
"""
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

from features import FEATURE_COLUMNS, split_frame

XGB_SETTINGS = dict(
    n_estimators=600,
    learning_rate=0.03,
    max_depth=3,            # shallow trees: financial data is very noisy
    min_child_weight=20,    # every leaf must rest on many rows
    subsample=0.8,
    colsample_bytree=0.8,
    reg_lambda=5.0,
    eval_metric="logloss",
    early_stopping_rounds=40,
    random_state=42,
    n_jobs=-1,
)


def evaluate(y_true, proba):
    """Classification metrics for the UP class at a 0.5 threshold."""
    y_true = np.asarray(y_true)
    predicted = (np.asarray(proba) >= 0.5).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predicted, labels=[0, 1]).ravel()
    return {
        "accuracy": accuracy_score(y_true, predicted),
        "precision": precision_score(y_true, predicted, zero_division=0),
        "recall": recall_score(y_true, predicted, zero_division=0),
        "f1": f1_score(y_true, predicted, zero_division=0),
        "roc_auc": roc_auc_score(y_true, proba) if len(set(y_true)) == 2 else float("nan"),
        "log_loss": log_loss(y_true, np.clip(proba, 1e-6, 1 - 1e-6), labels=[0, 1]),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def noise_band(n_rows):
    """Rough 95% band for an accuracy figure, assuming independent rows."""
    return 1.96 * math.sqrt(0.25 / n_rows)


def run_experiment(dataset, horizon, model_dir=None, quiet=False):
    """Train and evaluate. Returns a dict of results. Saves the model if model_dir is given."""
    say = (lambda *a, **k: None) if quiet else print

    parts = split_frame(dataset, 0.6, 0.2, gap=horizon)
    train, val, test = parts["train"], parts["val"], parts["test"]
    x_train, y_train = train[FEATURE_COLUMNS], train["target_up"]
    x_val, y_val = val[FEATURE_COLUMNS], val["target_up"]
    x_test, y_test = test[FEATURE_COLUMNS], test["target_up"]

    train_share = float(y_train.mean())
    results = {"always_majority": {}, "logistic": {}, "xgboost": {}}

    # ---- baseline 1: always predict the training majority class ----
    constant = np.full(len(y_val), train_share)
    results["always_majority"]["val"] = evaluate(y_val, constant)
    results["always_majority"]["test"] = evaluate(y_test, np.full(len(y_test), train_share))

    # ---- baseline 2: logistic regression (scaler fitted on train only) ----
    logistic = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000))
    logistic.fit(x_train, y_train)
    results["logistic"]["val"] = evaluate(y_val, logistic.predict_proba(x_val)[:, 1])
    results["logistic"]["test"] = evaluate(y_test, logistic.predict_proba(x_test)[:, 1])

    # ---- XGBoost: validation set is used only to decide when to stop ----
    model = XGBClassifier(**XGB_SETTINGS)
    model.fit(x_train, y_train, eval_set=[(x_val, y_val)], verbose=False)
    proba_val = model.predict_proba(x_val)[:, 1]
    proba_test = model.predict_proba(x_test)[:, 1]
    results["xgboost"]["val"] = evaluate(y_val, proba_val)
    results["xgboost"]["test"] = evaluate(y_test, proba_test)
    results["best_iteration"] = int(model.best_iteration)

    # ---- importance (gain share). Real explanations (SHAP) come in Phase 13 ----
    gain = model.get_booster().get_score(importance_type="gain")
    total_gain = sum(gain.values()) or 1.0
    importance = {c: gain.get(c, 0.0) / total_gain for c in FEATURE_COLUMNS}
    results["importance"] = dict(sorted(importance.items(), key=lambda kv: -kv[1]))

    # ---- per-stock test accuracy ----
    per_stock = {}
    test_view = test[["symbol", "target_up"]].copy()
    test_view["predicted"] = (proba_test >= 0.5).astype(int)
    for symbol, group in test_view.groupby("symbol"):
        per_stock[symbol] = {
            "xgboost": float((group["predicted"] == group["target_up"]).mean()),
            "always_up": float((group["target_up"] == 1).mean()),
        }
    results["per_stock_test"] = per_stock

    # ---------------- report ----------------
    say(f"Horizon: {horizon} trading day(s). Features: {len(FEATURE_COLUMNS)} (groups A-C only).")
    say(f"Rows  train {len(train)} ({str(train['date'].min())[:10]} to {str(train['date'].max())[:10]})  "
        f"val {len(val)} ({str(val['date'].min())[:10]} to {str(val['date'].max())[:10]})  "
        f"test {len(test)} ({str(test['date'].min())[:10]} to {str(test['date'].max())[:10]})")
    say(f"Training share UP: {train_share:.1%}. XGBoost stopped at tree {results['best_iteration']} "
        f"of at most {XGB_SETTINGS['n_estimators']}.\n")

    for name, label in (("val", "VALIDATION (used for early stopping, slightly optimistic)"),
                        ("test", "TEST (evaluated once, the honest number)")):
        n = len(y_val) if name == "val" else len(y_test)
        say(f"=== {label} ===")
        say(f"{'model':<18}{'accuracy':>9}{'precision':>10}{'recall':>8}{'F1':>7}{'ROC-AUC':>9}{'log loss':>10}")
        for model_name, pretty in (("always_majority", "always-majority"), ("logistic", "logistic regr."), ("xgboost", "XGBoost")):
            m = results[model_name][name]
            say(f"{pretty:<18}{m['accuracy']:>9.3f}{m['precision']:>10.3f}{m['recall']:>8.3f}"
                f"{m['f1']:>7.3f}{m['roc_auc']:>9.3f}{m['log_loss']:>10.4f}")
        gap_pp = (results["xgboost"][name]["accuracy"] - results["always_majority"][name]["accuracy"]) * 100
        say(f"XGBoost minus always-majority accuracy: {gap_pp:+.1f} percentage points. "
            f"Rough 95% noise band: about +/-{noise_band(n) * 100:.1f} pp at the very least "
            f"(stocks move together, so the true band is wider).")
        m = results["xgboost"][name]
        say(f"XGBoost confusion matrix (rows = actual, columns = predicted):")
        say(f"                 pred DOWN   pred UP")
        say(f"  actual DOWN    {m['tn']:>9}   {m['fp']:>7}")
        say(f"  actual UP      {m['fn']:>9}   {m['tp']:>7}\n")

    say("=== XGBoost feature importance (share of total gain) ===")
    for feature, share in list(results["importance"].items())[:10]:
        say(f"  {feature:<20}{share:>7.1%}")
    say("\n=== PER-STOCK TEST ACCURACY (XGBoost vs always-UP) ===")
    say("  " + "   ".join(f"{s} {v['xgboost']:.0%}/{v['always_up']:.0%}" for s, v in per_stock.items()))

    if model_dir is not None:
        model_dir = Path(model_dir)
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / f"xgb_direction_h{horizon}.json"
        meta_path = model_dir / f"xgb_direction_h{horizon}_meta.json"
        model.save_model(str(model_path))
        meta = {
            "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "task": f"direction of the close {horizon} trading day(s) ahead (1 = up)",
            "feature_columns": FEATURE_COLUMNS,
            "horizon": horizon,
            "xgboost_settings": {k: v for k, v in XGB_SETTINGS.items()},
            "best_iteration": results["best_iteration"],
            "train_dates": [str(train["date"].min())[:10], str(train["date"].max())[:10]],
            "val_dates": [str(val["date"].min())[:10], str(val["date"].max())[:10]],
            "test_dates": [str(test["date"].min())[:10], str(test["date"].max())[:10]],
            "metrics": {k: results[k] for k in ("always_majority", "logistic", "xgboost")},
            "note": "Test metrics are from a single evaluation. Not a guarantee of future results.",
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        say(f"\nSaved: {model_path.name} and {meta_path.name} in {model_dir}")

    return results


def main():
    horizon = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    from config import BASE_DIR
    from ml_data import load_dataset

    dataset = load_dataset(horizon)
    print(f"Dataset: {len(dataset)} rows, {dataset['symbol'].nunique()} stocks\n")
    run_experiment(dataset, horizon, model_dir=BASE_DIR / "models")
    print("\nReminder: do not change settings because of the test numbers above.")


if __name__ == "__main__":
    main()