"""
Build the HELIOS-L1 standalone app for the current OS and archive it.

    pip install -e .[build]
    python packaging/build.py

Output: dist/HELIOS-L1/ (runnable folder) and dist/HELIOS-L1-<version>-<os>-<arch>.zip|.tar.gz
"""
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios import __version__  # noqa: E402

OS_NAMES = {"win32": "windows", "darwin": "macos"}


def main():
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(ROOT / "dist"), "--workpath", str(ROOT / "build"),
         str(ROOT / "packaging" / "helios.spec")],
        check=True,
    )
    os_name = OS_NAMES.get(sys.platform, "linux")
    arch = platform.machine().lower().replace("amd64", "x86_64").replace("aarch64", "arm64")
    base = ROOT / "dist" / f"HELIOS-L1-{__version__}-{os_name}-{arch}"
    fmt = "zip" if os_name == "windows" else "gztar"
    archive = shutil.make_archive(str(base), fmt, root_dir=ROOT / "dist", base_dir="HELIOS-L1")
    print(f"Built {archive}")


if __name__ == "__main__":
    main()
