"""
Post-build packaging utility.
Packages the PyInstaller output into a clean, distributable ZIP archive for Windows.
"""
import os
import zipfile
from pathlib import Path

def create_distribution_zip():
    root = Path(__file__).resolve().parent
    dist_dir = root / "dist" / "HELIOS-L1"
    output_zip = root / "dist" / "HELIOS-L1-v1.0-Windows-x64.zip"

    if not dist_dir.exists():
        print(f"[!] Target directory does not exist: {dist_dir}")
        return

    print(f"[*] Packaging {dist_dir} into {output_zip}...")
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
        for file in dist_dir.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(root / "dist")
                zipf.write(file, arcname)

        # Include README and launcher batch script
        readme_path = root / "README.md"
        if readme_path.exists():
            zipf.write(readme_path, "HELIOS-L1/README.md")

        batch_path = root / "Launch-HELIOS.bat"
        if batch_path.exists():
            zipf.write(batch_path, "HELIOS-L1/Launch-HELIOS.bat")

    size_mb = os.path.getsize(output_zip) / (1024 * 1024)
    print(f"[+] Distribution package created: {output_zip} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    create_distribution_zip()
