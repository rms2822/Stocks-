"""
app/analysis/fundamental.py
────────────────────────────
Fundamental analysis scoring for DSE stocks.
 
Inputs:  Fundamentals ORM row  +  current price from Stock row
Outputs: FundamentalResult with score (0-100) and BUY/HOLD/SELL signal
 
Scoring methodology (DSE-calibrated):
──────────────────────────────────────
  P/E ratio     — DSE market avg ~15x; below 10 is cheap, above 25 is expensive
  P/B ratio     — computed as LTP / NAV; below 1.5 is undervalued
  EPS           — positive = healthy; negative = loss-making, heavy penalty
  EPS growth    — requires two years of data; skipped if unavailable
  Dividend yield— bonus for income investors
  ROE           — return on equity if available
 
Each factor returns a score contribution (-20 to +20).
Combined score is normalised to 0-100.
score >= 62  → BUY
score 40-61  → HOLD
score <  40  → SELL
"""
 
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
 
 
# ── DSE sector average P/E benchmarks ────────────────────────────────────────
# Used to judge whether a stock's P/E is cheap/fair/expensive vs its sector
SECTOR_PE_BENCHMARKS: dict[str, float] = {
    # Benchmarks derived from actual DSE data (profitable stocks, PE<50)
    "Bank":                          7.6,   # actual avg 7.61x
    "Banking":                       7.6,
    "Fuel and Power":                9.6,   # actual avg 9.55x
    "Fuel & Power":                  9.6,
    "Telecommunication":             12.9,  # actual avg 12.86x
    "Telecom":                       12.9,
    "Services and Real Estate":      13.3,  # actual avg 13.25x
    "Cement":                        14.1,  # actual avg 14.10x
    "Financial Institutions":        15.4,  # actual avg 15.36x
    "Non-Bank Financial":            15.4,
    "Textile":                       14.7,  # actual avg 14.65x (excl outliers)
    "Tannery Industries":             7.9,  # actual avg 7.85x
    "Insurance":                     17.1,  # actual avg 17.07x
    "Pharmaceuticals and Chemicals": 16.6,  # actual avg 16.64x
    "Pharmaceuticals":               16.6,
    "Food and Allied":               11.4,  # actual avg 11.43x
    "Food & Allied":                 11.4,
    "IT Sector":                     17.7,  # actual avg 17.67x
    "IT":                            17.7,
    "Jute":                          26.2,  # only 1 stock
    "Paper and Printing":            24.4,  # actual avg 24.41x
    "Paper & Printing":              24.4,
    "Travel and Leisure":             9.6,  # actual avg 9.63x
    "Engineering":                    9.9,  # actual avg 9.91x (excl outliers)
    "Ceramics Sector":               12.0,  # estimated
    "Miscellaneous":                 18.8,  # actual avg 18.83x
}
DEFAULT_MARKET_PE = 13.0   # actual DSE market average (profitable stocks, PE<50)
 
 
# ── Data containers ───────────────────────────────────────────────────────────
 
@dataclass
class FundamentalSignal:
    name:   str
    value:  str    # "Bullish" | "Neutral" | "Bearish"
    detail: str
    weight: float = 1.0
 
 
@dataclass
class FundamentalResult:
    ticker:          str
    current_price:   float
 
    # Raw values
    eps:             Optional[float] = None
    pe:              Optional[float] = None
    nav:             Optional[float] = None
    pb:              Optional[float] = None   # computed: price / nav
    dividend:        Optional[float] = None
    dividend_yield:  Optional[float] = None   # computed: dividend / price * 100
    roe:             Optional[float] = None
    paid_up_capital: Optional[float] = None
    sector:          Optional[str]   = None
 
    # Sector context
    sector_pe:       Optional[float] = None   # benchmark P/E for this sector
 
    # Output
    signals:         list[FundamentalSignal] = field(default_factory=list)
    score:           float = 50.0
    recommendation:  str   = "HOLD"
    warning:         Optional[str] = None
 
 


