"""
Process the generated mission patch into the production logo and icon assets:
- helios_logo.png (512x512 with transparent circular border)
- helios.ico (multi-resolution 16, 24, 32, 48, 64, 128, 256 px)
- Copies to static web directories and binary assets
"""
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps

def process_logo_assets(source_jpg_path: Path, project_root: Path):
    img = Image.open(source_jpg_path).convert("RGBA")
    w, h = img.size

    # The badge is centered in the square. Let's find the circle bounds.
    # We create a circular mask that smoothly anti-aliases the outer rim
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    
    # Outer circle border is located at approximately margin 12 px from edges
    cx, cy = w // 2, h // 2
    radius = int(min(w, h) * 0.488)  # perfectly captures the outer stitched/metallic rim
    
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=255)
    
    # Apply mask
    transparent_badge = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    transparent_badge.paste(img, (0, 0), mask=mask)
    
    # Resize to 512x512 with high quality Lanczos resampling
    logo_512 = transparent_badge.resize((512, 512), resample=Image.Resampling.LANCZOS)
    logo_256 = transparent_badge.resize((256, 256), resample=Image.Resampling.LANCZOS)
    
    # Target directories
    assets_dir = project_root / "assets"
    static_img_dir = project_root / "helios" / "gui" / "static" / "img"
    installed_dir = Path("C:/Users/AGY-VCO/HELIOS-L1")
    installed_assets = installed_dir / "assets"
    installed_static = installed_dir / "_internal" / "helios" / "gui" / "static" / "img"

    for d in [assets_dir, static_img_dir, installed_assets, installed_static]:
        d.mkdir(parents=True, exist_ok=True)
        
    # Save PNGs
    for p in [
        assets_dir / "helios_logo.png",
        static_img_dir / "helios_logo.png",
        installed_assets / "helios_logo.png",
        installed_static / "helios_logo.png"
    ]:
        logo_512.save(str(p), format="PNG")
        print(f"[+] Saved PNG logo: {p}")

    # Generate multi-size ICO
    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    for p in [
        assets_dir / "helios.ico",
        static_img_dir / "helios.ico",
        installed_assets / "helios.ico",
        installed_static / "helios.ico"
    ]:
        logo_256.save(str(p), format="ICO", sizes=icon_sizes)
        print(f"[+] Saved ICO icon: {p}")

if __name__ == "__main__":
    src_jpg = Path(r"C:\Users\AGY-VCO\.gemini\antigravity-cli\brain\29452af0-6261-4348-b4d1-6996dd3c9a6c\helios_mission_patch_1790085949505.jpg")
    proj_root = Path(__file__).resolve().parent.parent
    process_logo_assets(src_jpg, proj_root)
