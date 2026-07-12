"""
app/analysis/technical.py
─────────────────────────
Pure-Python technical analysis — no pandas, no ta-lib dependency.
Takes a list of PriceHistory ORM rows and returns a TechnicalResult.
 
Indicators computed:
    SMA   — 20, 50, 200 day simple moving averages
    EMA   — 12, 26 day exponential moving averages
    MACD  — MACD line, signal line (9-day EMA of MACD), histogram
    RSI   — 14-period Wilder RSI
    BB    — 20-day Bollinger Bands (±2 std dev)
    VWAP  — Volume-weighted average price (rolling 20 days)
 
Scoring (0–100):
    Each indicator contributes a signal (Bullish / Neutral / Bearish)
    which maps to +weight / 0 / -weight.
    Final score is normalised to 0–100.
    Score >= 60  →  BUY
    Score 40–59  →  HOLD
    Score <  40  →  SELL
"""
 
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
 
 
# ── Data containers ───────────────────────────────────────────────────────────
 
@dataclass
class IndicatorValues:
    """Raw computed values for every indicator."""
    # Price context
    current_price:  float
    prev_close:     Optional[float]
 
    # Moving averages
    sma20:   Optional[float] = None
    sma50:   Optional[float] = None
    sma200:  Optional[float] = None
    ema12:   Optional[float] = None
    ema26:   Optional[float] = None
 
    # MACD
    macd:         Optional[float] = None   # MACD line  = EMA12 - EMA26
    macd_signal:  Optional[float] = None   # 9-day EMA of MACD line
    macd_hist:    Optional[float] = None   # MACD - signal
 
    # RSI
    rsi: Optional[float] = None
 
    # Bollinger Bands
    bb_upper: Optional[float] = None
    bb_mid:   Optional[float] = None       # same as SMA20
    bb_lower: Optional[float] = None
    bb_width: Optional[float] = None       # (upper - lower) / mid  — volatility proxy
 
    # Volume
    avg_volume_20:  Optional[float] = None
    current_volume: Optional[float] = None
    volume_ratio:   Optional[float] = None  # current / avg  > 1 = above average
 
    # 52-week range (from available history)
    week52_high: Optional[float] = None
    week52_low:  Optional[float] = None
    pct_from_52h: Optional[float] = None   # (price - 52h) / 52h * 100
 
 
@dataclass
class Signal:
    name:      str
    value:     str          # "Bullish" | "Neutral" | "Bearish"
    detail:    str          # human-readable explanation
    weight:    float = 1.0  # how much this signal contributes to the score
 
 
@dataclass
class TechnicalResult:
    ticker:        str
    current_price: float
    indicators:    IndicatorValues
    signals:       list[Signal] = field(default_factory=list)
    score:         float  = 50.0   # 0–100
    recommendation: str   = "HOLD" # BUY | HOLD | SELL
    data_days:     int    = 0      # how many history rows were used
    warning:       Optional[str] = None  # set when data is insufficient
 
 
# ── Math helpers ──────────────────────────────────────────────────────────────
 
def _sma(closes: list[float], n: int) -> Optional[float]:
    if len(closes) < n:
        return None
    return round(sum(closes[-n:]) / n, 4)
 
 
def _ema(closes: list[float], n: int) -> Optional[float]:
    """Standard EMA — seeds from the first n-period SMA."""
    if len(closes) < n:
        return None
    k   = 2 / (n + 1)
    val = sum(closes[:n]) / n          # seed: SMA of first n closes
    for price in closes[n:]:
        val = price * k + val * (1 - k)
    return round(val, 4)
 
 
def _ema_series(closes: list[float], n: int) -> list[float]:
    """Return the full EMA series (same length as closes, NaN-padded at start)."""
    if len(closes) < n:
        return []
    k      = 2 / (n + 1)
    result = [None] * (n - 1)
    val    = sum(closes[:n]) / n
    result.append(val)
    for price in closes[n:]:
        val = price * k + val * (1 - k)
        result.append(val)
    return result
 
 
