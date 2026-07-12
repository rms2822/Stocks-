"""
app/analysis/screener.py
────────────────────────
Stock screener — filters all DSE stocks by fundamental + technical
criteria and returns a ranked list.

Used by GET /screener endpoint in main.py.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from sqlalchemy.orm import Session
from .. import models
from .technical import compute_technical_analysis
from .fundamental import compute_fundamental_analysis


@dataclass
class ScreenerResult:
    ticker:          str
    company:         Optional[str]
    sector:          Optional[str]
    ltp:             Optional[float]
    eps:             Optional[float]
    pe:              Optional[float]
    nav:             Optional[float]
    market_cap:      Optional[float]
    tech_score:      float
    fund_score:      float
    combined_score:  float
    recommendation:  str
    data_days:       int


def run_screener(
    db: Session,

    # Fundamental filters
    sector:          Optional[str]  = None,
    min_eps:         Optional[float] = None,
    max_eps:         Optional[float] = None,
    min_pe:          Optional[float] = None,
    max_pe:          Optional[float] = None,
    profitable_only: bool = False,   # eps > 0

    # Technical filters
    min_tech_score:  Optional[float] = None,
    max_tech_score:  Optional[float] = None,

    # Combined filters
    recommendation:  Optional[str]  = None,   # BUY | HOLD | SELL
    min_score:       Optional[float] = None,
    min_data_days:   int = 1,

    # Output
    limit:           int = 30,
    sort_by:         str = "combined_score",  # combined_score | tech_score | fund_score | pe | eps
    sort_dir:        str = "desc",

    # Weights
    tech_weight:     float = 0.45,
    fund_weight:     float = 0.55,
) -> list[ScreenerResult]:
    """
    Screen all stocks in the DB and return a ranked filtered list.

    Strategy:
      1. Pre-filter stocks by fundamental criteria using DB queries (fast)
      2. Load price history and run technical analysis (slower)
      3. Apply remaining filters and rank
    """

    # ── Step 1: DB-level fundamental pre-filter ───────────────────────────────
    stock_q = db.query(models.Stock)

    if sector:
        # Case-insensitive partial match
        stock_q = stock_q.filter(
            models.Stock.sector.ilike(f"%{sector}%")
        )

    stocks = stock_q.all()
    if not stocks:
        return []

    # Build fundamentals lookup
    tickers = [s.ticker for s in stocks]
    fund_map: dict[str, models.Fundamentals] = {
        f.ticker: f
        for f in db.query(models.Fundamentals)
        .filter(models.Fundamentals.ticker.in_(tickers))
        .all()
    }

    # Build price history lookup (fetch all at once to avoid N+1)
    from ..crud import get_price_history
    history_map: dict[str, list] = {}
    for ticker in tickers:
        history_map[ticker] = get_price_history(db, ticker, limit=200)

    # ── Step 2: Score and filter ──────────────────────────────────────────────
    tw = tech_weight / (tech_weight + fund_weight)
    fw = fund_weight / (tech_weight + fund_weight)

    results = []

    for stock in stocks:
        ticker   = stock.ticker
        fund_row = fund_map.get(ticker)
        history  = history_map.get(ticker, [])

        # Pre-filter before expensive scoring
        eps = fund_row.eps if fund_row else None
        pe  = fund_row.pe  if fund_row else None

        # Skip mutual funds and unknown sector stocks with no fundamental data
        if eps is None and pe is None and (stock.sector is None or stock.sector == "Unknown"):
            continue
        if profitable_only and (eps is None or eps <= 0):
            continue
        if min_eps is not None and (eps is None or eps < min_eps):
            continue
        if max_pe is not None and (pe is not None and pe > max_pe):
            continue
        if min_pe is not None and (pe is None or pe < min_pe):
            continue

        # Fundamental analysis
        eps_hist = {}
        if fund_row:
            for yr, attr in [(2021,"eps_2021"),(2022,"eps_2022"),(2023,"eps_2023"),(2024,"eps_2024"),(2025,"eps_2025")]:
                v = getattr(fund_row, attr, None)
                if v is not None:
                    eps_hist[yr] = v
        fund = compute_fundamental_analysis(
            ticker        = ticker,
            current_price = stock.ltp or stock.close or 0,
            eps           = fund_row.eps  if fund_row else None,
            pe            = fund_row.pe   if fund_row else None,
            nav           = fund_row.nav  if fund_row else None,
            dividend      = fund_row.dividend if fund_row else None,
            roe           = fund_row.roe      if fund_row else None,
            sector        = stock.sector,
            eps_history   = eps_hist if eps_hist else None,
            total_debt_mn = getattr(fund_row, "total_debt_mn", None) if fund_row else None,
            shares_outstanding = getattr(fund_row, "shares_outstanding", None) if fund_row else None,
        )

        # Technical analysis
        tech = compute_technical_analysis(ticker, history)

        # Combined score
        combined = round(tech.score * tw + fund.score * fw, 1)
        if combined >= 62:
            rec = "BUY"
        elif combined >= 42:
            rec = "HOLD"
        else:
            rec = "SELL"

        # ── Apply filters ─────────────────────────────────────────────────────
        if max_eps is not None and (eps is not None and eps > max_eps):
            continue
        if min_tech_score is not None and tech.score < min_tech_score:
            continue
        if max_tech_score is not None and tech.score > max_tech_score:
            continue
        if min_score is not None and combined < min_score:
            continue
        if recommendation and rec != recommendation.upper():
            continue
        if tech.data_days < min_data_days:
            continue

        results.append(ScreenerResult(
            ticker         = ticker,
            company        = stock.company,
            sector         = stock.sector,
            ltp            = stock.ltp or stock.close,
            eps            = eps,
            pe             = pe,
            nav            = fund_row.nav if fund_row else None,
            market_cap     = fund_row.market_cap if fund_row else None,
            tech_score     = round(tech.score, 1),
            fund_score     = round(fund.score, 1),
            combined_score = combined,
            recommendation = rec,
            data_days      = tech.data_days,
        ))

    # ── Step 3: Sort ──────────────────────────────────────────────────────────
    sort_key_map = {
        "combined_score": lambda r: r.combined_score,
        "tech_score":     lambda r: r.tech_score,
        "fund_score":     lambda r: r.fund_score,
        "pe":             lambda r: r.pe if r.pe is not None else 9999,
        "eps":            lambda r: r.eps if r.eps is not None else -9999,
        "ltp":            lambda r: r.ltp if r.ltp is not None else 0,
    }
    key_fn  = sort_key_map.get(sort_by, sort_key_map["combined_score"])
    reverse = (sort_dir.lower() != "asc")
    results.sort(key=key_fn, reverse=reverse)

    return results[:limit]
