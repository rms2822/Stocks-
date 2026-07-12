import requests
import sqlite3
from datetime import datetime

API = "http://localhost:8000"

def get(path):
    try:
        return requests.get(API + path, timeout=10).json()
    except:
        return None

def divider(title=""):
    if title:
        print(f"\n{'='*20} {title} {'='*20}")
    else:
        print("="*60)

def fmt(n, prefix=""):
    if n is None: return "-"
    return f"{prefix}{n:,.2f}"

print()
print("╔══════════════════════════════════════════════════════════╗")
print("║           DSE MORNING BRIEFING                          ║")
print(f"║           {datetime.now().strftime('%A, %d %B %Y  %I:%M %p'):<46}║")
print("╚══════════════════════════════════════════════════════════╝")

# ── 1. Market Overview ──────────────────────────────────────────
divider("MARKET OVERVIEW")
stocks = get("/stocks")
stock_list = stocks.get("stocks", []) if stocks else []

gainers = [s for s in stock_list if s.get("percent_change") and s["percent_change"] > 0]
losers  = [s for s in stock_list if s.get("percent_change") and s["percent_change"] < 0]
unchanged = [s for s in stock_list if s.get("percent_change") == 0]
total_value = sum(s.get("value_mn", 0) or 0 for s in stock_list)

print(f"  Total stocks    : {len(stock_list)}")
print(f"  Advancing       : {len(gainers)} stocks")
print(f"  Declining       : {len(losers)} stocks")
print(f"  Unchanged       : {len(unchanged)} stocks")
print(f"  Market breadth  : {'Bullish' if len(gainers) > len(losers) else 'Bearish'}")
print(f"  Total turnover  : BDT {total_value:,.1f} mn")

# ── 2. Top Gainers & Losers ─────────────────────────────────────
divider("TOP 5 GAINERS")
top_gainers = sorted(gainers, key=lambda x: x["percent_change"], reverse=True)[:5]
for s in top_gainers:
    print(f"  {s['ticker']:<12} BDT {s['ltp']:<8.1f} +{s['percent_change']:.2f}%  Vol: {s.get('volume',0):,.0f}")

divider("TOP 5 LOSERS")
top_losers = sorted(losers, key=lambda x: x["percent_change"])[:5]
for s in top_losers:
    print(f"  {s['ticker']:<12} BDT {s['ltp']:<8.1f} {s['percent_change']:.2f}%  Vol: {s.get('volume',0):,.0f}")

# ── 3. Screener Opportunities ───────────────────────────────────
divider("TOP BUY OPPORTUNITIES")
screener = get("/screener?profitable_only=true&max_pe=15&limit=8&recommendation=BUY")
results = screener.get("results", []) if screener else []
print(f"  {'Ticker':<12} {'Price':>7} {'PE':>6} {'P/B':>5} {'Score':>6} {'Sector'}")
print(f"  {'-'*65}")
for s in results:
    nav = s.get("nav")
    ltp = s.get("ltp") or 0
    pb = round(ltp/nav, 2) if nav and nav > 0 else None
    print(f"  {s['ticker']:<12} {ltp:>7.1f} {s.get('pe') or 0:>6.1f} {str(pb or '-'):>5} {s.get('combined_score',0):>6.1f}  {(s.get('sector') or '')[:20]}")

# ── 4. Oversold Stocks ──────────────────────────────────────────
divider("OVERSOLD STOCKS (RSI < 30) - Potential Bounce")
conn = sqlite3.connect("dse.db")
cur = conn.cursor()
try:
    import json
    with open("tech_analysis_all.json") as f:
        tech = json.load(f)
    oversold = [t for t in tech if 0 < t.get("rsi", 100) < 30]
    oversold.sort(key=lambda x: x["rsi"])
    for t in oversold[:5]:
        cur.execute("SELECT ltp, sector FROM stocks WHERE ticker=?", (t["ticker"],))
        row = cur.fetchone()
        ltp = row[0] if row else 0
        sector = (row[1] or "")[:15] if row else ""
        rec = t.get("rec", "?")
        warning = " ⚠ SELL-rated" if rec == "SELL" else ""
        print(f"  {t['ticker']:<12} RSI={t['rsi']:.1f}  Price=BDT {ltp:.1f}  Score={t.get('score',0):.0f}  Rec={rec}{warning}")
    if not oversold:
        print("  No stocks currently oversold")
except:
    print("  Run scan_all.py to get RSI data")

# ── 5. Overbought Warning ───────────────────────────────────────
divider("OVERBOUGHT STOCKS (RSI > 75) - Avoid Chasing")
try:
    overbought = [t for t in tech if t.get("rsi", 0) > 75]
    overbought.sort(key=lambda x: x["rsi"], reverse=True)
    for t in overbought[:5]:
        cur.execute("SELECT ltp FROM stocks WHERE ticker=?", (t["ticker"],))
        row = cur.fetchone()
        ltp = row[0] if row else 0
        print(f"  {t['ticker']:<12} RSI={t['rsi']:.1f}  Price=BDT {ltp:.1f}  Score={t.get('score',0):.0f}")
except:
    print("  Run scan_all.py to get RSI data")

# ── 6. Portfolio Status ─────────────────────────────────────────
divider("PORTFOLIO STATUS")
portfolio = get("/portfolio/analysis")
if portfolio and "summary" in portfolio:
    s = portfolio["summary"]
    pl = s.get("total_pl", 0)
    pct = s.get("total_pl_pct", 0)
    sign = "+" if pl >= 0 else ""
    print(f"  Invested        : BDT {s.get('total_invested',0):,.0f}")
    print(f"  Current Value   : BDT {s.get('total_value',0):,.0f}")
    print(f"  Total P&L       : {sign}BDT {abs(pl):,.0f} ({sign}{pct:.2f}%)")
    print(f"  Holdings        : {s.get('holdings_count',0)} stocks")
    print(f"  Avg Score       : {s.get('avg_score',0):.1f}/100")

    holdings = portfolio.get("hold",[]) + portfolio.get("buy_more",[]) + portfolio.get("sell_suggestions",[])
    if holdings:
        print(f"\n  {'Ticker':<12} {'Buy':>7} {'Now':>7} {'P&L%':>7} {'Signal'}")
        print(f"  {'-'*50}")
        for h in holdings:
            pl_pct = h.get("pl_pct", 0)
            sign = "+" if pl_pct >= 0 else ""
            print(f"  {h['ticker']:<12} {h['buy_price']:>7.1f} {h['current_price']:>7.1f} {sign}{pl_pct:>6.2f}%  {h['recommendation']}")

    sell = portfolio.get("sell_suggestions", [])
    if sell:
        print(f"\n  ⚠ SELL ALERTS:")
        for h in sell:
            print(f"    {h['ticker']}: Score={h['score']:.0f}, P&L={h['pl_pct']:.1f}%")
else:
    print("  Portfolio is empty")

# ── 7. Today's Action Plan ──────────────────────────────────────
divider("TODAY'S ACTION PLAN")
print("  1. Check stop losses on all holdings before market opens")
print("  2. DSE opens at 10:30 AM - first 30 min is volatile, avoid trading")
print("  3. Best entry window: 11:00 AM - 12:30 PM")
print("  4. Set alerts for oversold stocks if RSI crosses back above 30")
print("  5. Market closes at 2:30 PM - data auto-updates at 3:00 PM")

conn.close()
divider()
print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"  Next auto-update: Today 3:00 PM BST")
divider()
