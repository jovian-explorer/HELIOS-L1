"""
Desktop application launcher and window management for HELIOS-L1.
Initializes background FastAPI server and launches pywebview native window
with automatic fallback to system web browser.
"""
import sys
import time
import socket
import threading
import webbrowser
import logging
import urllib.request
import json
from typing import Tuple

import uvicorn

from helios.config import DEFAULT_HOST, DEFAULT_PORT, LOG_DIR
from helios.api.guard import is_loopback_host
from helios.api.server import app


def _setup_logging():
    """Log launcher events to the per-user HELIOS log directory."""
    logging.basicConfig(
        filename=str(LOG_DIR / "helios_app.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

def check_bind_host(host: str) -> None:
    """
    Raise ValueError unless `host` is a loopback address. The API changes settings and
    reads imported files; bound to 0.0.0.0 or a LAN address it would be open to the network.
    """
    if not is_loopback_host(host):
        raise ValueError(f"HELIOS-L1 only listens on the local machine (127.0.0.1, localhost or ::1), not {host!r}.")


def _url_host(host: str) -> str:
    """Host as written in a URL (IPv6 addresses in brackets)."""
    h = host.strip("[]")
    return f"[{h}]" if ":" in h else h


def _family(host: str) -> int:
    return socket.AF_INET6 if ":" in host.strip("[]") else socket.AF_INET


def is_port_in_use(port: int, host: str = DEFAULT_HOST) -> bool:
    """Check if server port is already bound."""
    with socket.socket(_family(host), socket.SOCK_STREAM) as s:
        return s.connect_ex((host.strip("[]"), port)) == 0

def check_existing_helios(host: str, port: int) -> bool:
    """Check if HELIOS-L1 is already running on the given host/port."""
    try:
        req = urllib.request.Request(f"http://{_url_host(host)}:{port}/api/status", headers={"User-Agent": "HELIOS-Launcher"})
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("app_name") == "HELIOS-L1"
    except (OSError, ValueError):  # refused, timed out, HTTP error, not JSON
        pass
    return False

def find_available_port(host: str = DEFAULT_HOST, preferred_port: int = DEFAULT_PORT) -> int:
    """Find an available port or reuse existing HELIOS instance."""
    if check_existing_helios(host, preferred_port):
        return preferred_port
    for p in range(preferred_port, preferred_port + 50):
        with socket.socket(_family(host), socket.SOCK_STREAM) as s:
            try:
                s.bind((host.strip("[]"), p))
                return p
            except OSError:
                continue
    return preferred_port  # all busy: the server start then fails with a clear message

def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Tuple[uvicorn.Server, threading.Thread]:
    """Run the uvicorn server in a daemon thread; returns the server (its `started` flag) and the thread."""
    config = uvicorn.Config(
        app=app,
        host=host.strip("[]"),
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.start_error = None

    def run():
        try:
            server.run()
        except (OSError, SystemExit) as exc:  # bind failure (uvicorn raises or exits)
            server.start_error = exc
            logging.error("HELIOS-L1 server failed to start on %s:%s: %s", host, port, exc)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return server, thread

def wait_for_server(server: uvicorn.Server, thread: threading.Thread, timeout: float = 15.0) -> bool:
    """
    Wait until this server is listening. False if its thread ended first (uvicorn could not
    bind the port) or the timeout passed. Checking only whether something answers on the
    port, as before, mistook another program on that port for HELIOS-L1.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.started:
            return True
        if not thread.is_alive():
            return False
        thread.join(0.05)
    return bool(server.started)

def launch_desktop(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    headless: bool = False,
    force_browser: bool = False
):
    """Launch the HELIOS-L1 application."""
    _setup_logging()
    print("=" * 65)
    print(" HELIOS-L1: Heliophysical Exploration & L1 Space-weather Suite")
    print("=" * 65)
    try:
        check_bind_host(host)
    except ValueError as exc:
        print(f"[!] {exc}")
        logging.error(str(exc))
        sys.exit(2)

    actual_port = find_available_port(host, port)
    is_existing = check_existing_helios(host, actual_port)

    url = f"http://{_url_host(host)}:{actual_port}"
    logging.info(f"Launching HELIOS-L1 on {url} (Existing instance: {is_existing})")

    if not is_existing:
        print(f"[*] Starting local scientific telemetry engine on {url}")
        server, server_thread = start_server(host, actual_port)
        if not wait_for_server(server, server_thread):
            if server_thread.is_alive():
                msg = f"The HELIOS-L1 server did not start on {host}:{actual_port} within 15 s."
            else:
                msg = (f"The HELIOS-L1 server could not listen on {host}:{actual_port}: the port is in use by "
                       f"another program or not permitted. Close that program or start HELIOS-L1 with "
                       f"--port <a free port>."
                       + (f" ({server.start_error})" if isinstance(server.start_error, OSError) else ""))
            print(f"[!] {msg}")
            logging.error(msg)
            sys.exit(1)
    else:
        print(f"[+] Reconnecting to active HELIOS-L1 engine on {url}")

    print(f"[+] Engine online: {url}")

    if headless:
        print("[i] Running in headless server mode. Press Ctrl+C to terminate.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[*] Shutting down HELIOS-L1 engine.")
            sys.exit(0)

    if not force_browser:
        try:
            import webview
            print("[+] Initializing native desktop UI window...")
            webview.create_window(
                title="HELIOS-L1 | Space Weather & L1 Heliophysics Observatory",
                url=url,
                width=1320,
                height=880,
                min_size=(960, 600)
            )
            # Keep the window's browser storage between runs (pywebview defaults to a
            # private session, which forgot every preference and the incident log).
            from helios.config import WEBVIEW_STORAGE_DIR
            try:
                webview.start(private_mode=False, storage_path=str(WEBVIEW_STORAGE_DIR))
            except TypeError:  # pywebview without these options
                webview.start()
            logging.info("Desktop window closed normally.")
            return
        except Exception as e:  # not BaseException: Ctrl+C or a window-close exit must not open a browser
            logging.warning(f"Native webview fallback triggered: {e}")
            print(f"[i] Native webview notice: {e}. Launching default browser interface.")

    # Browser fallback
    print(f"[+] Opening {url} in your system web browser...")
    webbrowser.open(url)
    print("[i] HELIOS-L1 application is running. Keep this console window open.")
    print("[i] Press Ctrl+C in this terminal to shut down the server.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down HELIOS-L1 engine.")
        sys.exit(0)
