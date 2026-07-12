"""
position_sizer.py — risk-based position sizing for U1254
─────────────────────────────────────────────────────────
Replaces the "no name > 15%" *notional* cap with proper fixed-fractional
*risk* sizing, then layers the notional, liquidity, and cluster caps on top.

Core idea (what a desk actually does):
    risk budget  = equity * risk_pct           (e.g. 1% of equity per trade)
    shares       = risk_budget / (entry - stop) (so every trade risks the SAME taka)
    then cap by:  notional (<=15% of book), liquidity (<=X% of ADV)

This fixes the flaw that a tight-stop and a wide-stop name at the same 15%
weight carry wildly different ACTUAL risk. Here, risk is constant; the
position SIZE flexes with the stop distance.

Run `python position_sizer.py` for a worked demo on the U1254 book.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

# DSE all-in round-trip friction: commission + laga/howla + 0.05% sell tax + slippage.
# Tune to your LankaBangla schedule; 1.2% is a realistic default for liquid names,
# higher for thin ones (spread dominates).
DSE_ROUNDTRIP_COST = 0.012


@dataclass
class SizeResult:
    ticker: str
    shares: int
    capital: float
    pct_of_book: float
    risk_taka: float
    risk_pct_actual: float
    bound_by: str                       # "risk" | "notional" | "liquidity"
    rr_to_target: Optional[float] = None
    net_target_pct: Optional[float] = None
    warnings: list = field(default_factory=list)

    def line(self) -> str:
        rr = f"{self.rr_to_target:.2f}" if self.rr_to_target else "—"
        return (f"{self.ticker:11} {self.shares:5d} sh  "
                f"৳{self.capital:>8,.0f}  {self.pct_of_book:>4.1f}% book  "
                f"risk ৳{self.risk_taka:>5,.0f} ({self.risk_pct_actual:.2f}%)  "
                f"R:R {rr:>4}  [{self.bound_by}]")


def size_position(ticker: str, equity: float, entry: float, stop: float,
                  target: Optional[float] = None,
                  risk_pct: float = 0.01,
                  notional_cap_pct: float = 0.15,
                  adv_mn: Optional[float] = None,
                  max_adv_participation: float = 0.10,
                  roundtrip_cost: float = DSE_ROUNDTRIP_COST) -> SizeResult:
    """
    equity         : total account equity (PV + cash)
    entry, stop    : prices; stop MUST be below entry for a long
    target         : optional, to compute reward:risk and net-of-cost target
    risk_pct       : fraction of equity to risk if the stop is hit (default 1%)
    notional_cap_pct : hard cap on position as % of book (default 15%)
    adv_mn         : average daily traded VALUE in millions (liquidity) — optional
    max_adv_participation : don't let the position exceed this % of one day's ADV
    """
    if entry <= stop:
        raise ValueError(f"{ticker}: entry ({entry}) must be above stop ({stop}) for a long.")

    warnings: list[str] = []
    risk_per_share = entry - stop

    # 1) RISK-based count — the primary driver
    shares_risk = (equity * risk_pct) / risk_per_share
    # 2) NOTIONAL cap
    shares_notional = (equity * notional_cap_pct) / entry
    # 3) LIQUIDITY cap — never be more than X% of a day's traded value
    shares_liq = float("inf")
    if adv_mn:
        shares_liq = (adv_mn * 1e6 * max_adv_participation) / entry

    candidates = [(shares_risk, "risk"),
                  (shares_notional, "notional"),
                  (shares_liq, "liquidity")]
    shares_float, bound_by = min(candidates, key=lambda x: x[0])
    shares = int(shares_float)

    capital = shares * entry
    risk_taka = shares * risk_per_share

    rr = net_target = None
    if target:
        rr = (target - entry) / risk_per_share
        net_target = round((target - entry) / entry - roundtrip_cost, 4)
        if rr < 1.5:
            warnings.append(f"R:R {rr:.2f} (<1.5) — thin reward for the risk; pass or tighten target.")
        if net_target is not None and net_target <= 0:
            warnings.append("Target does NOT clear round-trip costs — this trade loses money even if it works.")

    if bound_by == "notional":
        warnings.append("Capped by 15% notional (stop is tight, so risk-sizing wanted more). Fine.")
    if bound_by == "liquidity":
        warnings.append(f"Capped by liquidity (>{max_adv_participation:.0%} of ADV). Exit may be slow — size down further or skip.")
    if risk_per_share / entry > 0.10:
        warnings.append(f"Stop is {risk_per_share/entry:.0%} away — very wide; risk-sizing gives only {shares} sh.")
    if shares == 0:
        warnings.append("Risk/liquidity caps round to ZERO shares — trade too small to take or stop too wide.")

    return SizeResult(ticker, shares, round(capital), round(capital / equity * 100, 1),
                      round(risk_taka), round(risk_taka / equity * 100, 3),
                      bound_by, round(rr, 2) if rr else None, net_target, warnings)


# ── Cluster / correlation cap ────────────────────────────────────────────────
# Treat correlated names as ONE risk unit. The book learned this reactively
# (both banks soft at once); make it a rule.
CLUSTER_MAP = {
    "Bank": "FINANCIALS", "NBFI": "FINANCIALS", "Financial Institutions": "FINANCIALS",
    "Insurance": "INSURANCE",
    "Pharma": "PHARMA", "Pharmaceuticals": "PHARMA",
    "Textile": "TEXTILE",
    "Fuel/Power": "FUEL", "Fuel and Power": "FUEL",
    "Cement": "MATERIALS", "Engineering": "MATERIALS",
}

def check_cluster_caps(positions: list[tuple[str, float, str]], equity: float,
                       cluster_cap_pct: float = 0.30,
                       single_sector_cap_pct: float = 0.20) -> list[str]:
    """
    positions: list of (ticker, capital_taka, sector).
    Flags any correlated cluster over cluster_cap_pct and any single sector
    over single_sector_cap_pct. Returns a list of human-readable flags.
    """
    sector_tot: dict[str, float] = {}
    cluster_tot: dict[str, float] = {}
    for _t, cap, sector in positions:
        sector_tot[sector] = sector_tot.get(sector, 0) + cap
        cl = CLUSTER_MAP.get(sector, sector)
        cluster_tot[cl] = cluster_tot.get(cl, 0) + cap

    flags = []
    for sec, cap in sorted(sector_tot.items(), key=lambda x: -x[1]):
        pct = cap / equity
        if pct > single_sector_cap_pct:
            flags.append(f"SECTOR {sec}: {pct:.0%} of book (> {single_sector_cap_pct:.0%} cap)")
    for cl, cap in sorted(cluster_tot.items(), key=lambda x: -x[1]):
        pct = cap / equity
        if pct > cluster_cap_pct:
            flags.append(f"CLUSTER {cl}: {pct:.0%} of book (> {cluster_cap_pct:.0%} cap) — correlated names, treat as one risk")
    return flags


# ── Demo on the U1254 book ────────────────────────────────────────────────────
if __name__ == "__main__":
    EQUITY = 193_300   # PV + cash from the 14-Jun statement

    print("=" * 78)
    print(f"RISK-BASED SIZING DEMO  ·  equity ৳{EQUITY:,}  ·  1% risk per trade")
    print("=" * 78)
    # (ticker, entry, stop, target, adv_mn)
    plays = [
        ("PRAGATIINS", 76.90, 71.80, 82.20, 60),
        ("IDLC",       41.00, 38.40, 44.50, 24),
        ("DOREENPWR",  31.60, 30.20, 34.30, 31),
        ("BXPHARMA",  125.70,122.00,136.00, 132),   # tight stop → notional-capped
    ]
    for tk, e, s, t, adv in plays:
        r = size_position(tk, EQUITY, e, s, t, risk_pct=0.01, adv_mn=adv)
        print(r.line())
        for w in r.warnings:
            print(f"            ⚠ {w}")

    print("\n" + "-" * 78)
    print("Contrast: what 'equal-weight ~7,900 each' actually risked vs 1% sizing")
    print("-" * 78)
    for tk, e, s, t, adv in plays[:3]:
        eq_shares = int(7900 // e)
        eq_risk = eq_shares * (e - s)
        print(f"{tk:11} equal-wt {eq_shares:4d} sh → risk ৳{eq_risk:,.0f} "
              f"({eq_risk/EQUITY*100:.2f}% of book)  vs 1% target ৳{EQUITY*0.01:,.0f}")

    print("\n" + "-" * 78)
    print("CLUSTER CHECK on the current 14-Jun book")
    print("-" * 78)
    book = [
        ("BXPHARMA",29923,"Pharma"),("SQURPHARMA",25884,"Pharma"),("ACMELAB",20094,"Pharma"),
        ("CITYBANK",14700,"Bank"),("PRIMEBANK",10325,"Bank"),
        ("IDLC",9864,"NBFI"),("DBH",9045,"NBFI"),
        ("MALEKSPIN",10010,"Textile"),("ENVOYTEX",6552,"Textile"),("PTL",8714,"Textile"),
        ("PRAGATIINS",11460,"Insurance"),("CONFIDCEM",8854,"Cement"),
        ("BSC",8618,"Miscellaneous"),("MPETROLEUM",4182,"Fuel/Power"),
    ]
    for f in check_cluster_caps(book, EQUITY):
        print("  ⚠", f)
