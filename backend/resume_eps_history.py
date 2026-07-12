import requests
from bs4 import BeautifulSoup
import sqlite3
import time
from app.analysis.eps_trend import robust_eps_trend

conn = sqlite3.connect("dse.db")
cur = conn.cursor()

def scrape_eps_history(ticker, retries=3):
    url = f"https://www.dsebd.org/displayCompany.php?name={ticker}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for attempt in range(retries):
        try:
            r = requests.get(url, headers=headers, timeout=20)
            soup = BeautifulSoup(r.text, "html.parser")
            lines = [l.strip() for l in soup.get_text(separator="\n").split("\n") if l.strip()]
            history = {}
            for i, line in enumerate(lines):
                if line in ["2021","2022","2023","2024","2025"] and i+7 < len(lines):
                    year = int(line)
                    if year in history:
                        continue
                    try:
                        eps = float(lines[i+4])
                        nav = float(lines[i+7])
                        if nav > 5:
                            history[year] = {"eps": eps, "nav": nav}
                    except:
                        try:
                            eps = float(lines[i+4])
                            nav = float(lines[i+5])
                            if nav > 5 and nav != eps:
                                history[year] = {"eps": eps, "nav": nav}
                        except:
                            pass
            return history
        except Exception as e:
            if attempt < retries-1:
                time.sleep(3)
            else:
                return {}
    return {}

from app.analysis.eps_trend import robust_eps_trend   # add at top

def calc_trend(history):
    return robust_eps_trend(history)

# Only process stocks that don't have history yet
cur.execute("""SELECT s.ticker FROM stocks s
LEFT JOIN fundamentals f ON s.ticker=f.ticker
WHERE f.eps_2025 IS NULL OR f.eps_2024 IS NULL
ORDER BY s.ticker""")
tickers = [r[0] for r in cur.fetchall()]
print(f"Resuming - {len(tickers)} stocks still need history...")

success = 0
for i, ticker in enumerate(tickers):
    history = scrape_eps_history(ticker)
    if history:
        trend = calc_trend(history)
        cur.execute("""UPDATE fundamentals SET
            eps_2021=?, eps_2022=?, eps_2023=?, eps_2024=?, eps_2025=?,
            nav_2021=?, nav_2022=?, nav_2023=?, nav_2024=?, nav_2025=?, eps_trend=?
            WHERE ticker=?""", (
            history.get(2021,{}).get("eps"), history.get(2022,{}).get("eps"),
            history.get(2023,{}).get("eps"), history.get(2024,{}).get("eps"),
            history.get(2025,{}).get("eps"), history.get(2021,{}).get("nav"),
            history.get(2022,{}).get("nav"), history.get(2023,{}).get("nav"),
            history.get(2024,{}).get("nav"), history.get(2025,{}).get("nav"),
            trend, ticker))
        conn.commit()
        success += 1
    if (i+1) % 20 == 0:
        print(f"Progress: {i+1}/{len(tickers)} | Success: {success}")
    time.sleep(1)

conn.close()
print(f"Done! Loaded history for {success} more stocks")
