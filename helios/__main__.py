"""
HELIOS-L1 command-line entry point: `helios` or `python -m helios`.
"""
import argparse

from helios import __version__
from helios.config import DEFAULT_HOST, DEFAULT_PORT


def main():
    parser = argparse.ArgumentParser(
        prog="helios",
        description="HELIOS-L1: Scientific data analysis and visualization suite for Sun-Earth L1 missions."
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host address (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port number (default: {DEFAULT_PORT})")
    parser.add_argument("--headless", action="store_true", help="Run in headless server mode without desktop window")
    parser.add_argument("--browser", action="store_true", help="Force opening in default system web browser")
    parser.add_argument("--version", action="version", version=f"HELIOS-L1 {__version__}")

    args = parser.parse_args()

    # Imported here so `--help`/`--version` stay fast.
    from helios.gui.app import launch_desktop

    launch_desktop(
        host=args.host,
        port=args.port,
        headless=args.headless,
        force_browser=args.browser
    )


if __name__ == "__main__":
    main()