def _score_eps_trend(eps_history: dict) -> FundamentalSignal:
    years = sorted(eps_history.keys())
    if len(years) < 2:
        return None
    vals = [eps_history[y] for y in years if eps_history.get(y) is not None]
    if len(vals) < 2:
        return None
    latest = vals[-1]
    oldest = vals[0]
    if oldest <= 0:
        return None
    change_pct = (latest - oldest) / oldest * 100
    if change_pct >= 20:
        return FundamentalSignal("EPS Trend", "Bullish",
            f"EPS grew {change_pct:.0f}% over {len(years)} years", weight=2.0)
    elif change_pct >= 0:
        return FundamentalSignal("EPS Trend", "Neutral",
            f"EPS stable over {len(years)} years", weight=0.0)
    elif change_pct >= -30:
        return FundamentalSignal("EPS Trend", "Bearish",
            f"EPS declined {abs(change_pct):.0f}% over {len(years)} years", weight=1.5)
    else:
        return FundamentalSignal("EPS Trend", "Bearish",
            f"EPS collapsed {abs(change_pct):.0f}% over {len(years)} years", weight=3.0)



def _score_debt_equity(total_debt_mn: float, nav: float, shares: float) -> FundamentalSignal:
    """Score Debt/Equity ratio. High debt = major risk especially in high interest rate environment."""
    if not total_debt_mn or not nav or not shares or shares <= 0:
        return None
    equity_mn = (nav * shares) / 1_000_000
    if equity_mn <= 0:
        return None
    de = round(total_debt_mn / equity_mn, 2)
    if de < 0.3:
        return FundamentalSignal("Debt/Equity", "Bullish",
            f"D/E {de:.2f}x - very low leverage, financially conservative", weight=2.0)
    elif de < 0.8:
        return FundamentalSignal("Debt/Equity", "Bullish",
            f"D/E {de:.2f}x - manageable debt level", weight=1.0)
    elif de < 1.5:
        return FundamentalSignal("Debt/Equity", "Neutral",
            f"D/E {de:.2f}x - moderate leverage", weight=0.0)
    elif de < 2.5:
        return FundamentalSignal("Debt/Equity", "Bearish",
            f"D/E {de:.2f}x - elevated leverage, interest rate risk", weight=1.5)
    elif de < 5.0:
        return FundamentalSignal("Debt/Equity", "Bearish",
            f"D/E {de:.2f}x - high leverage, significant financial risk", weight=2.5)
    else:
        return FundamentalSignal("Debt/Equity", "Bearish",
            f"D/E {de:.2f}x - dangerous leverage level", weight=3.0)


# ── Individual factor scorers ─────────────────────────────────────────────────
 
def _score_pe(pe: float, sector_pe: float) -> FundamentalSignal:
    """Score P/E ratio relative to sector benchmark."""
    ratio = pe / sector_pe   # < 1 = cheaper than sector, > 1 = more expensive
 
    if pe <= 0:
        return FundamentalSignal("P/E Ratio", "Bearish",
            f"Negative P/E ({pe:.1f}x) — company is loss-making", weight=3.0)
    elif ratio < 0.6:
        return FundamentalSignal("P/E Ratio", "Bullish",
            f"P/E {pe:.1f}x is well below sector avg {sector_pe:.1f}x — deeply undervalued",
            weight=3.0)
    elif ratio < 0.85:
        return FundamentalSignal("P/E Ratio", "Bullish",
            f"P/E {pe:.1f}x below sector avg {sector_pe:.1f}x — modestly undervalued",
            weight=1.5)
    elif ratio <= 1.15:
        return FundamentalSignal("P/E Ratio", "Neutral",
            f"P/E {pe:.1f}x in line with sector avg {sector_pe:.1f}x — fairly valued",
            weight=0.0)
    elif ratio <= 1.5:
        return FundamentalSignal("P/E Ratio", "Bearish",
            f"P/E {pe:.1f}x above sector avg {sector_pe:.1f}x — slight premium",
            weight=1.5)
    else:
        return FundamentalSignal("P/E Ratio", "Bearish",
            f"P/E {pe:.1f}x significantly above sector avg {sector_pe:.1f}x — expensive",
            weight=3.0)
 
 
def _score_pb(pb: float) -> FundamentalSignal:
    """Score Price-to-Book ratio."""
    if pb <= 0:
        return FundamentalSignal("P/B Ratio", "Bearish",
            f"Negative book value (P/B {pb:.2f}x) — equity erosion", weight=2.0)
    elif pb < 0.8:
        return FundamentalSignal("P/B Ratio", "Bullish",
            f"P/B {pb:.2f}x — trading below book value, strong value signal",
            weight=2.5)
    elif pb < 1.5:
        return FundamentalSignal("P/B Ratio", "Bullish",
            f"P/B {pb:.2f}x — trading near book value, reasonable",
            weight=1.0)
    elif pb < 3.0:
        return FundamentalSignal("P/B Ratio", "Neutral",
            f"P/B {pb:.2f}x — moderate premium to book", weight=0.0)
    else:
        return FundamentalSignal("P/B Ratio", "Bearish",
            f"P/B {pb:.2f}x — significant premium to book value", weight=1.5)
 
 
