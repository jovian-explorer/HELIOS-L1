"""
HELIOS-L1 Scientific Logo & Icon Asset Generator.
Generates:
1. helios_logo.svg - Scalable vector logo with Sun, Coronal Loops, Parker Spiral, L1 Halo Orbit, and Spacecraft.
2. helios_logo.png - 512x512 high-resolution anti-aliased logo.
3. helios.ico - Multi-resolution Windows icon (16, 24, 32, 48, 64, 128, 256 px).
4. Synchronizes to assets/ and helios/gui/static/img/ directories.
"""
import os
import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

SVG_CONTENT = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <!-- Background Gradient -->
    <radialGradient id="badgeBg" cx="45%" cy="40%" r="65%">
      <stop offset="0%" stop-color="#0e1b38" />
      <stop offset="55%" stop-color="#070e20" />
      <stop offset="100%" stop-color="#02050e" />
    </radialGradient>

    <!-- Outer Gold Ring -->
    <linearGradient id="ringGold" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fbbf24" />
      <stop offset="50%" stop-color="#f59e0b" />
      <stop offset="100%" stop-color="#b45309" />
    </linearGradient>

    <!-- Cyan Plasma Gradient -->
    <linearGradient id="plasmaGrad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8" />
      <stop offset="50%" stop-color="#06b6d4" />
      <stop offset="100%" stop-color="#0284c7" />
    </linearGradient>

    <!-- Solar Core Radial Gradient -->
    <radialGradient id="sunCore" cx="40%" cy="38%" r="60%">
      <stop offset="0%" stop-color="#ffffff" />
      <stop offset="20%" stop-color="#fef08a" />
      <stop offset="50%" stop-color="#fbbf24" />
      <stop offset="78%" stop-color="#f59e0b" />
      <stop offset="95%" stop-color="#d97706" />
      <stop offset="100%" stop-color="#9a3412" />
    </radialGradient>

    <!-- Solar Corona Glow -->
    <radialGradient id="coronaGlow" cx="50%" cy="50%" r="50%">
      <stop offset="0%" stop-color="#fbbf24" stop-opacity="0.85" />
      <stop offset="35%" stop-color="#f59e0b" stop-opacity="0.55" />
      <stop offset="70%" stop-color="#ea580c" stop-opacity="0.2" />
      <stop offset="100%" stop-color="#dc2626" stop-opacity="0" />
    </radialGradient>

    <!-- L1 Orbit Glow -->
    <linearGradient id="haloOrbit" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8" stop-opacity="0.9" />
      <stop offset="50%" stop-color="#10b981" stop-opacity="0.8" />
      <stop offset="100%" stop-color="#0284c7" stop-opacity="0.5" />
    </linearGradient>

    <!-- Glow Filters -->
    <filter id="bloom" x="-30%" y="-30%" width="160%" height="160%">
      <feGaussianBlur stdDeviation="6" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>

    <filter id="strongBloom" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="14" result="blur" />
      <feMerge>
        <feMergeNode in="blur" />
        <feMergeNode in="SourceGraphic" />
      </feMerge>
    </filter>
  </defs>

  <!-- Base Circular Badge -->
  <circle cx="256" cy="256" r="248" fill="url(#badgeBg)" stroke="#1e293b" stroke-width="2" />

  <!-- Technical Reticle & Graduation Ticks -->
  <circle cx="256" cy="256" r="236" fill="none" stroke="#334155" stroke-width="1.5" stroke-dasharray="3 7" opacity="0.6" />
  <circle cx="256" cy="256" r="218" fill="none" stroke="#0ea5e9" stroke-width="1" opacity="0.25" />

  <!-- Astrometric Axis Lines -->
  <line x1="256" y1="20" x2="256" y2="492" stroke="#1e293b" stroke-width="1" stroke-dasharray="4 6" opacity="0.4" />
  <line x1="20" y1="256" x2="492" y2="256" stroke="#1e293b" stroke-width="1" stroke-dasharray="4 6" opacity="0.4" />

  <!-- Parker Archimedean Magnetic Spiral Streamlines -->
  <g opacity="0.55" filter="url(#bloom)">
    <!-- Streamline 1 -->
    <path d="M 175,230 C 130,220 85,260 55,310 C 30,350 35,400 65,435" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-dasharray="6 4" />
    <!-- Streamline 2 (Passing through L1) -->
    <path d="M 215,200 C 235,140 295,115 365,135 C 415,150 445,190 460,240" fill="none" stroke="#06b6d4" stroke-width="2.5" stroke-linecap="round" />
    <!-- Streamline 3 -->
    <path d="M 155,290 C 145,350 180,410 240,445 C 290,470 350,465 395,430" fill="none" stroke="#0284c7" stroke-width="1.8" stroke-linecap="round" stroke-dasharray="4 4" />
  </g>

  <!-- Sun Coronal Envelope & Prominence Loops -->
  <circle cx="175" cy="256" r="115" fill="url(#coronaGlow)" filter="url(#strongBloom)" />

  <!-- Magnetic Prominence Arcades (Coronal Loops) -->
  <g stroke="#fbbf24" fill="none" stroke-linecap="round" opacity="0.85" filter="url(#bloom)">
    <path d="M 125,185 C 105,140 160,130 185,170" stroke-width="3" />
    <path d="M 100,240 C 65,220 70,290 105,280" stroke-width="2.5" />
    <path d="M 135,325 C 120,370 180,380 195,335" stroke-width="2.8" />
  </g>

  <!-- Core Solar Disk -->
  <circle cx="175" cy="256" r="68" fill="url(#sunCore)" filter="url(#bloom)" stroke="#fef08a" stroke-width="1.5" />

  <!-- Sun Limb Flare Accents -->
  <circle cx="175" cy="256" r="62" fill="none" stroke="#ffffff" stroke-width="1.5" opacity="0.5" />
  <circle cx="152" cy="235" r="8" fill="#ffffff" opacity="0.35" filter="url(#bloom)" />

  <!-- Sun-Earth Lagrange L1 Line of Sight -->
  <line x1="175" y1="256" x2="435" y2="256" stroke="#fbbf24" stroke-width="1.5" stroke-dasharray="3 5" opacity="0.6" />

  <!-- L1 Halo Orbit (3D Tilted Ellipse) -->
  <g transform="rotate(-18 365 256)" filter="url(#bloom)">
    <!-- Halo orbit path -->
    <ellipse cx="365" cy="256" rx="55" ry="92" fill="none" stroke="url(#haloOrbit)" stroke-width="2.5" stroke-dasharray="7 5" />
    <!-- Orbit perspective shadow/rear arc -->
    <path d="M 365,164 A 55 92 0 0 1 420,256" fill="none" stroke="#0ea5e9" stroke-width="1.5" opacity="0.4" />
  </g>

  <!-- L1 Equilibrium Crosshair Marker -->
  <g transform="translate(365, 256)" opacity="0.7">
    <circle cx="0" cy="0" r="14" fill="none" stroke="#10b981" stroke-width="1" stroke-dasharray="2 3" />
    <line x1="-18" y1="0" x2="18" y2="0" stroke="#10b981" stroke-width="1" />
    <line x1="0" y1="-18" x2="0" y2="18" stroke="#10b981" stroke-width="1" />
  </g>

  <!-- L1 Spacecraft / Observatory (Aditya-L1 / DSCOVR Insp.) -->
  <!-- Positioned along the halo orbit at (378, 225) -->
  <g transform="translate(378, 222) rotate(22)" filter="url(#bloom)">
    <!-- Shock Wave / Plasma Shield Arc ahead of spacecraft -->
    <path d="M -18,-15 C -25,-4 -25,4 -18,15" fill="none" stroke="#38bdf8" stroke-width="2.5" stroke-linecap="round" opacity="0.9" />

    <!-- Solar Wind Stream Particles entering sensor -->
    <line x1="-28" y1="-6" x2="-18" y2="-6" stroke="#fbbf24" stroke-width="1.5" stroke-linecap="round" opacity="0.8" />
    <line x1="-32" y1="0" x2="-20" y2="0" stroke="#f59e0b" stroke-width="2" stroke-linecap="round" />
    <line x1="-28" y1="6" x2="-18" y2="6" stroke="#fbbf24" stroke-width="1.5" stroke-linecap="round" opacity="0.8" />

    <!-- Spacecraft Central Bus -->
    <rect x="-8" y="-9" width="16" height="18" rx="2" fill="#f8fafc" stroke="#64748b" stroke-width="1.5" />
    <rect x="-5" y="-6" width="10" height="12" fill="#0284c7" opacity="0.4" />

    <!-- High-Gain Antenna (Earth-pointing) -->
    <path d="M 8,0 L 14,-5 M 8,0 L 14,5 M 14,-5 A 6 6 0 0 1 14,5" fill="none" stroke="#e2e8f0" stroke-width="1.5" />
    <line x1="8" y1="0" x2="16" y2="0" stroke="#94a3b8" stroke-width="1.5" />

    <!-- Magnetometer Boom -->
    <line x1="0" y1="9" x2="0" y2="28" stroke="#cbd5e1" stroke-width="1.2" />
    <circle cx="0" cy="28" r="2.5" fill="#f59e0b" stroke="#ffffff" stroke-width="0.8" />

    <!-- Left Solar Array Wing -->
    <g transform="translate(0, -9)">
      <line x1="0" y1="0" x2="0" y2="-5" stroke="#94a3b8" stroke-width="2" />
      <rect x="-14" y="-28" width="28" height="23" rx="1.5" fill="#0369a1" stroke="#38bdf8" stroke-width="1.2" />
      <!-- Photovoltaic Grid lines -->
      <line x1="-14" y1="-20" x2="14" y2="-20" stroke="#38bdf8" stroke-width="0.8" opacity="0.7" />
      <line x1="-14" y1="-12" x2="14" y2="-12" stroke="#38bdf8" stroke-width="0.8" opacity="0.7" />
      <line x1="0" y1="-28" x2="0" y2="-5" stroke="#38bdf8" stroke-width="0.8" opacity="0.7" />
    </g>

    <!-- Right Solar Array Wing -->
    <g transform="translate(0, 9)">
      <line x1="0" y1="0" x2="0" y2="5" stroke="#94a3b8" stroke-width="2" />
      <rect x="-14" y="5" width="28" height="23" rx="1.5" fill="#0369a1" stroke="#38bdf8" stroke-width="1.2" />
      <!-- Photovoltaic Grid lines -->
      <line x1="-14" y1="13" x2="14" y2="13" stroke="#38bdf8" stroke-width="0.8" opacity="0.7" />
      <line x1="-14" y1="21" x2="14" y2="21" stroke="#38bdf8" stroke-width="0.8" opacity="0.7" />
      <line x1="0" y1="5" x2="0" y2="28" stroke="#38bdf8" stroke-width="0.8" opacity="0.7" />
    </g>

    <!-- Active Telemetry Beacon Ping -->
    <circle cx="0" cy="0" r="3" fill="#10b981" />
  </g>

  <!-- Orbit Ping Signal Rings -->
  <g transform="translate(378, 222)" opacity="0.8" filter="url(#bloom)">
    <circle cx="0" cy="0" r="16" fill="none" stroke="#10b981" stroke-width="1.2" opacity="0.7" />
    <circle cx="0" cy="0" r="28" fill="none" stroke="#38bdf8" stroke-width="1" stroke-dasharray="3 3" opacity="0.4" />
  </g>

  <!-- Typography Arc & Labels -->
  <!-- Top Curving Subtitle: HELIOPHYSICAL OBSERVATORY -->
  <path id="textArcTop" d="M 75,256 A 181 181 0 0 1 437,256" fill="none" />
  <text fill="#94a3b8" font-family="'Segoe UI', -apple-system, sans-serif" font-size="12" font-weight="700" letter-spacing="4.5">
    <textPath href="#textArcTop" startOffset="50%" text-anchor="middle">
      SUN-EARTH LAGRANGE-1 SUITE
    </textPath>
  </text>

  <!-- Lower Branding: HELIOS-L1 -->
  <g transform="translate(256, 462)" text-anchor="middle">
    <rect x="-95" y="-24" width="190" height="32" rx="6" fill="#0b1329" stroke="#38bdf8" stroke-width="1.5" opacity="0.95" />
    <text x="0" y="-3" fill="#ffffff" font-family="'Segoe UI', -apple-system, sans-serif" font-size="19" font-weight="900" letter-spacing="3">
      HELIOS<tspan fill="#f59e0b">-L1</tspan>
    </text>
  </g>

  <!-- Precision Outer Bezel Ring -->
  <circle cx="256" cy="256" r="248" fill="none" stroke="url(#ringGold)" stroke-width="4" opacity="0.9" />
  <circle cx="256" cy="256" r="252" fill="none" stroke="#0ea5e9" stroke-width="1" opacity="0.4" />
