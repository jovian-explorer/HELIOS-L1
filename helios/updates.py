"""
Weekly automatic update of a published HELIOS-L1 build from the GitHub releases of
jovian-explorer/HELIOS-L1.

Once a week (Settings, *Automatic updates*, on by default; *Check now* at any time) a
published build asks the GitHub API for the releases. When one is newer than this copy,
the archive for this system (``HELIOS-L1-<version>-<os>-<arch>.zip`` or ``.tar.gz``, the
names packaging/build.py gives them) is downloaded into the settings folder
(``updates/``), checked against the size and the SHA-256 digest GitHub lists for it, and
unpacked beside the installation (``<folder>.update``). The next time HELIOS-L1 starts it
hands over to a small script that waits for it to exit, renames the installation to
``<folder>.previous``, moves the new one into its place and starts it with the same
command-line arguments; the new build then deletes the previous one. If a step fails,
the old folder is put back and started.

Only the installation folder is replaced. The cache, logs and settings.json live in
other folders and are never touched; an installation that holds them (HELIOS_HOME inside
it) or whose parent folder is not writable is not updated automatically. Copies run from
source or installed with pip are never updated (only PyInstaller builds are).

Which releases count: drafts never; pre-releases only while this copy is itself a 0.x
version (every build before 1.0.0 is published as a pre-release). The GitHub API is used
without a login, as for anyone once the repository is public; when GITHUB_TOKEN or
GH_TOKEN is set, or the GitHub CLI is logged in, that token is sent to api.github.com
(and only there), so the check also works while the repository is private.
HELIOS_UPDATE_API replaces https://api.github.com (for tests with a local server).

State (last check, the staged build, the notes of the installed one) is kept in
``updates/state.json`` in the settings folder.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from helios import __version__
from helios import config
from helios.release_names import APP, platform_tag

REPO = "jovian-explorer/HELIOS-L1"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
CHECK_EVERY_S = 7 * 24 * 3600
TIMEOUT_S = 30.0

_lock = threading.Lock()
_job: Dict[str, Any] = {"running": False, "message": "", "done": 0, "total": 0, "error": None, "result": None}


def updates_dir() -> Path:
    return config.CONFIG_DIR / "updates"


def _state_path() -> Path:
    return updates_dir() / "state.json"


def api_base() -> str:
    return (os.environ.get("HELIOS_UPDATE_API") or "https://api.github.com").rstrip("/")


# ---------------------------------------------------------------- versions and names

def version_tuple(v: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3])


def parse_tag(tag: str) -> Tuple[int, ...]:
    """"v0.0.2" -> (0, 0, 2); () for a tag that is not a version."""
    m = re.match(r"v?(\d+(?:\.\d+){0,2})$", (tag or "").strip())
    return version_tuple(m.group(1)) if m else ()


def is_newer(tag: str, version: str = __version__) -> bool:
    rv = parse_tag(tag)
    return bool(rv) and rv > version_tuple(version)


# ---------------------------------------------------------------- state

def load_state() -> Dict[str, Any]:
    try:
        data = json.loads(_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(state: Dict[str, Any]) -> None:
    updates_dir().mkdir(parents=True, exist_ok=True)
    tmp = _state_path().with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    os.replace(tmp, _state_path())


def installed_notes() -> Optional[Dict[str, Any]]:
    """Release notes of this version when the updater installed it (for "What's new")."""
    inst = load_state().get("installed") or {}
    if inst.get("version") == __version__:
        return {"tag": inst.get("tag"), "name": inst.get("name"), "notes": inst.get("notes") or "",
                "url": inst.get("url")}
    return None


# ---------------------------------------------------------------- this installation

def install_root() -> Optional[Path]:
    """The unpacked folder holding HELIOS-L1(.exe) and _internal/; None when not a build."""
    if not getattr(sys, "frozen", False):
        return None
    return Path(sys.executable).resolve().parent


def launcher(root: Path) -> Path:
    return root / (f"{APP}.exe" if sys.platform == "win32" else APP)


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def install_problem(root: Optional[Path] = None) -> Optional[str]:
    """Why this copy cannot update itself, or None."""
    if root is None:
        if not getattr(sys, "frozen", False):
            return "this copy runs from source or a pip install (only the published builds update themselves)"
        root = install_root()
    if root is None:
        return "the installation folder could not be found"
    for folder in (config.CONFIG_DIR, config.CACHE_DIR, config.LOG_DIR):
        if _inside(folder, root):
            return f"the data folder {folder} is inside the installation folder"
    if not launcher(root).is_file():
        return f"{launcher(root).name} is not in {root}"
    if not os.access(root.parent, os.W_OK):
        return f"{root.parent} is not writable"
    return None


def staged_dir(root: Path) -> Path:
    return root.parent / f"{root.name}.update"


def previous_dir(root: Path) -> Path:
    return root.parent / f"{root.name}.previous"


# ---------------------------------------------------------------- GitHub

def _token() -> Optional[str]:
    """A GitHub token for api.github.com, if the user has one (environment or GitHub CLI)."""
    if urlparse(api_base()).hostname != "api.github.com":
        return None
    for name in ("GITHUB_TOKEN", "GH_TOKEN"):
        if os.environ.get(name):
            return os.environ[name].strip()
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        kw: Dict[str, Any] = {"capture_output": True, "text": True, "timeout": 5}
        if sys.platform == "win32":
            kw["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        out = subprocess.run([gh, "auth", "token", "--hostname", "github.com"], **kw)
        tok = out.stdout.strip()
        return tok if out.returncode == 0 and tok else None
    except (OSError, subprocess.SubprocessError):
        return None


def _client(token: Optional[str]):
    import httpx
    from helios.core.downloader import _ssl_context
    headers = {"Accept": "application/vnd.github+json", "User-Agent": f"{APP}/{__version__}",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    # httpx drops the Authorization header when a redirect leaves the API host (the asset
    # download is redirected to GitHub's file storage).
    return httpx.Client(headers=headers, timeout=TIMEOUT_S, follow_redirects=True, verify=_ssl_context())


def list_releases(token: Optional[str] = None) -> List[Dict[str, Any]]:
    with _client(token) as c:
        r = c.get(f"{api_base()}/repos/{REPO}/releases", params={"per_page": 30})
        r.raise_for_status()
        data = r.json()
    return data if isinstance(data, list) else []


def newest_release(releases: List[Dict[str, Any]], version: str = __version__) -> Optional[Dict[str, Any]]:
    """The release with the highest version that this copy may install (see the module docstring)."""
    allow_pre = version_tuple(version)[:1] == (0,)
    best, best_v = None, ()
    for rel in releases:
        if rel.get("draft") or (rel.get("prerelease") and not allow_pre):
            continue
        v = parse_tag(rel.get("tag_name", ""))
        if v and v > best_v:
            best, best_v = rel, v
    return best


def pick_asset(release: Dict[str, Any], tag: Optional[str] = None) -> Optional[Dict[str, Any]]:
    tag = tag or platform_tag()
    for a in release.get("assets") or []:
        name = a.get("name", "")
        if name.startswith(f"{APP}-") and (name.endswith(f"-{tag}.zip") or name.endswith(f"-{tag}.tar.gz")):
            return a
    return None


# ---------------------------------------------------------------- download, check, unpack

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(path: Path, size: Optional[int], digest: Optional[str]) -> None:
    """Raise ValueError unless the file has the listed size and SHA-256 digest ("sha256:<hex>")."""
    if size is not None and path.stat().st_size != int(size):
        raise ValueError(f"the download has {path.stat().st_size} bytes, the release lists {size}")
    algo, _, want = (digest or "").partition(":")
    if algo.lower() != "sha256" or not re.fullmatch(r"[0-9a-fA-F]{64}", want):
        raise ValueError(f"the release lists no SHA-256 digest for this file ({digest!r}); not installed")
    got = _sha256(path)
    if got.lower() != want.lower():
        raise ValueError(f"SHA-256 {got} does not match the release's {want}")


def extract(archive: Path, dest: Path) -> Path:
    """
    Unpack a release archive (zip or tar.gz) into ``dest`` and return the folder holding
    the launcher. Members that would land outside ``dest``, and links in tar files, are
    refused. Unix permissions are restored from the archive.
    """
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    root = dest.resolve()
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"{bad} in the download is damaged")
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not _inside(target, root):
                    raise ValueError(f"{info.filename} would be written outside the update folder")
                zf.extract(info, dest)
                mode = (info.external_attr >> 16) & 0o777
                if mode and os.name != "nt":
                    os.chmod(target, mode)
    else:
        with tarfile.open(archive, "r:gz") as tf:
            members = tf.getmembers()
            for m in members:
                target = (dest / m.name).resolve()
                if not _inside(target, root):
                    raise ValueError(f"{m.name} would be written outside the update folder")
                if not (m.isfile() or m.isdir()):
                    # PyInstaller folders on macOS contain symlinks inside the bundle; keep
                    # those that stay inside it, refuse everything else.
                    if m.issym() and _inside((target.parent / m.linkname).resolve(), root):
                        continue
                    raise ValueError(f"{m.name} is not a plain file or folder")
            for m in members:
                if m.issym():
                    continue
                if hasattr(tarfile, "tar_filter"):  # Python 3.12+ (and security releases of 3.10/3.11)
                    tf.extract(m, dest, filter="tar")
                else:
                    tf.extract(m, dest)
                if m.isfile() and os.name != "nt":
                    os.chmod(dest / m.name, m.mode & 0o777)
            for m in members:
                if m.issym():
                    link = dest / m.name
                    link.parent.mkdir(parents=True, exist_ok=True)
                    if link.exists() or link.is_symlink():
                        link.unlink()
                    os.symlink(m.linkname, link)
    # The archives hold one folder, HELIOS-L1/, with the launcher of the same name inside
    # (on macOS and Linux the launcher HELIOS-L1 and the folder HELIOS-L1 share the name).
    tops = [p for p in dest.iterdir() if p.is_dir()]
    top = tops[0] if len(tops) == 1 and launcher(tops[0]).is_file() else dest
    if not launcher(top).is_file():
        raise ValueError(f"the release has no {launcher(top).name}")
    return top


def _progress(done: int, total: int, message: str) -> None:
    _job.update(done=done, total=total, message=message)


def due(now: Optional[float] = None) -> bool:
    if not config.ACTIVE_AUTO_UPDATE or install_problem() is not None:
        return False
    last = load_state().get("last_check")
    return not last or (now or time.time()) - float(last) >= CHECK_EVERY_S


def check_and_stage(force: bool = False, releases: Optional[List[Dict[str, Any]]] = None,
                    progress: Callable[[int, int, str], None] = _progress,
                    root: Optional[Path] = None) -> Dict[str, Any]:
    """
    Look for a newer published build and, when there is one, download, verify and unpack
    it beside the installation. Returns {"result": "latest" | "staged" | "already staged" |
    "disabled" | "error", ...}.
    """
    problem = install_problem(root)
    if problem:
        return {"result": "disabled", "reason": problem}
    if not force and not due():
        return {"result": "disabled", "reason": "checked less than a week ago"}
    root = root or install_root()
    token = _token()
    rels = list_releases(token) if releases is None else releases
    st = load_state()
    st["last_check"] = time.time()
    rel = newest_release(rels)
    if rel is None or not is_newer(rel.get("tag_name", "")):
        save_state(st)
        return {"result": "latest", "tag": rel.get("tag_name") if rel else None}
    tag = rel["tag_name"]
    staged = st.get("staged") or {}
    if staged.get("tag") == tag and launcher(staged_dir(root)).is_file():
        save_state(st)
        return {"result": "already staged", "tag": tag}
    asset = pick_asset(rel)
    if asset is None:
        # Not counted as a check: a release is listed before all its files are uploaded.
        return {"result": "error", "reason": f"release {tag} has no download for {platform_tag()} yet"}
    updates_dir().mkdir(parents=True, exist_ok=True)
    part = updates_dir() / (asset["name"] + ".part")
    total = int(asset.get("size") or 0)
    progress(0, total, f"Downloading {asset['name']}")
    with _client(token) as c:
        if token and asset.get("url"):
            req = c.stream("GET", asset["url"], headers={"Accept": "application/octet-stream"})
        else:
            req = c.stream("GET", asset["browser_download_url"], headers={"Accept": "application/octet-stream"})
        with req as r:
            r.raise_for_status()
            done = 0
            with open(part, "wb") as fh:
                for chunk in r.iter_bytes(1 << 20):
                    fh.write(chunk)
                    done += len(chunk)
                    progress(done, total, f"Downloading {asset['name']}")
    final = updates_dir() / asset["name"]
    try:
        progress(total, total, "Checking the download")
        verify(part, asset.get("size"), asset.get("digest"))
        os.replace(part, final)
        progress(total, total, "Unpacking")
        work = updates_dir() / "unpacked"
        top = extract(final, work)
        target = staged_dir(root)
        shutil.rmtree(target, ignore_errors=True)
        shutil.move(str(top), str(target))
        shutil.rmtree(work, ignore_errors=True)
    finally:
        part.unlink(missing_ok=True)
        final.unlink(missing_ok=True)
    version = ".".join(str(x) for x in parse_tag(tag))
    st["staged"] = {"tag": tag, "version": version, "name": rel.get("name") or tag, "notes": rel.get("body") or "",
                    "url": rel.get("html_url"), "sha256": (asset.get("digest") or "").partition(":")[2],
                    "size": asset.get("size"), "staged_at": time.time()}
    save_state(st)
    return {"result": "staged", "tag": tag}


def status() -> Dict[str, Any]:
    st = load_state()
    last = st.get("last_check")
    staged = st.get("staged") or None
    return {"enabled": bool(config.ACTIVE_AUTO_UPDATE), "problem": install_problem(), "last_check": last,
            "next_check": (last + CHECK_EVERY_S) if last else None,
            "staged": None if not staged else {k: staged.get(k) for k in ("tag", "name", "version", "staged_at")},
            "job": dict(_job), "version": __version__, "platform": platform_tag(), "releases": RELEASES_PAGE}


_MESSAGES = {"latest": "This is the latest build.",
             "staged": "The new build will be installed the next time HELIOS-L1 starts.",
             "already staged": "The new build will be installed the next time HELIOS-L1 starts."}


def start_check(force: bool = False) -> Dict[str, Any]:
    """Run check_and_stage in the background (one at a time)."""
    with _lock:
        if _job["running"]:
            return status()
        _job.update(running=True, error=None, message="Checking for a newer build", done=0, total=0, result=None)

    def run():
        try:
            res = check_and_stage(force=force)
            _job.update(result=res, message=_MESSAGES.get(res["result"], res.get("reason", "")))
        except Exception as exc:  # offline, rate limited, refused download: shown, not raised
            _job.update(error=str(exc)[:300], message="")
        finally:
            _job["running"] = False
    threading.Thread(target=run, daemon=True, name="helios-update").start()
    return status()


def scheduler() -> None:
    """In a running build: the weekly check (first a minute after start), then every hour whether a week has passed."""
    def loop():
        time.sleep(60)
        while True:
            try:
                if due():
                    start_check(force=False)
            except Exception:  # never stop the loop
                pass
            time.sleep(3600)
    if install_problem() is None:
        threading.Thread(target=loop, daemon=True, name="helios-update-scheduler").start()


# ---------------------------------------------------------------- installing at start-up

def finish_install() -> None:
    """At start-up: when this build is the one that was staged, it has been installed:
    keep its notes for "What's new" and remove the previous installation."""
    st = load_state()
    staged = st.get("staged")
    if not staged or staged.get("version") != __version__:
        return
    st["installed"] = {k: staged.get(k) for k in ("tag", "version", "name", "notes", "url")}
    st["installed"]["installed_at"] = time.time()
    st.pop("staged", None)
    save_state(st)
    root = install_root()
    if root is not None:
        shutil.rmtree(previous_dir(root), ignore_errors=True)
        shutil.rmtree(staged_dir(root), ignore_errors=True)


def helper_script(root: Path, staged: Path, previous: Path, args: List[str], pid: int) -> Tuple[Path, List[str]]:
    """(script path, command) of the swap-and-restart script for this system."""
    updates_dir().mkdir(parents=True, exist_ok=True)
    log = updates_dir() / "install.log"
    exe = launcher(root)
    if sys.platform == "win32":
        def q(p):
            return "'" + str(p).replace("'", "''") + "'"
        arglist = ", ".join(q(a) for a in args)
        start = (f"Start-Process -FilePath {q(exe)} -WorkingDirectory {q(root)} -ArgumentList @({arglist})"
                 if args else f"Start-Process -FilePath {q(exe)} -WorkingDirectory {q(root)}")
        body = f"""$ErrorActionPreference = 'Stop'
