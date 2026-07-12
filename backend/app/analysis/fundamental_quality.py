"""
app/analysis/fundamental_quality.py
───────────────────────────────────
Add-on factors for fundamental.py that catch "structurally cheap" traps the
ratio-only scorer misses — e.g. Padma/Jamuna Oil, where low P/E, sub-book P/B,
fat dividend and low (interest-bearing) debt all fire bullish, but the cheapness
is justified by interest-income-driven earnings, working-capital-float cash, and
state ownership.

Each function returns a FundamentalSignal (same dataclass as fundamental.py) so
they slot straight into the existing scoring loop.

TIER 1 — implementable today, NO new data (uses fields already in Fundamentals):
    _score_ownership          → govt_holding, public_holding, sponsor_holding
    _score_liquidity          → daily turnover (ltp*volume/1e6) from Stock
    _score_earnings_stability → eps_2021..eps_2025

TIER 2 — needs ~3 new scraped fields (see "SCRAPER / MODEL ADDITIONS" at bottom):
    _score_earnings_quality   → revenue_mn        (net-income-to-revenue check)
    _score_real_net_cash      → cash_mn, total_liabilities_mn

Plus compute_score_with_buckets(), which replaces the raw bull/bear sum in
fundamental.py so the three valuation signals can't triple-count cheapness.
"""

from __future__ import annotations
import statistics
from typing import Optional

# Reuse the existing dataclass so signals are interchangeable
from .fundamental import FundamentalSignal


# ─────────────────────────────────────────────────────────────────────────────
# TIER 1 — no new data required
# ─────────────────────────────────────────────────────────────────────────────

def _score_ownership(
    govt_holding:    Optional[float],
    public_holding:  Optional[float],
    sponsor_holding: Optional[float] = None,
) -> Optional[FundamentalSignal]:
    """
    State control + thin float carry a PERMANENT discount the market applies on
    purpose. The old scorer is blind to this and reads the resulting low P/E as
    'undervalued'. Holdings are percentages (0-100).
    """
    if govt_holding is None and public_holding is None:
        return None

    # State-controlled: capital allocation serves the government, not minorities
    if govt_holding is not None and govt_holding >= 30:
        return FundamentalSignal(
            "Ownership", "Bearish",
            f"Govt holds {govt_holding:.0f}% — state-controlled; persistent "
            f"discount & minority-unfriendly capital allocation", weight=2.0)

    # Thin free float → illiquid, hard to exit, value can stay trapped for years
    if public_holding is not None and public_holding < 15:
        return FundamentalSignal(
            "Ownership", "Bearish",
            f"Public float only {public_holding:.0f}% — thin float, "
            f"illiquidity discount", weight=1.5)

    if public_holding is not None and public_holding >= 35:
        return FundamentalSignal(
            "Ownership", "Bullish",
            f"Healthy public float {public_holding:.0f}%", weight=0.5)

    return FundamentalSignal("Ownership", "Neutral",
                             "Ownership structure unremarkable", weight=0.0)


def _score_liquidity(turnover_mn: Optional[float]) -> Optional[FundamentalSignal]:
    """
    turnover_mn = daily traded value = ltp * volume / 1e6  (pass from Stock row).
    Illiquidity is itself a reason a cheap stock stays cheap — and a real risk
    for anyone who has to exit.
    """
    if turnover_mn is None:
        return None
    if turnover_mn < 3:
        return FundamentalSignal(
            "Liquidity", "Bearish",
            f"Turnover ~{turnover_mn:.0f}mn — illiquid; exit risk, value can "
            f"stay trapped", weight=1.5)
    if turnover_mn < 10:
        return FundamentalSignal("Liquidity", "Neutral",
            f"Turnover ~{turnover_mn:.0f}mn — thin", weight=0.0)
    return FundamentalSignal("Liquidity", "Bullish",
        f"Turnover ~{turnover_mn:.0f}mn — liquid", weight=0.5)


