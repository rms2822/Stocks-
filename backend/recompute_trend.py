import sqlite3
from app.analysis.eps_trend import robust_eps_trend

con = sqlite3.connect("dse.db")
cur = con.cursor()
rows = cur.execute("""SELECT ticker, eps_2021, eps_2022, eps_2023, eps_2024, eps_2025
                      FROM fundamentals""").fetchall()
n = 0
for tk, *eps in rows:
    hist = {2021+i: {"eps": e} for i, e in enumerate(eps) if e is not None}
    if len(hist) >= 2:
        cur.execute("UPDATE fundamentals SET eps_trend=? WHERE ticker=?",
                    (robust_eps_trend(hist), tk))
        n += 1
con.commit(); con.close()
print(f"Recomputed eps_trend for {n} tickers")