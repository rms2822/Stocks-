"""app/company_fundamentals.py -- scrape per-company fundamentals from dse.com.bd.

The new DSE company page (https://www.dse.com.bd/company/<CODE>) carries a
Next.js RSC payload with structured financials: NAV, face value, paid-up
capital, short/long-term loans, multi-year EPS, dividend history and
shareholding pattern. amarstock gives EPS/PE; this fills the rest
(NAV, P/B input, debt/equity, EPS trend, dividend, holdings).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

import requests

BASE = "https://www.dse.com.bd/company/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.dse.com.bd/",
}


def _rsc_payload(html: str) -> str:
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)', html)
    return "".join(chunks).encode().decode("unicode_escape", errors="replace")


def _extract(payload: str, key: str) -> Any:
    """Return the JSON value for the first `"key":` via balanced bracket matching."""
    m = re.search(r'"%s":' % re.escape(key), payload)
    if not m:
        return None
    i = m.end()
    while i < len(payload) and payload[i] == " ":
        i += 1
    if i >= len(payload):
        return None
    if payload[i] in "[{":
        depth, j, instr, esc = 0, i, False, False
        while j < len(payload):
            ch = payload[j]
            if instr:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    instr = False
            else:
                if ch == '"':
                    instr = True
                elif ch in "[{":
                    depth += 1
                elif ch in "]}":
                    depth -= 1
                    if depth == 0:
                        break
            j += 1
        try:
            return json.loads(payload[i:j + 1])
        except Exception:
            return None
    m2 = re.match(r'("(?:[^"\\]|\\.)*"|-?[\d.]+|true|false|null)', payload[i:])
    if m2:
        try:
            return json.loads(m2.group(1))
        except Exception:
            return None
    return None


def parse_company(html: str) -> dict:
    p = _rsc_payload(html)
    out: dict = {}

    # Company-level NAV / face value / paid-up capital (distinct from the
    # per-year nav inside multiYearFinancials): they appear as a cluster.
    m = re.search(r'"faceValue":([\d.]+),"paidUpCapital":([\d.]+),"nav":(-?[\d.]+)', p)
    if m:
        out["face_value"] = float(m.group(1))
        out["paid_up_capital"] = float(m.group(2))
        out["nav"] = float(m.group(3))

    loan = _extract(p, "loanStatus")
    if isinstance(loan, dict):
        st = loan.get("shortTerm") or 0
        lt = loan.get("longTerm") or 0
        out["total_debt_mn"] = round(float(st) + float(lt), 3) if (st or lt) else None

    myf = _extract(p, "multiYearFinancials")
    if isinstance(myf, list):
        eps_by_year, nav_by_year = {}, {}
        for row in myf:
            y = row.get("year")
            if y is None:
                continue
            e = row.get("epsBasic")
            nv = row.get("nav")
            if e is not None:
                eps_by_year[int(y)] = e
            if nv is not None:
                nav_by_year[int(y)] = nv
        out["eps_by_year"] = eps_by_year
        out["nav_by_year"] = nav_by_year

    divh = _extract(p, "dividendHistory")
    if isinstance(divh, list) and divh:
        latest = max(divh, key=lambda d: d.get("year", 0))
        out["dividend"] = latest.get("cash")
        out["dividend_yield"] = latest.get("yieldPct")

    sp = _extract(p, "sharePattern")
    if isinstance(sp, list) and sp:
        pat = (sp[-1] or {}).get("pattern", {})
        out["sponsor_holding"] = pat.get("sponsor")
        out["govt_holding"] = pat.get("government")
        out["institute_holding"] = pat.get("institution")
        out["foreign_holding"] = pat.get("foreign")
        out["public_holding"] = pat.get("public")

    # Derived
    nav = out.get("nav")
    pu, fv = out.get("paid_up_capital"), out.get("face_value")
    if pu and fv:
        out["shares_outstanding"] = pu / fv
    shares = out.get("shares_outstanding")
    debt = out.get("total_debt_mn")
    if nav and shares and debt is not None:
        equity_mn = (nav * shares) / 1_000_000
        out["debt_equity"] = round(debt / equity_mn, 3) if equity_mn else None
    return out


def fetch_company(code: str, timeout: int = 25) -> Optional[dict]:
    try:
        r = requests.get(BASE + code.upper(), headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        d = parse_company(r.text)
        return d or None
    except Exception:
        return None
