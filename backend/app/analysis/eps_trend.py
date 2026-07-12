"""
app/analysis/eps_trend.py — robust EPS-trend (fixes the small-base blowup +
loss→profit blind spot in the old calc_trend).

The OLD formula was (latest - oldest) / oldest * 100, which:
  • explodes when the oldest year is tiny  (ENVOYTEX 0.05 → 0.75 read as +1400%)
  • returns 0.0 for any loss→profit turnaround  (because of `if oldest > 0`)
  • compounds multi-year growth into a single huge number

This replaces it with an ANNUALIZED (CAGR) trend, capped, and turnaround-aware.

USE IT IN BOTH PLACES so the stored column and the score agree:
  1. resume_eps_history.py  → replace calc_trend's body with `return robust_eps_trend(history)`
  2. fundamental.py _score_eps_trend → compute the % via robust_eps_trend(...) instead of its own math
"""

from __future__ import annotations

TREND_CAP = 60.0          # cap annualized % so no single name dominates
TURNAROUND = 50.0         # signal value for loss/0 → profit
DETERIORATION = -50.0     # signal value for profit → loss/0


def robust_eps_trend(history: dict) -> float:
    """
    history: {year: {"eps": x, ...}}  (the shape resume_eps_history already builds)
    Returns a capped annualized trend %, or a fixed turnaround/deterioration value.
    """
    years = sorted(history.keys())
    vals = [history[y]["eps"] for y in years
            if isinstance(history.get(y), dict) and history[y].get("eps") is not None]
    if len(vals) < 2:
        return 0.0
    oldest, latest = vals[0], vals[-1]
    span = max(1, years[-1] - years[0])

    if oldest > 0 and latest > 0:
        cagr = ((latest / oldest) ** (1.0 / span) - 1.0) * 100.0
        return round(max(-TREND_CAP, min(TREND_CAP, cagr)), 1)
    if oldest <= 0 and latest > 0:
        return TURNAROUND          # real turnaround — was invisible (0.0) before
    if oldest > 0 and latest <= 0:
        return DETERIORATION
    return 0.0                      # still loss-making both ends


def robust_eps_trend_from_dict(eps_history: dict) -> float:
    """
    Convenience for fundamental._score_eps_trend, whose `eps_history` is
    {year: eps_float} rather than {year: {"eps": ...}}.
    """
    wrapped = {y: {"eps": v} for y, v in eps_history.items() if v is not None}
    return robust_eps_trend(wrapped)


if __name__ == "__main__":
    tests = {
        "ENVOYTEX blowup":      {2021: {"eps": 0.05}, 2025: {"eps": 0.75}},
        "Normal grower":        {2021: {"eps": 3.0},  2025: {"eps": 5.7}},
        "Loss->profit":         {2021: {"eps": -1.2}, 2025: {"eps": 2.4}},
        "Profit->loss":         {2021: {"eps": 4.0},  2025: {"eps": -0.5}},
        "Flat":                 {2022: {"eps": 2.0},  2025: {"eps": 2.1}},
    }
    for name, h in tests.items():
        print(f"{name:18} {robust_eps_trend(h):+6.1f}")