def _score_eps(eps: float) -> FundamentalSignal:
    """Score EPS — positive is good, negative is a red flag."""
    if eps > 20:
        return FundamentalSignal("EPS", "Bullish",
            f"Strong EPS ৳{eps:.2f} — high earnings power", weight=2.0)
    elif eps > 5:
        return FundamentalSignal("EPS", "Bullish",
            f"Healthy EPS ৳{eps:.2f}", weight=1.0)
    elif eps > 0:
        return FundamentalSignal("EPS", "Neutral",
            f"Positive but modest EPS ৳{eps:.2f}", weight=0.5)
    elif eps == 0:
        return FundamentalSignal("EPS", "Neutral",
            "EPS is zero — breakeven", weight=0.0)
    else:
        return FundamentalSignal("EPS", "Bearish",
            f"Negative EPS ৳{eps:.2f} — company is loss-making", weight=3.0)
 
 
def _score_dividend_yield(div_yield: float) -> FundamentalSignal:
    """Score dividend yield — DSE market avg is around 2-4%."""
    if div_yield >= 8:
        return FundamentalSignal("Dividend Yield", "Bullish",
            f"High yield {div_yield:.1f}% — strong income return", weight=1.5)
    elif div_yield >= 4:
        return FundamentalSignal("Dividend Yield", "Bullish",
            f"Good yield {div_yield:.1f}% — above market average", weight=1.0)
    elif div_yield >= 1:
        return FundamentalSignal("Dividend Yield", "Neutral",
            f"Modest yield {div_yield:.1f}%", weight=0.0)
    else:
        return FundamentalSignal("Dividend Yield", "Neutral",
            "No dividend or yield below 1%", weight=0.0)
 
 
def _score_nav_vs_price(price: float, nav: float) -> FundamentalSignal:
    """
    Separate NAV signal — focuses on margin of safety.
    Complements P/B by highlighting when price is dramatically below NAV.
    """
    if price < nav * 0.7:
        return FundamentalSignal("NAV Safety Margin", "Bullish",
            f"Price ৳{price} is 30%+ below NAV ৳{nav:.2f} — strong margin of safety",
            weight=2.0)
    elif price < nav:
        return FundamentalSignal("NAV Safety Margin", "Bullish",
            f"Price ৳{price} below NAV ৳{nav:.2f} — trading at discount",
            weight=1.0)
    elif price < nav * 1.5:
        return FundamentalSignal("NAV Safety Margin", "Neutral",
            f"Price ৳{price} within 50% of NAV ৳{nav:.2f} — reasonable premium",
            weight=0.0)
    else:
        return FundamentalSignal("NAV Safety Margin", "Bearish",
            f"Price ৳{price} is more than 50% above NAV ৳{nav:.2f}",
            weight=1.0)
 
 
# ── Main entry point ──────────────────────────────────────────────────────────
 