def _rsi(closes: list[float], n: int = 14) -> Optional[float]:
    """Wilder RSI — uses Wilder smoothing (RMA), not simple EMA."""
    if len(closes) < n + 1:
        return None
 
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [abs(min(d, 0.0)) for d in deltas]
 
    # Seed with simple average of first n periods
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
 
    # Wilder smoothing for remaining periods
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n
 
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)
 
 
def _bollinger(closes: list[float], n: int = 20, k: float = 2.0):
    """Returns (upper, mid, lower, width) or (None, None, None, None)."""
    if len(closes) < n:
        return None, None, None, None
    window = closes[-n:]
    mid    = sum(window) / n
    std    = (sum((c - mid) ** 2 for c in window) / n) ** 0.5
    upper  = round(mid + k * std, 4)
    lower  = round(mid - k * std, 4)
    mid    = round(mid, 4)
    width  = round((upper - lower) / mid, 4) if mid else None
    return upper, mid, lower, width
 
 
def _macd_series(closes: list[float]):
    """
    Returns (macd_line, signal_line, histogram) as scalars.
    macd_line   = EMA12 - EMA26
    signal_line = 9-day EMA of macd_line series
    """
    ema12_series = _ema_series(closes, 12)
    ema26_series = _ema_series(closes, 26)
 
    if not ema12_series or not ema26_series:
        return None, None, None
 
    # Align: both series start from index 25 (first valid EMA26 value)
    macd_line_series = []
    for e12, e26 in zip(ema12_series, ema26_series):
        if e12 is None or e26 is None:
            macd_line_series.append(None)
        else:
            macd_line_series.append(e12 - e26)
 
    valid_macd = [v for v in macd_line_series if v is not None]
    if len(valid_macd) < 9:
        macd_val = valid_macd[-1] if valid_macd else None
        return macd_val, None, None
 
    signal = _ema(valid_macd, 9)
    macd_val = valid_macd[-1]
    hist = round(macd_val - signal, 4) if signal is not None else None
    return round(macd_val, 4), signal, hist
 
 
def _vwap(closes: list[float], volumes: list[float], n: int = 20) -> Optional[float]:
    """Rolling VWAP over last n periods."""
    if len(closes) < n or len(volumes) < n:
        return None
    c = closes[-n:]
    v = volumes[-n:]
    total_vol = sum(v)
    if total_vol == 0:
        return None
    return round(sum(c[i] * v[i] for i in range(n)) / total_vol, 4)
 
 
# ── Signal builders ───────────────────────────────────────────────────────────
 
def _trend_signals(ind: IndicatorValues) -> list[Signal]:
    signals = []
    p = ind.current_price
 
    if ind.sma20 is not None:
        if p > ind.sma20:
            signals.append(Signal("SMA20", "Bullish",
                f"Price ৳{p} above SMA20 ৳{ind.sma20}", weight=1.0))
        else:
            signals.append(Signal("SMA20", "Bearish",
                f"Price ৳{p} below SMA20 ৳{ind.sma20}", weight=1.0))
 
    if ind.sma50 is not None:
        if p > ind.sma50:
            signals.append(Signal("SMA50", "Bullish",
                f"Price ৳{p} above SMA50 ৳{ind.sma50}", weight=1.5))
        else:
            signals.append(Signal("SMA50", "Bearish",
                f"Price ৳{p} below SMA50 ৳{ind.sma50}", weight=1.5))
 
    if ind.sma200 is not None:
        if p > ind.sma200:
            signals.append(Signal("SMA200", "Bullish",
                f"Price above 200-day MA ৳{ind.sma200} — long-term uptrend", weight=2.0))
        else:
            signals.append(Signal("SMA200", "Bearish",
                f"Price below 200-day MA ৳{ind.sma200} — long-term downtrend", weight=2.0))
 
    # Golden / death cross
    if ind.sma20 and ind.sma50:
        if ind.sma20 > ind.sma50:
            signals.append(Signal("MA Cross", "Bullish",
                f"SMA20 ({ind.sma20}) above SMA50 ({ind.sma50}) — golden cross zone",
                weight=1.5))
        else:
            signals.append(Signal("MA Cross", "Bearish",
                f"SMA20 ({ind.sma20}) below SMA50 ({ind.sma50}) — death cross zone",
                weight=1.5))
 
    return signals
 
 
