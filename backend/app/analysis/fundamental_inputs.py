"""
app/analysis/fundamental_inputs.py — ONE place that decides what feeds the
fundamental scorer. Import this from main.py, screener.py, and scan.py so every
caller scores a stock identically (today they pass slightly different args, so the
same stock can get different fund_scores depending on which endpoint ran it).

It also wires the new fundamental_quality factors (ownership / liquidity /
earnings-stability / earnings-quality / real-net-cash) by passing the fields they
need — all pulled from the Stock + Fundamentals rows you already have.

Usage:
    from .fundamental_inputs import build_fundamental_kwargs
    fund = compute_fundamental_analysis(**build_fundamental_kwargs(stock, fund_row))
"""

from __future__ import annotations


def build_fundamental_kwargs(stock, fund_row) -> dict:
    """stock: models.Stock row · fund_row: models.Fundamentals row (or None)."""
    g = (lambda a: getattr(fund_row, a, None)) if fund_row else (lambda a: None)

    # multi-year EPS — used by both the trend signal and the new stability factor
    eps_hist, eps_years = {}, []
    for yr, attr in [(2021, "eps_2021"), (2022, "eps_2022"), (2023, "eps_2023"),
                     (2024, "eps_2024"), (2025, "eps_2025")]:
        v = g(attr)
        if v is not None:
            eps_hist[yr] = v
            eps_years.append(v)

    # daily traded value (liquidity) from the live Stock snapshot
    turnover_mn = None
    if stock and stock.ltp and stock.volume:
        turnover_mn = stock.ltp * stock.volume / 1e6

    return dict(
        ticker             = stock.ticker,
        current_price      = (stock.ltp or stock.close or 0),
        eps                = g("eps"),
        pe                 = g("pe"),
        nav                = g("nav"),
        dividend           = g("dividend"),
        roe                = g("roe"),
        paid_up            = g("paid_up_capital"),
        sector             = stock.sector,
        eps_history        = eps_hist or None,
        total_debt_mn      = g("total_debt_mn"),
        shares_outstanding = g("shares_outstanding"),
        # ── new quality-factor inputs ───────────────────────────────────────
        govt_holding         = g("govt_holding"),
        public_holding       = g("public_holding"),
        sponsor_holding      = g("sponsor_holding"),
        turnover_mn          = turnover_mn,
        eps_years            = eps_years or None,
        market_cap_mn        = g("market_cap"),
        # Tier-2 (return None until you scrape them — scorers no-op gracefully)
        revenue_mn           = g("revenue_mn"),
        cash_mn              = g("cash_mn"),
        total_liabilities_mn = g("total_liabilities_mn"),
    )
