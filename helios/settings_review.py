"""
What changed in the settings between the version that wrote settings.json and this one.

Another version (an update, or an older copy started again) may have settings this one
lacks, lack settings this one has, or allow other values. Nothing stored is changed when
that happens: every stored value this version can use is used as it is, and the others
stay in settings.json (config.update_system_settings writes them back). Once per version
the user is shown what changed, together with the release notes after an automatic
update, and can keep the values or pick others; the settings this version had when they
saw it are then kept in ``settings_seen.json`` beside settings.json and the next
comparison starts from there.

A first start (no settings.json yet) has nothing to compare and shows nothing.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from helios import __version__
from helios import config


def marker_path() -> Path:
    return config.CONFIG_DIR / "settings_seen.json"


def current_schema() -> Dict[str, Dict[str, Any]]:
    """Each setting of this version with its default and allowed values."""
    rules = config.setting_rules()
    return {key: {"default": config.SETTING_DEFAULTS[key], "rule": rules[key]} for key in config.SETTING_KEYS}


def compare(stored: Dict[str, Any], old_schema: Optional[Dict[str, Dict[str, Any]]],
            new_schema: Dict[str, Dict[str, Any]],
            reviewed: Optional[Dict[str, Any]] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    The differences that concern the user.

    ``stored``: settings.json as written; ``old_schema``: the schema of the version the user
    last reviewed (None when unknown: the stored keys stand for it). Returns
      new      settings this version has and the old one had not: {key, default, rule}
      removed  settings of the old version (the stored keys when it is unknown) that this
               one has not: {key, stored}
      changed  settings whose allowed values or default changed:
               {key, rule, old_rule, default, old_default, stored, valid}
      invalid  other stored values this version cannot use: {key, stored, rule, default}
               (not those the user has already reviewed with the same stored value,
               ``reviewed``: they are kept in settings.json and not shown again)
    """
    reviewed = reviewed or {}
    old_keys = set(old_schema) if old_schema is not None else set(stored)
    out: Dict[str, List[Dict[str, Any]]] = {"new": [], "removed": [], "changed": [], "invalid": []}
    for key, spec in new_schema.items():
        if key not in old_keys:
            out["new"].append({"key": key, "default": spec["default"], "rule": spec["rule"]})
            continue
        has = key in stored
        valid = has and config.setting_is_valid(key, stored[key])
        old = (old_schema or {}).get(key)
        if old is not None and (old.get("rule") != spec["rule"] or old.get("default") != spec["default"]):
            out["changed"].append({"key": key, "rule": spec["rule"], "old_rule": old.get("rule"),
                                   "default": spec["default"], "old_default": old.get("default"),
                                   "stored": stored.get(key), "valid": valid})
        elif has and not valid and not (key in reviewed and reviewed[key] == stored[key]):
            out["invalid"].append({"key": key, "stored": stored[key], "rule": spec["rule"], "default": spec["default"]})
    for key in sorted(old_keys):
        if key not in new_schema:
            out["removed"].append({"key": key, "stored": stored.get(key)})
    return out


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def write_marker() -> None:
    """Remember the settings of this version and the unusable stored values the user has seen."""
    path = marker_path()
    stored = config.read_settings_file()
    reviewed = {k: v for k, v in stored.items() if k in config.SETTING_KEYS and not config.setting_is_valid(k, v)}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": __version__, "schema": current_schema(), "reviewed": reviewed},
                              indent=2), encoding="utf-8")
    os.replace(tmp, path)


def pending(release_notes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    What to show the user once at this start: the settings changes since the version they
    last reviewed and, after an automatic update, the release notes of the new version
    (``release_notes``, from helios.updates). When there is nothing to show, the marker is
    brought up to date at once.
    """
    marker = _read_json(marker_path())
    stored = config.read_settings_file()
    if marker is None and not config.SETTINGS_FILE.exists():
        try:
            write_marker()
        except OSError:
            pass
        return {"show": False}
    changes = compare(stored, (marker or {}).get("schema"), current_schema(), (marker or {}).get("reviewed"))
    seen_here = marker is not None and marker.get("version") == __version__
    notes = None if seen_here else release_notes
    if not any(changes.values()) and not notes:
        try:
            write_marker()
        except OSError:
            pass
        return {"show": False}
    return {"show": True, "version": __version__,
            "previous_version": None if marker is None else marker.get("version"),
            "whats_new": notes, "changes": changes,
            "settings": config._current_values()}


def acknowledge(patch: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    The user has seen the changes: apply the values they picked (all validated first;
    ValueError for an invalid one, and nothing is changed then), save, and remember the
    settings of this version. Stored values they did not change stay as they are.
    """
    patch = {k: v for k, v in (patch or {}).items() if v is not None}
    unknown = [k for k in patch if k not in config.SETTING_KEYS]
    if unknown:
        raise ValueError(f"Unknown setting(s): {', '.join(unknown)}.")
    config._validate_settings(**patch)
    if patch or not config.SETTINGS_FILE.exists():
        result = config.update_system_settings(**patch)
    else:
        result = config.get_system_settings()
    write_marker()
    return result
