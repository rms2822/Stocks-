"""
backtest.py — walk-forward backtest for the U1254 swing ruleset
────────────────────────────────────────────────────────────────
Answers the question a desk asks BEFORE trusting a mechanical system:
    "Does this ruleset actually have an edge — and how big?"

It reuses the project's OWN indicator math (technical.py: Wilder RSI,
EMA-seeded MACD, SMA) so the test reflects the real signals, not a
re-implementation. It walks each ticker's PriceHistory day by day,
recomputing indicators point-in-time (no look-ahead), enters when the
entry filter passes, and exits on stop / target / time-stop — net of
DSE transaction costs.

Outputs: trade count, win rate, avg win/loss, EXPECTANCY (the number that
matters), profit factor, max drawdown, avg hold. Plus a parameter sweep so
you can test whether RSI 50–68 actually beats other bands instead of
trusting it on faith.

USAGE (from the backend dir, where dse.db and technical.py live):
    python backtest.py                      # full backtest, default params
    python backtest.py --sweep rsi          # sweep the RSI entry band
    python backtest.py --tickers BXPHARMA,IDLC,SQURPHARMA

Self-test (no DB needed):
    python backtest.py --selftest
"""

from __future__ import annotations
import sqlite3, argparse, statistics, sys
from dataclasses import dataclass
from typing import Optional

# Reuse the project's EXACT indicator functions. Run from the dir containing technical.py.
try:
    from app.analysis.technical import _sma, _rsi, _macd_series
except ImportError:
    # allow running the self-test standalone
    _sma = _rsi = _macd_series = None

DSE_ROUNDTRIP_COST = 0.012   # commission + 0.05% tax + slippage, round trip


# ── Strategy parameters (everything tunable — that's the point) ───────────────
@dataclass
class Params:
    rsi_min: float = 50.0
    rsi_max: float = 68.0
    require_macd_pos: bool = True
    require_above_sma20: bool = True
    require_above_sma50: bool = True
    vol_ratio_min: float = 1.3
    pct52_min: float = -22.0          # room-to-run window
    pct52_max: float = -2.0
    # ── Stop placement ───────────────────────────────────────────────────────
    stop_mode: str = "structure"       # "structure" | "atr" | "sma20" | "pct"
    swing_lookback: int = 10           # bars to find the recent swing low (structure)
    atr_period: int = 14
    atr_mult: float = 2.0              # stop = entry - atr_mult * ATR  (atr mode)
    stop_buffer: float = 0.005         # place stop just BELOW the level (structure/sma20)
    stop_pct: float = 0.045            # fixed stop (pct mode) + fallback when level missing
    min_stop_pct: float = 0.02         # clamp: never tighter than 2%
    max_stop_pct: float = 0.12         # clamp: never wider than 12% (else R math breaks)
    target_R: float = 1.9              # target = entry + target_R * risk  (R-multiple)
    time_stop_days: int = 7
    warmup: int = 55                   # need >=50 for SMA50 + buffer
    cost: float = DSE_ROUNDTRIP_COST


@dataclass
class Trade:
    ticker: str
    entry_i: int
    entry_px: float
    exit_px: float
    bars_held: int
    exit_reason: str        # stop | target | time
    gross_ret: float
    net_ret: float          # after round-trip cost


# ── Indicator snapshot at a point in time (no look-ahead) ────────────────────
def _snapshot(closes, highs, lows, vols, i):
    """Compute the indicators the entry filter needs, using data UP TO day i only."""
    c = closes[: i + 1]
    if len(c) < 51:
        return None
    sma20 = _sma(c, 20)
    sma50 = _sma(c, 50)
    rsi = _rsi(c, 14)
    _macd, _sig, hist = _macd_series(c)
    avg_vol = sum(vols[max(0, i - 19): i + 1]) / min(20, i + 1) if vols else None
    vol_ratio = (vols[i] / avg_vol) if (avg_vol and avg_vol > 0) else None
    w52h = max(highs[max(0, i - 251): i + 1]) if highs else None
    pct52 = ((c[-1] - w52h) / w52h * 100) if w52h else None
    return dict(price=c[-1], sma20=sma20, sma50=sma50, rsi=rsi,
                macd_hist=hist, vol_ratio=vol_ratio, pct52=pct52)


