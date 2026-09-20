#!/usr/bin/env python3
"""
HELIOS-L1: Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite
Main Application Entry Point.
"""
import sys
import argparse
from pathlib import Path

# Ensure root directory is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from helios.config import DEFAULT_HOST, DEFAULT_PORT
from helios.gui.app import launch_desktop

def main():
    parser = argparse.ArgumentParser(
        description="HELIOS-L1: Scientific data analysis and visualization suite for Sun-Earth L1 missions."
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Host address (default: {DEFAULT_HOST})")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Port number (default: {DEFAULT_PORT})")
    parser.add_argument("--headless", action="store_true", help="Run in headless server mode without desktop window")
    parser.add_argument("--browser", action="store_true", help="Force opening in default system web browser")

    args = parser.parse_args()

    launch_desktop(
        host=args.host,
        port=args.port,
        headless=args.headless,
        force_browser=args.browser
    )

if __name__ == "__main__":
    main()
