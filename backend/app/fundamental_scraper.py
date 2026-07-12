"""
app/fundamental_scraper.py
──────────────────────────
Fetches EPS, P/E, and sector for all DSE stocks from amarstock.com.

Endpoint:  GET https://www.amarstock.com/market-pe
Response:  { "scripPEDataList": [ { "Scrip": "ACI", "Eps": -7.4, "PE": -33.3, ... } ] }

Confirmed field names from live data (2026-05-24):
    Scrip             — DSE trading code
    Eps               — Reported EPS (annual, BDT) — USE THIS
    AnnualizedEPS     — Annualized estimate — less reliable
    Q1Eps..Q4Eps      — Quarterly EPS breakdown
    PE                — P/E ratio (negative when loss-making)
    WeightedPE        — Market-cap weighted PE
    BusinessSegment   — Sector name
    LTP               — Last traded price
    MarketCapital     — Market cap in BDT
    TotalSecurities   — Shares outstanding

NAV is not available on this endpoint — left as None.
"""

import requests
import pandas as pd
import logging
import time

logger = logging.getLogger(__name__)

API_URL = "https://www.amarstock.com/market-pe"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":  "en-US,en;q=0.9",
    "X-Requested-With": "XMLHttpRequest",
    "Referer":          "https://www.amarstock.com/market-pe-ratio",
}


def _safe_float(value) -> float | None:
    """Parse a value to float; return None on failure or NaN.
    NOTE: this does NOT null out zeros — use _zero_to_none() for fields where
    amarstock uses 0 as a 'no data' placeholder (EPS, PE, LTP, etc.)."""
    if value is None:
        return None
    try:
        v = float(str(value).replace(",", "").strip())
        return v if v == v else None   # filter NaN
    except (ValueError, TypeError):
        return None


def _zero_to_none(value) -> float | None:
    """Convert 0 to None — amarstock uses 0 as a missing value placeholder."""
    v = _safe_float(value)
    if v == 0.0:
        return None
    return v


def fetch_pe_data(timeout: int = 60, retries: int = 3) -> pd.DataFrame:
    """
    Fetch EPS, P/E, sector for all DSE stocks from amarstock.

    Returns DataFrame with columns:
        ticker, eps, pe, nav, sector, company,
        q1_eps, q2_eps, q3_eps, q4_eps,
        market_cap, shares_outstanding, ltp_from_amarstock

    Raises ConnectionError if all retries fail.
    """
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            logger.info(
                "Fetching fundamentals from amarstock (attempt %d/%d)...",
                attempt, retries
            )

            resp = requests.get(API_URL, headers=HEADERS, timeout=timeout)
            resp.raise_for_status()

            data  = resp.json()
            items = data.get("scripPEDataList") or []

            if not items:
                raise ValueError(
                    f"scripPEDataList missing or empty. "
                    f"Response keys: {list(data.keys())}"
                )

            rows = []
            for item in items:
                ticker = str(item.get("Scrip") or "").strip().upper()
                if not ticker:
                    continue

                # Eps is annual reported EPS.
                # amarstock reports a MISSING eps as 0, so map 0 -> None
                # (a real loss arrives as a NEGATIVE eps and is preserved).
                eps = _zero_to_none(item.get("Eps"))

                # Raw PE from AmarStock
                pe = _zero_to_none(item.get("PE"))

                # AmarStock LTP
                ltp = _zero_to_none(item.get("LTP"))

                # Fallback: derive PE if missing
                if pe is None and eps is not None and eps > 0 and ltp is not None:
                    pe = round(ltp / eps, 2)

                rows.append({
                    "ticker":              ticker,
                    "eps":                 eps,
                    "pe":                  pe,
                    "nav":                 None,   # not available on this endpoint
                    "sector":              str(item.get("BusinessSegment") or "").strip() or None,
                    "company":             None,   # not in this response
                    "q1_eps":              _zero_to_none(item.get("Q1Eps")),
                    "q2_eps":              _zero_to_none(item.get("Q2Eps")),
                    "q3_eps":              _zero_to_none(item.get("Q3Eps")),
                    "q4_eps":              _zero_to_none(item.get("Q4Eps")),
                    "annualized_eps":      _zero_to_none(item.get("AnnualizedEPS")),
                    "market_cap":          _zero_to_none(item.get("MarketCapital")),
                    "shares_outstanding":  _zero_to_none(item.get("TotalSecurities")),
                    "ltp_amarstock":       ltp,
                })

            df = pd.DataFrame(rows)
            logger.info(
                "Fetched %d stocks. %d have EPS, %d have PE.",
                len(df),
                df["eps"].notna().sum(),
                df["pe"].notna().sum(),
            )
            return df

        except requests.Timeout as e:
            last_error = e
            logger.warning(
                "Attempt %d/%d timed out. %s",
                attempt, retries,
                "Retrying in 5s..." if attempt < retries else "Giving up."
            )
            if attempt < retries:
                time.sleep(5)

        except ValueError as e:
            raise   # don't retry parsing errors

        except Exception as e:
            last_error = e
            logger.warning("Attempt %d/%d failed: %s", attempt, retries, e)
            if attempt < retries:
                time.sleep(3)

    raise ConnectionError(
        f"Failed to fetch fundamentals after {retries} attempts. "
        f"Last error: {last_error}"
    )