def _macd_signal(ind: IndicatorValues) -> list[Signal]:
    if ind.macd is None:
        return []
 
    signals = []
 
    if ind.macd_signal is not None:
        if ind.macd > ind.macd_signal:
            signals.append(Signal("MACD", "Bullish",
                f"MACD ({ind.macd:.3f}) above signal ({ind.macd_signal:.3f})",
                weight=2.0))
        else:
            signals.append(Signal("MACD", "Bearish",
                f"MACD ({ind.macd:.3f}) below signal ({ind.macd_signal:.3f})",
                weight=2.0))
 
    if ind.macd_hist is not None:
        if ind.macd_hist > 0.05:
            signals.append(Signal("MACD Histogram", "Bullish",
                f"Histogram positive ({ind.macd_hist:.3f}) — momentum building",
                weight=1.0))
        elif ind.macd_hist > 0:
            signals.append(Signal("MACD Histogram", "Neutral",
                f"Histogram barely positive ({ind.macd_hist:.3f}) — weak momentum",
                weight=0.0))
        elif ind.macd_hist < -0.05:
            signals.append(Signal("MACD Histogram", "Bearish",
                f"Histogram negative ({ind.macd_hist:.3f}) — momentum fading",
                weight=1.0))
        else:
            signals.append(Signal("MACD Histogram", "Neutral",
                f"Histogram near zero ({ind.macd_hist:.3f}) — no momentum",
                weight=0.0))
 
    # Zero-line cross
    if ind.macd > 0:
        signals.append(Signal("MACD Zero", "Bullish",
            "MACD above zero line", weight=0.5))
    else:
        signals.append(Signal("MACD Zero", "Bearish",
            "MACD below zero line", weight=0.5))
 
    return signals
 
 
def _rsi_signal(ind: IndicatorValues) -> list[Signal]:
    if ind.rsi is None:
        return []
 
    rsi = ind.rsi
    if rsi <= 30:
        return [Signal("RSI", "Bullish",
            f"RSI {rsi} — oversold, potential reversal upward", weight=2.5)]
    elif rsi <= 45:
        return [Signal("RSI", "Bullish",
            f"RSI {rsi} — approaching oversold, mild bullish bias", weight=1.0)]
    elif rsi <= 55:
        return [Signal("RSI", "Neutral",
            f"RSI {rsi} — neutral zone", weight=0.0)]
    elif rsi <= 70:
        return [Signal("RSI", "Bearish",
            f"RSI {rsi} — approaching overbought, mild bearish bias", weight=1.0)]
    else:
        return [Signal("RSI", "Bearish",
            f"RSI {rsi} — overbought, potential pullback", weight=2.5)]
 
 
def _bollinger_signal(ind: IndicatorValues) -> list[Signal]:
    if ind.bb_upper is None:
        return []
 
    p = ind.current_price
    signals = []
 
    if p < ind.bb_lower:
        signals.append(Signal("Bollinger", "Bullish",
            f"Price ৳{p} below lower band ৳{ind.bb_lower} — oversold squeeze",
            weight=2.0))
    elif p > ind.bb_upper:
        signals.append(Signal("Bollinger", "Bearish",
            f"Price ৳{p} above upper band ৳{ind.bb_upper} — overbought stretch",
            weight=2.0))
    else:
        # Position within band: 0 = at lower, 1 = at upper
        band_range = ind.bb_upper - ind.bb_lower
        position   = (p - ind.bb_lower) / band_range if band_range else 0.5
        if position < 0.35:
            signals.append(Signal("Bollinger", "Bullish",
                f"Price in lower third of Bollinger Band", weight=1.0))
        elif position > 0.65:
            signals.append(Signal("Bollinger", "Bearish",
                f"Price in upper third of Bollinger Band", weight=1.0))
        else:
            signals.append(Signal("Bollinger", "Neutral",
                f"Price mid-band — no directional bias", weight=0.0))
 
    return signals
 
 