def _score_earnings_stability(
    eps_years: list[Optional[float]]
) -> Optional[FundamentalSignal]:
    """
    Complements the existing _score_eps_trend (which only measures DIRECTION).
    This measures VOLATILITY + one-off spikes. A rate-driven jump (Padma's +38%)
    shows up as a recent spike vs the multi-year median → flag, don't extrapolate.
    Pass [eps_2021, eps_2022, eps_2023, eps_2024, eps_2025].
    """
    vals = [e for e in eps_years if e is not None]
    if len(vals) < 3:
        return None
    mean = statistics.mean(vals)
    if mean <= 0:
        return None
    cv     = statistics.pstdev(vals) / mean        # coefficient of variation
    median = statistics.median(vals)
    spike  = vals[-1] > median * 1.5               # latest year is an outlier high

    if cv > 0.6 or spike:
        why = f"CV {cv:.0%}" + (" + recent spike" if spike else "")
        return FundamentalSignal(
            "Earnings Stability", "Bearish",
            f"EPS erratic ({why}) — low-quality/cyclical earnings, "
            f"don't extrapolate the latest year", weight=1.5)
    if cv < 0.25:
        return FundamentalSignal(
            "Earnings Stability", "Bullish",
            f"EPS steady (CV {cv:.0%}) — durable earnings", weight=1.0)
    return FundamentalSignal("Earnings Stability", "Neutral",
        f"EPS moderately variable (CV {cv:.0%})", weight=0.0)


# ─────────────────────────────────────────────────────────────────────────────
# TIER 2 — needs new scraped fields (revenue_mn, cash_mn, total_liabilities_mn)
# ─────────────────────────────────────────────────────────────────────────────

def _score_earnings_quality(
    eps:                Optional[float],
    shares_outstanding: Optional[float],
    revenue_mn:         Optional[float],
) -> Optional[FundamentalSignal]:
    """
    THE key Padma/Jamuna factor. If net income is a large fraction of (or exceeds)
    revenue, the profit is NOT coming from the core business — it's interest/other
    income on a cash pile. A fuel distributor cannot earn 60%+ net margin on
    operations; that ratio is a giant red flag for earnings quality + rate risk.
    """
    if eps is None or not shares_outstanding or not revenue_mn or revenue_mn <= 0:
        return None
    net_income_mn = eps * shares_outstanding / 1_000_000.0
    ratio = net_income_mn / revenue_mn
    if ratio > 0.6:
        return FundamentalSignal(
            "Earnings Quality", "Bearish",
            f"Net income is {ratio:.0%} of revenue — profit is largely "
            f"non-operating (interest/other), rate-sensitive, not core business",
            weight=2.5)
    if ratio > 0.3:
        return FundamentalSignal(
            "Earnings Quality", "Neutral",
            f"Net income {ratio:.0%} of revenue — verify income mix", weight=0.0)
    return FundamentalSignal(
        "Earnings Quality", "Bullish",
        f"Net income {ratio:.0%} of revenue — operationally driven", weight=1.0)


def _score_real_net_cash(
    cash_mn:               Optional[float],
    total_liabilities_mn:  Optional[float],
    market_cap_mn:         Optional[float],
) -> Optional[FundamentalSignal]:
    """
    'Trapped cash' detector. A naive net-cash screen sees a huge cash balance and
    a near-zero interest-bearing debt and concludes 'trades below net cash'. But if
    that cash is offset by trade payables / dues to the parent (BPC), the true net
    cash after ALL liabilities is small. Catches the negative-EV illusion.
    Requires total_liabilities_mn (NOT just interest-bearing total_debt_mn).
    """
    if cash_mn is None or total_liabilities_mn is None or not market_cap_mn:
        return None
    true_net_cash = cash_mn - total_liabilities_mn
    looks_cash_rich = cash_mn > market_cap_mn * 0.5
    if looks_cash_rich and true_net_cash < market_cap_mn * 0.10:
        return FundamentalSignal(
            "Balance Sheet Quality", "Bearish",
            "Large cash is offset by liabilities (working-capital float) — "
            "'trading below net cash' is an accounting illusion", weight=2.0)
    if true_net_cash > market_cap_mn * 0.30:
        return FundamentalSignal(
            "Balance Sheet Quality", "Bullish",
            "Genuine net cash after ALL liabilities — real balance-sheet strength",
            weight=1.5)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Valuation de-duplication — replaces the raw bull/bear sum in fundamental.py
# ─────────────────────────────────────────────────────────────────────────────

# These three are really one underlying fact: "cheap vs accounting figures".
# Counting them separately gives a cash-rich value trap up to 7.5 bullish weight.
VALUATION_FACTORS = {"P/E Ratio", "P/B Ratio", "NAV Safety Margin"}
VALUATION_CAP = 3.5     # max combined contribution from the whole valuation bucket


