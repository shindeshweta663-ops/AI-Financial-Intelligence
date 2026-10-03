import numpy as np
import pandas as pd


def compute_indicators(close: pd.Series) -> pd.DataFrame:
    """
    Input : daily closing prices, oldest first (a pandas Series).
    Output: DataFrame with the same index and these columns:
            close, sma20, ema20, ema50, rsi, macd, macd_signal, volatility
    Early rows are NaN until enough history exists.
    """
    close = close.astype(float)
    out = pd.DataFrame(index=close.index)
    out["close"] = close

    # --- Moving averages ---
    out["sma20"] = close.rolling(window=20).mean()
    out["ema20"] = close.ewm(span=20, adjust=False, min_periods=20).mean()
    out["ema50"] = close.ewm(span=50, adjust=False, min_periods=50).mean()

    # --- RSI (Wilder smoothing, 14 periods) ---
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss
    out["rsi"] = 100 - (100 / (1 + rs))

    # --- MACD (12, 26, 9) ---
    ema12 = close.ewm(span=12, adjust=False, min_periods=12).mean()
    ema26 = close.ewm(span=26, adjust=False, min_periods=26).mean()
    out["macd"] = ema12 - ema26
    out["macd_signal"] = out["macd"].ewm(span=9, adjust=False, min_periods=9).mean()

    # --- Volatility: 20-day std of daily returns, annualized, in percent ---
    daily_returns = close.pct_change()
    out["volatility"] = daily_returns.rolling(window=20).std() * np.sqrt(252) * 100

    return out