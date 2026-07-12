"""
app/schemas.py
──────────────
Pydantic response models for all API endpoints.
FastAPI uses these to validate output and generate the /docs UI.
"""

from __future__ import annotations
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


# ── Price history ─────────────────────────────────────────────────────────────

class PriceHistoryOut(BaseModel):
    id:             int
    ticker:         str
    date:           date
    open:           Optional[float]
    high:           Optional[float]
    low:            Optional[float]
    close:          Optional[float]
    ltp:            Optional[float]
    volume:         Optional[float]
    value_mn:       Optional[float]
    trade:          Optional[float]
    change:         Optional[float]
    percent_change: Optional[float]
    scraped_at:     Optional[datetime]

    class Config:
        from_attributes = True


# ── Stock ─────────────────────────────────────────────────────────────────────

class StockOut(BaseModel):
    id:             int
    ticker:         str
    company:        Optional[str]
    sector:         Optional[str]
    ltp:            Optional[float]
    high:           Optional[float]
    low:            Optional[float]
    close:          Optional[float]
    ycp:            Optional[float]
    change:         Optional[float]
    percent_change: Optional[float]
    trade:          Optional[float]
    value_mn:       Optional[float]
    volume:         Optional[float]
    updated_at:     Optional[datetime]
    created_at:     Optional[datetime]

    class Config:
        from_attributes = True


# ── Technical analysis ────────────────────────────────────────────────────────

class IndicatorValuesOut(BaseModel):
    current_price:  float
    prev_close:     Optional[float]

    sma20:          Optional[float]
    sma50:          Optional[float]
    sma200:         Optional[float]
    ema12:          Optional[float]
    ema26:          Optional[float]

    macd:           Optional[float]
    macd_signal:    Optional[float]
    macd_hist:      Optional[float]

    rsi:            Optional[float]

    bb_upper:       Optional[float]
    bb_mid:         Optional[float]
    bb_lower:       Optional[float]
    bb_width:       Optional[float]

    avg_volume_20:  Optional[float]
    current_volume: Optional[float]
    volume_ratio:   Optional[float]

    week52_high:    Optional[float]
    week52_low:     Optional[float]
    pct_from_52h:   Optional[float]


class SignalOut(BaseModel):
    name:       str
    value:      str     # Bullish | Neutral | Bearish
    detail:     str
    weight:     float


class TechnicalAnalysisOut(BaseModel):
    ticker:         str
    current_price:  float
    recommendation: str           # BUY | HOLD | SELL
    score:          float         # 0–100
    data_days:      int
    warning:        Optional[str]
    indicators:     IndicatorValuesOut
    signals:        list[SignalOut]


# ── Load DSE response ─────────────────────────────────────────────────────────

class LoadDSEResponse(BaseModel):
    message:          str
    total_scraped:    int
    stocks_created:   int
    stocks_updated:   int
    history_inserted: int
    history_updated:  int
    skipped:          int


# ── History response ──────────────────────────────────────────────────────────

class HistoryResponse(BaseModel):
    ticker:  str
    company: Optional[str]
    count:   int
    history: list[PriceHistoryOut]


# ── Fundamentals ──────────────────────────────────────────────────────────────

class FundamentalsOut(BaseModel):
    id:              int
    ticker:          str
    eps:             Optional[float] = None
    pe:              Optional[float] = None
    nav:             Optional[float] = None
    paid_up_capital: Optional[float] = None
    dividend:        Optional[float] = None
    roe:             Optional[float] = None
    updated_at:      Optional[datetime] = None

    class Config:
        from_attributes = True


class FundamentalSignalOut(BaseModel):
    name:   str
    value:  str
    detail: str
    weight: float


class FundamentalAnalysisOut(BaseModel):
    ticker:          str
    current_price:   float
    recommendation:  str
    score:           float
    eps:             Optional[float] = None
    pe:              Optional[float] = None
    nav:             Optional[float] = None
    pb:              Optional[float] = None
    dividend_yield:  Optional[float] = None
    roe:             Optional[float] = None
    sector:          Optional[str]   = None
    sector_pe:       Optional[float] = None
    warning:         Optional[str]   = None
    signals:         list[FundamentalSignalOut]


class CombinedAnalysisOut(BaseModel):
    ticker:          str
    current_price:   float
    sector:          Optional[str]   = None
    company:         Optional[str]   = None

    # Final combined recommendation
    recommendation:  str       # BUY | HOLD | SELL
    combined_score:  float     # 0–100
    tech_score:      float
    fund_score:      float

    # Sub-analyses
    technical:    TechnicalAnalysisOut
    fundamental:  FundamentalAnalysisOut

    data_days:    int
    warning:      Optional[str] = None


class LoadFundamentalsResponse(BaseModel):
    message:  str
    total_scraped: int
    updated:  int
    created:  int
    skipped:  int


# ── Screener ──────────────────────────────────────────────────────────────────

class ScreenerResultOut(BaseModel):
    ticker:          str
    company:         Optional[str] = None
    sector:          Optional[str] = None
    ltp:             Optional[float] = None
    eps:             Optional[float] = None
    pe:              Optional[float] = None
    nav:             Optional[float] = None
    market_cap:      Optional[float] = None
    tech_score:      float
    fund_score:      float
    combined_score:  float
    recommendation:  str
    data_days:       int


class ScreenerResponse(BaseModel):
    total:   int
    filters: dict
    results: list[ScreenerResultOut]
