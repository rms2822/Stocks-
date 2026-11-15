"""fetch_live_prices.py -- fetch today's DSE share prices from the CURRENT DSE site.

Why this exists: in 2026 the Dhaka Stock Exchange migrated from the old
dsebd.org website to https://www.dse.com.bd, and the old scraper endpoint
(`latest_share_price_scroll_l.php`) now returns HTTP 410 "Gone". That silently
broke every automated refresh. This module targets the new site.

The new page is server-rendered with a Next.js RSC payload embedded in
`self.__next_f.push([...])` scripts; the per-stock records look like
    {"code":"SQURPHARMA","price":"219.70","change":0.41,"delta":0.90}
(code, last price, % change, absolute change). Volume/high/low are not in that
payload, so those are left blank here -- a known limitation of this source until
the full table/API is wired up.

Usage:  python fetch_live_prices.py [outfile.csv]
Writes dse_latest_prices_<YYYY-MM-DD>.csv by default and prints a summary.
"""
from __future__ import annotations

import csv
import datetime
import re
import sys
import urllib.request

URL = "https://www.dse.com.bd/markets/latest-share-price?view=sector"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.dse.com.bd/",
}

_REC = re.compile(
    r'\{"code":"([A-Z0-9]+)","price":"([\d.]+)","change":(-?[\d.]+),"delta":(-?[\d.]+)\}'
)


def fetch_html(url: str = URL, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def parse_prices(html: str) -> list[dict]:
    """Return [{ticker, ltp, percent_change, change}] from the RSC payload."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    payload = "".join(chunks).encode().decode("unicode_escape", errors="replace")
    out, seen = [], set()
    for code, price, change, delta in _REC.findall(payload):
        if code in seen:
            continue
        seen.add(code)
        out.append({
            "ticker": code,
            "ltp": float(price),
            "percent_change": float(change),
            "change": float(delta),
        })
    return out


def main() -> int:
    today = datetime.date.today().isoformat()
    outfile = sys.argv[1] if len(sys.argv) > 1 else f"dse_latest_prices_{today}.csv"
    try:
        html = fetch_html()
    except Exception as e:
        print(f"[fetch_live_prices] FAILED to reach DSE: {e}", file=sys.stderr)
        return 1
    rows = parse_prices(html)
    if not rows:
        print("[fetch_live_prices] no records parsed -- page format may have changed",
              file=sys.stderr)
        return 1
    with open(outfile, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["ticker", "ltp", "change", "percent_change", "source_date"])
        for r in rows:
            w.writerow([r["ticker"], round(r["ltp"], 2), round(r["change"], 2),
                        round(r["percent_change"], 2), today])
    gainers = sum(1 for r in rows if r["percent_change"] > 0)
    losers = sum(1 for r in rows if r["percent_change"] < 0)
    print(f"[fetch_live_prices] {len(rows)} stocks -> {outfile} "
          f"({gainers} up, {losers} down) as of {today}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
