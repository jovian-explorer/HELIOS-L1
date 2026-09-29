"""
Desktop application launcher and window management for HELIOS-L1.
Initializes background FastAPI server and launches pywebview native window
with automatic fallback to system web browser.
"""
import sys
import os
import time
import socket
import threading
import webbrowser
import logging
import urllib.request
import json
import uvicorn

from helios.config import DEFAULT_HOST, DEFAULT_PORT, LOG_DIR
from helios.api.server import app


def _setup_logging():
    """Log launcher events to the per-user HELIOS log directory."""
    logging.basicConfig(
        filename=str(LOG_DIR / "helios_app.log"),
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

def is_port_in_use(port: int, host: str = DEFAULT_HOST) -> bool:
    """Check if server port is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def check_existing_helios(host: str, port: int) -> bool:
    """Check if HELIOS-L1 is already running on the given host/port."""
    try:
        req = urllib.request.Request(f"http://{host}:{port}/api/status", headers={"User-Agent": "HELIOS-Launcher"})
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("app_name") == "HELIOS-L1"
    except Exception:
        pass
    return False

def find_available_port(host: str = DEFAULT_HOST, preferred_port: int = DEFAULT_PORT) -> int:
    """Find an available port or reuse existing HELIOS instance."""
    if check_existing_helios(host, preferred_port):
        return preferred_port
    for p in range(preferred_port, preferred_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
    return preferred_port

def start_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
    """Run uvicorn server in worker thread."""
    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False
    )
    server = uvicorn.Server(config)
    server.run()

def wait_for_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout: float = 6.0) -> bool:
    """Wait until backend server is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        if is_port_in_use(port, host):
            return True
        time.sleep(0.1)
    return False

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

    actual_port = find_available_port(host, port)
    is_existing = check_existing_helios(host, actual_port)

    url = f"http://{host}:{actual_port}"
    logging.info(f"Launching HELIOS-L1 on {url} (Existing instance: {is_existing})")

    if not is_existing:
        print(f"[*] Starting local scientific telemetry engine on {url}")
        server_thread = threading.Thread(target=start_server, args=(host, actual_port), daemon=True)
        server_thread.start()

        if not wait_for_server(host, actual_port):
            print(f"[!] Warning: Server startup timeout on {host}:{actual_port}. Attempting connection anyway...")
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
            window = webview.create_window(
                title="HELIOS-L1 | Space Weather & L1 Heliophysics Observatory",
                url=url,
                width=1320,
                height=880,
                min_size=(960, 600)
            )
            webview.start()
            logging.info("Desktop window closed normally.")
            return
        except (Exception, BaseException) as e:
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