def _volume_signal(ind: IndicatorValues) -> list[Signal]:
    if ind.volume_ratio is None:
        return []
 
    vr = ind.volume_ratio
    p  = ind.current_price
    pc = ind.prev_close
 
    if pc is None:
        return []
 
    price_up = p >= pc
 
    if vr >= 1.5 and price_up:
        return [Signal("Volume", "Bullish",
            f"Volume {vr:.1f}x average with price up — strong buying interest",
            weight=1.5)]
    elif vr >= 1.5 and not price_up:
        return [Signal("Volume", "Bearish",
            f"Volume {vr:.1f}x average with price down — strong selling pressure",
            weight=1.5)]
    elif vr < 0.5:
        return [Signal("Volume", "Neutral",
            f"Volume {vr:.1f}x average — low conviction move", weight=0.0)]
    else:
        return [Signal("Volume", "Neutral",
            f"Volume {vr:.1f}x average — normal activity", weight=0.0)]
 
 
def _week52_signal(ind: IndicatorValues) -> list[Signal]:
    if ind.pct_from_52h is None:
        return []
 
    pct = ind.pct_from_52h
    p   = ind.current_price
    w52l = ind.week52_low
 
    signals = []
 
    vol_ratio = ind.volume_ratio or 1.0

    if pct >= -3:
        # Very close to 52W high
        if vol_ratio >= 1.5:
            signals.append(Signal("52W Range", "Bullish",
                f"Within 3% of 52W high with {vol_ratio:.1f}x volume — breakout attempt", weight=1.5))
        elif vol_ratio >= 1.0:
            signals.append(Signal("52W Range", "Neutral",
                f"Near 52W high — watch for breakout confirmation", weight=0.0))
        else:
            signals.append(Signal("52W Range", "Bearish",
                f"Near 52W high with low volume — resistance likely", weight=0.5))
    elif pct >= -10:
        # Approaching 52W high
        if vol_ratio >= 1.2:
            signals.append(Signal("52W Range", "Bullish",
                f"{abs(pct):.1f}% below 52W high, volume building — momentum positive", weight=1.0))
    elif pct <= -40:
        signals.append(Signal("52W Range", "Bullish",
            f"More than 40% below 52-week high — deep value territory", weight=1.5))
    elif pct <= -25:
        signals.append(Signal("52W Range", "Neutral",
            f"{abs(pct):.1f}% below 52W high — significant recovery potential", weight=0.0))
 
    if w52l and p < w52l * 1.1:
        signals.append(Signal("52W Low", "Bullish",
            f"Price near 52-week low ৳{w52l} — contrarian opportunity", weight=1.0))
 
    return signals
 
 
# ── Main entry point ──────────────────────────────────────────────────────────
 
