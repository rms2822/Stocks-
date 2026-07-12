from sqlalchemy import (
    Column, Integer, String, Float,
    DateTime, Date, UniqueConstraint, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .database import Base


class Stock(Base):
    __tablename__ = "stocks"

    id      = Column(Integer, primary_key=True, index=True)

    # Identity
    ticker  = Column(String, unique=True, index=True, nullable=False)
    company = Column(String, nullable=True)
    sector  = Column(String, nullable=True)

    # Legacy column â€” kept so old DBs don't break before migration.
    # New code uses `ltp`. migrate_db.py copies price â†’ ltp.
    price   = Column(Float, nullable=True)

    # Latest snapshot (overwritten on every /load-dse call)
    ltp             = Column(Float, nullable=True)   # Last Traded Price
    high            = Column(Float, nullable=True)
    low             = Column(Float, nullable=True)
    close           = Column(Float, nullable=True)
    ycp             = Column(Float, nullable=True)   # Yesterday's closing price
    change          = Column(Float, nullable=True)
    percent_change  = Column(Float, nullable=True)
    trade           = Column(Float, nullable=True)   # Number of trades
    value_mn        = Column(Float, nullable=True)   # Traded value (million BDT)
    volume          = Column(Float, nullable=True)

    # Housekeeping
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship â€” lets you do stock.history to get all PriceHistory rows
    history = relationship(
        "PriceHistory",
        back_populates="stock",
        order_by="PriceHistory.date",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Stock ticker={self.ticker} ltp={self.ltp}>"


class PriceHistory(Base):
    """
    One row per (ticker, date).

    Populated automatically on every /load-dse call.
    Use `close` as the canonical daily price for technical indicators
    (RSI, MACD, SMA, etc.) â€” it is the official end-of-day price.
    `ltp` is also stored because intraday calls may land before the
    official close is published, giving you the last trade at that moment.

    UniqueConstraint on (ticker, date) means:
      - First scrape of the day  â†’ INSERT
      - Any later scrape same day â†’ UPDATE (upsert)
    so you can call /load-dse as often as you like without duplicates.
    """
    __tablename__ = "price_history"

    id      = Column(Integer, primary_key=True, index=True)
    ticker  = Column(
        String,
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    date    = Column(Date, nullable=False)   # calendar date only, no time component

    # OHLCV â€” mirrors the DSE scraper columns
    open    = Column(Float, nullable=True)   # DSE doesn't publish open; always None for now
    high    = Column(Float, nullable=True)
    low     = Column(Float, nullable=True)
    close   = Column(Float, nullable=True)   # official close â€” use this for indicators
    ltp     = Column(Float, nullable=True)   # last traded price at time of scrape
    volume  = Column(Float, nullable=True)
    value_mn = Column(Float, nullable=True)  # traded value in million BDT
    trade   = Column(Float, nullable=True)   # number of trades
    change  = Column(Float, nullable=True)
    percent_change = Column(Float, nullable=True)

    scraped_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship back to Stock
    stock = relationship("Stock", back_populates="history")

    # (ticker, date) must be unique â€” enforces one row per stock per day
    __table_args__ = (
        UniqueConstraint("ticker", "date", name="uq_price_history_ticker_date"),
        Index("ix_price_history_ticker_date", "ticker", "date"),
    )

    def __repr__(self):
        return f"<PriceHistory ticker={self.ticker} date={self.date} close={self.close}>"


class Fundamentals(Base):
    """
    One row per ticker â€” updated on every POST /load-fundamentals call.
    Source: amarstock.com/market-pe (single API call for all ~400 stocks)
    """
    __tablename__ = "fundamentals"

    id      = Column(Integer, primary_key=True, index=True)
    ticker  = Column(
        String,
        ForeignKey("stocks.ticker", ondelete="CASCADE"),
        unique=True,
        nullable=False,
        index=True,
    )

    # Core fundamentals
    eps              = Column(Float, nullable=True)
    pe               = Column(Float, nullable=True)
    nav              = Column(Float, nullable=True)

    # Quarterly EPS
    q1_eps           = Column(Float, nullable=True)
    q2_eps           = Column(Float, nullable=True)
    q3_eps           = Column(Float, nullable=True)
    q4_eps           = Column(Float, nullable=True)
    annualized_eps   = Column(Float, nullable=True)

    # Market data
    market_cap          = Column(Float, nullable=True)
    shares_outstanding  = Column(Float, nullable=True)
    ltp_amarstock       = Column(Float, nullable=True)

    # Manually enriched
    paid_up_capital  = Column(Float, nullable=True)
    dividend         = Column(Float, nullable=True)
    roe              = Column(Float, nullable=True)
    eps_2021         = Column(Float, nullable=True)
    eps_2022         = Column(Float, nullable=True)
    eps_2023         = Column(Float, nullable=True)
    eps_2024         = Column(Float, nullable=True)
    eps_2025         = Column(Float, nullable=True)
    nav_2021         = Column(Float, nullable=True)
    nav_2022         = Column(Float, nullable=True)
    nav_2023         = Column(Float, nullable=True)
    nav_2024         = Column(Float, nullable=True)
    nav_2025         = Column(Float, nullable=True)
    eps_trend        = Column(Float, nullable=True)

    # DSE scraped data
    nav_year         = Column(String, nullable=True)
    eps_dse          = Column(Float, nullable=True)
    short_term_debt_mn = Column(Float, nullable=True)
    long_term_debt_mn  = Column(Float, nullable=True)
    total_debt_mn    = Column(Float, nullable=True)
    sponsor_holding  = Column(Float, nullable=True)
    govt_holding     = Column(Float, nullable=True)
    institute_holding = Column(Float, nullable=True)
    foreign_holding  = Column(Float, nullable=True)
    public_holding   = Column(Float, nullable=True)
    debt_equity      = Column(Float, nullable=True)
    pb_ratio         = Column(Float, nullable=True)

    # Housekeeping
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Fundamentals ticker={self.ticker} eps={self.eps} pe={self.pe}>"


class Portfolio(Base):
    __tablename__ = "portfolio"
    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, nullable=False)
    buy_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    added_at = Column(String, default="")

