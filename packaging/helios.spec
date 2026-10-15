# -*- mode: python ; coding: utf-8 -*-
# Cross-platform PyInstaller spec for HELIOS-L1. Build with: python packaging/build.py
import sys
from importlib.metadata import PackageNotFoundError, requires
from pathlib import Path

from packaging.requirements import Requirement

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent
PKG = ROOT / "helios"

# Package metadata the [solar] extra reads at run time: sunpy checks its "map" and "net"
# extras by it, and streamtracer (under sunkit-magex) asks for its own version.
_solar_metadata = []
try:
    _solar_metadata += copy_metadata("sunkit-magex", recursive=True)
    for _req in map(Requirement, requires("sunpy") or []):
        if _req.marker and any(_req.marker.evaluate({"extra": e}) for e in ("map", "net")):
            _solar_metadata += copy_metadata(_req.name)
except PackageNotFoundError:  # a build without the [solar] extra
    pass

a = Analysis(
    [str(PKG / "__main__.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(PKG / "gui" / "static"), "helios/gui/static"),
        (str(PKG / "data" / "spice_kernels"), "helios/data/spice_kernels"),
        (str(PKG / "data" / "icme_richardson_cane.json"), "helios/data"),
        (str(PKG / "data" / "ipshocks_l1.json"), "helios/data"),
        (str(PKG / "data" / "omni_events.json.gz"), "helios/data"),
        *_solar_metadata,
        # cdflib reads its leap-second table (CDFLeapSeconds.txt) at run time (STEREO-A beacon)
        *collect_data_files("cdflib"),
    ],
    hiddenimports=[
        "uvicorn.logging", "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols", "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets", "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan", "uvicorn.lifespan.on",
        "webview", "spiceypy",
        # The [solar] extra (solar image FITS, PFSS, occultation field): sunpy and astropy
        # come with PyInstaller hooks; sunkit-magex has none.
        *collect_submodules("sunkit_magex", filter=lambda m: "tests" not in m.split(".")),
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest"],
    noarchive=False,
)

# Leave out the data files of the libraries' test suites (astropy's hook takes them all);
# the test modules stay, as astropy imports its test runner on import.
a.datas = [t for t in a.datas if not {"tests", "test"} & set(t[0].replace("\\", "/").split("/"))]
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