def _entry_ok(s, p: Params) -> bool:
    if s is None or None in (s["sma20"], s["sma50"], s["rsi"], s["macd_hist"]):
        return False
    if not (p.rsi_min <= s["rsi"] <= p.rsi_max):                return False
    if p.require_macd_pos and s["macd_hist"] <= 0:             return False
    if p.require_above_sma20 and s["price"] <= s["sma20"]:     return False
    if p.require_above_sma50 and s["price"] <= s["sma50"]:     return False
    if p.vol_ratio_min and (s["vol_ratio"] or 0) < p.vol_ratio_min: return False
    if s["pct52"] is None or not (p.pct52_min <= s["pct52"] <= p.pct52_max): return False
    return True


def _atr(highs, lows, closes, i, period):
    """Wilder-style ATR using data up to bar i (no look-ahead)."""
    if i < period:
        return None
    trs = []
    for k in range(i - period + 1, i + 1):
        tr = max(highs[k] - lows[k],
                 abs(highs[k] - closes[k - 1]),
                 abs(lows[k] - closes[k - 1]))
        trs.append(tr)
    return sum(trs) / period


def _place_stop(entry_px, ei, highs, lows, closes, p: Params):
    """Stop price for the chosen mode, clamped to [min_stop_pct, max_stop_pct]."""
    if p.stop_mode == "atr":
        atr = _atr(highs, lows, closes, ei, p.atr_period)
        stop = entry_px - p.atr_mult * atr if atr else entry_px * (1 - p.stop_pct)
    elif p.stop_mode == "structure":
        lo = min(lows[max(0, ei - p.swing_lookback): ei + 1])   # recent swing low
        stop = lo * (1 - p.stop_buffer)
    elif p.stop_mode == "sma20":
        s20 = _sma(closes[: ei + 1], 20)
        stop = s20 * (1 - p.stop_buffer) if s20 else entry_px * (1 - p.stop_pct)
    else:  # "pct"
        stop = entry_px * (1 - p.stop_pct)

    # clamp risk so structure stops can't be absurdly wide or inverted
    risk_pct = (entry_px - stop) / entry_px
    if risk_pct < p.min_stop_pct:
        stop = entry_px * (1 - p.min_stop_pct)
    elif risk_pct > p.max_stop_pct:
        stop = entry_px * (1 - p.max_stop_pct)
    return stop


def simulate_ticker(ticker, closes, highs, lows, vols, p: Params) -> list[Trade]:
    trades: list[Trade] = []
    i = p.warmup
    n = len(closes)
    while i < n - 1:
        s = _snapshot(closes, highs, lows, vols, i)
        if not _entry_ok(s, p):
            i += 1
            continue
        # Enter at NEXT bar's open ~ next close (no same-bar look-ahead)
        entry_i = i + 1
        entry_px = closes[entry_i]
        stop_px = _place_stop(entry_px, entry_i, highs, lows, closes, p)
        risk = entry_px - stop_px
        target_px = entry_px + p.target_R * risk

        exit_px = exit_reason = None
        j = entry_i + 1
        while j < n:
            lo, hi = lows[j], highs[j]
            if lo <= stop_px:                       # stop first (conservative)
                exit_px, exit_reason = stop_px, "stop"; break
            if hi >= target_px:
                exit_px, exit_reason = target_px, "target"; break
            if (j - entry_i) >= p.time_stop_days:
                exit_px, exit_reason = closes[j], "time"; break
            j += 1
        if exit_px is None:                          # ran out of data
            exit_px, exit_reason, j = closes[-1], "eod", n - 1

        gross = (exit_px - entry_px) / entry_px
        net = gross - p.cost
        trades.append(Trade(ticker, entry_i, entry_px, exit_px, j - entry_i,
                            exit_reason, round(gross, 4), round(net, 4)))
        i = j + 1                                    # no overlapping trades per ticker
    return trades


