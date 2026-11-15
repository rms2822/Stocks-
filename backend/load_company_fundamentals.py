"""load_company_fundamentals.py -- enrich the fundamentals table with per-company
data scraped from dse.com.bd company pages (NAV, debt, EPS history, dividend,
holdings). Run after /load-fundamentals (amarstock EPS/PE) and before full_scan.

Usage: python load_company_fundamentals.py [max_workers]
"""
from __future__ import annotations

import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from app.company_fundamentals import fetch_company

DB = "dse.db"


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    con = sqlite3.connect(DB)
    # Universe: tickers that have a fundamentals row (real companies w/ EPS).
    tickers = [r[0] for r in con.execute("SELECT ticker FROM fundamentals").fetchall()]
    ltp = dict(con.execute("SELECT ticker, ltp FROM stocks").fetchall())
    con.close()
    print(f"Enriching {len(tickers)} companies from dse.com.bd (workers={workers})...")

    results = {}
    done = fail = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_company, t): t for t in tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            d = fut.result()
            if d:
                results[t] = d
                done += 1
            else:
                fail += 1
            if (done + fail) % 50 == 0:
                print(f"  {done+fail}/{len(tickers)} (ok {done}, fail {fail})")

    # Write updates
    con = sqlite3.connect(DB)
    cur = con.cursor()
    upd = 0
    for t, d in results.items():
        nav = d.get("nav")
        pb = round(ltp[t] / nav, 3) if (nav and ltp.get(t)) else None
        eby = d.get("eps_by_year", {})
        nby = d.get("nav_by_year", {})
        fields = {
            "nav": nav,
            "pb_ratio": pb,
            "total_debt_mn": d.get("total_debt_mn"),
            "shares_outstanding": d.get("shares_outstanding"),
            "paid_up_capital": d.get("paid_up_capital"),
            "debt_equity": d.get("debt_equity"),
            "dividend": d.get("dividend"),
            "sponsor_holding": d.get("sponsor_holding"),
            "govt_holding": d.get("govt_holding"),
            "institute_holding": d.get("institute_holding"),
            "foreign_holding": d.get("foreign_holding"),
            "public_holding": d.get("public_holding"),
        }
        for y in range(2021, 2026):
            if y in eby:
                fields[f"eps_{y}"] = eby[y]
            if y in nby:
                fields[f"nav_{y}"] = nby[y]
        sets = ", ".join(f"{k}=?" for k in fields)
        cur.execute(f"UPDATE fundamentals SET {sets} WHERE ticker=?",
                    (*fields.values(), t))
        upd += 1
    con.commit()
    con.close()
    print(f"Updated {upd} fundamentals rows (ok {done}, fail {fail}).")


if __name__ == "__main__":
    main()
