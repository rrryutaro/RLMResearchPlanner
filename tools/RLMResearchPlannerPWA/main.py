from __future__ import annotations

import argparse
import contextlib
import http.server
import socket
import threading
import webbrowser
from functools import partial
from pathlib import Path


APP_HOST = "127.0.0.1"
DEFAULT_PORT = 4173
TOOL_ROOT = Path(__file__).resolve().parent


class _NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def log_message(self, format: str, *args: object) -> None:
        print(f"[{self.log_date_time_string()}] {format % args}")


def _port_accepts_connections(port: int) -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as client:
        client.settimeout(0.25)
        return client.connect_ex((APP_HOST, port)) == 0


def run(*, port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    url = f"http://{APP_HOST}:{port}/"
    if _port_accepts_connections(port):
        if open_browser:
            webbrowser.open(url)
        print(f"既にローカルサーバーが起動しています: {url}")
        return 0

    handler = partial(_NoCacheHandler, directory=str(TOOL_ROOT))
    server = http.server.ThreadingHTTPServer((APP_HOST, port), handler)
    if open_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    print("RLM Research Planner PWA")
    print(f"URL: {url}")
    print("このウィンドウを閉じるとローカル版を終了します。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="RLM Research Planner PWA local server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    return run(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
