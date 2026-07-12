"""
scan.py — single in-process scanner (replaces full_scan.py AND full_stock_analysis.py)
──────────────────────────────────────────────────────────────────────────────────────
Why this exists:
  • The two old scripts each made ~400 sequential HTTP calls to the local API,
    reloading history and recomputing everything per call (minutes per scan).
  • They sourced eps_trend / debt_equity DIFFERENTLY, so the CSV's debt_equity
    depended on which script you ran.

This computes everything IN-PROCESS in one pass (seconds), with a SINGLE source
for every column, and writes the same full_analysis.csv / .json.

Run from the backend dir:
    python scan.py
"""

from __future__ import annotations
import csv, json, sys, os

# make `app` importable when run from the backend root
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import SessionLocal
from app import models
from app.analysis.technical import compute_technical_analysis
from app.analysis.fundamental import compute_fundamental_analysis
from app.analysis.fundamental_inputs import build_fundamental_kwargs

COLS = [
    "ticker", "sector", "ltp", "percent_change", "volume",
    "combined_score", "tech_score", "fund_score", "recommendation",
    "rsi", "macd_hist", "volume_ratio", "pct_from_52h", "sma20", "sma50",
    "eps", "pe", "nav", "pb", "eps_trend", "debt_equity",
]
TECH_W, FUND_W = 0.45, 0.55


def _debt_equity(fund_row) -> float | None:
    """SINGLE authoritative D/E: total_debt_mn / (nav * shares / 1e6)."""
    if not fund_row:
        return None
    td, nav, sh = fund_row.total_debt_mn, fund_row.nav, fund_row.shares_outstanding
    if td and nav and sh and nav > 0 and sh > 0:
        equity_mn = nav * sh / 1e6
        if equity_mn > 0:
            return round(td / equity_mn, 2)
    return None


def run():
    db = SessionLocal()
    try:
        stocks = db.query(models.Stock).filter(models.Stock.ltp.isnot(None)).all()
        funds = {f.ticker: f for f in db.query(models.Fundamentals).all()}

        # batch-load ALL history once, group by ticker in Python (kills the N+1)
        hist: dict[str, list] = {}
        for row in (db.query(models.PriceHistory)
                    .order_by(models.PriceHistory.ticker, models.PriceHistory.date)
                    .all()):
            hist.setdefault(row.ticker, []).append(row)

        rows, errors = [], 0
        write_back = []   # (ticker, de) to persist debt_equity so column == CSV
        for s in stocks:
            try:
                fr = funds.get(s.ticker)
                tech = compute_technical_analysis(s.ticker, hist.get(s.ticker, []))
                fund = compute_fundamental_analysis(**build_fundamental_kwargs(s, fr))
                combined = round(tech.score * TECH_W + fund.score * FUND_W, 1)
                rec = "BUY" if combined >= 62 else "HOLD" if combined >= 42 else "SELL"
                de = _debt_equity(fr)
                if fr and de is not None and fr.debt_equity != de:
                    fr.debt_equity = de            # keep stored column in sync
                    write_back.append(s.ticker)
                ind = tech.indicators
                rows.append({
                    "ticker": s.ticker, "sector": s.sector, "ltp": s.ltp,
                    "percent_change": s.percent_change, "volume": s.volume,
                    "combined_score": combined, "tech_score": tech.score,
                    "fund_score": fund.score, "recommendation": rec,
                    "rsi": ind.rsi, "macd_hist": ind.macd_hist,
                    "volume_ratio": ind.volume_ratio, "pct_from_52h": ind.pct_from_52h,
                    "sma20": ind.sma20, "sma50": ind.sma50,
                    "eps": fund.eps, "pe": fund.pe, "nav": fund.nav, "pb": fund.pb,
                    "eps_trend": (fr.eps_trend if fr else None),   # stored, fixed by calc_trend
                    "debt_equity": de,
                })
            except Exception as e:
                errors += 1
                print(f"  ! {s.ticker}: {e}")

        if write_back:
            db.commit()
            print(f"  synced debt_equity for {len(write_back)} tickers")

        rows.sort(key=lambda r: r["combined_score"] or 0, reverse=True)

        with open("full_analysis.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=COLS); w.writeheader(); w.writerows(rows)
        with open("full_analysis.json", "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2, default=str)

        buys = sum(1 for r in rows if r["recommendation"] == "BUY")
        holds = sum(1 for r in rows if r["recommendation"] == "HOLD")
        sells = sum(1 for r in rows if r["recommendation"] == "SELL")
        print(f"\nDone. {len(rows)} stocks ({errors} errors) → full_analysis.csv / .json")
        print(f"BUY {buys} | HOLD {holds} | SELL {sells}")
        print("\nTop 15 BUYs:")
        for r in [r for r in rows if r["recommendation"] == "BUY"][:15]:
            print(f"  {r['ticker']:<12} {r['combined_score']:>5}  {r['sector']}")
    finally:
        db.close()


if __name__ == "__main__":
    run()
