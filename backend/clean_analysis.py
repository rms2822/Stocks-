"""clean_analysis.py -- clean full_analysis.csv and emit a data-quality-checked dataset.

Fixes the issues found in the raw scan output:
  1. Blank `sector` -- filled from an explicit override map plus ticker-suffix
     heuristics (life-insurance -> Insurance, mutual-fund schemes -> Mutual Fund).
  2. Extreme / non-meaningful `pe` -- kept as-is but flagged (`pe_reliable`)
     so downstream views can warn instead of silently averaging garbage.
  3. Missing fundamentals -- summarised with a `has_fundamentals` flag rather
     than dropped, so coverage is visible instead of hidden.

Outputs full_analysis_clean.csv / .json next to the source file, and prints a
before/after data-quality report. Re-runnable and side-effect free on the source.
"""
from __future__ import annotations

import csv
import json
import os
from collections import Counter

SRC = os.path.join(os.path.dirname(__file__), "full_analysis.csv")
OUT_CSV = os.path.join(os.path.dirname(__file__), "full_analysis_clean.csv")
OUT_JSON = os.path.join(os.path.dirname(__file__), "full_analysis_clean.json")

# --- Sector recovery -------------------------------------------------------
# Explicit overrides for tickers the upstream feed leaves without a sector.
# (Verified individually; suffix heuristics below act as a safety net.)
SECTOR_OVERRIDES = {
    # Life insurance -> Insurance
    "POPULARLIF": "Insurance", "FAREASTLIF": "Insurance", "PADMALIFE": "Insurance",
    "RUPALILIFE": "Insurance", "SANDHANINS": "Insurance", "DELTALIFE": "Insurance",
    "MEGHNALIFE": "Insurance", "NATLIFEINS": "Insurance", "PRAGATILIF": "Insurance",
    "TILIL": "Insurance", "SONALILIFE": "Insurance", "PRIMELIFE": "Insurance",
    "SUNLIFEINS": "Insurance", "PROGRESLIF": "Insurance", "CLICL": "Insurance",
    # Mutual fund / closed-end schemes -> Mutual Fund
    "PRIME1ICBA": "Mutual Fund", "CAPITECGBF": "Mutual Fund", "FBFIF": "Mutual Fund",
    "SEMLIBBLSF": "Mutual Fund", "VAMLRBBF": "Mutual Fund", "RELIANCE1": "Mutual Fund",
    # Bangladesh Services Ltd (Hotel InterContinental)
    "BDSERVICE": "Services and Real Estate",
}

# Suffix heuristics used only when no explicit override exists.
INSURANCE_SUFFIXES = ("LIFE", "LIF", "LIFEINS", "INS", "LIL")
MUTUALFUND_SUFFIXES = ("MF", "ICBA", "GBF", "FIF", "BBLSF", "RBBF", "MF1")


def recover_sector(ticker: str) -> str:
    if ticker in SECTOR_OVERRIDES:
        return SECTOR_OVERRIDES[ticker]
    for suf in MUTUALFUND_SUFFIXES:
        if ticker.endswith(suf):
            return "Mutual Fund"
    for suf in INSURANCE_SUFFIXES:
        if ticker.endswith(suf):
            return "Insurance"
    return "Unclassified"


# --- Helpers ---------------------------------------------------------------
def to_float(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# A |PE| above this is treated as not economically meaningful (near-zero or
# negative earnings), so it should not drive valuation comparisons.
PE_RELIABLE_MAX = 100.0

FUND_FIELDS = ("eps", "pe", "nav", "pb")


def main():
    with open(SRC, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys())
    # New data-quality columns appended after the originals.
    for col in ("sector_source", "pe_reliable", "has_fundamentals"):
        if col not in fieldnames:
            fieldnames.append(col)

    blank_before = sum(1 for r in rows if not r["sector"].strip())
    pe_extreme = 0
    no_fund = 0

    for r in rows:
        # 1. Sector
        if r["sector"].strip():
            r["sector_source"] = "feed"
        else:
            r["sector"] = recover_sector(r["ticker"])
            r["sector_source"] = "recovered"

        # 2. PE reliability
        pe = to_float(r["pe"])
        reliable = pe is not None and abs(pe) <= PE_RELIABLE_MAX and pe > 0
        r["pe_reliable"] = "true" if reliable else "false"
        if pe is not None and not reliable:
            pe_extreme += 1

        # 3. Fundamentals coverage
        present = sum(1 for fld in FUND_FIELDS if r[fld].strip())
        r["has_fundamentals"] = "true" if present >= 2 else "false"
        if present == 0:
            no_fund += 1

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # JSON with numeric coercion for the dashboard.
    num_cols = {
        "ltp", "percent_change", "volume", "combined_score", "tech_score",
        "fund_score", "rsi", "macd_hist", "volume_ratio", "pct_from_52h",
        "sma20", "sma50", "eps", "pe", "nav", "pb", "eps_trend", "debt_equity",
    }
    json_rows = []
    for r in rows:
        o = {}
        for k, v in r.items():
            if k in num_cols:
                o[k] = to_float(v)
            elif k in ("pe_reliable", "has_fundamentals"):
                o[k] = (v == "true")
            else:
                o[k] = v
        json_rows.append(o)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(json_rows, f, indent=2)

    recovered = Counter(r["sector"] for r in rows if r["sector_source"] == "recovered")
    print(f"Rows: {len(rows)}")
    print(f"Blank sectors fixed: {blank_before} -> 0")
    for sec, n in recovered.most_common():
        print(f"    recovered -> {sec}: {n}")
    print(f"Extreme/negative PE flagged (pe_reliable=false): {pe_extreme}")
    print(f"Rows with zero fundamentals: {no_fund}")
    print(f"Wrote {OUT_CSV}")
    print(f"Wrote {OUT_JSON}")


if __name__ == "__main__":
    main()