# ── Aggregate metrics ─────────────────────────────────────────────────────────
def summarize(trades: list[Trade]) -> dict:
    if not trades:
        return {"trades": 0}
    rets = [t.net_ret for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    # max drawdown on the sequential equity curve (1 unit compounded per trade)
    eq, peak, mdd = 1.0, 1.0, 0.0
    for r in rets:
        eq *= (1 + r)
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
    expectancy = statistics.mean(rets)
    return {
        "trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "avg_win": statistics.mean(wins) if wins else 0.0,
        "avg_loss": statistics.mean(losses) if losses else 0.0,
        "expectancy": expectancy,                      # avg net return per trade
        "expectancy_per_100": expectancy * 100,
        "profit_factor": (gross_win / gross_loss) if gross_loss else float("inf"),
        "max_drawdown": mdd,
        "avg_bars": statistics.mean(t.bars_held for t in trades),
        "total_compounded": eq - 1,
        "exit_mix": {r: sum(1 for t in trades if t.exit_reason == r)
                     for r in ("stop", "target", "time", "eod")},
    }


def print_summary(title, m):
    print(f"\n── {title} ──")
    if m["trades"] == 0:
        print("  no trades triggered"); return
    print(f"  trades {m['trades']}  ·  win {m['win_rate']:.0%}  ·  "
          f"avg win {m['avg_win']*100:+.1f}%  avg loss {m['avg_loss']*100:+.1f}%")
    print(f"  EXPECTANCY {m['expectancy_per_100']:+.2f}% / trade  ·  "
          f"profit factor {m['profit_factor']:.2f}  ·  max DD {m['max_drawdown']*100:.1f}%")
    print(f"  avg hold {m['avg_bars']:.1f} bars  ·  exits {m['exit_mix']}")
    verdict = ("EDGE looks real" if m["expectancy"] > 0.003 and m["profit_factor"] > 1.3
               else "NO reliable edge — do not size up" if m["expectancy"] <= 0
               else "marginal — costs eat most of it")
    print(f"  → {verdict}")


# ── DB loading ────────────────────────────────────────────────────────────────
def load_ticker(con, ticker):
    q = ("SELECT date, COALESCE(close, ltp), high, low, volume "
         "FROM price_history WHERE ticker=? ORDER BY date ASC")
    rows = con.execute(q, (ticker,)).fetchall()
    closes = [float(r[1]) for r in rows if r[1] is not None]
    highs = [float(r[2]) if r[2] is not None else float(r[1]) for r in rows if r[1] is not None]
    lows = [float(r[3]) if r[3] is not None else float(r[1]) for r in rows if r[1] is not None]
    vols = [float(r[4]) if r[4] is not None else 0.0 for r in rows if r[1] is not None]
    return closes, highs, lows, vols


def run(db="dse.db", tickers=None, p: Params = None):
    p = p or Params()
    con = sqlite3.connect(db)
    if not tickers:
        tickers = [r[0] for r in con.execute(
            "SELECT DISTINCT ticker FROM price_history").fetchall()]
    all_trades = []
    for tk in tickers:
        closes, highs, lows, vols = load_ticker(con, tk)
        if len(closes) < p.warmup + 5:
            continue
        all_trades += simulate_ticker(tk, closes, highs, lows, vols, p)
    con.close()
    return all_trades


# ── Parameter sweep (kills the "RSI 50–68 is arbitrary" objection) ───────────
def sweep_stops(db, tickers=None):
    print("\n=== STOP-MODE COMPARISON (default RSI band) ===")
    modes = [
        ("pct 4.5% (old)",   Params(stop_mode="pct",       stop_pct=0.045)),
        ("structure swing",  Params(stop_mode="structure", swing_lookback=10)),
        ("ATR x2.0",         Params(stop_mode="atr",        atr_mult=2.0)),
        ("ATR x2.5",         Params(stop_mode="atr",        atr_mult=2.5)),
        ("below SMA20",      Params(stop_mode="sma20")),
    ]
    for label, p in modes:
        m = summarize(run(db, tickers, p))
        if m["trades"]:
            ex = m["exit_mix"]
            print(f"  {label:18} n={m['trades']:4d}  win {m['win_rate']:.0%}  "
                  f"expectancy {m['expectancy_per_100']:+.2f}%  PF {m['profit_factor']:.2f}  "
                  f"stops/targets {ex['stop']}/{ex['target']}")
        else:
            print(f"  {label:18} no trades")


def sweep_rsi(db, tickers=None):
    print("\n=== RSI ENTRY-BAND SWEEP ===")
    for lo, hi in [(45, 65), (50, 68), (50, 72), (55, 70), (40, 60), (55, 75)]:
        p = Params(rsi_min=lo, rsi_max=hi)
        m = summarize(run(db, tickers, p))
        if m["trades"]:
            print(f"  RSI {lo}-{hi}:  n={m['trades']:4d}  win {m['win_rate']:.0%}  "
                  f"expectancy {m['expectancy_per_100']:+.2f}%  PF {m['profit_factor']:.2f}  "
                  f"maxDD {m['max_drawdown']*100:.0f}%")
        else:
            print(f"  RSI {lo}-{hi}:  no trades")


# ── Synthetic self-test (proves the engine works without the DB) ─────────────
def selftest():
    import math, random
    random.seed(7)
    # Build a trending series with noise so SOME entries trigger and resolve
    closes = []
    px = 100.0
    for t in range(400):
        drift = 0.004 * math.sin(t / 30)        # cyclical up/down regimes
        px *= (1 + drift + random.uniform(-0.012, 0.012))
        closes.append(round(px, 2))
    highs = [c * 1.012 for c in closes]
    lows = [c * 0.988 for c in closes]
    # occasional volume spikes so the vol_ratio filter can pass
    vols = [1000 * (3.0 if t % 11 == 0 else random.uniform(0.6, 1.2)) for t in range(len(closes))]
    if _sma is None:
        print("technical.py not importable — run from backend dir for the real test."); return
    # relaxed params for the self-test ONLY — just to exercise entries/exits/metrics
    p = Params(rsi_min=40, rsi_max=80, vol_ratio_min=1.2, pct52_min=-40, pct52_max=0)
    trades = simulate_ticker("SYNTH", closes, highs, lows, vols, p)
    print(f"Self-test: generated {len(trades)} trades on synthetic data.")
    print_summary("SELF-TEST (synthetic, not real edge)", summarize(trades))
    print("\nEngine OK. Point it at dse.db from the backend dir for the real backtest.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="dse.db")
    ap.add_argument("--tickers", default=None)
    ap.add_argument("--sweep", default=None, choices=["rsi", "stops"])
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    tickers = a.tickers.split(",") if a.tickers else None

    if a.selftest:
        selftest()
    elif a.sweep == "rsi":
        sweep_rsi(a.db, tickers)
    elif a.sweep == "stops":
        sweep_stops(a.db, tickers)
    else:
        trades = run(a.db, tickers)
        print_summary("FULL BACKTEST (default params)", summarize(trades))
        # exit-reason + per-ticker context helps sanity-check
        if trades:
            byt = {}
            for t in trades:
                byt.setdefault(t.ticker, []).append(t.net_ret)
            print("\n  per-ticker expectancy (top/bottom):")
            ranked = sorted(byt.items(), key=lambda kv: statistics.mean(kv[1]))
            for tk, rs in ranked[:3] + ranked[-3:]:
                print(f"    {tk:11} n={len(rs):3d}  exp {statistics.mean(rs)*100:+.2f}%")