</svg>
"""

def generate_svg_and_raster(project_dir: Path):
    """Generate SVG, PNG, and ICO logo files."""
    img_dir = project_dir / "helios" / "gui" / "static" / "img"
    assets_dir = project_dir / "assets"
    dist_dir = project_dir / "dist" / "HELIOS-L1" / "assets"

    for d in [img_dir, assets_dir, dist_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Write SVG to static/img and assets
    svg_static = img_dir / "helios_logo.svg"
    svg_assets = assets_dir / "helios_logo.svg"
    svg_static.write_text(SVG_CONTENT, encoding="utf-8")
    svg_assets.write_text(SVG_CONTENT, encoding="utf-8")
    print(f"[+] SVG Logo saved to {svg_static}")

    # 2. Render high-res 512x512 Master Raster Image using PIL
    # We draw at 1024x1024 for supersampling then downsample with LANCZOS for razor-sharp quality
    size = 1024
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    cx, cy = size // 2, size // 2
    r_badge = 490

    # Background badge circle
    for r in range(r_badge, 0, -4):
        frac = r / r_badge
        r_col = int(14 * frac + 2 * (1 - frac))
        g_col = int(27 * frac + 5 * (1 - frac))
        b_col = int(56 * frac + 14 * (1 - frac))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(r_col, g_col, b_col, 255))

    # Grid / reticle rings
    draw.ellipse([cx - 460, cy - 460, cx + 460, cy + 460], outline=(30, 41, 59, 180), width=3)
    draw.ellipse([cx - 430, cy - 430, cx + 430, cy + 430], outline=(14, 165, 233, 70), width=2)

    # Parker Spiral Streamlines (Golden / Cyan curves)
    sun_x, sun_y = int(size * 0.35), cy
    steps = 400
    # Spiral 1
    pts1 = []
    for i in range(steps):
        theta = i * 0.018
        rad = 80 + theta * 65
        px = int(sun_x + rad * math.cos(theta + 0.8))
        py = int(sun_y + rad * math.sin(theta + 0.8))
        if 0 <= px < size and 0 <= py < size:
            pts1.append((px, py))
    if len(pts1) > 2:
        draw.line(pts1, fill=(56, 189, 248, 140), width=5)

    # Spiral 2 (Passing towards L1)
    pts2 = []
    for i in range(steps):
        theta = i * 0.016
        rad = 90 + theta * 70
        px = int(sun_x + rad * math.cos(theta - 2.1))
        py = int(sun_y + rad * math.sin(theta - 2.1))
        if 0 <= px < size and 0 <= py < size:
            pts2.append((px, py))
    if len(pts2) > 2:
        draw.line(pts2, fill=(6, 182, 212, 170), width=6)

    # Coronal Outer Glow
    for glow_r in range(260, 130, -5):
        alpha = int(210 * (1 - (glow_r - 130) / 130) * 0.45)
        draw.ellipse([sun_x - glow_r, sun_y - glow_r, sun_x + glow_r, sun_y + glow_r], fill=(245, 158, 11, alpha))

    # Coronal Magnetic Loops
    for loop_angle in [-0.8, -0.4, 0.4, 0.8]:
        loop_pts = []
        for a in range(50):
            t = a / 49.0
            ang = loop_angle + math.sin(t * math.pi) * 0.45
            dist = 135 + math.sin(t * math.pi) * 55
            lx = int(sun_x + dist * math.cos(ang))
            ly = int(sun_y + dist * math.sin(ang))
            loop_pts.append((lx, ly))
        if len(loop_pts) > 2:
            draw.line(loop_pts, fill=(251, 191, 36, 200), width=6)

    # Core Sun Disk
    r_sun = 135
    for r in range(r_sun, 0, -2):
        frac = r / r_sun
        if frac > 0.7:
            # Orange edge
            f2 = (frac - 0.7) / 0.3
            cr = int(245 * (1 - f2) + 217 * f2)
            cg = int(158 * (1 - f2) + 119 * f2)
            cb = int(11 * (1 - f2) + 6 * f2)
        elif frac > 0.3:
            # Golden amber
            f2 = (frac - 0.3) / 0.4
            cr = int(254 * (1 - f2) + 245 * f2)
            cg = int(240 * (1 - f2) + 158 * f2)
            cb = int(138 * (1 - f2) + 11 * f2)
        else:
            # White-hot solar core
            f2 = frac / 0.3
            cr = 255
            cg = int(255 * (1 - f2) + 240 * f2)
            cb = int(255 * (1 - f2) + 138 * f2)
        draw.ellipse([sun_x - r, sun_y - r, sun_x + r, sun_y + r], fill=(cr, cg, cb, 255))
    draw.ellipse([sun_x - r_sun, sun_y - r_sun, sun_x + r_sun, sun_y + r_sun], outline=(254, 240, 138, 255), width=4)

    # Lagrange Line of Sight
    l1_x, l1_y = int(size * 0.72), cy
    draw.line([(sun_x + r_sun, sun_y), (l1_x, l1_y)], fill=(251, 191, 36, 150), width=3)

    # L1 Lissajous / Halo Orbit (Tilted Ellipse)
    halo_rx, halo_ry = 110, 180
    halo_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    halo_draw = ImageDraw.Draw(halo_img)
    halo_draw.ellipse([l1_x - halo_rx, l1_y - halo_ry, l1_x + halo_rx, l1_y + halo_ry], outline=(6, 182, 212, 210), width=7)
    # Rotate halo orbit by -18 degrees
    halo_rotated = halo_img.rotate(-18, center=(l1_x, l1_y), resample=Image.Resampling.BICUBIC)
    img.alpha_composite(halo_rotated)

    # Spacecraft on Halo Orbit
    sat_x, sat_y = int(l1_x + 30), int(l1_y - 70)

    # Bow Shock wave ahead of spacecraft
    draw.arc([sat_x - 65, sat_y - 45, sat_x - 15, sat_y + 45], start=100, end=260, fill=(56, 189, 248, 240), width=6)

    # Solar wind particle vectors hitting probe
    draw.line([(sat_x - 85, sat_y - 12), (sat_x - 45, sat_y - 12)], fill=(251, 191, 36, 220), width=4)
    draw.line([(sat_x - 95, sat_y), (sat_x - 50, sat_y)], fill=(245, 158, 11, 240), width=5)
    draw.line([(sat_x - 85, sat_y + 12), (sat_x - 45, sat_y + 12)], fill=(251, 191, 36, 220), width=4)

    # Solar Panel Wings
    wing_w, wing_h = 32, 60
    # Upper wing
    draw.rectangle([sat_x - wing_w//2, sat_y - 75, sat_x + wing_w//2, sat_y - 20], fill=(2, 132, 199, 255), outline=(56, 189, 248, 255), width=3)
    draw.line([(sat_x - wing_w//2, sat_y - 48), (sat_x + wing_w//2, sat_y - 48)], fill=(56, 189, 248, 200), width=2)
    # Lower wing
    draw.rectangle([sat_x - wing_w//2, sat_y + 20, sat_x + wing_w//2, sat_y + 75], fill=(2, 132, 199, 255), outline=(56, 189, 248, 255), width=3)
    draw.line([(sat_x - wing_w//2, sat_y + 48), (sat_x + wing_w//2, sat_y + 48)], fill=(56, 189, 248, 200), width=2)

    # Spacecraft Central Bus
    bus_r = 24
    draw.rectangle([sat_x - bus_r, sat_y - bus_r, sat_x + bus_r, sat_y + bus_r], fill=(241, 245, 249, 255), outline=(100, 116, 139, 255), width=4)
    draw.ellipse([sat_x - 10, sat_y - 10, sat_x + 10, sat_y + 10], fill=(16, 185, 129, 255), outline=(255, 255, 255, 255), width=2)

    # Magnetometer boom
    draw.line([(sat_x, sat_y + bus_r), (sat_x, sat_y + 105)], fill=(203, 213, 225, 255), width=4)
    draw.ellipse([sat_x - 7, sat_y + 100, sat_x + 7, sat_y + 114], fill=(245, 158, 11, 255), outline=(255, 255, 255, 255), width=2)

    # Earth Antenna dish
    draw.arc([sat_x + 20, sat_y - 18, sat_x + 44, sat_y + 18], start=270, end=90, fill=(226, 232, 240, 255), width=5)
    draw.line([(sat_x + bus_r, sat_y), (sat_x + 32, sat_y)], fill=(148, 163, 184, 255), width=4)

    # Active Beacon Signal Ring
    draw.ellipse([sat_x - 45, sat_y - 45, sat_x + 45, sat_y + 45], outline=(16, 185, 129, 200), width=3)
    draw.ellipse([sat_x - 80, sat_y - 80, sat_x + 80, sat_y + 80], outline=(56, 189, 248, 120), width=2)

    # Outer Bezel Rings
    draw.ellipse([cx - r_badge, cy - r_badge, cx + r_badge, cy + r_badge], outline=(245, 158, 11, 255), width=9)
    draw.ellipse([cx - r_badge - 4, cy - r_badge - 4, cx + r_badge + 4, cy + r_badge + 4], outline=(14, 165, 233, 140), width=3)

    # Downsample with high quality Lanczos anti-aliasing to 512x512
    master_512 = img.resize((512, 512), resample=Image.Resampling.LANCZOS)
    master_256 = img.resize((256, 256), resample=Image.Resampling.LANCZOS)

    # Save PNG files
    png_img_dir = img_dir / "helios_logo.png"
    png_assets = assets_dir / "helios_logo.png"
    master_512.save(str(png_img_dir), format="PNG")
    master_512.save(str(png_assets), format="PNG")
    print(f"[+] 512x512 PNG Logo saved to {png_img_dir} and {png_assets}")

    # Generate Multi-Resolution Windows ICO
    ico_img_dir = img_dir / "helios.ico"
    ico_assets = assets_dir / "helios.ico"
    ico_dist = dist_dir / "helios.ico"

    icon_sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (24, 24), (16, 16)]
    master_256.save(str(ico_assets), format="ICO", sizes=icon_sizes)
    master_256.save(str(ico_img_dir), format="ICO", sizes=icon_sizes)
    if dist_dir.exists():
        master_256.save(str(ico_dist), format="ICO", sizes=icon_sizes)
    print(f"[+] Multi-Resolution ICO saved to {ico_assets}")

if __name__ == "__main__":
    proj_root = Path(__file__).resolve().parent.parent
    generate_svg_and_raster(proj_root)
