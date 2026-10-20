"""A quote for stocks whose live price we cannot fetch (NSE / BSE).

Twelve Data's free plan does not cover Indian exchanges, so the live quote
call fails for them. Instead we answer from the latest two STORED daily
closes. This is the last available daily close, not a live price, and the
response says so (source, and quote_time left empty).
"""
from typing import List

from market_data import Quote


def quote_from_stored_bars(stock, bars: List) -> Quote:
    """bars: price_history rows, oldest first, at least one."""
    last = bars[-1]
    price = float(last.close_price)
    previous = float(bars[-2].close_price) if len(bars) > 1 and bars[-2].close_price is not None else None
    change = round(price - previous, 2) if previous else None
    percent = round((price / previous - 1.0) * 100.0, 2) if previous else None
    return Quote(
        symbol=stock.symbol,
        name=stock.company_name,
        exchange=stock.exchange,
        currency="INR",
        price=price,
        open=float(last.open_price) if last.open_price is not None else None,
        high=float(last.high_price) if last.high_price is not None else None,
        low=float(last.low_price) if last.low_price is not None else None,
        previous_close=previous,
        change=change,
        percent_change=percent,
        volume=int(last.volume) if last.volume is not None else None,
        quote_time=None,
        is_market_open=None,
        source="stored daily close (live quotes for this exchange are not available)",
    )