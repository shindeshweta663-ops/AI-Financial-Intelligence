from datetime import date
from typing import Dict, List, Optional

from pydantic import BaseModel

from config import settings
from market_data import MarketDataError, _get_json

FINNHUB_REPORTED_URL = "https://finnhub.io/api/v1/stock/financials-reported"

REVENUE_CONCEPTS = [
    "us-gaap_RevenueFromContractWithCustomerExcludingAssessedTax",
    "us-gaap_Revenues",
    "us-gaap_SalesRevenueNet",
    "us-gaap_RevenueFromContractWithCustomerIncludingAssessedTax",
    "us-gaap_RevenuesNetOfInterestExpense",
]
NET_PROFIT_CONCEPTS = ["us-gaap_NetIncomeLoss", "us-gaap_ProfitLoss"]
ASSETS_CONCEPTS = ["us-gaap_Assets"]
EPS_CONCEPTS = ["us-gaap_EarningsPerShareDiluted", "us-gaap_EarningsPerShareBasic"]

DEBT_TOTAL_CONCEPTS = [
    "us-gaap_LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
    "us-gaap_LongTermDebt",
]
DEBT_PART_CONCEPTS = ["us-gaap_LongTermDebtNoncurrent", "us-gaap_LongTermDebtCurrent"]
DEBT_EXTRA_CONCEPTS = ["us-gaap_ShortTermBorrowings", "us-gaap_CommercialPaper"]


class FinancialRecord(BaseModel):
    report_date: date
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    total_assets: Optional[float] = None
    total_debt: Optional[float] = None
    eps: Optional[float] = None
    profit_margin: Optional[float] = None


def _values(items) -> Dict[str, float]:
    """Turn a list of line items into {concept: value}, keeping numbers only."""
    out: Dict[str, float] = {}
    for item in items or []:
        concept = item.get("concept")
        value = item.get("value")
        if concept and isinstance(value, (int, float)) and concept not in out:
            out[concept] = float(value)
    return out


def _first(values: Dict[str, float], names: List[str]) -> Optional[float]:
    for name in names:
        if name in values:
            return values[name]
    return None


def _total_debt(balance: Dict[str, float]) -> Optional[float]:
    total = _first(balance, DEBT_TOTAL_CONCEPTS)
    if total is None:
        parts = [balance[c] for c in DEBT_PART_CONCEPTS if c in balance]
        if not parts:
            return None  # unknown, so we do not store a made-up 0
        total = sum(parts)
    extras = [balance[c] for c in DEBT_EXTRA_CONCEPTS if c in balance]
    return total + sum(extras)


def get_annual_financials(symbol: str) -> List[FinancialRecord]:
    """Annual 10-K figures from Finnhub, oldest first."""
    if not settings.finnhub_api_key:
        raise MarketDataError("FINNHUB_API_KEY is not set in .env")

    symbol = symbol.strip().upper()
    data = _get_json(
        FINNHUB_REPORTED_URL,
        {"symbol": symbol, "freq": "annual", "token": settings.finnhub_api_key},
        "Finnhub",
    )
    filings = data.get("data") or []
    if not filings:
        raise MarketDataError(f"Finnhub returned no annual filings for {symbol}")

    # One filing per period end date. If duplicated, keep the most recently filed.
    by_date = {}
    for filing in filings:
        if filing.get("form") != "10-K":
            continue
        try:
            period_end = date.fromisoformat(str(filing.get("endDate", ""))[:10])
        except ValueError:
            continue
        previous = by_date.get(period_end)
        if previous is None or str(filing.get("filedDate", "")) > str(previous.get("filedDate", "")):
            by_date[period_end] = filing

    records: List[FinancialRecord] = []
    for period_end, filing in sorted(by_date.items()):
        report = filing.get("report") or {}
        income = _values(report.get("ic"))
        balance = _values(report.get("bs"))

        revenue = _first(income, REVENUE_CONCEPTS)
        net_profit = _first(income, NET_PROFIT_CONCEPTS)
        total_assets = _first(balance, ASSETS_CONCEPTS)
        eps = _first(income, EPS_CONCEPTS)
        total_debt = _total_debt(balance)

        margin = None
        if revenue and net_profit is not None:
            margin = round(net_profit / revenue * 100, 4)

        if all(v is None for v in (revenue, net_profit, total_assets, eps)):
            continue  # nothing usable in this filing

        records.append(
            FinancialRecord(
                report_date=period_end,
                revenue=revenue,
                net_profit=net_profit,
                total_assets=total_assets,
                total_debt=total_debt,
                eps=eps,
                profit_margin=margin,
            )
        )
    return records