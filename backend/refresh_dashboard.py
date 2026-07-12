"""refresh_dashboard.py -- one-command daily refresh of the analysis dashboard.

Runs the full pipeline end to end and degrades gracefully:

    1. init the DB and start the FastAPI backend
    2. scrape fresh DSE prices + fundamentals (needs internet access to dsebd.org)
    3. run full_scan.py       -> full_analysis.csv / .json
    4. run clean_analysis.py  -> full_analysis_clean.csv / .json  (fix data quality)
    5. run build_dashboard.py -> analysis_dashboard.html

If the data-refresh steps (1-3) fail -- e.g. dsebd.org is unreachable from the
current network -- the script logs the failure and still rebuilds the dashboard
from whatever full_analysis.csv is already committed, so the artifact is never
left broken. Exit code is 0 on a full or fallback refresh, 1 only if even the
rebuild fails.

Intended to be invoked by CI (GitHub Actions, where dsebd.org is reachable) or
by a human/agent locally:  python refresh_dashboard.py [--no-scan]
"""
from __future__ import annotations

import subprocess
import sys
import time
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
API = "http://127.0.0.1:8000"


def log(msg):
    print(f"[refresh] {msg}", flush=True)


def run(cmd, **kw):
    log("$ " + " ".join(cmd))
    return subprocess.run(cmd, cwd=HERE, **kw)


def wait_for_health(timeout=60):
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(API + "/", timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1.5)
    return False


def post(path, timeout):
    import urllib.request
    try:
        req = urllib.request.Request(API + path, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            log(f"POST {path} -> {r.status}")
            return True
    except Exception as e:
        log(f"POST {path} FAILED: {e}")
        return False


def refresh_data() -> bool:
    """Start the backend, scrape fresh data, and regenerate full_analysis.csv.

    Returns True only if full_scan.py completes; False on any failure so the
    caller can fall back to rebuilding from existing data.
    """
    run([PY, "init_db.py"])

    log("starting backend (uvicorn)...")
    server = subprocess.Popen(
        [PY, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=HERE, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        if not wait_for_health():
            log("backend did not become healthy in time")
            return False

        # Best-effort data loads. Prices are essential; history is optional.
        if not post("/load-dse", timeout=600):
            return False
        post("/load-fundamentals", timeout=1200)
        post("/load-history?days=30", timeout=1800)

        r = run([PY, "full_scan.py"])
        return r.returncode == 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=15)
        except subprocess.TimeoutExpired:
            server.kill()
        log("backend stopped")


def rebuild_dashboard() -> bool:
    """clean_analysis + build_dashboard from whatever full_analysis.csv exists."""
    ok = run([PY, "clean_analysis.py"]).returncode == 0
    ok = run([PY, "build_dashboard.py"]).returncode == 0 and ok
    return ok


def main():
    skip_scan = "--no-scan" in sys.argv
    if not os.path.exists(os.path.join(HERE, "full_analysis.csv")) and skip_scan:
        log("--no-scan given but no full_analysis.csv exists; nothing to rebuild")
        return 1

    scanned = False
    if not skip_scan:
        try:
            scanned = refresh_data()
        except Exception as e:
            log(f"data refresh crashed: {e}")
        if scanned:
            log("live data refresh OK")
        else:
            log("live data refresh unavailable -> rebuilding from existing CSV")
    else:
        log("--no-scan: rebuilding dashboard from existing CSV only")

    if not rebuild_dashboard():
        log("dashboard rebuild FAILED")
        return 1
    log(f"done ({'live data' if scanned else 'existing data'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
