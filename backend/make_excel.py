"""make_excel.py — build a formatted single-sheet Excel workbook from full_analysis.csv"""
import csv
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SRC = "full_analysis.csv"
OUT = "full_analysis.xlsx"

INT_COLS = {"volume"}
PCT_COLS = {"percent_change", "eps_trend"}
SCORE_COLS = {"combined_score", "tech_score", "fund_score", "rsi", "volume_ratio", "pct_from_52h"}
MONEY_COLS = {"ltp", "sma20", "sma50", "eps", "pe", "nav", "pb", "debt_equity", "macd_hist"}

REC_FILL = {
    "BUY": PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid"),
    "HOLD": PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid"),
    "SELL": PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid"),
}
REC_FONT = {
    "BUY": Font(color="006100", bold=True),
    "HOLD": Font(color="9C6500", bold=True),
    "SELL": Font(color="9C0006", bold=True),
}

with open(SRC, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    cols = reader.fieldnames
    rows = list(reader)

wb = Workbook()
ws = wb.active
ws.title = "Full Analysis"

header_fill = PatternFill(start_color="305496", end_color="305496", fill_type="solid")
header_font = Font(color="FFFFFF", bold=True)
thin = Side(style="thin", color="D9D9D9")
border = Border(left=thin, right=thin, top=thin, bottom=thin)

for c, name in enumerate(cols, 1):
    cell = ws.cell(row=1, column=c, value=name.replace("_", " ").title())
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="center", vertical="center")
    cell.border = border

for r, row in enumerate(rows, 2):
    rec = row.get("recommendation", "")
    for c, name in enumerate(cols, 1):
        raw = row[name]
        val = raw
        if raw == "" or raw is None:
            val = None
        elif name in INT_COLS:
            val = int(float(raw))
        elif name in PCT_COLS | SCORE_COLS | MONEY_COLS:
            try:
                val = float(raw)
            except ValueError:
                val = raw
        cell = ws.cell(row=r, column=c, value=val)
        cell.border = border
        if name in MONEY_COLS or name in SCORE_COLS:
            cell.number_format = "0.00"
        elif name in PCT_COLS:
            cell.number_format = "0.0"
        elif name in INT_COLS:
            cell.number_format = "#,##0"
        if name == "recommendation" and rec in REC_FILL:
            cell.fill = REC_FILL[rec]
            cell.font = REC_FONT[rec]
            cell.alignment = Alignment(horizontal="center")
        if name == "ticker":
            cell.font = Font(bold=True)

widths = {
    "ticker": 12, "sector": 26, "ltp": 9, "percent_change": 10, "volume": 12,
    "combined_score": 10, "tech_score": 9, "fund_score": 9, "recommendation": 12,
    "rsi": 8, "macd_hist": 10, "volume_ratio": 10, "pct_from_52h": 11,
    "sma20": 9, "sma50": 9, "eps": 8, "pe": 10, "nav": 9, "pb": 8,
    "eps_trend": 10, "debt_equity": 11,
}
for c, name in enumerate(cols, 1):
    ws.column_dimensions[get_column_letter(c)].width = widths.get(name, 12)

ws.freeze_panes = "A2"
ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{len(rows)+1}"

wb.save(OUT)
print(f"Wrote {OUT} with {len(rows)} rows")
