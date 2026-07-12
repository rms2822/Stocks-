# Swing Project Context — U1254 (LankaBangla / DSE)

> **Purpose:** Standing primer for this project. A new chat should read this first to orient.
> Upload to the project's knowledge and update the dated sections as the book changes.
> **Account:** Client U1254 · RAFSAAN MUHAB SHAMS · LankaBangla Securities · CASH account (no margin).
> **Last updated from:** statement As-On 11-Jun-2026 + scan `full_analysis_8th_June.csv` (8-Jun close).
> *Everything here is mechanical strategy output, not financial advice.*

---

## 1. The system (how the pieces fit)

A FastAPI server (`app.main:app`) holds market data in `dse.db`. Three POST endpoints refresh it; `full_stock_analysis.py` then scores every stock and writes `full_analysis.json` + `full_analysis.csv`.

**Environment:** Windows, PowerShell, working dir `C:\dse analyzer\backend`. Scripts use **relative** `dse.db`, so always run them from the backend dir. In PowerShell use `cd "C:\dse analyzer\backend"` (no `/d`), and `curl.exe` / `Invoke-RestMethod` (not the `curl` alias).

**Refresh + scan commands:**
```powershell
cd "C:\dse analyzer\backend"
python -m uvicorn app.main:app --port 8000      # leave running (kill stale: taskkill /PID <pid> /F)
python auto_update.py                            # POST /load-dse, /load-fundamentals, /load-history?days=30
python full_stock_analysis.py                    # writes full_analysis.json + .csv
```
Scan columns: `ticker, sector, ltp, percent_change, volume, combined_score, tech_score, fund_score, recommendation, rsi, macd_hist, volume_ratio, pct_from_52h, sma20, sma50, eps, pe, nav, pb, eps_trend, debt_equity`.

## 2. Session workflow (repeat each trading day)

1. **User uploads the broker statement PDF** (`Portfolio_U1254.pdf`). This is **authoritative** for prices, quantities, cost basis, P/L, cash, and sector exposure.
2. **Use the matching scan CSV** for signals (score/RSI/MACD/SMA). The scan whose LTP matches the statement's market prices is the right one (statement "As-On D" ≈ prior-session close = scan of that close).
3. **Produce:** a dated status file `Swing_Portfolio_U1254_Status_YYYY-MM-DD.md` and a color-coded action-sheet PNG `Swing_U1254_Action_Sheet_YYYY-MM-DD.png` (HOLD = blue, new-buy/breakeven = green, watch/extended = amber, exit = red, scale-out = orange).
4. **Anchor prices/P&L to the statement; treat scan signals as ~1 session old** and flag it. If the user runs a fresh scan, recompute stops/overbought off it.

## 3. Strategy rules (7-day swing)

- **Entry filter (all must hold):** combined score ≥ 70 · RSI 50–68 (rising, not overbought) · MACD histogram > 0 · price above SMA20 **and** SMA50 · volume ≥ ~1.3× average · liquid (turnover ≥ ~20mn so a position can be exited) · ~2–22% below 52-week high (room to target). **RSI > 72 → no fresh entry.**
- **Position management:** 6–9 positions · no single name > ~15% of book · keep 3–4+ sectors · hold ~10–15% dry powder · hard stop just under SMA20 / last swing low (~4–5% risk per trade) · move stop to **breakeven at +3–4%**.
- **Exits:** scale out ~half at first target (~+7–10% or next resistance), trail the rest. Exit on any of: stop hit · RSI > 75 on a down day · MACD histogram flips negative · 7 sessions with no progress (time stop).
- **Concentration rule:** when a sector is overweight (esp. pharma), **new buys must come from other sectors.**
- **Two horizons, two lenses:** swing = momentum/technical (RSI, MACD, volume, SMA). Long-term = fundamentals (low P/E, low P/B, growing EPS, low debt) and ignores RSI. Don't mix the lenses.

## 4. Current holdings — cost basis (from 11-Jun statement)

PV 160,581 · cost 158,058 · unrealized **+2,523 (+1.60%)** · cash **33,629 (only ~23,669 settled)** · account equity 191,687.

