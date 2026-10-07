"""
Build the HELIOS-L1 standalone app for the current OS and archive it.

    pip install -e .[build]
    python packaging/build.py

Output: dist/HELIOS-L1/ (runnable folder) and dist/HELIOS-L1-<version>-<os>-<arch>.zip|.tar.gz
(--dist and --work choose other output and work folders).
"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios.release_names import archive_basename, archive_format  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Build the HELIOS-L1 standalone app and archive it.")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist", help="output folder (default: dist/)")
    parser.add_argument("--work", type=Path, default=ROOT / "build", help="PyInstaller work folder (default: build/)")
    args = parser.parse_args()
    dist = args.dist.resolve()
    subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
         "--distpath", str(dist), "--workpath", str(args.work.resolve()),
         str(ROOT / "packaging" / "helios.spec")],
        check=True,
    )
    # The updater (helios/updates.py) picks the archive for its system by this name.
    base = dist / archive_basename()
    archive = shutil.make_archive(str(base), archive_format(), root_dir=dist, base_dir="HELIOS-L1")
    print(f"Built {archive}")


if __name__ == "__main__":
    main()
