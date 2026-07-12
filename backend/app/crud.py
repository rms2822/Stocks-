import pandas as pd
from datetime import date, datetime
from sqlalchemy.orm import Session
from . import models


# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_float(value) -> float | None:
    """
    Coerce a value to float, handling DSE quirks:
      '2.90-0.10'  →  2.90   (merged cell artifact — take the first number)
      '1,234.50'   →  1234.5  (thousands separator)
      '-' / '--'   →  None   (DSE uses these for missing data)
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).replace(",", "").strip()
    if value in ("-", "--", "N/A", ""):
        return None
    # '25.60-1.20' is a DSE rendering bug where two cells merge
    if "-" in value and not value.startswith("-"):
        value = value.split("-")[0]
    try:
        return float(value)
    except ValueError:
        return None


def _today() -> date:
    return datetime.utcnow().date()


# ── Stock CRUD ────────────────────────────────────────────────────────────────

def create_stock(
    db: Session,
    ticker: str,
    company: str | None = None,
    sector: str  | None = None,
) -> models.Stock:
    """
    Create a new Stock row or update company/sector on an existing one.
    Safe to call multiple times.
    """
    ticker = ticker.upper().strip()
    existing = db.query(models.Stock).filter(
        models.Stock.ticker == ticker
    ).first()

    if existing:
        if company:
            existing.company = company
        if sector:
            existing.sector = sector
        db.commit()
        db.refresh(existing)
        return existing

    stock = models.Stock(ticker=ticker, company=company, sector=sector)
    db.add(stock)
    db.commit()
    db.refresh(stock)
    return stock


def get_stock(db: Session, ticker: str) -> models.Stock | None:
    return db.query(models.Stock).filter(
        models.Stock.ticker == ticker.upper()
    ).first()


def get_all_stocks(db: Session) -> list[models.Stock]:
    return db.query(models.Stock).order_by(models.Stock.ticker).all()


def delete_stock(db: Session, ticker: str) -> bool:
    stock = get_stock(db, ticker)
    if not stock:
        return False
    db.delete(stock)   # cascades to price_history via ondelete="CASCADE"
    db.commit()
    return True


# ── Price history queries ─────────────────────────────────────────────────────

def get_price_history(
    db: Session,
    ticker: str,
    limit: int = 200,
) -> list[models.PriceHistory]:
    """
    Return up to `limit` days of history for a ticker, newest first.
    200 days covers SMA-200. Pass limit=60 for faster indicator runs.
    """
    return (
        db.query(models.PriceHistory)
        .filter(models.PriceHistory.ticker == ticker.upper())
        .order_by(models.PriceHistory.date.desc())
        .limit(limit)
        .all()
    )


def get_price_history_range(
    db: Session,
    ticker: str,
    start: date,
    end: date,
) -> list[models.PriceHistory]:
    """Return history between two dates (inclusive), oldest first."""
    return (
        db.query(models.PriceHistory)
        .filter(
            models.PriceHistory.ticker == ticker.upper(),
            models.PriceHistory.date   >= start,
            models.PriceHistory.date   <= end,
        )
        .order_by(models.PriceHistory.date.asc())
        .all()
    )


# ── DSE bulk save ─────────────────────────────────────────────────────────────

def save_dse_data(df: pd.DataFrame, db: Session) -> dict:
    """
    Process a scraped DataFrame in a single transaction:

      1. Upsert the `stocks` table  — latest snapshot, always overwritten
      2. Upsert `price_history`     — one row per ticker per day, safe to
                                      call multiple times on the same day

    Returns:
        {
            "stocks_created":   int,
            "stocks_updated":   int,
            "history_inserted": int,
            "history_updated":  int,
            "skipped":          int,
        }
    """
    counts = {
        "stocks_created":   0,
        "stocks_updated":   0,
        "history_inserted": 0,
        "history_updated":  0,
        "skipped":          0,
    }

    today = _today()

    # ── 1. Load all existing Stock rows into memory (single query) ────────────
    existing_stocks: dict[str, models.Stock] = {
        s.ticker: s for s in db.query(models.Stock).all()
    }

    # ── 2. Load today's PriceHistory rows into memory (single query) ──────────
    # Knowing which tickers already have a row for today lets us decide
    # INSERT vs UPDATE without issuing a query per ticker.
    todays_history: dict[str, models.PriceHistory] = {
        h.ticker: h
        for h in db.query(models.PriceHistory)
        .filter(models.PriceHistory.date == today)
        .all()
    }

    # ── 3. Walk the DataFrame ─────────────────────────────────────────────────
    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            counts["skipped"] += 1
            continue

        ltp = safe_float(row.get("ltp"))
        if ltp is None:
            # A row with no price has no analysis value — skip it
            counts["skipped"] += 1
            continue

        # Build the shared field dict once (reused for both tables)
        fields = {
            "ltp":            ltp,
            "high":           safe_float(row.get("high")),
            "low":            safe_float(row.get("low")),
            "close":          safe_float(row.get("close")),
            "ycp":            safe_float(row.get("ycp")),
            "change":         safe_float(row.get("change")),
            "percent_change": safe_float(row.get("percent_change")),
            "trade":          safe_float(row.get("trade")),
            "value_mn":       safe_float(row.get("value_mn")),
            "volume":         safe_float(row.get("volume")),
        }

        # ── 3a. Upsert stocks table ───────────────────────────────────────────
        if ticker in existing_stocks:
            stock = existing_stocks[ticker]
            for field, val in fields.items():
                setattr(stock, field, val)
            counts["stocks_updated"] += 1
        else:
            stock = models.Stock(ticker=ticker, **fields)
            db.add(stock)
            existing_stocks[ticker] = stock   # prevent duplicate in same batch
            counts["stocks_created"] += 1

        # ── 3b. Upsert price_history for today ───────────────────────────────
        # `close` is the canonical price for technical indicators.
        # Fall back to `ltp` when close is missing (mid-session scrape).
        canonical_close = fields["close"] or ltp

        history_fields = {
            "open":           None,               # DSE doesn't publish open price
            "high":           fields["high"],
            "low":            fields["low"],
            "close":          canonical_close,
            "ltp":            ltp,
            "volume":         fields["volume"],
            "value_mn":       fields["value_mn"],
            "trade":          fields["trade"],
            "change":         fields["change"],
            "percent_change": fields["percent_change"],
        }

        if ticker in todays_history:
            # Row already exists for today — update in place
            history_row = todays_history[ticker]
            for field, val in history_fields.items():
                setattr(history_row, field, val)
            counts["history_updated"] += 1
        else:
            # First scrape of the day — insert a new row
            history_row = models.PriceHistory(
                ticker=ticker,
                date=today,
                **history_fields,
            )
            db.add(history_row)
            todays_history[ticker] = history_row  # prevent duplicate in same batch
            counts["history_inserted"] += 1

    # ── 4. Single commit covers both tables ───────────────────────────────────
    db.commit()
    return counts


# ── Fundamentals CRUD ─────────────────────────────────────────────────────────

def get_fundamentals(db: Session, ticker: str) -> models.Fundamentals | None:
    return db.query(models.Fundamentals).filter(
        models.Fundamentals.ticker == ticker.upper()
    ).first()


def save_fundamentals(df, db: Session) -> dict:
    """
    Upsert fundamentals from amarstock DataFrame.
    Preserves NAV/dividend/roe if already set (not in amarstock data).
    Returns {updated, created, skipped}
    """
    counts = {"updated": 0, "created": 0, "skipped": 0}

    existing: dict[str, models.Fundamentals] = {
        f.ticker: f for f in db.query(models.Fundamentals).all()
    }

    for _, row in df.iterrows():
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            counts["skipped"] += 1
            continue

        eps = safe_float(row.get("eps"))
        pe  = safe_float(row.get("pe"))

        if eps is None and pe is None:
            counts["skipped"] += 1
            continue

        fields = {
            "eps":             eps,
            "pe":              pe,
            "q1_eps":          safe_float(row.get("q1_eps")),
            "q2_eps":          safe_float(row.get("q2_eps")),
            "q3_eps":          safe_float(row.get("q3_eps")),
            "q4_eps":          safe_float(row.get("q4_eps")),
            "annualized_eps":  safe_float(row.get("annualized_eps")),
            "market_cap":      safe_float(row.get("market_cap")),
            "shares_outstanding": safe_float(row.get("shares_outstanding")),
            "ltp_amarstock":   safe_float(row.get("ltp_amarstock")),
        }
        # Only overwrite sector on Stock if provided
        sector  = str(row.get("sector") or "").strip() or None

        if ticker in existing:
            fund = existing[ticker]
            for field, val in fields.items():
                setattr(fund, field, val)
            # Update sector on the Stock row too
            if sector:
                stock = db.query(models.Stock).filter(models.Stock.ticker == ticker).first()
                if stock and not stock.sector:
                    stock.sector = sector
            counts["updated"] += 1
        else:
            fund = models.Fundamentals(ticker=ticker, **fields)
            db.add(fund)
            existing[ticker] = fund
            if sector:
                stock = db.query(models.Stock).filter(models.Stock.ticker == ticker).first()
                if stock and not stock.sector:
                    stock.sector = sector
            counts["created"] += 1

    db.commit()
    return counts

