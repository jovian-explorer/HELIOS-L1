"""
Generates an iconic, ultra-clean, minimalist aerospace vector logo for HELIOS-L1.
Pure geometric elegance:
- Deep cosmic navy badge (#060d1e)
- Stylized radiant golden Sun with 12 clean geometric coronal rays & luminous core
- Elegant electric-cyan Archimedean Parker Spiral streamline gracefully arching towards L1
- Emerald/cyan 3D Halo Orbit ellipse centered at Lagrange Point L1
- High-precision geometric space observatory satellite with dual solar wings & magnetometer
- Clean outer bezel ring in aerospace gold and cyan
- Drawn entirely from geometric primitives: no noise, clutter or stray lines.
"""
import math
from pathlib import Path
from PIL import Image, ImageDraw

CLEAN_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <!-- Deep Space Radial Background -->
    <radialGradient id="spaceBg" cx="35%" cy="30%" r="75%">
      <stop offset="0%" stop-color="#0c1833" />
      <stop offset="60%" stop-color="#060c1d" />
      <stop offset="100%" stop-color="#02050e" />
    </radialGradient>

    <!-- Solar Core Radial Gradient -->
    <radialGradient id="sunDisk" cx="35%" cy="35%" r="65%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="25%" stop-color="#fef08a" />
      <stop offset="60%" stop-color="#f59e0b" />
      <stop offset="90%" stop-color="#d97706" />
      <stop offset="100%" stop-color="#b45309" />
    </radialGradient>

    <!-- Solar Ray Gold Gradient -->
    <linearGradient id="rayGold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fef08a" />
      <stop offset="50%" stop-color="#fbbf24" />
      <stop offset="100%" stop-color="#d97706" />
    </linearGradient>

    <!-- Bezel Gold Gradient -->
    <linearGradient id="bezelGold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fef08a" />
      <stop offset="35%" stop-color="#f59e0b" />
      <stop offset="70%" stop-color="#d97706" />
      <stop offset="100%" stop-color="#b45309" />
    </linearGradient>

    <!-- Electric Cyan Gradient -->
    <linearGradient id="cyanLine" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="60%" stop-color="#06b6d4" />
      <stop offset="100%" stop-color="#0284c7" />
    </linearGradient>

    <!-- Halo Orbit Gradient -->
    <linearGradient id="orbitGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#10b981" />
      <stop offset="50%" stop-color="#06b6d4" />
      <stop offset="100%" stop-color="#0284c7" />
    </linearGradient>
  </defs>

  <!-- Outer Circular Badge -->
  <circle cx="256" cy="256" r="248" fill="url(#spaceBg)" />

  <!-- Subtle Celestial Grid Lines -->
  <circle cx="256" cy="256" r="215" fill="none" stroke="#1e293b" stroke-width="1.5" stroke-dasharray="3 9" opacity="0.6" />
  <circle cx="256" cy="256" r="150" fill="none" stroke="#1e293b" stroke-width="1" stroke-dasharray="2 6" opacity="0.4" />

  <!-- 1. The Sun (Helios) on Left (cx=155, cy=256) -->
  <!-- 12 Clean Geometric Coronal Rays -->
  <g fill="url(#rayGold)" opacity="0.9">
    <!-- Ray 0 deg -->
    <polygon points="230,256 220,251 220,261" />
    <!-- Ray 30 deg -->
    <polygon points="220,293 211,286 219,277" />
    <!-- Ray 60 deg -->
    <polygon points="192,321 187,311 195,304" />
    <!-- Ray 90 deg -->
    <polygon points="155,331 150,321 160,321" />
    <!-- Ray 120 deg -->
    <polygon points="118,321 115,304 123,311" />
    <!-- Ray 150 deg -->
    <polygon points="90,293 91,277 99,286" />
    <!-- Ray 180 deg -->
    <polygon points="80,256 90,251 90,261" />
    <!-- Ray 210 deg -->
    <polygon points="90,219 99,226 91,235" />
    <!-- Ray 240 deg -->
    <polygon points="118,191 123,201 115,208" />
    <!-- Ray 270 deg -->
    <polygon points="155,181 150,191 160,191" />
    <!-- Ray 300 deg -->
    <polygon points="192,191 195,208 187,201" />
    <!-- Ray 330 deg -->
    <polygon points="220,219 219,235 211,226" />
  </g>

  <!-- Luminous Solar Disc -->
  <circle cx="155" cy="256" r="62" fill="url(#sunDisk)" stroke="#fef08a" stroke-width="2" />
  <!-- Solar specular gleam -->
  <circle cx="138" cy="239" r="7" fill="#ffffff" opacity="0.5" />

  <!-- 2. Archimedean Parker Spiral (Electric Cyan Field Streamline) -->
  <!-- Smooth vector streamline originating at Sun and curving gracefully past L1 -->
  <path d="M 155,194 C 175,135 235,100 300,105 C 385,112 435,175 440,255 C 445,320 405,385 345,410 C 290,432 230,420 180,380"
        fill="none" stroke="url(#cyanLine)" stroke-width="3.5" stroke-linecap="round" />
  <path d="M 215,220 C 260,185 330,185 375,220 C 415,255 410,315 370,355"
        fill="none" stroke="#0ea5e9" stroke-width="1.8" stroke-linecap="round" stroke-dasharray="4 6" opacity="0.45" />

  <!-- 3. Sun-to-L1 Lagrange Baseline -->
  <line x1="155" y1="256" x2="365" y2="256" stroke="#fbbf24" stroke-width="1.5" stroke-dasharray="4 5" opacity="0.6" />

  <!-- 4. L1 Halo Orbit (Clean Tilted 3D Ellipse) -->
  <g transform="rotate(-15 365 256)">
    <ellipse cx="365" cy="256" rx="42" ry="88" fill="none" stroke="url(#orbitGrad)" stroke-width="2.5" stroke-dasharray="6 4" opacity="0.9" />
  </g>
  <!-- L1 Saddle Point Equilibrium Marker -->
  <circle cx="365" cy="256" r="3.5" fill="#10b981" />

  <!-- 5. Spacecraft (Aditya-L1 / DSCOVR) at L1 -->
  <!-- Positioned cleanly on halo orbit at (378, 222) -->
  <g transform="translate(378, 222) rotate(18)">
    <!-- Active telemetry ping ring -->
    <circle cx="0" cy="0" r="14" fill="none" stroke="#10b981" stroke-width="1.2" opacity="0.7" />

    <!-- Left Solar Array Wing -->
    <rect x="-7" y="-28" width="14" height="20" rx="1.5" fill="#0284c7" stroke="#38bdf8" stroke-width="1.2" />
    <line x1="-7" y1="-18" x2="7" y2="-18" stroke="#38bdf8" stroke-width="0.8" />

    <!-- Right Solar Array Wing -->
    <rect x="-7" y="8" width="14" height="20" rx="1.5" fill="#0284c7" stroke="#38bdf8" stroke-width="1.2" />
    <line x1="-7" y1="18" x2="7" y2="18" stroke="#38bdf8" stroke-width="0.8" />

    <!-- Spacecraft Central Bus -->
    <rect x="-8" y="-8" width="16" height="16" rx="2" fill="#f8fafc" stroke="#475569" stroke-width="1.5" />
    <circle cx="0" cy="0" r="3.5" fill="#10b981" />

    <!-- Magnetometer Boom pointing Sunward -->
    <line x1="-8" y1="0" x2="-22" y2="0" stroke="#cbd5e1" stroke-width="1.5" />
    <circle cx="-22" cy="0" r="2" fill="#f59e0b" />

    <!-- Earth Antenna Dish -->
    <line x1="8" y1="0" x2="16" y2="0" stroke="#cbd5e1" stroke-width="1.5" />
    <path d="M 16,-4 A 5 5 0 0 1 16,4" fill="none" stroke="#94a3b8" stroke-width="1.5" />
  </g>

  <!-- Clean Bottom Typographic Ribbon: HELIOS-L1 -->
  <g transform="translate(256, 458)" text-anchor="middle">
    <rect x="-92" y="-22" width="184" height="30" rx="6" fill="#070f22" stroke="#38bdf8" stroke-width="1.2" opacity="0.95" />
    <text x="0" y="-1" fill="#ffffff" font-family="'Segoe UI', -apple-system, sans-serif" font-size="18" font-weight="900" letter-spacing="4">
      HELIOS<tspan fill="#f59e0b">-L1</tspan>
    </text>
  </g>

  <!-- Outer Precision Aerospace Bezel -->
  <circle cx="256" cy="256" r="248" fill="none" stroke="url(#bezelGold)" stroke-width="4.5" />
  <circle cx="256" cy="256" r="243" fill="none" stroke="#0ea5e9" stroke-width="1.5" opacity="0.6" />
