"""
Weekly automatic update of a published build (helios/updates.py), against a local server
that answers like the GitHub releases API.
"""
import hashlib
import http.server
import io
import json
import os
import sys
import tarfile
import threading
import zipfile
from pathlib import Path

import pytest

from helios import __version__, config, updates
from helios.release_names import APP, archive_basename, platform_tag

EXE = f"{APP}.exe" if sys.platform == "win32" else APP


def _zip_build(path: Path, version: str, extra=None) -> bytes:
    """A release zip as packaging/build.py makes it: HELIOS-L1/<launcher> and _internal/."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"{APP}/{EXE}", f"build {version}")
        zf.writestr(f"{APP}/_internal/base_library.zip", "x" * 100)
        for name, data in (extra or {}).items():
            zf.writestr(name, data)
    data = buf.getvalue()
    path.write_bytes(data)
    return data


def _release(tag, asset_name, data, base_url, prerelease=False, draft=False, digest=True):
    asset = {"name": asset_name, "size": len(data),
             "browser_download_url": f"{base_url}/download/{asset_name}",
             "url": f"{base_url}/assets/1"}
    if digest:
        asset["digest"] = "sha256:" + hashlib.sha256(data).hexdigest()
    return {"tag_name": tag, "name": f"HELIOS-L1 {tag[1:]}", "body": f"Changes in {tag}.",
            "html_url": f"https://github.com/{updates.REPO}/releases/tag/{tag}",
            "draft": draft, "prerelease": prerelease, "assets": [asset]}


@pytest.fixture
def server(tmp_path):
    """Local HTTP server: /repos/<repo>/releases (JSON set by the test) and /download/<file>."""
    files = {}
    state = {"releases": []}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path.startswith(f"/repos/{updates.REPO}/releases"):
                body = json.dumps(state["releases"]).encode()
                ctype = "application/json"
            elif self.path.startswith(f"/repos/{updates.REPO}/tags") and state.get("tags") is not None:
                body = json.dumps([{"name": t} for t in state["tags"]]).encode()
                ctype = "application/json"
            elif self.path.startswith("/download/") and self.path[10:] in files:
                body = files[self.path[10:]]
                ctype = "application/octet-stream"
            else:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield {"base": base, "files": files, "state": state}
    srv.shutdown()


@pytest.fixture
def installed(tmp_path, monkeypatch, server):
    """An unpacked build in tmp/apps/HELIOS-L1 with its data folders elsewhere."""
    root = tmp_path / "apps" / APP
    (root / "_internal").mkdir(parents=True)
    (root / EXE).write_text("build old")
    data = tmp_path / "data"
    for name in ("CONFIG_DIR", "CACHE_DIR", "LOG_DIR"):
        (data / name).mkdir(parents=True)
        monkeypatch.setattr(config, name, data / name)
    monkeypatch.setenv("HELIOS_UPDATE_API", server["base"])
    monkeypatch.setattr(updates, "install_root", lambda: root)
    return root


def test_archive_names_match_the_build_script():
    """packaging/build.py names the archive with the same function the updater picks it by."""
    src = (Path(__file__).parent.parent / "packaging" / "build.py").read_text(encoding="utf-8")
    assert "archive_basename()" in src and "archive_format()" in src
    rel = {"assets": [{"name": f"{APP}-0.0.2-linux-x86_64.tar.gz"}, {"name": f"{APP}-0.0.2-macos-arm64.tar.gz"},
                      {"name": f"{APP}-0.0.2-windows-x86_64.zip"}, {"name": "notes.txt"}]}
    assert updates.pick_asset(rel, "windows-x86_64")["name"].endswith("windows-x86_64.zip")
    assert updates.pick_asset(rel, "macos-arm64")["name"].endswith("macos-arm64.tar.gz")
    assert updates.pick_asset(rel, "linux-arm64") is None
    mine = {"assets": [{"name": archive_basename("0.0.2") + (".zip" if sys.platform == "win32" else ".tar.gz")}]}
    assert updates.pick_asset(mine) is not None
    assert archive_basename("1.2.3") == f"{APP}-1.2.3-{platform_tag()}"


def test_every_bundled_data_file_is_packaged():
    """
    Each file under helios/data (catalogue snapshots, SPICE kernels) is read at run time, so it
    must reach both the wheel (pyproject package-data) and the standalone build (PyInstaller
    datas); a file missing from either fails only in that installation.
    """
    import fnmatch
    import re
    root = Path(__file__).parent.parent
    data = root / "helios" / "data"
    files = [p.relative_to(root / "helios").as_posix() for p in data.rglob("*") if p.is_file()]
    assert len(files) >= 5
    globs = re.findall(r'"([^"]+)"', re.search(r"helios\s*=\s*\[(.*?)\]", (root / "pyproject.toml").read_text(encoding="utf-8")).group(1))
    assert [f for f in files if not any(fnmatch.fnmatch(f, g) for g in globs)] == []
    spec = (root / "packaging" / "helios.spec").read_text(encoding="utf-8")
    entries = {"data/" + m for m in re.findall(r'PKG / "data" / "([^"]+)"', spec)}
    assert [f for f in files if not any(f == e or f.startswith(e + "/") for e in entries)] == []


def test_which_release_counts():
    rels = [{"tag_name": "v0.0.3", "draft": True}, {"tag_name": "v0.0.2", "prerelease": True},
            {"tag_name": "v0.0.1"}, {"tag_name": "nightly"}]
    assert updates.newest_release(rels, "0.0.1")["tag_name"] == "v0.0.2"  # drafts never
    assert updates.is_newer("v0.0.2", "0.0.1") and not updates.is_newer("v0.0.1", "0.0.1")
    assert not updates.is_newer("v0.0.10", "0.1.0") and updates.is_newer("v0.0.10", "0.0.9")
    # From 1.0 on, pre-releases are not offered.
    rels = [{"tag_name": "v1.1.0", "prerelease": True}, {"tag_name": "v1.0.1"}]
    assert updates.newest_release(rels, "1.0.0")["tag_name"] == "v1.0.1"
    assert updates.parse_tag("v0.0.2") == (0, 0, 2) and updates.parse_tag("latest") == ()


def test_download_is_verified(tmp_path):
    f = tmp_path / "a.zip"
    data = _zip_build(f, "0.0.2")
    good = "sha256:" + hashlib.sha256(data).hexdigest()
    updates.verify(f, len(data), good)
    with pytest.raises(ValueError, match="bytes"):
        updates.verify(f, len(data) + 1, good)
    with pytest.raises(ValueError, match="does not match"):
        updates.verify(f, len(data), "sha256:" + "0" * 64)
    with pytest.raises(ValueError, match="no SHA-256 digest"):
        updates.verify(f, len(data), None)
    with pytest.raises(ValueError, match="no SHA-256 digest"):
        updates.verify(f, len(data), "md5:abc")


def test_extract_refuses_paths_outside_and_needs_the_launcher(tmp_path):
    ok = tmp_path / "ok.zip"
    _zip_build(ok, "0.0.2")
    top = updates.extract(ok, tmp_path / "x")
    assert top.name == APP and (top / EXE).read_text() == "build 0.0.2"
    evil = tmp_path / "evil.zip"
    _zip_build(evil, "0.0.2", {"../../outside.txt": "no"})
    with pytest.raises(ValueError, match="outside"):
        updates.extract(evil, tmp_path / "y")
    assert not (tmp_path / "outside.txt").exists()
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr(f"{APP}/readme.txt", "no launcher")
    with pytest.raises(ValueError, match="no HELIOS-L1"):
        updates.extract(empty, tmp_path / "z")
    # tar.gz (macOS, Linux): files, folders and links inside the bundle; links out refused
    tgz = tmp_path / "b.tar.gz"
    with tarfile.open(tgz, "w:gz") as tf:
        for name, data in ((f"{APP}/{EXE}", b"build tar"), (f"{APP}/_internal/lib.so", b"x")):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tf.addfile(info, io.BytesIO(data))
    assert (updates.extract(tgz, tmp_path / "t") / EXE).read_bytes() == b"build tar"
    bad = tmp_path / "bad.tar.gz"
    with tarfile.open(bad, "w:gz") as tf:
        info = tarfile.TarInfo(f"{APP}/escape")
        info.type, info.linkname = tarfile.SYMTYPE, "../../../etc"
        tf.addfile(info)
    with pytest.raises(ValueError):
        updates.extract(bad, tmp_path / "u")


def test_extract_unix_layout_where_folder_and_launcher_share_the_name(tmp_path, monkeypatch):
    """macOS/Linux archives: HELIOS-L1/HELIOS-L1 (launcher) plus links inside _internal, as in
    the published v0.0.1 tarballs (16-17 relative symlinks each). The staged folder must be
    HELIOS-L1/, not the folder above it."""
    monkeypatch.setattr(updates, "launcher", lambda root: root / APP)
    made = []
    monkeypatch.setattr(updates.os, "symlink", lambda src, dst: made.append((src, Path(dst))))
    tgz = tmp_path / "linux.tar.gz"
    with tarfile.open(tgz, "w:gz") as tf:
        for name, data in ((f"{APP}/{APP}", b"elf"), (f"{APP}/_internal/numpy.libs/libg.so.5", b"so")):
            info = tarfile.TarInfo(name)
            info.size, info.mode = len(data), 0o755
            tf.addfile(info, io.BytesIO(data))
        link = tarfile.TarInfo(f"{APP}/_internal/libg.so.5")
        link.type, link.linkname = tarfile.SYMTYPE, "numpy.libs/libg.so.5"
        tf.addfile(link)
    top = updates.extract(tgz, tmp_path / "out")
    assert top == tmp_path / "out" / APP and (top / APP).read_bytes() == b"elf"
    assert made == [("numpy.libs/libg.so.5", top / "_internal" / "libg.so.5")]


def test_only_builds_with_separate_data_folders_update_themselves(tmp_path, monkeypatch):
    assert "source" in updates.install_problem()  # the test suite runs from source
    root = tmp_path / APP
    root.mkdir()
    assert "is not in" in updates.install_problem(root)
    (root / EXE).write_text("x")
    monkeypatch.setattr(config, "CONFIG_DIR", root / "home" / "config")
    assert "inside the installation folder" in updates.install_problem(root)
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path / "elsewhere")
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "elsewhere")
    monkeypatch.setattr(config, "LOG_DIR", tmp_path / "elsewhere")
    assert updates.install_problem(root) is None


def test_token_only_for_github(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "secret")
    monkeypatch.setenv("HELIOS_UPDATE_API", "http://127.0.0.1:9")
    assert updates._token() is None  # never sent to another server
    monkeypatch.delenv("HELIOS_UPDATE_API")
    assert updates.api_base() == "https://api.github.com" and updates._token() == "secret"


def test_check_downloads_verifies_and_stages(installed, server, monkeypatch):
    root = installed
    newer = ".".join(str(x) for x in (updates.version_tuple(__version__)[:2] + (updates.version_tuple(__version__)[2] + 1,)))
    name = archive_basename(newer) + ".zip"
    data = _zip_build(Path(installed.parent / "tmp.zip"), newer)
    server["files"][name] = data
    rel_new = _release(f"v{newer}", name, data, server["base"], prerelease=True)
    rel_old = _release(f"v{__version__}", archive_basename(__version__) + ".zip", data, server["base"])
    # nothing newer: nothing downloaded, the check is recorded
    server["state"]["releases"] = [rel_old]
    assert updates.check_and_stage(force=True, root=root)["result"] == "latest"
    assert updates.load_state()["last_check"] > 0
    assert updates.check_and_stage(force=False, root=root)["result"] == "disabled"  # within the week
    # a release whose files are not uploaded yet: not counted as this week's check
    partial = dict(rel_new, assets=[])
    server["state"]["releases"] = [partial, rel_old]
    st = updates.load_state()
    st["last_check"] -= updates.CHECK_EVERY_S + 1
    updates.save_state(st)
    assert updates.check_and_stage(force=True, root=root)["result"] == "error"
    # a wrong digest: refused, nothing staged
    bad = json.loads(json.dumps(rel_new))
    bad["assets"][0]["digest"] = "sha256:" + "0" * 64
    server["state"]["releases"] = [bad]
    with pytest.raises(ValueError, match="does not match"):
        updates.check_and_stage(force=True, root=root)
    assert not updates.staged_dir(root).exists() and not list(updates.updates_dir().glob("*.part"))
    # the newer pre-release (this copy is 0.x): downloaded, checked, unpacked beside the installation
    server["state"]["releases"] = [rel_new, rel_old]
    assert updates.check_and_stage(force=True, root=root) == {"result": "staged", "tag": f"v{newer}"}
    staged = updates.staged_dir(root)
    assert (staged / EXE).read_text() == f"build {newer}" and (root / EXE).read_text() == "build old"
    assert updates.load_state()["staged"]["notes"] == f"Changes in v{newer}."
    assert updates.check_and_stage(force=True, root=root)["result"] == "already staged"
    assert not list(updates.updates_dir().glob("*.zip"))  # the download is removed after unpacking
    # the data folders were not touched
    assert not any((Path(config.CONFIG_DIR) / f).exists() for f in ("settings.json",))


def test_installed_build_keeps_its_notes_and_cleans_up(installed, monkeypatch):
    root = installed
    updates.staged_dir(root).mkdir()
    updates.previous_dir(root).mkdir()
    updates.save_state({"staged": {"tag": f"v{__version__}", "version": __version__, "name": "N",
                                   "notes": "What changed.", "url": "u"}})
    updates.finish_install()
    # The previous build stays until this one has run a while (the install script may need it).
    assert not updates.staged_dir(root).exists() and updates.previous_dir(root).exists()
    st = updates.load_state()
    st["installed"]["installed_at"] -= updates.KEEP_PREVIOUS_S + 1
    updates.save_state(st)
    updates.finish_install()  # a later start
    assert not updates.previous_dir(root).exists()
    notes = updates.installed_notes()
    assert {k: notes[k] for k in ("tag", "name", "notes", "url")} == {
        "tag": f"v{__version__}", "name": "N", "notes": "What changed.", "url": "u"}
    assert notes["releases_behind"] is None  # staged before releases were counted
    # the settings review shows them once
    from helios import settings_review
    (Path(config.CONFIG_DIR) / "settings.json").write_text("{}")
    monkeypatch.setattr(config, "SETTINGS_FILE", Path(config.CONFIG_DIR) / "settings.json")
    marker = {"version": "0.0.0", "schema": settings_review.current_schema()}
    (Path(config.CONFIG_DIR) / "settings_seen.json").write_text(json.dumps(marker))
    rev = settings_review.pending(release_notes=updates.installed_notes())
    assert rev["show"] and rev["whats_new"]["notes"] == "What changed."


def test_swap_script_restarts_with_the_same_arguments(installed):
    root = installed
    script, cmd = updates.helper_script(root, updates.staged_dir(root), updates.previous_dir(root),
                                        ["--headless", "--port", "8793"], 4242)
    body = script.read_text(encoding="utf-8-sig")
    assert "4242" in body and str(updates.staged_dir(root)) in body and str(updates.previous_dir(root)) in body
    assert "'--headless', '--port', '8793'" in body or "'--headless' '--port' '8793'" in body
    assert cmd[-1] == str(script)
    # nothing staged: start-up goes on normally
    updates.save_state({})
    assert updates.install_staged_on_start(["--headless"]) is False


def test_failed_install_runs_the_old_build_and_retries_later(installed):
    """
    A locked installation folder made every start hand over to the install script, which
    could not move the folder and started the old build, which handed over again: the
    application never came up (seen end to end: a new attempt every 33 s for as long as
    the folder was locked). A failed attempt is now recorded and the old build runs.
    """
    root = installed
    newer = "9.9.9"
    staged = updates.staged_dir(root)
    staged.mkdir()
    (staged / EXE).write_text("build new")
    updates.save_state({"staged": {"tag": f"v{newer}", "version": newer, "name": "N", "notes": "x"}})
    script, _ = updates.helper_script(root, staged, updates.previous_dir(root), [], 1)
    body = script.read_text(encoding="utf-8-sig")
    flag = str(updates.updates_dir() / "install_failed.txt")
    assert flag in body and str(root.parent / f"{root.name}.failed") in body
    assert "exited with code" in body and str(updates.HEALTH_CHECK_S) in body
    # the script reports a failure; the old build starts and absorbs it
    (updates.updates_dir() / "install_failed.txt").write_text("could not move the installation aside: in use")
    updates.finish_install()
    failed = updates.load_state()["failed"]
    assert failed["tag"] == f"v{newer}" and failed["attempts"] == 1 and "in use" in failed["reason"]
    assert not (updates.updates_dir() / "install_failed.txt").exists()
    assert updates.status()["failed"]["attempts"] == 1
    monkey_problem = updates.install_problem
    try:
        updates.install_problem = lambda root=None: None  # as in a build
        assert updates.install_staged_on_start([], now=failed["at"] + 60) is False  # not again at once
        # a second failure an hour later counts as attempt 2; after MAX_ATTEMPTS the build is discarded
        (updates.updates_dir() / "install_failed.txt").write_text("could not move the installation aside")
        updates.finish_install()
        st = updates.load_state()
        assert st["failed"]["attempts"] == 2
        st["failed"]["attempts"] = updates.MAX_ATTEMPTS
        updates.save_state(st)
        assert updates.install_staged_on_start([], now=st["failed"]["at"] + updates.RETRY_AFTER_S + 1) is False
        assert not staged.exists() and "staged" not in updates.load_state()
    finally:
        updates.install_problem = monkey_problem


def test_new_build_that_crashed_is_removed_and_its_notes_dropped(installed):
    root = installed
    broken = root.parent / f"{root.name}.failed"
    (broken / "_internal").mkdir(parents=True)
    # the crashed build had marked itself installed before it failed
    updates.save_state({"installed": {"tag": "v9.9.9", "version": "9.9.9", "name": "N", "notes": "x",
                                      "installed_at": 1.0}})
    (updates.updates_dir() / "install_failed.txt").write_text(
        "the new build exited with code 1 within 20 s of its start; the previous build was put back")
    updates.finish_install()
    st = updates.load_state()
    assert not broken.exists() and "installed" not in st and "staged" not in st
    assert st["failed"]["tag"] == "v9.9.9" and "exited with code 1" in st["failed"]["reason"]
    assert updates.installed_notes() is None


def test_check_skips_a_release_that_failed_too_often_unless_forced(installed, server):
    root = installed
    name = archive_basename("9.9.9") + ".zip"
    data = _zip_build(Path(root.parent / "t.zip"), "9.9.9")
    server["files"][name] = data
    server["state"]["releases"] = [_release("v9.9.9", name, data, server["base"])]
    updates.save_state({"failed": {"tag": "v9.9.9", "reason": "crashed", "at": 1.0, "attempts": updates.MAX_ATTEMPTS},
                        "last_check": 1.0})
    monkey_due = updates.due
    try:
        updates.due = lambda now=None: True
        res = updates.check_and_stage(force=False, root=root)
        assert res["result"] == "error" and "Check now" in res["reason"]
    finally:
        updates.due = monkey_due
    assert updates.check_and_stage(force=True, root=root)["result"] == "staged"
    assert "failed" not in updates.load_state()


def test_the_newest_release_is_staged_not_the_next_one(installed, server):
    """
    Only the two newest releases are kept on GitHub, so the installed one may be gone:
    an old build must still find and stage the newest release, whatever the list order.
    """
    root = installed
    for v in ("9.0.5", "9.0.9"):
        name = archive_basename(v) + ".zip"
        data = _zip_build(Path(root.parent / f"{v}.zip"), v)
        server["files"][name] = data
        server["state"].setdefault("rel", {})[v] = _release(f"v{v}", name, data, server["base"], prerelease=False)
    # newest last (not newest first as GitHub sorts), installed release absent from the list
    server["state"]["releases"] = [server["state"]["rel"]["9.0.5"], server["state"]["rel"]["9.0.9"]]
    assert updates.check_and_stage(force=True, root=root) == {"result": "staged", "tag": "v9.0.9"}
    assert (updates.staged_dir(root) / EXE).read_text() == "build 9.0.9"
    # build numbers order releases of one version; versions order everything else
    rels = [{"tag_name": "v0.0.5-build.3"}, {"tag_name": "v0.0.5-build.12"}, {"tag_name": "v0.0.4-build.99"}]
    assert updates.newest_release(rels, "0.0.1")["tag_name"] == "v0.0.5-build.12"
    assert updates.newest_release([{"tag_name": "v0.0.2"}, {"tag_name": "v0.0.3"}], "0.0.1")["tag_name"] == "v0.0.3"
    assert updates.newest_release([], "0.0.1") is None
    assert updates.version_tuple("1.2") == (1, 2, 0) and updates.is_newer("v1.2.1", "1.2")
    assert not updates.is_newer("v0.0.1-build.40", "0.0.1")  # same version: not offered


def test_skipped_releases_are_counted_with_a_compare_link(installed, server):
    """
    After an update that skips releases, "What's new" says how many and links the GitHub
    comparison from the old tag to the new one (tags stay when old releases are deleted),
    or the CHANGELOG when the tags cannot be read.
    """
    root = installed
    old = __version__
    name = archive_basename("9.0.9") + ".zip"
    data = _zip_build(Path(root.parent / "n.zip"), "9.0.9")
    server["files"][name] = data
    # only the two newest releases are still listed; the tags of all of them remain
    server["state"]["releases"] = [_release("v9.0.9", name, data, server["base"]),
                                   _release("v9.0.5", name, data, server["base"])]
    server["state"]["tags"] = [f"v{old}", "v9.0.1", "v9.0.5", "v9.0.9", "not-a-version"]
    assert updates.check_and_stage(force=True, root=root)["result"] == "staged"
    st = updates.load_state()["staged"]
    assert st["releases_behind"] == 3 and st["counted_from"] == "tags" and st["previous_version"] == old
    assert st["compare_url"] == f"https://github.com/{updates.REPO}/compare/v{old}...v9.0.9"
    # the new build starts: the notes carry the count and the link
    st = updates.load_state()
    st["installed"] = {k: st["staged"].get(k) for k in ("tag", "version", "name", "notes", "url", "previous_version",
                                                        "releases_behind", "compare_url", "changelog_url")}
    st["installed"]["version"] = __version__  # as seen by that build
    updates.save_state(st)
    notes = updates.installed_notes()
    assert notes["releases_behind"] == 3 and notes["compare_url"].endswith(f"v{old}...v9.0.9")
    # without the tag list: the releases still listed are counted, and the CHANGELOG is linked
    info = updates.releases_behind("v9.0.9", None, server["state"]["releases"], old)
    assert info["releases_behind"] == 2 and info["compare_url"] is None
    assert info["changelog_url"] == f"https://github.com/{updates.REPO}/blob/v9.0.9/CHANGELOG.md"
    # the old tag is missing (e.g. a copy built from an untagged commit): CHANGELOG as well
    assert updates.releases_behind("v9.0.9", ["v9.0.9"], [], old)["compare_url"] is None
    assert updates.releases_behind("v9.0.9", [f"v{old}", "v9.0.9"], [], old)["releases_behind"] == 1
