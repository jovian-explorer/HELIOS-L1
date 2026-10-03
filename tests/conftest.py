"""
Shared pytest configuration.

* Points HELIOS_HOME at a throw-away folder before any helios module is imported,
  so the suite never reads or writes the user's real cache and log folders.
* Blocks network access by default: DataDownloader.fetch_json and fetch_text (CDAWeb
  HAPI) return None, which exercises the documented offline path. Tests that need
  specific archive payloads patch them themselves.
"""
import os
import shutil
import tempfile

import pytest

_TEST_HOME = tempfile.mkdtemp(prefix="helios-test-home-")
os.environ["HELIOS_HOME"] = _TEST_HOME


@pytest.fixture(autouse=True)
def _offline_downloader(monkeypatch):
    from helios.core.downloader import DataDownloader

    async def _no_network(self, url, cache_key):
        return None

    async def _no_text(self, url, timeout=120.0):
        return None

    monkeypatch.setattr(DataDownloader, "fetch_json", _no_network)
    monkeypatch.setattr(DataDownloader, "fetch_text", _no_text)
    yield


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_HOME, ignore_errors=True)
