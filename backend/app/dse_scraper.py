import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# NOTE (2026): DSE migrated from dsebd.org to www.dse.com.bd. The old endpoint
# `latest_share_price_scroll_l.php` now returns HTTP 410 "Gone", which silently
# broke every refresh. The new page is server-rendered with a Next.js RSC
# payload embedded in `self.__next_f.push([...])` scripts holding per-stock
# records {"code","price","change","delta"}. We parse that. Volume/high/low are
# not in that payload, so they come back as None until the full table is wired.
DSE_URL = "https://www.dse.com.bd/markets/latest-share-price?view=sector"
# Legacy endpoint, retired — kept only for reference:
DSE_URL_LEGACY = "https://www.dsebd.org/latest_share_price_scroll_l.php"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.dse.com.bd/",
}

# Per-stock record shape in the dse.com.bd RSC payload.
_RSC_RECORD = re.compile(
    r'\{"code":"([A-Z0-9]+)","price":"([\d.]+)","change":(-?[\d.]+),"delta":(-?[\d.]+)\}'
)
 
# DSE table column order (from the actual page):
# #  | Trading Code | LTP | High | Low | Closep | YCP | Change | Trade | Value | Volume
COL_INDEX = {
    "ticker":          1,
    "ltp":             2,   # Last Traded Price
    "high":            3,
    "low":             4,
    "close":           5,   # Today's close
    "ycp":             6,   # Yesterday's closing price
    "change":          7,   # Absolute change
    "trade":           8,   # Number of trades
    "value_mn":        9,   # Value in million BDT
    "volume":         10,   # Volume (shares)
}
 
 
def _safe_float(value: str) -> float | None:
    """
    Convert messy DSE strings to float.
    Handles cases like '2.90-0.10' (merged cells), '1,234.50', '-', '--'.
    """
    if not value or value.strip() in ("-", "--", ""):
        return None
    # Strip commas (thousands separator)
    value = value.replace(",", "").strip()
    # Some cells merge price and change: '25.60-1.20' — take the first number
    if value.count("-") > 0 and not value.startswith("-"):
        value = value.split("-")[0]
    try:
        return float(value)
    except ValueError:
        return None
 
 
def _parse_percent(value: str) -> str | None:
    """Return the percent string as-is (e.g. '-2.50%'), or None if empty."""
    value = value.strip()
    return value if value not in ("", "-", "--") else None
 
 
def fetch_dse_data() -> pd.DataFrame:
    """
    Scrape latest share prices from DSE and return a clean DataFrame.
 
    Columns returned:
        ticker, ltp, high, low, close, ycp,
        change, percent_change, trade, value_mn, volume
 
    Raises:
        requests.HTTPError  – if DSE returns a non-200 response
        ValueError          – if the expected table is not found in the page
    """
    response = requests.get(DSE_URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    # Reconstruct the Next.js RSC streamed payload and pull per-stock records.
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', response.text)
    payload = "".join(chunks).encode().decode("unicode_escape", errors="replace")

    stocks, seen = [], set()
    for code, price, change_pct, delta in _RSC_RECORD.findall(payload):
        if code in seen:
            continue
        seen.add(code)
        ltp = _safe_float(price)
        pct = _safe_float(change_pct)
        change = _safe_float(delta)
        ycp = round(ltp - change, 2) if (ltp is not None and change is not None) else None
        stocks.append({
            "ticker":         code,
            "ltp":            ltp,
            "high":           None,   # not exposed by the new RSC feed
            "low":            None,
            "close":          ltp,
            "ycp":            ycp,
            "change":         change,
            "percent_change": pct,
            "trade":          None,
            "value_mn":       None,
            "volume":         None,
        })

    if not stocks:
        raise ValueError(
            "Scraped 0 stocks from dse.com.bd — the RSC payload format may have "
            "changed. Check _RSC_RECORD in dse_scraper.py against the live page."
        )

    df = pd.DataFrame(stocks)
    logger.info("Fetched %d stocks from DSE (%s)", len(df), DSE_URL)
    return df