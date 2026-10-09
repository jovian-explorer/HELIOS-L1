# -*- mode: python ; coding: utf-8 -*-
# Cross-platform PyInstaller spec for HELIOS-L1. Build with: python packaging/build.py
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
PKG = ROOT / "helios"

a = Analysis(
    [str(PKG / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(PKG / "gui" / "static"), "helios/gui/static"),
        (str(PKG / "data" / "spice_kernels"), "helios/data/spice_kernels"),
        (str(PKG / "data" / "icme_richardson_cane.json"), "helios/data"),
        (str(PKG / "data" / "ipshocks_l1.json"), "helios/data"),
    ],
    hiddenimports=[
        "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "webview", "spiceypy",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="HELIOS-L1",
    debug=False,
    strip=False,
    upx=False,
    console=True,
    icon=str(ROOT / "assets" / "helios.ico") if sys.platform == "win32" else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="HELIOS-L1",
)
