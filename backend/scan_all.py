import requests
import json

API = "http://localhost:8000"

stocks = requests.get(f"{API}/stocks").json()
stock_list = stocks.get("stocks", []) if isinstance(stocks, dict) else stocks
tickers = [s["ticker"] for s in stock_list if s.get("ltp", 0) > 0]

print(f"Analyzing {len(tickers)} stocks...")

results = []
errors = 0
for i, ticker in enumerate(tickers):
    try:
        r = requests.get(f"{API}/stocks/{ticker}/analysis/technical", timeout=10)
        if r.status_code == 200:
            d = r.json()
            ind = d.get("indicators", {})
            results.append({
                "ticker": ticker,
                "score": d.get("score", 0),
                "rec": d.get("recommendation", ""),
                "rsi": ind.get("rsi", 0),
                "macd_hist": ind.get("macd_hist", 0),
                "volume_ratio": ind.get("volume_ratio", 0),
                "pct_from_52h": ind.get("pct_from_52h", 0),
                "price": ind.get("current_price", 0),
                "above_sma20": ind.get("current_price", 0) > ind.get("sma20", 999),
                "above_sma50": ind.get("current_price", 0) > ind.get("sma50", 999),
                "above_sma200": ind.get("current_price", 0) > ind.get("sma200", 999),
            })
    except:
        errors += 1
    if (i+1) % 50 == 0:
        print(f"Progress: {i+1}/{len(tickers)}")

print(f"Done. Analyzed {len(results)} stocks, {errors} errors")
results.sort(key=lambda x: x["score"], reverse=True)

with open("tech_analysis_all.json", "w") as f:
    json.dump(results, f, indent=2)
print("Saved to tech_analysis_all.json")

print("\n=== TOP 20 TECHNICAL BUY SIGNALS ===")
buys = [r for r in results if r["rec"] == "BUY"]
for r in buys[:20]:
    print(f"{r['ticker']}: Score={r['score']}, RSI={r['rsi']:.1f}, MACD={r['macd_hist']:.3f}, Vol={r['volume_ratio']:.2f}x, 52H={r['pct_from_52h']:.1f}%")

print("\n=== TOP 20 TECHNICAL SELL SIGNALS ===")
sells = [r for r in results if r["rec"] == "SELL"]
sells.sort(key=lambda x: x["score"])
for r in sells[:20]:
    print(f"{r['ticker']}: Score={r['score']}, RSI={r['rsi']:.1f}, MACD={r['macd_hist']:.3f}, Vol={r['volume_ratio']:.2f}x, 52H={r['pct_from_52h']:.1f}%")

print("\n=== OVERSOLD STOCKS RSI < 30 ===")
oversold = [r for r in results if 0 < r.get("rsi", 100) < 30]
oversold.sort(key=lambda x: x["rsi"])
for r in oversold:
    print(f"{r['ticker']}: RSI={r['rsi']:.1f}, Score={r['score']}, Price={r['price']}")

print("\n=== OVERBOUGHT STOCKS RSI > 70 ===")
overbought = [r for r in results if r.get("rsi", 0) > 70]
overbought.sort(key=lambda x: x["rsi"], reverse=True)
for r in overbought[:15]:
    print(f"{r['ticker']}: RSI={r['rsi']:.1f}, Score={r['score']}, Price={r['price']}")
