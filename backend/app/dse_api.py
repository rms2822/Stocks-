"""app/dse_api.py -- client for the current DSE data API (www.dse.com.bd).

In 2026 DSE migrated off dsebd.org. The new site exposes a JSON "day-end
archive" endpoint that returns full OHLCV (with volume, value, trades) both for
the latest trading day (all instruments) and for a date range per instrument:

    GET /api/live/data-archive/day-end?from=<YYYY-MM-DD>&to=<YYYY-MM-DD>&inst=<CODE>&page=<n>
    -> {"rows":[{date,tradingCode,ltp,high,low,openp,closep,ycp,trade,value,volume}],
        "total":N,"page":p,"pageSize":500}

This module is the single source of truth for DSE market data; dse_scraper and
history_loader both delegate here so there is one place to maintain when the
site changes again.
"""
from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE = "https://www.dse.com.bd"
DAY_END = "/api/live/data-archive/day-end"
PAGE_SIZE = 500

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.dse.com.bd/",
}


def _get(params: dict, retries: int = 3, pause: float = 0.3, timeout: int = 20) -> dict:
    last = None
    for attempt in range(retries):
        try:
            r = requests.get(BASE + DAY_END, params=params, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(pause * (attempt + 1))
    raise RuntimeError(f"DSE API GET failed ({params}): {last}")


def day_end_rows(start: str, end: str, code: Optional[str] = None) -> list[dict]:
    """Return every day-end row for the range (all pages). `code` limits to one instrument."""
    base = {"from": start, "to": end}
    if code:
        base["inst"] = code.upper()
    first = _get(base)
    rows = list(first.get("rows") or [])
    total = first.get("total") or len(rows)
    size = first.get("pageSize") or PAGE_SIZE
    pages = (total + size - 1) // size if size else 1
    for p in range(2, pages + 1):
        rows.extend(_get({**base, "page": p}).get("rows") or [])
    return rows


def _latest_trading_day(max_lookback: int = 7) -> str:
    """Most recent date that actually has rows (handles weekends/holidays)."""
    today = _dt.date.today()
    start = (today - _dt.timedelta(days=max_lookback)).isoformat()
    rows = day_end_rows(start, today.isoformat(), code="SQURPHARMA")  # liquid probe
    dates = sorted({r["date"] for r in rows})
    return dates[-1] if dates else today.isoformat()


def latest_prices():
    """All instruments for the latest trading day, as a DataFrame matching the
    legacy dse_scraper contract: ticker, ltp, high, low, close, ycp, change,
    percent_change, trade, value_mn, volume."""
    import pandas as pd

    day = _latest_trading_day()
    rows = day_end_rows(day, day)
    out = []
    for r in rows:
        ltp, ycp = r.get("ltp"), r.get("ycp")
        change = round(ltp - ycp, 2) if (ltp is not None and ycp is not None) else None
        pct = round(change / ycp * 100, 2) if (change is not None and ycp) else None
        out.append({
            "ticker":         r["tradingCode"],
            "ltp":            ltp,
            "high":           r.get("high"),
            "low":            r.get("low"),
            "close":          r.get("closep"),
            "ycp":            ycp,
            "change":         change,
            "percent_change": pct,
            "trade":          r.get("trade"),
            "value_mn":       r.get("value"),
            "volume":         r.get("volume"),
        })
    df = pd.DataFrame(out)
    logger.info("DSE latest_prices: %d instruments for %s", len(df), day)
    return df


def history(code: str, start: _dt.date, end: _dt.date):
    """Daily OHLCV for one ticker as a DataFrame indexed by date, with columns
    open/high/low/close/ltp/volume/value/trade/ycp/change (history_loader schema)."""
    import pandas as pd

    rows = day_end_rows(start.isoformat(), end.isoformat(), code=code)
    recs = []
    for r in rows:
        ltp, ycp = r.get("ltp"), r.get("ycp")
        recs.append({
            "date":   r["date"],
            "open":   r.get("openp"),
            "high":   r.get("high"),
            "low":    r.get("low"),
            "close":  r.get("closep"),
            "ltp":    ltp,
            "volume": r.get("volume"),
            "value":  r.get("value"),
            "trade":  r.get("trade"),
            "ycp":    ycp,
            "change": round(ltp - ycp, 2) if (ltp is not None and ycp is not None) else None,
        })
    if not recs:
        return pd.DataFrame()
    df = pd.DataFrame(recs)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()
