"""
app/history_loader.py
─────────────────────
Backfills historical OHLCV data for all DSE stocks using bdshare.

Usage:
    POST /load-history?days=365          — backfill 1 year for all stocks
    POST /load-history?days=365&ticker=ACI — single stock only

bdshare handles retries, rate limiting, and DSE scraping internally.
We just loop through tickers, fetch, and upsert into price_history.
"""

import pandas as pd
import logging
import time
from datetime import date, timedelta, datetime
from typing import Optional

logger = logging.getLogger(__name__)


def _safe_float(value) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(str(value).replace(",", "").strip())
        return None if v != v else v   # filter NaN
    except (ValueError, TypeError):
        return None


def fetch_historical(ticker: str, start: date, end: date) -> pd.DataFrame:
    """
    Fetch historical daily OHLCV for one ticker using bdshare.
    Returns empty DataFrame on failure.
    """
    try:
        from bdshare import get_historical_data
        df = get_historical_data(
            start.strftime("%Y-%m-%d"),
            end.strftime("%Y-%m-%d"),
            ticker.upper(),
        )
        return df if df is not None and not df.empty else pd.DataFrame()
    except Exception as e:
        logger.debug("bdshare failed for %s: %s", ticker, e)
        return pd.DataFrame()


def load_history_for_ticker(
    ticker: str,
    start: date,
    end: date,
    db,
    existing_dates: Optional[set] = None,
) -> dict:
    """
    Fetch and upsert price history for a single ticker.
    Returns {"inserted": int, "updated": int, "skipped": int}
    """
    from . import models

    counts = {"inserted": 0, "updated": 0, "skipped": 0}

    df = fetch_historical(ticker, start, end)
    if df.empty:
        counts["skipped"] += 1
        return counts

    # Load existing dates for this ticker if not provided
    if existing_dates is None:
        existing_rows = (
            db.query(models.PriceHistory.date)
            .filter(models.PriceHistory.ticker == ticker.upper())
            .all()
        )
        existing_dates = {r.date for r in existing_rows}

    for row_date, row in df.iterrows():
        # row_date is the index (a date or datetime)
        if hasattr(row_date, "date"):
            row_date = row_date.date()
        elif isinstance(row_date, str):
            try:
                row_date = datetime.strptime(row_date, "%Y-%m-%d").date()
            except ValueError:
                continue

        close  = _safe_float(row.get("close"))
        ltp    = _safe_float(row.get("ltp"))
        canon  = close or ltp
        if canon is None:
            continue

        fields = {
            "open":           _safe_float(row.get("open")),
            "high":           _safe_float(row.get("high")),
            "low":            _safe_float(row.get("low")),
            "close":          canon,
            "ltp":            ltp,
            "volume":         _safe_float(row.get("volume")),
            "value_mn":       _safe_float(row.get("value")),
            "trade":          _safe_float(row.get("trade")),
            "change":         _safe_float(row.get("change") if "change" in row.index else None),
            "percent_change": None,
        }

        # Compute percent_change from ycp if available
        ycp = _safe_float(row.get("ycp"))
        if ycp and ycp != 0 and fields["close"]:
            fields["percent_change"] = round(
                (fields["close"] - ycp) / ycp * 100, 2
            )

        if row_date in existing_dates:
            # Update existing row
            hist_row = (
                db.query(models.PriceHistory)
                .filter(
                    models.PriceHistory.ticker == ticker.upper(),
                    models.PriceHistory.date   == row_date,
                )
                .first()
            )
            if hist_row:
                for field, val in fields.items():
                    if val is not None:
                        setattr(hist_row, field, val)
                counts["updated"] += 1
        else:
            hist_row = models.PriceHistory(
                ticker = ticker.upper(),
                date   = row_date,
                **fields,
            )
            db.add(hist_row)
            existing_dates.add(row_date)
            counts["inserted"] += 1

    db.commit()
    return counts


def bulk_load_history(
    tickers: list[str],
    days: int = 365,
    db = None,
    pause: float = 0.5,
) -> dict:
    """
    Backfill history for a list of tickers.

    Args:
        tickers:  list of DSE trading codes
        days:     how many calendar days back to fetch
        db:       SQLAlchemy session
        pause:    seconds between requests (bdshare has built-in rate limiting
                  but an extra pause avoids hammering DSE)

    Returns summary dict.
    """
    end   = date.today()
    start = end - timedelta(days=days)

    total   = len(tickers)
    summary = {"total_tickers": total, "inserted": 0, "updated": 0, "skipped": 0, "failed": 0}

    logger.info(
        "Backfilling %d days of history for %d tickers (%s → %s)...",
        days, total, start, end,
    )

    for i, ticker in enumerate(tickers, 1):
        try:
            counts = load_history_for_ticker(ticker, start, end, db)
            summary["inserted"] += counts["inserted"]
            summary["updated"]  += counts["updated"]
            summary["skipped"]  += counts["skipped"]

            if i % 20 == 0 or i == total:
                logger.info(
                    "  Progress: %d/%d | inserted=%d updated=%d failed=%d",
                    i, total,
                    summary["inserted"],
                    summary["updated"],
                    summary["failed"],
                )
        except Exception as e:
            logger.warning("Failed for %s: %s", ticker, e)
            summary["failed"] += 1

        if i < total:
            time.sleep(pause)

    return summary
