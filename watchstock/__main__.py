"""`python -m watchstock` — start the server and open the browser.

Windows notes:
- The browser is opened only once the server actually answers. On a first run,
  importing pandas/yfinance can take 10-30 s, and opening the page earlier shows
  "can't connect".
- Logs go to data/watchstock.log, not the console. If the user clicks inside a
  Windows console window (QuickEdit mode), every write to it blocks until they press
  a key, which looks like the app froze.
- Double-clicking start.bat while WatchStock is already running just opens the browser.
"""

import argparse
import logging
import logging.handlers
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from watchstock import config


def _already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/health", timeout=1) as resp:
            return b'"ok":true' in resp.read().replace(b" ", b"")
    except OSError:
        return False


def _open_when_ready(url: str, timeout: float = 120) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _already_running(url):
            webbrowser.open(url)
            return
        time.sleep(0.5)
    logging.getLogger(__name__).error("server did not come up within %ss", timeout)


def _setup_logging() -> None:
    handler = logging.handlers.RotatingFileHandler(
        config.data_dir() / "watchstock.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    # Keep yfinance's chatter out of the log unless it's a real problem.
    logging.getLogger("yfinance").setLevel(logging.ERROR)


def main() -> None:
    parser = argparse.ArgumentParser(prog="watchstock")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--port", type=int, default=config.PORT)
    args = parser.parse_args()
    url = f"http://{config.HOST}:{args.port}"

    if _already_running(url):
        print(f"WatchStock is already running at {url}. Opening it.")
        if not args.no_browser:
            webbrowser.open(url)
        return

    _setup_logging()
    print(f"\n  WatchStock is starting at {url}")
    print("  Your browser opens when it's ready. Close this window to stop WatchStock.")
    print(f"  Log file: {config.data_dir() / 'watchstock.log'}\n")
    sys.stdout.flush()

    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run(
        "watchstock.app:app",
        host=config.HOST,
        port=args.port,
        log_config=None,  # use our file logging
        access_log=False,
    )


if __name__ == "__main__":
    main()