def compute_technical_analysis(ticker: str, history_rows: list) -> TechnicalResult:
    """
    Takes a list of PriceHistory ORM objects (any order — will be sorted).
    Returns a fully populated TechnicalResult.
 
    Minimum data requirements:
        < 14 rows  → no RSI, no MACD, score unreliable  (warning issued)
        < 20 rows  → no Bollinger Bands
        < 26 rows  → no MACD
        < 50 rows  → no SMA50
        < 200 rows → no SMA200
    """
    if not history_rows:
        return TechnicalResult(
            ticker=ticker,
            current_price=0.0,
            indicators=IndicatorValues(current_price=0.0, prev_close=None),
            warning="No price history available. Call POST /load-dse first.",
        )
 
    # Sort oldest → newest
    rows = sorted(history_rows, key=lambda r: r.date)
 
    # Extract close prices — fall back to ltp when close is missing
    closes  = [float(r.close or r.ltp) for r in rows if (r.close or r.ltp) is not None]
    volumes = [float(r.volume) for r in rows if r.volume is not None]
 
    if not closes:
        return TechnicalResult(
            ticker=ticker,
            current_price=0.0,
            indicators=IndicatorValues(current_price=0.0, prev_close=None),
            warning="All price history rows have null close and ltp.",
        )
 
    current_price = closes[-1]
    prev_close    = closes[-2] if len(closes) >= 2 else None
    n             = len(closes)
 
    # ── Compute all indicators ────────────────────────────────────────────────
    sma20  = _sma(closes, 20)
    sma50  = _sma(closes, 50)
    sma200 = _sma(closes, 200)
    ema12  = _ema(closes, 12)
    ema26  = _ema(closes, 26)
 
    macd_val, macd_sig, macd_hist = _macd_series(closes)
    rsi_val = _rsi(closes, 14)
 
    bb_upper, bb_mid, bb_lower, bb_width = _bollinger(closes, 20)
 
    avg_vol    = sum(volumes[-20:]) / min(len(volumes), 20) if volumes else None
    curr_vol   = volumes[-1] if volumes else None
    vol_ratio  = round(curr_vol / avg_vol, 2) if (avg_vol and curr_vol and avg_vol > 0) else None
 
    highs  = [float(r.high) for r in rows if r.high is not None]
    lows   = [float(r.low)  for r in rows if r.low  is not None]
    w52h   = round(max(highs), 2) if highs else None
    w52l   = round(min(lows),  2) if lows  else None
    pct52h = round((current_price - w52h) / w52h * 100, 2) if w52h else None
 
    ind = IndicatorValues(
        current_price  = current_price,
        prev_close     = prev_close,
        sma20          = sma20,
        sma50          = sma50,
        sma200         = sma200,
        ema12          = ema12,
        ema26          = ema26,
        macd           = macd_val,
        macd_signal    = macd_sig,
        macd_hist      = macd_hist,
        rsi            = rsi_val,
        bb_upper       = bb_upper,
        bb_mid         = bb_mid,
        bb_lower       = bb_lower,
        bb_width       = bb_width,
        avg_volume_20  = round(avg_vol, 0) if avg_vol else None,
        current_volume = curr_vol,
        volume_ratio   = vol_ratio,
        week52_high    = w52h,
        week52_low     = w52l,
        pct_from_52h   = pct52h,
    )
 
    # ── Collect signals ───────────────────────────────────────────────────────
    signals = (
        _trend_signals(ind)
        + _macd_signal(ind)
        + _rsi_signal(ind)
        + _bollinger_signal(ind)
        + _volume_signal(ind)
        + _week52_signal(ind)
    )
 
    # ── Score (weighted) ──────────────────────────────────────────────────────
    # Each signal contributes: Bullish = +weight, Neutral = 0, Bearish = -weight
    # Total possible = sum of all weights (all Bullish)
    # Normalise to 0–100 with 50 as neutral baseline
    bull_score = sum(s.weight for s in signals if s.value == "Bullish")
    bear_score = sum(s.weight for s in signals if s.value == "Bearish")
    max_score  = sum(s.weight for s in signals if s.value != "Neutral")
 
    if max_score > 0:
        raw   = (bull_score - bear_score) / max_score   # -1 to +1
        score = round(50 + raw * 50, 1)                 # 0 to 100
    else:
        score = 50.0

    # Momentum quality cap - prevents weak trends scoring 100
    vol_ratio  = ind.volume_ratio or 0
    macd_hist  = abs(ind.macd_hist or 0)
    if vol_ratio < 0.5 and macd_hist < 0.05:
        score = min(score, 75.0)   # low volume + flat MACD
    elif vol_ratio < 0.8 and macd_hist < 0.05:
        score = min(score, 85.0)   # below avg volume + flat MACD
    elif macd_hist < 0.02:
        score = min(score, 88.0)   # very flat MACD regardless of volume
 
    # ── Recommendation ────────────────────────────────────────────────────────
    if score >= 62:
        recommendation = "BUY"
    elif score >= 42:
        recommendation = "HOLD"
    else:
        recommendation = "SELL"
 
    # ── Warning for thin data ─────────────────────────────────────────────────
    warning = None
    if n < 14:
        warning = (
            f"Only {n} days of history available — indicators are unreliable. "
            "Call POST /load-dse daily to build up history."
        )
    elif n < 26:
        warning = (
            f"{n} days of history — MACD unavailable, some signals missing. "
            "Accuracy improves after 26+ trading days."
        )
 
    return TechnicalResult(
        ticker         = ticker.upper(),
        current_price  = current_price,
        indicators     = ind,
        signals        = signals,
        score          = score,
        recommendation = recommendation,
        data_days      = n,
        warning        = warning,
    )
 