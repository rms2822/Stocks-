"""full_scan.py — regenerates full_analysis.csv/.json with combined recommendations."""
import requests, csv, json, sqlite3

API = "http://localhost:8000"
DB  = "dse.db"

# Sector recovery for tickers the feed leaves blank (see clean_analysis.py).
SECTOR_OVERRIDES = {
    "POPULARLIF": "Insurance", "FAREASTLIF": "Insurance", "PADMALIFE": "Insurance",
    "RUPALILIFE": "Insurance", "SANDHANINS": "Insurance", "DELTALIFE": "Insurance",
    "MEGHNALIFE": "Insurance", "NATLIFEINS": "Insurance", "PRAGATILIF": "Insurance",
    "TILIL": "Insurance", "SONALILIFE": "Insurance", "PRIMELIFE": "Insurance",
    "SUNLIFEINS": "Insurance", "PROGRESLIF": "Insurance", "CLICL": "Insurance",
    "PRIME1ICBA": "Mutual Fund", "CAPITECGBF": "Mutual Fund", "FBFIF": "Mutual Fund",
    "SEMLIBBLSF": "Mutual Fund", "VAMLRBBF": "Mutual Fund", "RELIANCE1": "Mutual Fund",
    "BDSERVICE": "Services and Real Estate",
}
_INS_SUF = ("LIFE", "LIF", "LIFEINS", "INS", "LIL")
_MF_SUF = ("MF", "ICBA", "GBF", "FIF", "BBLSF", "RBBF", "MF1")


def normalize_sector(ticker, sector):
    """Return a non-blank sector, recovering it from ticker when the feed omits it."""
    if sector and str(sector).strip():
        return sector
    if ticker in SECTOR_OVERRIDES:
        return SECTOR_OVERRIDES[ticker]
    if any(ticker.endswith(s) for s in _MF_SUF):
        return "Mutual Fund"
    if any(ticker.endswith(s) for s in _INS_SUF):
        return "Insurance"
    return "Unclassified"

COLS = [
    "ticker", "sector", "ltp", "percent_change", "volume",
    "combined_score", "tech_score", "fund_score", "recommendation",
    "rsi", "macd_hist", "volume_ratio", "pct_from_52h", "sma20", "sma50",
    "eps", "pe", "nav", "pb", "eps_trend", "debt_equity",
]

def main():
    resp = requests.get(f"{API}/stocks", timeout=30).json()
    stock_list = resp.get("stocks", []) if isinstance(resp, dict) else resp
    universe = {s["ticker"]: s for s in stock_list if (s.get("ltp") or 0) > 0}
    print(f"Scanning {len(universe)} stocks...")

    trend_map, de_map = {}, {}
    try:
        conn = sqlite3.connect(DB)
        for t, tr, de in conn.execute("SELECT ticker, eps_trend, debt_equity FROM fundamentals"):
            trend_map[t] = tr
            de_map[t] = de
        conn.close()
    except Exception as e:
        print(f"  (DB read skipped: {e})")

    rows, errors = [], 0
    for i, (ticker, s) in enumerate(universe.items(), 1):
        try:
            d = requests.get(f"{API}/stocks/{ticker}/analysis", timeout=15).json()
            ind = d.get("technical", {}).get("indicators", {})
            fund = d.get("fundamental", {})
            rows.append({
                "ticker": ticker,
                "sector": normalize_sector(ticker, d.get("sector") or s.get("sector")),
                "ltp": d.get("current_price") or s.get("ltp"),
                "percent_change": s.get("percent_change"),
                "volume": s.get("volume"),
                "combined_score": d.get("combined_score"),
                "tech_score": d.get("tech_score"),
                "fund_score": d.get("fund_score"),
                "recommendation": d.get("recommendation"),
                "rsi": ind.get("rsi"),
                "macd_hist": ind.get("macd_hist"),
                "volume_ratio": ind.get("volume_ratio"),
                "pct_from_52h": ind.get("pct_from_52h"),
                "sma20": ind.get("sma20"),
                "sma50": ind.get("sma50"),
                "eps": fund.get("eps"),
                "pe": fund.get("pe"),
                "nav": fund.get("nav"),
                "pb": fund.get("pb"),
                "eps_trend": trend_map.get(ticker),
                "debt_equity": de_map.get(ticker),
            })
        except Exception:
            errors += 1
        if i % 50 == 0:
            print(f"  progress {i}/{len(universe)}")

    rows.sort(key=lambda r: r["combined_score"] or 0, reverse=True)

    with open("full_analysis.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    with open("full_analysis.json", "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2)

    buys = [r for r in rows if r["recommendation"] == "BUY"]
    holds = sum(1 for r in rows if r["recommendation"] == "HOLD")
    sells = sum(1 for r in rows if r["recommendation"] == "SELL")
    print(f"\nDone. {len(rows)} stocks ({errors} errors) -> full_analysis.csv / full_analysis.json")
    print(f"BUY {len(buys)} | HOLD {holds} | SELL {sells}\n")
    print("Top 15 BUY recommendations:")
    for r in buys[:15]:
        print(f"  {r['ticker']:<12} {r['combined_score']:>5}  {r['sector']}")

if __name__ == "__main__":
    main()
