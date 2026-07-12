import requests
import json
import sqlite3
import time

API = "http://localhost:8000"

# Get all stocks
stocks = requests.get(f"{API}/stocks").json()["stocks"]
print(f"Total stocks: {len(stocks)}")

conn = sqlite3.connect("dse.db")
cur = conn.cursor()

results = []
failed = 0

for i, stock in enumerate(stocks):
    ticker = stock["ticker"]
    try:
        r = requests.get(f"{API}/stocks/{ticker}/analysis", timeout=15).json()
        results.append({
            "ticker": ticker,
            "sector": stock.get("sector"),
            "ltp": stock.get("ltp"),
            "percent_change": stock.get("percent_change"),
            "volume": stock.get("volume"),
            "combined_score": r.get("combined_score"),
            "tech_score": r.get("tech_score"),
            "fund_score": r.get("fund_score"),
            "recommendation": r.get("recommendation"),
            "rsi": r.get("technical", {}).get("indicators", {}).get("rsi"),
            "macd_hist": r.get("technical", {}).get("indicators", {}).get("macd_hist"),
            "volume_ratio": r.get("technical", {}).get("indicators", {}).get("volume_ratio"),
            "pct_from_52h": r.get("technical", {}).get("indicators", {}).get("pct_from_52h"),
            "sma20": r.get("technical", {}).get("indicators", {}).get("sma20"),
            "sma50": r.get("technical", {}).get("indicators", {}).get("sma50"),
            "eps": r.get("fundamental", {}).get("eps"),
            "pe": r.get("fundamental", {}).get("pe"),
            "nav": r.get("fundamental", {}).get("nav"),
            "pb": r.get("fundamental", {}).get("pb"),
            "eps_trend": None,
            "debt_equity": None,
        })
        # Get eps_trend and D/E from DB
        cur.execute("SELECT eps_trend, total_debt_mn, shares_outstanding, nav FROM fundamentals WHERE ticker=?", (ticker,))
        row = cur.fetchone()
        if row:
            results[-1]["eps_trend"] = row[0]
            if row[1] and row[2] and row[3] and row[2] > 0 and row[3] > 0:
                equity = row[2] * row[3] / 1_000_000
                results[-1]["debt_equity"] = round(row[1] / equity, 2) if equity > 0 else None

    except Exception as e:
        failed += 1

    if (i+1) % 50 == 0:
        print(f"Progress: {i+1}/{len(stocks)} | Failed: {failed}")

conn.close()

# Save to JSON
with open("full_analysis.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)

# Save to CSV for easy viewing
import csv
with open("full_analysis.csv", "w", newline="", encoding="utf-8") as f:
    if results:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

print(f"\nDone! {len(results)} stocks analyzed, {failed} failed")
print(f"Saved to full_analysis.json and full_analysis.csv")
