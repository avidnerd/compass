"""`compass` — start the local app and open it.

Deliberately a launcher, not a desktop wrapper. Compass's focus monitoring uses
`navigator.mediaDevices.getDisplayMedia`, which is broken or absent in embedded
webviews: Tauri's webview cannot raise the macOS screen-picker, and Electron
requires its own `desktopCapturer` API instead. Serving on loopback and opening
the user's real browser keeps that feature working, keeps the install small, and
leaves the architecture exactly as it already is — one process already serves
the API, the WebSocket and the built SPA.
"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser
from pathlib import Path


def _free_port(preferred: int) -> int:
    """Use the preferred port when it is free, otherwise let the OS choose.

    A student running this is not going to debug "address already in use".
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _spa_built() -> bool:
    from .main import SPA_DIST
    return (SPA_DIST / "index.html").exists()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="compass", description="Run Compass locally.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1",
                        help="Loopback by default; Compass holds your own data.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser.")
    parser.add_argument("--data-dir", help="Where the database and app secret live.")
    args = parser.parse_args(argv)

    if args.data_dir:
        import os
        os.environ["COMPASS_DATA_DIR"] = args.data_dir

    from .config import DATA_DIR, settings

    if not settings.app_secret:
        print(f"compass: cannot write to {DATA_DIR}. Pass --data-dir, or set "
              "COMPASS_APP_SECRET yourself.", file=sys.stderr)
        return 1

    if not _spa_built():
        print("compass: the web interface is not built. From a source checkout run "
              "`make build` first.", file=sys.stderr)
        return 1

    port = _free_port(args.port)
    url = f"http://{'localhost' if args.host == '127.0.0.1' else args.host}:{port}"

    print(f"Compass  →  {url}")
    print(f"Data     →  {DATA_DIR}")
    print("Add your own free OpenRouter key in Settings → Connections.")
    print("Ctrl-C to stop.\n")

    if not args.no_browser:
        # After the server is listening, not before, or the tab races the bind.
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
