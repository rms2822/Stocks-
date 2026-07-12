import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
 
logger = logging.getLogger(__name__)
 
DSE_URL = "https://www.dsebd.org/latest_share_price_scroll_l.php"
 
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.dsebd.org/",
}
 
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
    response = requests.get(DSE_URL, headers=HEADERS, timeout=15)
    response.raise_for_status()
 
    soup = BeautifulSoup(response.text, "html.parser")
 
    # The data lives in <table class="table table-bordered ...">
    # Fall back to any <table> if the class changes.
    table = (
        soup.find("table", {"class": lambda c: c and "table" in c})
        or soup.find("table")
    )
    if table is None:
        raise ValueError("Could not find the stock data table on the DSE page.")
 
    stocks = []
    rows = table.find_all("tr")
 
    for row in rows[1:]:   # skip header row
        cols = row.find_all("td")
        if len(cols) < 10:
            continue
 
        def cell(idx: int) -> str:
            return cols[idx].get_text(strip=True).replace("\xa0", "")
 
        ticker = cell(COL_INDEX["ticker"])
        if not ticker:
            continue
 
        # Percent change is usually the last column (index 11) or second-to-last
        # We compute it ourselves to be safe
        ltp    = _safe_float(cell(COL_INDEX["ltp"]))
        ycp    = _safe_float(cell(COL_INDEX["ycp"]))
        change = _safe_float(cell(COL_INDEX["change"]))
 
        percent_change: float | None = None
        if change is not None and ycp and ycp != 0:
            percent_change = round(change / ycp * 100, 2)
 
        stocks.append({
            "ticker":         ticker,
            "ltp":            ltp,
            "high":           _safe_float(cell(COL_INDEX["high"])),
            "low":            _safe_float(cell(COL_INDEX["low"])),
            "close":          _safe_float(cell(COL_INDEX["close"])),
            "ycp":            ycp,
            "change":         change,
            "percent_change": percent_change,
            "trade":          _safe_float(cell(COL_INDEX["trade"])),
            "value_mn":       _safe_float(cell(COL_INDEX["value_mn"])),
            "volume":         _safe_float(cell(COL_INDEX["volume"])),
        })
 
    if not stocks:
        raise ValueError(
            "Scraped 0 stocks — the page structure may have changed. "
            "Check COL_INDEX in dse_scraper.py against the live page."
        )
 
    df = pd.DataFrame(stocks)
    logger.info("Fetched %d stocks from DSE", len(df))
    return df