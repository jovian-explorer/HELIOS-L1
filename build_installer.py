"""
Complete Build and Packaging Automation for HELIOS-L1.
1. Generates custom application icon.
2. Builds main scientific engine and native GUI into dist/HELIOS-L1/HELIOS-L1.exe.
3. Packages runtime assets, sample datasets, and batch launcher into application folder.
4. Compresses application bundle into payload.zip and release ZIP archive.
5. Builds standalone single-file Windows installer executable: dist/HELIOS-L1-Setup.exe.
"""
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw

def create_app_icon(output_path: Path):
    """Ensure production multi-resolution icon is in place."""
    assets_png = output_path.parent / "helios_logo.png"
    if assets_png.exists():
        img = Image.open(assets_png).convert("RGBA")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img.resize((256, 256), Image.Resampling.LANCZOS).save(
            str(output_path),
            format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
        )
        print(f"[+] Production multi-resolution icon verified: {output_path}")
        return

    # Fallback generator if image not present
    img = Image.new("RGBA", (256, 256), (11, 19, 41, 0))
    draw = ImageDraw.Draw(img)
    for r in range(120, 70, -5):
        alpha = int(255 * (1 - (r - 70) / 50) * 0.4)
        draw.ellipse([128 - r, 128 - r, 128 + r, 128 + r], fill=(245, 158, 11, alpha))
    draw.ellipse([128 - 65, 128 - 65, 128 + 65, 128 + 65], fill=(251, 191, 36, 255), outline=(245, 158, 11, 255), width=3)
    draw.ellipse([20, 80, 236, 176], outline=(56, 189, 248, 200), width=4)
    draw.ellipse([190, 100, 208, 118], fill=(16, 185, 129, 255), outline=(255, 255, 255, 255), width=2)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print(f"[+] Icon generated: {output_path}")

def build_app(root_dir: Path, icon_path: Path):
    """Compile main HELIOS-L1 application bundle."""
    static_src = root_dir / "helios" / "gui" / "static"
    data_src = root_dir / "helios" / "data"

    add_data_static = f"{static_src};helios/gui/static"
    add_data_data = f"{data_src};helios/data"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--name", "HELIOS-L1",
        "--icon", str(icon_path),
        "--add-data", add_data_static,
        "--add-data", add_data_data,
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespans",
        "--hidden-import", "uvicorn.lifespans.on",
        "--hidden-import", "pandas",
        "--hidden-import", "matplotlib",
        "--hidden-import", "scipy",
        "--hidden-import", "webview",
        "--hidden-import", "spiceypy",
        "run.py"
    ]

    print("[*] Stage 1: Compiling HELIOS-L1 application bundle...")
    res = subprocess.run(cmd, cwd=str(root_dir))
    if res.returncode != 0:
        raise RuntimeError(f"Application build failed with exit code {res.returncode}")

    # Copy auxiliary files into dist/HELIOS-L1
    dist_dir = root_dir / "dist" / "HELIOS-L1"
    assets_dest = dist_dir / "assets"
    assets_dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(icon_path, assets_dest / "helios.ico")
    for asset_file in ["helios_logo.png", "helios_logo.svg"]:
        src_asset = root_dir / "assets" / asset_file
        if src_asset.exists():
            shutil.copy2(src_asset, assets_dest / asset_file)

    for f in ["Launch-HELIOS.bat", "README.md"]:
        src = root_dir / f
        if src.exists():
            shutil.copy2(src, dist_dir / f)

    print("[+] Application bundle compiled at dist/HELIOS-L1")

def package_payload(root_dir: Path):
    """Compress dist/HELIOS-L1 into payload.zip and release ZIP."""
    dist_dir = root_dir / "dist" / "HELIOS-L1"
    payload_zip = root_dir / "dist" / "payload.zip"
    release_zip = root_dir / "dist" / "HELIOS-L1-v1.0-Windows-x64.zip"

    print(f"[*] Stage 2: Packaging payload into {payload_zip.name}...")
    with zipfile.ZipFile(payload_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for file in dist_dir.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(dist_dir)
                z.write(file, arcname)

    # Duplicate as release ZIP
    shutil.copy2(payload_zip, release_zip)
    size_mb = os.path.getsize(release_zip) / (1024 * 1024)
    print(f"[+] Distribution ZIP created: {release_zip.name} ({size_mb:.2f} MB)")

def build_setup_installer(root_dir: Path, icon_path: Path):
    """Compile installer_wizard.py into standalone HELIOS-L1-Setup.exe."""
    payload_zip = root_dir / "dist" / "payload.zip"
    if not payload_zip.exists():
        raise FileNotFoundError(f"Missing payload: {payload_zip}")

    add_data_payload = f"{payload_zip};."

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "HELIOS-L1-Setup",
        "--icon", str(icon_path),
        "--add-data", add_data_payload,
        "installer_wizard.py"
    ]

    print("[*] Stage 3: Compiling single-file Windows Installer: HELIOS-L1-Setup.exe...")
    res = subprocess.run(cmd, cwd=str(root_dir))
    if res.returncode != 0:
        raise RuntimeError(f"Installer build failed with exit code {res.returncode}")

    setup_exe = root_dir / "dist" / "HELIOS-L1-Setup.exe"
    if setup_exe.exists():
        size_mb = os.path.getsize(setup_exe) / (1024 * 1024)
        print(f"[+] SUCCESS! Windows Installer executable created:")
        print(f"    -> {setup_exe} ({size_mb:.2f} MB)")
    else:
        raise FileNotFoundError("Setup exe was not found in dist/")

def main():
    root_dir = Path(__file__).resolve().parent
    icon_path = root_dir / "assets" / "helios.ico"
    create_app_icon(icon_path)

    build_app(root_dir, icon_path)
    package_payload(root_dir)
    build_setup_installer(root_dir, icon_path)

    print("\n" + "=" * 65)
    print(" HELIOS-L1: FULL BUILD AND PACKAGING FINISHED")
    print("=" * 65)
    print(" Output Deliverables:")
    print(" 1. Setup Installer: dist\\HELIOS-L1-Setup.exe (Self-installing EXE)")
    print(" 2. Application:     dist\\HELIOS-L1\\HELIOS-L1.exe")
    print(" 3. ZIP Archive:     dist\\HELIOS-L1-v1.0-Windows-x64.zip")
    print("=" * 65)

if __name__ == "__main__":
    main()