| Stock | Sector | Qty | Avg cost | Last px | Stop | Target |
|---|---|---|---|---|---|---|
| BXPHARMA | Pharma | 239 | 121.71 | 125.70 | 122 | 136 (=52wk high) |
| SQURPHARMA | Pharma | 120 | 208.32 | 216.00 | 209 | 226 |
| ACMELAB | Pharma | 255 | 77.81 | 79.30 | 78 | 86 |
| CITYBANK | Bank | 500 | 28.92 | 29.30 | 27.8 | 31.5 |
| MALEKSPIN | Textile | 344 | 29.22 | 29.30 | 28.5 | 32.5 |
| MPETROLEUM | Fuel/Power | 20 | 209.33 | 211.30 | 205 trail | 220 |
| PRIMEBANK | Bank | 350 | 29.22 | 29.70 | 28.8 | 31 |
| CONFIDCEM | Cement | 139 | 64.78 | 63.60 | 62.5 | 70 |
| ENVOYTEX | Textile | 130 | 51.30 | 50.30 | 48 | 54 |
| BSC | Shipping/Misc | 82 | 107.73 | 106.90 | 103 | 116 |
| DBH | NBFI | 225 | 39.26 | 39.20 | 37.2 (BE) | 43 |
| PTL (Paramount) | Textile | 141 | 62.65 | 62.90 | 62.6 (BE) | 68 |
| BSRMSTEEL | Engineering | 42 | 72.29 | 76.50 | 76 trail | 82 |

**Closed:** IDLC (sold ~+315), BRACBANK, GP stub, MARICO (cleanup), PeoplesINS (sold +~1,104 after a +10% day). Marico 200 BDT cash dividend receivable to bank (record 01-Jun).

## 5. Open / recurring action items

1. **PTL** — sitting on breakeven stop (~62.6); honor it if it slips.
2. **BXPHARMA** — largest position (~18%); consider trimming toward ~15% to de-risk; keep 122 stop regardless.
3. **BSRMSTEEL** — keep trailing ~76.
4. **Move new winners to breakeven** as they clear +3–4% (DBH, PTL done).
5. **Watch CONFIDCEM (stop 62.5) and ENVOYTEX (stop 48)** — red but above stops.
6. **Deploy dry powder only on a confirmed setup**, from under-weighted **non-pharma, non-textile** sectors (bank/NBFI/fuel/insurance). Don't chase a gapped-up tape.

## 6. Standing flags (carry into every session)

- **BXPHARMA court/governance overhang (LIVE).** BSEC moved to appoint 9 independent directors after Aug-2024 regime change; board can't approve accounts → audited FY-June-2025 results unpublished → London AIM GDR trading suspended from 2-Jan-2026. High Court writ hearings run after the 15-Mar–18-Apr-2026 vacation; a decision was expected **around end of June 2026** — a binary, two-sided catalyst. Business still sound (declared 40% cash dividend). DSE/CSE shares trade normally. **Its 122 stop is the most important line in the book.** Re-check for a ruling before acting near that event.
- **Pharma concentration** ~45–47% (SQUR + BX + ACME ≈ 41%). Above the comfort zone → new buys stay non-pharma.
- **Textile concentration** crept to ~16% (ENVOYTEX + MALEKSPIN + PTL) → second-largest sector, **no textile adds.**
- **Cash-settlement quirk.** DSE is T+ settlement: sale proceeds and just-bought shares aren't immediately usable. Headline cash overstates buying power (e.g. 33,629 total but only ~23,669 settled); just-bought lots show **saleable-0** until they settle and can't be sold that session. Always separate settled vs maturing cash.
- **Execution pattern to watch:** buys get executed precisely; the sell/cleanup side has historically been deferred. Push the exits.
- **Data freshness:** statement = live; scan signals lag ~1 session. After a rally, RSI/scores read more overbought than the file shows — refresh before new entries.

## 7. Useful reference (fundamentals snapshot, 8-Jun)

Top quality+value names on the exchange (cheap, profitable, growing, low-debt): MPETROLEUM, PADMAOIL, CITYBANK, SQURPHARMA, UTTARABANK, EHL. Caveats: fuel distributors are policy-driven & illiquid; banks (CITYBANK/UTTARA/ONEBANK/SHAHJA) share NPL/asset-quality risk — treat as one risk; ENVOYTEX +1,400% EPS trend is a base-effect artifact. BERGERPBL = quality business but richly valued (P/E ~19, P/B ~4.2) → long-term "wait for pullback," not a swing entry.

---

### How to start a new chat in this project
Upload the latest `Portfolio_U1254.pdf` (and a fresh `full_analysis*.csv` if you've re-scanned). Say e.g. *"New session — update the book."* The chat will read this primer for rules/flags, the statement for the live book, and the scan for signals, then produce the dated status + action-sheet image. Keep this file updated (sections 4–6) each session, or ask the chat to regenerate it.
