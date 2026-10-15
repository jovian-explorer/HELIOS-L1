"""
Shared pytest configuration.

* Every run works in folders of its own, so suites run at the same time (also with the same
  --basetemp) do not touch each other's files:
  - HELIOS_HOME points at a throw-away folder, set before any helios module is imported, so
    the suite never reads or writes the user's real cache and log folders;
  - pytest empties a --basetemp folder whenever a run starts. A second run given the same
    --basetemp therefore deleted the temporary files of a run in progress. With --basetemp
    the run now uses <basetemp>/run-*/tmp (and HELIOS_HOME <basetemp>/run-*/home); the
    folder is removed after a run without failures and kept for inspection otherwise.
    Leftovers older than a day are removed when a run starts.
  - If these folders are deleted while the suite runs (a cleanup elsewhere), they are
    created again before the next test. Before, every later test that used tmp_path failed
    in setup (the one-off "287 passed, 19 errors").
* Blocks network access by default: DataDownloader.fetch_json, fetch_text (CDAWeb
  HAPI) and fetch_bytes (images) return None, which exercises the documented offline path. Tests that need
  specific archive payloads patch them themselves.
"""
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

_RUN_DIR = None

# CI runs a copy of tests/ against the installed package, so files of the package are found
# through it, and files only in the source tree (scripts/, packaging/, pyproject.toml) skip
# the tests that need them there.
SOURCE_ROOT = Path(__file__).resolve().parents[1]


def package_dir() -> Path:
    import helios
    return Path(helios.__file__).resolve().parent


def source_root() -> Path:
    if not (SOURCE_ROOT / "pyproject.toml").is_file():
        pytest.skip("needs the source tree (scripts/, packaging/, pyproject.toml)")
    return SOURCE_ROOT


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    # tryfirst: before pytest's own tmpdir plugin reads config.option.basetemp.
    global _RUN_DIR
    given = config.option.basetemp
    if given:
        root = Path(given).resolve()
        root.mkdir(parents=True, exist_ok=True)
        for old in root.iterdir():
            try:
                if time.time() - old.stat().st_mtime > 86400:
                    shutil.rmtree(old) if old.is_dir() else old.unlink()
            except OSError:
                pass
        _RUN_DIR = Path(tempfile.mkdtemp(prefix="run-", dir=root))
        config.option.basetemp = str(_RUN_DIR / "tmp")
    else:
        _RUN_DIR = Path(tempfile.mkdtemp(prefix="helios-test-home-"))
    os.environ["HELIOS_HOME"] = str(_RUN_DIR / "home")


@pytest.fixture(autouse=True)
def _run_folders_exist(tmp_path_factory):
    # Autouse fixtures are set up before tmp_path, so a folder deleted mid-run is back in time.
    from helios import config
    for folder in (tmp_path_factory.getbasetemp(), config.CACHE_DIR, config.LOG_DIR, config.CONFIG_DIR):
        folder.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _offline_downloader(monkeypatch):
    from helios.core.downloader import DataDownloader

    async def _no_network(self, url, cache_key):
        return None

    async def _no_text(self, url, timeout=120.0):
        return None

    monkeypatch.setattr(DataDownloader, "fetch_json", _no_network)
    # The ICME list is read from its bundled snapshot (no live page in tests).
    from helios.core import icme_catalog
    monkeypatch.setattr(icme_catalog, "_fetch_live", lambda cache_dir: None)
    monkeypatch.setattr(DataDownloader, "fetch_text", _no_text)
    monkeypatch.setattr(DataDownloader, "fetch_bytes", _no_text)
    # SPICE kernels and JPL Horizons (positions, occultation): offline unless network tests run,
    # and no failure is remembered from one test to the next.
    if os.environ.get("HELIOS_NETWORK_TESTS") != "1":
        from helios.core import occultation

        def _no_download(url):
            raise OSError("network disabled in tests")
        monkeypatch.setattr(occultation, "_get", _no_download)
    from helios.core import ephemeris
    ephemeris._failed.clear()
    if os.environ.get("HELIOS_NETWORK_TESTS") != "1":
        monkeypatch.setattr(ephemeris, "state", _recorded_state)
    yield


_RECORDED = None


def _recorded_state(body, t, cache_dir):
    """
    Offline stand-in for helios.core.ephemeris.state: JPL Horizons vectors recorded in
    tests/data/ephemeris/horizons_2026.json.gz (heliocentric, ecliptic J2000, km and km/s;
    daily through 2026, every 10 min for GOES-19 on 9-10 Oct 2026; the L1 spacecraft only up to
    14 Oct 2026, where Horizons' coverage ended), cubic Hermite between samples. None outside
    them, as the real function answers without a kernel.
    """
    global _RECORDED
    import gzip
    import json
    import numpy as np
    if _RECORDED is None:
        path = Path(__file__).parent / "data" / "ephemeris" / "horizons_2026.json.gz"
        _RECORDED = {k: np.array(v) for k, v in json.loads(gzip.decompress(path.read_bytes())).items()}
    rows = _RECORDED.get(body)
    if rows is None:
        return None
    jd = t.timestamp() / 86400.0 + 2440587.5
    i = int(np.searchsorted(rows[:, 0], jd))
    if i == 0 or i >= len(rows):
        return None
    (j0, *s0), (j1, *s1) = rows[i - 1], rows[i]
    h, u = (j1 - j0) * 86400.0, (jd - j0) / (j1 - j0)
    p0, v0, p1, v1 = np.array(s0[:3]), np.array(s0[3:]), np.array(s1[:3]), np.array(s1[3:])
    h00, h10, h01, h11 = 2*u**3 - 3*u**2 + 1, u**3 - 2*u**2 + u, -2*u**3 + 3*u**2, u**3 - u**2
    pos = h00 * p0 + h10 * h * v0 + h01 * p1 + h11 * h * v1
    d00, d10, d01, d11 = 6*u**2 - 6*u, 3*u**2 - 4*u + 1, -6*u**2 + 6*u, 3*u**2 - 2*u
    vel = (d00 * p0 + d01 * p1) / h + d10 * v0 + d11 * v1
    return pos, vel


def pytest_sessionfinish(session, exitstatus):
    if _RUN_DIR is None:
        return
    keep = session.config.option.basetemp and exitstatus != 0
    shutil.rmtree(_RUN_DIR / "home" if keep else _RUN_DIR, ignore_errors=True)