</svg>
"""

def generate_clean_logo_and_icons(project_dir: Path):
    img_dir = project_dir / "helios" / "gui" / "static" / "img"
    assets_dir = project_dir / "assets"

    for d in [img_dir, assets_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Save SVG
    for p in [img_dir / "helios_logo.svg", assets_dir / "helios_logo.svg"]:
        p.write_text(CLEAN_SVG, encoding="utf-8")
        print(f"[+] Clean SVG written: {p}")

    # 2. Master Raster Draw at 1024x1024
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r_badge = 490

    # Background circle
    draw.ellipse([cx - r_badge, cy - r_badge, cx + r_badge, cy + r_badge], fill=(7, 15, 32, 255))

    # Grid / reticle rings
    draw.ellipse([cx - 430, cy - 430, cx + 430, cy + 430], outline=(30, 41, 59, 150), width=3)
    draw.ellipse([cx - 300, cy - 300, cx + 300, cy + 300], outline=(30, 41, 59, 100), width=2)

    # 1. Sun on Left (cx=310, cy=512)
    sun_x, sun_y = int(size * 0.305), cy
    r_sun = 124

    # 12 Geometric Coronal Rays
    for i in range(12):
        ang = i * (2 * math.pi / 12)
        tip_r = r_sun + 36
        base_r = r_sun + 8
        half_w = 0.12
        p1 = (int(sun_x + tip_r * math.cos(ang)), int(sun_y + tip_r * math.sin(ang)))
        p2 = (int(sun_x + base_r * math.cos(ang - half_w)), int(sun_y + base_r * math.sin(ang - half_w)))
        p3 = (int(sun_x + base_r * math.cos(ang + half_w)), int(sun_y + base_r * math.sin(ang + half_w)))
        draw.polygon([p1, p2, p3], fill=(251, 191, 36, 230))

    # Sun Disk Gradient
    for r in range(r_sun, 0, -2):
        frac = r / r_sun
        if frac > 0.6:
            f2 = (frac - 0.6) / 0.4
            cr = int(245 * (1 - f2) + 217 * f2)
            cg = int(158 * (1 - f2) + 119 * f2)
            cb = int(11 * (1 - f2) + 6 * f2)
        elif frac > 0.2:
            f2 = (frac - 0.2) / 0.4
            cr = 255
            cg = int(240 * (1 - f2) + 158 * f2)
            cb = int(138 * (1 - f2) + 11 * f2)
        else:
            cr, cg, cb = 255, 255, 250
        draw.ellipse([sun_x - r, sun_y - r, sun_x + r, sun_y + r], fill=(cr, cg, cb, 255))
    draw.ellipse([sun_x - r_sun, sun_y - r_sun, sun_x + r_sun, sun_y + r_sun], outline=(254, 240, 138, 255), width=4)

    # 2. Parker Spiral Streamline (Electric Cyan Vector Curve)
    pts = []
    for i in range(290):
        theta = i * 0.015
        rad = 135 + theta * 115
        px = int(sun_x + rad * math.cos(theta - 2.1))
        py = int(sun_y + rad * math.sin(theta - 2.1))
        if 0 <= px < size and 0 <= py < size:
            pts.append((px, py))
    if len(pts) > 2:
        draw.line(pts, fill=(56, 189, 248, 240), width=8)

    # Sun-to-L1 line
    l1_x, l1_y = int(size * 0.71), cy
    draw.line([(sun_x + r_sun, sun_y), (l1_x, l1_y)], fill=(251, 191, 36, 160), width=3)

    # 3. L1 Halo Orbit (Clean tilted ellipse)
    halo_rx, halo_ry = 84, 176
    halo_canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    halo_draw = ImageDraw.Draw(halo_canvas)
    halo_draw.ellipse([l1_x - halo_rx, l1_y - halo_ry, l1_x + halo_rx, l1_y + halo_ry], outline=(16, 185, 129, 230), width=6)
    halo_rot = halo_canvas.rotate(-15, center=(l1_x, l1_y), resample=Image.Resampling.BICUBIC)
    img.alpha_composite(halo_rot)

    # L1 Point
    draw.ellipse([l1_x - 7, l1_y - 7, l1_x + 7, l1_y + 7], fill=(16, 185, 129, 255))

    # 4. Spacecraft at L1 (Aditya-L1 / DSCOVR style)
    sat_x, sat_y = int(l1_x + 26), int(l1_y - 68)

    # Signal ring
    draw.ellipse([sat_x - 28, sat_y - 28, sat_x + 28, sat_y + 28], outline=(16, 185, 129, 160), width=2)

    # Solar Panels
    pw = 28
    draw.rectangle([sat_x - pw//2, sat_y - 58, sat_x + pw//2, sat_y - 14], fill=(2, 132, 199, 255), outline=(56, 189, 248, 255), width=3)
    draw.rectangle([sat_x - pw//2, sat_y + 14, sat_x + pw//2, sat_y + 58], fill=(2, 132, 199, 255), outline=(56, 189, 248, 255), width=3)
    draw.line([(sat_x - pw//2, sat_y - 36), (sat_x + pw//2, sat_y - 36)], fill=(56, 189, 248, 255), width=2)
    draw.line([(sat_x - pw//2, sat_y + 36), (sat_x + pw//2, sat_y + 36)], fill=(56, 189, 248, 255), width=2)

    # Satellite Bus
    br = 18
    draw.rectangle([sat_x - br, sat_y - br, sat_x + br, sat_y + br], fill=(248, 250, 252, 255), outline=(71, 85, 105, 255), width=4)
    draw.ellipse([sat_x - 7, sat_y - 7, sat_x + 7, sat_y + 7], fill=(16, 185, 129, 255))

    # Magnetometer boom pointing Sunward
    draw.line([(sat_x - br, sat_y), (sat_x - 46, sat_y)], fill=(203, 213, 225, 255), width=3)
    draw.ellipse([sat_x - 50, sat_y - 4, sat_x - 42, sat_y + 4], fill=(245, 158, 11, 255))

    # Earth Antenna dish
    draw.line([(sat_x + br, sat_y), (sat_x + 34, sat_y)], fill=(203, 213, 225, 255), width=3)
    draw.arc([sat_x + 26, sat_y - 10, sat_x + 42, sat_y + 10], start=270, end=90, fill=(148, 163, 184, 255), width=4)

    # 5. Bottom Typography Badge: HELIOS-L1
    badge_w, badge_h = 360, 60
    bx0, by0 = cx - badge_w // 2, int(size * 0.88)
    draw.rounded_rectangle([bx0, by0, bx0 + badge_w, by0 + badge_h], radius=12, fill=(6, 12, 26, 240), outline=(56, 189, 248, 220), width=3)

    # 6. Outer Precision Bezel Rings
    draw.ellipse([cx - r_badge, cy - r_badge, cx + r_badge, cy + r_badge], outline=(245, 158, 11, 255), width=9)
    draw.ellipse([cx - r_badge + 8, cy - r_badge + 8, cx + r_badge - 8, cy + r_badge - 8], outline=(14, 165, 233, 160), width=3)

    # Apply circular mask
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([cx - r_badge - 4, cy - r_badge - 4, cx + r_badge + 4, cy + r_badge + 4], fill=255)
    clean_badge = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    clean_badge.paste(img, (0, 0), mask=mask)

    # Lanczos downsample to 512, 256
    logo_512 = clean_badge.resize((512, 512), resample=Image.Resampling.LANCZOS)
    logo_256 = clean_badge.resize((256, 256), resample=Image.Resampling.LANCZOS)

    # Save PNGs: 512 px for the packaging assets; the page shows the logo at 40-96 px, so its
    # copy is 192 px (102 KB at 512 px was the largest image of the first page load).
    logo_512.save(str(assets_dir / "helios_logo.png"), format="PNG")
    clean_badge.resize((192, 192), resample=Image.Resampling.LANCZOS).save(str(img_dir / "helios_logo.png"), format="PNG", optimize=True)
    print(f"[+] Clean PNG logos saved: {assets_dir / 'helios_logo.png'}, {img_dir / 'helios_logo.png'}")

    # Generate multi-resolution ICO (standard Windows sizes: 16, 24, 32, 48, 64, 128, 256)
    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    for p in [
        assets_dir / "helios.ico",
        img_dir / "helios.ico",
    ]:
        logo_256.save(str(p), format="ICO", sizes=icon_sizes)
        print(f"[+] Clean multi-res ICO saved: {p}")

if __name__ == "__main__":
    proj_root = Path(__file__).resolve().parent.parent
    generate_clean_logo_and_icons(proj_root)
