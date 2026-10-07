"""
Settings across versions: stored values are kept as they are, and once per version the
user sees which settings are new, removed, changed or not usable (helios/settings_review.py).
"""
import json

import pytest
from fastapi.testclient import TestClient

from helios import config, settings_review

LOCAL = "http://127.0.0.1:8765"


@pytest.fixture
def home(monkeypatch, tmp_path):
    """A settings folder of its own; the active values are restored afterwards."""
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    before = config._current_values()
    yield tmp_path
    config._apply_settings(**before)


def _schema_without(*keys):
    return {k: v for k, v in settings_review.current_schema().items() if k not in keys}


def test_compare_lists_new_removed_changed_and_invalid():
    new_schema = settings_review.current_schema()
    old = _schema_without("auto_update")
    old["theme"] = {"default": "mission-slate", "rule": ["mission-slate", "deep-space"]}
    old["legacy_units"] = {"default": "metric", "rule": ["metric", "imperial"]}
    stored = {"processors": 2, "theme": "deep-space", "font_size": "huge", "timezone": "UTC",
              "legacy_units": "imperial", "beta_panel": True}
    out = settings_review.compare(stored, old, new_schema)
    assert out["new"] == [{"key": "auto_update", "default": True, "rule": [False, True]}]
    assert {r["key"]: r["stored"] for r in out["removed"]} == {"legacy_units": "imperial"}
    ch = out["changed"]
    assert [c["key"] for c in ch] == ["theme"] and ch[0]["valid"] and ch[0]["stored"] == "deep-space"
    assert ch[0]["old_rule"] == ["mission-slate", "deep-space"] and "high-contrast" in ch[0]["rule"]
    assert out["invalid"] == [{"key": "font_size", "stored": "huge", "rule": ["compact", "normal", "large"],
                               "default": "normal"}]
    # Unknown old schema (settings.json from a version before this review existed): the
    # stored keys stand for it, so settings missing from the file are new.
    out = settings_review.compare({"theme": "deep-space"}, None, new_schema)
    assert {r["key"] for r in out["new"]} == {"processors", "font_size", "timezone", "auto_update"}
    assert out["removed"] == out["changed"] == out["invalid"] == []
    out = settings_review.compare({"theme": "deep-space", "beta_panel": True}, None, new_schema)
    assert out["removed"] == [{"key": "beta_panel", "stored": True}]
    # An unusable value already reviewed is not listed again while it is unchanged.
    out = settings_review.compare(stored, old, new_schema, reviewed={"font_size": "huge"})
    assert out["invalid"] == []


def test_stored_values_are_kept_as_they_are(home):
    """Values this version cannot use stay in settings.json when the settings are saved."""
    (home / "settings.json").write_text(json.dumps(
        {"theme": "aurora-glass", "font_size": "large", "beta_panel": {"x": 1}, "timezone": "Europe/Oslo"}))
    config._apply_settings(theme="mission-slate", font_size="normal", timezone="UTC")
    config._load_saved_settings()
    assert (config.ACTIVE_THEME, config.ACTIVE_FONT_SIZE, config.ACTIVE_TIMEZONE) == ("mission-slate", "large", "Europe/Oslo")
    config.update_system_settings(processors=1)
    saved = json.loads((home / "settings.json").read_text())
    assert saved["theme"] == "aurora-glass" and saved["beta_panel"] == {"x": 1}
    assert saved["processors"] == 1 and saved["font_size"] == "large" and saved["auto_update"] is True
    # Picking a theme replaces the unusable value; the unknown entry stays.
    config.update_system_settings(theme="deep-space")
    saved = json.loads((home / "settings.json").read_text())
    assert saved["theme"] == "deep-space" and saved["beta_panel"] == {"x": 1}


def test_review_is_shown_once_per_version(home):
    client = TestClient(__import__("helios.api.server", fromlist=["app"]).app, base_url=LOCAL)
    # First start: nothing to compare, nothing shown, marker written.
    assert client.get("/api/settings/review").json() == {"show": False}
    assert json.loads((home / "settings_seen.json").read_text())["schema"] == settings_review.current_schema()
    # A settings.json written by an older version without auto_update and a stored value
    # this one cannot use: shown once, nothing stored is changed by showing it.
    (home / "settings_seen.json").unlink()
    stored = {"processors": 2, "theme": "deep-space", "font_size": "gigantic", "timezone": "UTC"}
    (home / "settings.json").write_text(json.dumps(stored))
    config._load_saved_settings()  # as at start-up
    rev = client.get("/api/settings/review").json()
    assert rev["show"] and [n["key"] for n in rev["changes"]["new"]] == ["auto_update"]
    assert rev["changes"]["invalid"][0]["key"] == "font_size" and rev["whats_new"] is None
    assert json.loads((home / "settings.json").read_text()) == stored
    # An invalid choice changes nothing.
    assert client.post("/api/settings/review", json={"settings": {"font_size": "tiny"}}).status_code == 422
    assert client.post("/api/settings/review", json={"settings": {"colour": "red"}}).status_code == 422
    assert not (home / "settings_seen.json").exists()
    # Accepting with a new font size: saved, the other stored values kept, not shown again.
    r = client.post("/api/settings/review", json={"settings": {"font_size": "compact"}})
    assert r.status_code == 200 and r.json()["font_size"] == "compact"
    saved = json.loads((home / "settings.json").read_text())
    assert saved["font_size"] == "compact" and saved["theme"] == "deep-space" and saved["processors"] == 2
    assert client.get("/api/settings/review").json() == {"show": False}
    # Keeping an unusable value and an unknown entry: both stay stored and are not shown again.
    (home / "settings.json").write_text(json.dumps({**saved, "font_size": "gigantic", "beta_panel": True}))
    (home / "settings_seen.json").unlink()
    config._load_saved_settings()
    rev = client.get("/api/settings/review").json()
    assert rev["show"] and rev["changes"]["removed"] == [{"key": "beta_panel", "stored": True}]
    assert client.post("/api/settings/review", json={"settings": {}}).status_code == 200
    saved = json.loads((home / "settings.json").read_text())
    assert saved["font_size"] == "gigantic" and saved["beta_panel"] is True
    assert client.get("/api/settings/review").json() == {"show": False}


def test_review_after_update_shows_release_notes_once(home):
    (home / "settings.json").write_text(json.dumps(config._current_values()))
    settings_review.write_marker()
    notes = {"tag": "v0.0.2", "name": "HELIOS-L1 0.0.2", "notes": "New: automatic updates."}
    # Same version as the marker: notes of an install already reviewed are not shown again.
    assert settings_review.pending(release_notes=notes) == {"show": False}
    marker = json.loads((home / "settings_seen.json").read_text())
    marker["version"] = "0.0.0"
    (home / "settings_seen.json").write_text(json.dumps(marker))
    rev = settings_review.pending(release_notes=notes)
    assert rev["show"] and rev["whats_new"] == notes and rev["previous_version"] == "0.0.0"
    assert not any(rev["changes"].values())
    settings_review.acknowledge({})
    assert settings_review.pending(release_notes=notes) == {"show": False}