def compute_score_with_buckets(signals: list[FundamentalSignal]) -> float:
    """
    Drop-in replacement for the bull/bear/maxi block in compute_fundamental_analysis.
    Identical maths, except the valuation signals are collapsed into ONE capped
    contribution so cheapness is counted once, not three times.
    """
    bull = bear = maxi = 0.0
    val_bull = val_bear = 0.0

    for s in signals:
        if s.value == "Neutral":
            continue
        if s.name in VALUATION_FACTORS:
            if s.value == "Bullish":
                val_bull += s.weight
            else:
                val_bear += s.weight
            continue
        if s.value == "Bullish":
            bull += s.weight
        else:
            bear += s.weight
        maxi += s.weight

    # Collapse the valuation bucket to a single net contribution, capped at ±CAP
    val_net = max(-VALUATION_CAP, min(VALUATION_CAP, val_bull - val_bear))
    if val_net >= 0:
        bull += val_net
    else:
        bear += -val_net
    if val_bull or val_bear:
        maxi += VALUATION_CAP   # bucket can contribute at most ±CAP to the range

    if maxi <= 0:
        return 50.0
    raw = (bull - bear) / maxi          # -1 .. +1
    return round(50 + raw * 50, 1)      # 0 .. 100


# ─────────────────────────────────────────────────────────────────────────────
# INTEGRATION — wiring into fundamental.py
# ─────────────────────────────────────────────────────────────────────────────
#
# 1) In compute_fundamental_analysis(), accept the new inputs:
#        govt_holding=None, public_holding=None, sponsor_holding=None,
#        turnover_mn=None, eps_years=None,
#        revenue_mn=None, cash_mn=None, total_liabilities_mn=None,
#        market_cap_mn=None,
#    (crud.py already loads the Fundamentals row — pass these straight through;
#     turnover_mn = stock.ltp * stock.volume / 1e6 from the Stock row.)
#
# 2) After the existing signals.append(...) calls, add:
#        from .fundamental_quality import (
#            _score_ownership, _score_liquidity, _score_earnings_stability,
#            _score_earnings_quality, _score_real_net_cash,
#            compute_score_with_buckets)
#        for sig in (
#            _score_ownership(govt_holding, public_holding, sponsor_holding),
#            _score_liquidity(turnover_mn),
#            _score_earnings_stability(eps_years or []),
#            _score_earnings_quality(eps, shares_outstanding, revenue_mn),
#            _score_real_net_cash(cash_mn, total_liabilities_mn, market_cap_mn),
#        ):
#            if sig:
#                signals.append(sig)
#
# 3) Replace the bull/bear/maxi/score block with:
#        score = compute_score_with_buckets(signals)
#    (keep all the existing caps/penalties below it unchanged.)
#
# 4) RE-CALIBRATE the BUY/HOLD cutoffs. Adding bearish-capable factors will pull
#    some scores down; re-check the 62/42 thresholds against a sample so you don't
#    silently turn old BUYs into HOLDs. Spot-check PADMAOIL/JAMUNAOIL drop to HOLD
#    and a genuine name (e.g. IDLC) stays BUY.
#
# ─────────────────────────────────────────────────────────────────────────────
# SCRAPER / MODEL ADDITIONS (Tier 2 only)
# ─────────────────────────────────────────────────────────────────────────────
#
# The ownership + debt fields already come from your DSE company-page scraper
# (dse_scraper.py → models.Fundamentals). The DSE financial-highlights page that
# already yields short_term_debt_mn / govt_holding also carries cash, total
# liabilities and turnover/revenue. To enable Tier 2:
#
#   a) models.py → add to Fundamentals:
#          revenue_mn            = Column(Float, nullable=True)
#          cash_mn               = Column(Float, nullable=True)
#          total_liabilities_mn  = Column(Float, nullable=True)
#
#   b) dse_scraper.py → parse those three rows from the same financial-highlights
#      table you already read debt/ownership from, and write them on upsert.
#
#   c) Run your migration path (init_db.py / migrate) to add the columns.
#
# Until (a)-(c) are done, the Tier-2 scorers simply return None (missing data) and
# the Tier-1 factors alone already flag Padma/Jamuna via ownership + erratic EPS.
