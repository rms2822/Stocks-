import requests
import logging

logging.basicConfig(
    filename=r"C:\dse analyzer\backend\auto_update.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

BASE = "http://127.0.0.1:8000"

def post(path):
    try:
        r = requests.post(f"{BASE}{path}", timeout=1800)
        logging.info(f"{path} -> {r.status_code} {r.text[:200]}")
    except Exception as e:
        logging.error(f"{path} failed: {e}")

logging.info("=== Auto update started ===")
post("/load-dse")
post("/load-fundamentals")
post("/load-history?days=30")
logging.info("=== Auto update complete ===")
