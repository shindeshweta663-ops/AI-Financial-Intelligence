"""Independent cross-check of risk.py using plain Python loops, no pandas math.

Run from the backend folder:  python check_risk_independent.py [SYMBOL] [WINDOW]
Read-only. Compares volatility, total return, max drawdown, VaR and CVaR.
Sharpe/Sortino are not rechecked here (covered by the hand-worked unit tests).
"""
import math
import sys

import pandas as pd

from crud import get_price_history, get_stock_by_symbol
from database import SessionLocal
from risk import compute_risk

symbol = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
window = int(sys.argv[2]) if len(sys.argv) > 2 else 756

db = SessionLocal()
try:
    stock = get_stock_by_symbol(db, symbol)
    if stock is None:
        raise SystemExit(f"{symbol} is not tracked")
    rows = get_price_history(db, stock.stock_id, limit=window + 1)
finally:
    db.close()

dates = [r.date for r in rows]
closes = [float(r.close_price) for r in rows]
print(f"{symbol}: {len(closes)} closes, {dates[0]} to {dates[-1]}")

# --- independent calculation with loops ---
rets = [closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))]
n = len(rets)
mean = sum(rets) / n
var_sample = sum((x - mean) ** 2 for x in rets) / (n - 1)
vol = math.sqrt(var_sample) * math.sqrt(252)
total = closes[-1] / closes[0] - 1.0

peak, worst = closes[0], 0.0
for c in closes:
    peak = max(peak, c)
    worst = min(worst, c / peak - 1.0)

ordered = sorted(rets)
q = 0.05 * (n - 1)               # linear interpolation, same rule as numpy's default
lo = int(math.floor(q))
cut = ordered[lo] + (ordered[min(lo + 1, n - 1)] - ordered[lo]) * (q - lo)
tail = [x for x in rets if x <= cut]
my_var, my_cvar = -cut, -sum(tail) / len(tail)

# --- risk.py ---
close = pd.Series(closes, index=pd.to_datetime(dates))
r = compute_risk(close, risk_free_pct=None)

pairs = [
    ("total_return", total, r["total_return"]),
    ("annualized_volatility", vol, r["annualized_volatility"]),
    ("max_drawdown", worst, r["max_drawdown"]),
    ("var (95%)", my_var, r["var"]),
    ("cvar (95%)", my_cvar, r["cvar"]),
]
bad = 0
print(f"\n{'measure':<24}{'loops':>14}{'risk.py':>14}   result")
for name, a, b in pairs:
    ok = abs(a - b) < 1e-9
    bad += not ok
    print(f"{name:<24}{a:>14.8f}{b:>14.8f}   {'MATCH' if ok else 'DIFFERENT'}")

print("\nAll match." if bad == 0 else f"\n{bad} measure(s) differ. Do not trust risk.py until explained.")