def compute_fundamental_analysis(
    ticker:       str,
    current_price: float,
    eps:          Optional[float] = None,
    pe:           Optional[float] = None,
    nav:          Optional[float] = None,
    dividend:     Optional[float] = None,
    roe:          Optional[float] = None,
    paid_up:      Optional[float] = None,
    sector:       Optional[str]   = None,
    eps_history:  Optional[dict]  = None,
    total_debt_mn: Optional[float] = None,
    shares_outstanding: Optional[float] = None,
    govt_holding:         Optional[float] = None,
    public_holding:       Optional[float] = None,
    sponsor_holding:      Optional[float] = None,
    turnover_mn:          Optional[float] = None,
    eps_years:            Optional[list]  = None,
    market_cap_mn:        Optional[float] = None,
    revenue_mn:           Optional[float] = None,
    cash_mn:              Optional[float] = None,
    total_liabilities_mn: Optional[float] = None,
) -> FundamentalResult:
    """
    Score a stock's fundamentals and return a FundamentalResult.
 
    All parameters except ticker and current_price are optional —
    the scorer gracefully handles missing data and notes it in warnings.
    """
    result = FundamentalResult(
        ticker        = ticker.upper(),
        current_price = current_price,
        eps           = eps,
        pe            = pe,
        nav           = nav,
        dividend      = dividend,
        roe           = roe,
        paid_up_capital = paid_up,
        sector        = sector,
    )
 
    # Compute derived values
    if nav and nav > 0 and current_price > 0:
        result.pb = round(current_price / nav, 3)
 
    if dividend and dividend > 0 and current_price > 0:
        result.dividend_yield = round(dividend / current_price * 100, 2)
 
    sector_pe = SECTOR_PE_BENCHMARKS.get(sector, DEFAULT_MARKET_PE) if sector else DEFAULT_MARKET_PE
    result.sector_pe = sector_pe
 
    signals  = []
    missing  = []
 
    # ── EPS ───────────────────────────────────────────────────────────────────
    if eps is not None:
        signals.append(_score_eps(eps))
    else:
        missing.append("EPS")
 
    # ── P/E ───────────────────────────────────────────────────────────────────
    if pe is not None:
        signals.append(_score_pe(pe, sector_pe))
    else:
        missing.append("P/E")
 
    # ── P/B and NAV ───────────────────────────────────────────────────────────
    if result.pb is not None:
        signals.append(_score_pb(result.pb))
        signals.append(_score_nav_vs_price(current_price, nav))
    else:
        missing.append("NAV/P/B")
 
    # ── Dividend yield ────────────────────────────────────────────────────────
    if result.dividend_yield is not None:
        signals.append(_score_dividend_yield(result.dividend_yield))
 
    # ── ROE ───────────────────────────────────────────────────────────────────
    if roe is not None:
        if roe >= 20:
            signals.append(FundamentalSignal("ROE", "Bullish",
                f"Strong ROE {roe:.1f}% — management generating good returns", weight=1.5))
        elif roe >= 10:
            signals.append(FundamentalSignal("ROE", "Neutral",
                f"Adequate ROE {roe:.1f}%", weight=0.0))
        else:
            signals.append(FundamentalSignal("ROE", "Bearish",
                f"Low ROE {roe:.1f}% — poor capital efficiency", weight=1.0))
 
    # EPS Trend
    if eps_history:
        trend_sig = _score_eps_trend(eps_history)
        if trend_sig:
            signals.append(trend_sig)

    # D/E Ratio
    if total_debt_mn is not None and nav and shares_outstanding:
        de_signal = _score_debt_equity(total_debt_mn, nav, shares_outstanding)
        if de_signal:
            signals.append(de_signal)

    # ── Quality / structural factors (catch ratio-screen traps) ───────────────
    from .fundamental_quality import (
        _score_ownership, _score_liquidity, _score_earnings_stability,
        _score_earnings_quality, _score_real_net_cash,
    )
    for sig in (
        _score_ownership(govt_holding, public_holding, sponsor_holding),
        _score_liquidity(turnover_mn),
        _score_earnings_stability(eps_years or []),
        _score_earnings_quality(eps, shares_outstanding, revenue_mn),
        _score_real_net_cash(cash_mn, total_liabilities_mn, market_cap_mn),
    ):
        if sig:
            signals.append(sig)

    result.signals = signals
 
    # ── Score ─────────────────────────────────────────────────────────────────
    from .fundamental_quality import compute_score_with_buckets
    score = compute_score_with_buckets(signals)   # P/E+P/B+NAV collapsed so cheapness counts once

    # Cap score based on signal count - sparse signals inflate scores
    active_signals = [s for s in signals if s.value != "Neutral"]
    if len(active_signals) < 2:
        score = min(score, 65.0)
    elif len(active_signals) < 3:
        score = min(score, 80.0)
 
    # Cap score if no EPS history available — can't fully trust without trend data
    if not eps_history and eps is not None and eps > 0:
        score = min(score, 85.0)  # good fundamentals but unverified trend

    # Penalize missing or negative earnings
    if eps is None and pe is None:
        score = min(score, 40.0)
    elif eps is not None and eps <= 0:
        score = min(score, 35.0)
    elif pe is None and eps is not None and eps > 0:
        score = min(score, 75.0)
    # Penalize extreme overvaluation
    elif pe is not None and pe > 100:
        score = min(score, 30.0)   # PE > 100x = speculative, never BUY
    elif pe is not None and pe > 50:
        score = min(score, 45.0)   # PE > 50x = expensive, max HOLD


    result.score = score
 
    # ── Recommendation ────────────────────────────────────────────────────────
    if score >= 62:
        result.recommendation = "BUY"
    elif score >= 42:
        result.recommendation = "HOLD"
    else:
        result.recommendation = "SELL"
 
    # ── Warning for missing data ──────────────────────────────────────────────
    if missing:
        result.warning = (
            f"Missing fundamental data: {', '.join(missing)}. "
            "Call POST /load-fundamentals to fetch from DSE."
        )
 
    return result
 

