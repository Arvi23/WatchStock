"""`python -m watchstock` — start the server and open the browser."""

import argparse
import logging
import threading
import webbrowser

import uvicorn

from watchstock import config


def main() -> None:
    parser = argparse.ArgumentParser(prog="watchstock")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    parser.add_argument("--port", type=int, default=config.PORT)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    url = f"http://{config.HOST}:{args.port}"
    print(f"\n  WatchStock is running at {url}\n  Close this window to stop it.\n")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    uvicorn.run("watchstock.app:app", host=config.HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
