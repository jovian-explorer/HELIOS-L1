"""
Names of the release archives, shared by packaging/build.py (which makes them) and
helios/updates.py (which picks the one for this system), so the two cannot drift apart.
Imports nothing that touches the user's folders.
"""
import platform
import sys

from helios import __version__

APP = "HELIOS-L1"


def platform_tag() -> str:
    """The system part of a release archive's name: windows-x86_64, macos-arm64, linux-x86_64."""
    os_tag = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    return f"{os_tag}-{arch}"


def archive_format() -> str:
    """shutil.make_archive format of the release archive on this system (.zip or .tar.gz)."""
    return "zip" if sys.platform == "win32" else "gztar"


def archive_basename(version: str = __version__) -> str:
    """Release archive name without extension, e.g. HELIOS-L1-0.0.2-windows-x86_64."""
    return f"{APP}-{version}-{platform_tag()}"