function Log($m) {{ Add-Content -LiteralPath {q(log)} -Value ("[" + (Get-Date -Format s) + "] " + $m) }}
function Start-Helios {{ {start} }}
Log 'waiting for HELIOS-L1 (process {pid}) to exit'
try {{ Wait-Process -Id {pid} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{ }}
if (Test-Path -LiteralPath {q(previous)}) {{ Remove-Item -LiteralPath {q(previous)} -Recurse -Force }}
$moved = $false
for ($i = 0; $i -lt 60 -and -not $moved; $i++) {{
  try {{ Move-Item -LiteralPath {q(root)} -Destination {q(previous)}; $moved = $true }} catch {{ Start-Sleep -Milliseconds 500 }}
}}
if (-not $moved) {{ Log 'could not move the installation aside; starting the old build'; Start-Helios; exit 1 }}
try {{ Move-Item -LiteralPath {q(staged)} -Destination {q(root)} }}
catch {{ Log ('could not move the new build in: ' + $_); Move-Item -LiteralPath {q(previous)} -Destination {q(root)}; Start-Helios; exit 1 }}
Log 'installed; starting the new build'
Start-Helios
"""
        script = updates_dir() / "install_update.ps1"
        script.write_text(body, encoding="utf-8-sig")
        return script, ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-WindowStyle", "Hidden", "-File", str(script)]

    def q(p):
        return "'" + str(p).replace("'", "'\\''") + "'"
    start = f"nohup {q(exe)} {' '.join(q(a) for a in args)} >/dev/null 2>&1 &"
    body = f"""#!/bin/sh
log() {{ echo "[$(date '+%Y-%m-%dT%H:%M:%S')] $1" >> {q(log)}; }}
start_helios() {{
  cd {q(root)} && {start}
}}
log 'waiting for HELIOS-L1 (process {pid}) to exit'
n=0; while kill -0 {pid} 2>/dev/null && [ $n -lt 240 ]; do sleep 0.5; n=$((n+1)); done
rm -rf {q(previous)}
if ! mv {q(root)} {q(previous)}; then log 'could not move the installation aside'; start_helios; exit 1; fi
if ! mv {q(staged)} {q(root)}; then log 'could not move the new build in'; mv {q(previous)} {q(root)}; start_helios; exit 1; fi
log 'installed; starting the new build'
start_helios
"""
    script = updates_dir() / "install_update.sh"
    script.write_text(body, encoding="utf-8")
    os.chmod(script, 0o755)
    return script, ["/bin/sh", str(script)]


def install_staged_on_start(args: List[str]) -> bool:
    """
    At start-up of a published build, before the server starts: when a newer build is
    staged and complete, start the swap script and return True (the caller exits at once;
    the script starts the new build with the same ``args``).
    """
    if install_problem() is not None:
        return False
    staged = load_state().get("staged")
    root = install_root()
    if not staged or root is None:
        return False
    path = staged_dir(root)
    if not is_newer(staged.get("tag", "")) or not launcher(path).is_file():
        return False
    _, cmd = helper_script(root, path, previous_dir(root), list(args), os.getpid())
    kw: Dict[str, Any] = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
                          "close_fds": True, "cwd": str(updates_dir())}
    if sys.platform == "win32":
        flags = 0x00000200 | 0x08000000  # CREATE_NEW_PROCESS_GROUP, CREATE_NO_WINDOW
        try:
            subprocess.Popen(cmd, creationflags=flags | 0x01000000, **kw)  # CREATE_BREAKAWAY_FROM_JOB
        except OSError:
            subprocess.Popen(cmd, creationflags=flags, **kw)
        return True
    subprocess.Popen(cmd, start_new_session=True, **kw)
    return True
