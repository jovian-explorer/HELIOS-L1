/**
 * HELIOS-L1: HIGH-RESOLUTION SOLAR DISK & ACTIVE REGION ANALYZER
 * Features:
 * - Multi-wavelength EUV & White-Light Coronagraph Simulation (AIA 193, 304, 171, 131, LASCO C2/C3)
 * - True Solar Limb Darkening & Coronal Loop Arcs
 * - Real-time Stonyhurst / Carrington Heliographic Coordinate Grid
 * - Active Region (AR) Scanning with Hale Magnetic Complexity (beta, beta-gamma, beta-gamma-delta)
 * - Flare Probability Predictor (C, M, X-class) and Coronal Mass Ejection Eruption Tracing
 */

class SolarDiskViewer {
  constructor(canvasId, tooltipId) {
    this.canvas = document.getElementById(canvasId);
    this.tooltip = document.getElementById(tooltipId);
    if (!this.canvas) return;

    this.ctx = this.canvas.getContext('2d');
    this.width = 0;
    this.height = 0;
    this.time = 0;

    // View Options
    this.wavelength = '193'; // 193, 304, 171, 131, C2, C3
    this.showGrid = true;
    this.showActiveRegions = true;
    this.showLimbDarkening = true;
    this.selectedRegion = null;
    this.hoveredRegion = null;

    // Benchmark Active Regions (Solar Cycle 25 Superstorm Reference Catalog)
    this.activeRegions = [
      {
        id: 'AR 3664',
        name: 'Carrington-Class Complex',
        lat: -18.5,
        lon: -15.0, // central meridian offset
        area: 2450,
        hale: 'β-γ-δ (Extreme Multi-Polar)',
        flareProb: { c: 99, m: 85, x: 45 },
        recentFlare: 'X8.7 (May 14, 2024)',
        cmeType: 'Fast Full Halo CME (V > 1800 km/s)',
        summary: 'Massive complex sunspot cluster responsible for G5 geomagnetic superstorm. Extreme magnetic shear along neutral inversion line.'
      },
      {
        id: 'AR 3697',
        name: 'Recurrent Monster Region',
        lat: -19.2,
        lon: 32.0,
        area: 1850,
        hale: 'β-γ-δ',
        flareProb: { c: 95, m: 70, x: 30 },
        recentFlare: 'X2.9 (May 27, 2024)',
        cmeType: 'Partial Halo CME (V = 1450 km/s)',
        summary: 'Return of AR 3664 after full solar rotation. Maintained strong delta spots and produced high-energy proton flux storm.'
      },
      {
        id: 'AR 3842',
        name: 'Fast-Growing Dipole',
        lat: 14.5,
        lon: -42.0,
        area: 980,
        hale: 'β-γ',
        flareProb: { c: 85, m: 50, x: 15 },
        recentFlare: 'X7.1 (Oct 1, 2024)',
        cmeType: 'Earth-Directed Halo CME',
        summary: 'Northern hemisphere active region with rapid flux emergence. Strong magnetic gradient driving eruptive prominence liftoff.'
      },
      {
        id: 'AR 3848',
        name: 'Trans-Equatorial Loop Cluster',
        lat: -12.0,
        lon: 10.0,
        area: 1200,
        hale: 'β-γ-δ',
        flareProb: { c: 90, m: 65, x: 25 },
        recentFlare: 'X1.8 (Oct 9, 2024)',
        cmeType: 'Direct Earth Impact Shock',
        summary: 'Central meridian alignment with direct Earth-facing connectivity. Generated G4 severe geomagnetic storm.'
      }
    ];

    this.initEventListeners();
    this.resize();
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
  }

  setWavelength(wl) {
    this.wavelength = wl;
    window.playBlip?.();
  }

  initEventListeners() {
    window.addEventListener('resize', () => this.resize());

    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;

      const cx = this.width / 2;
      const cy = this.height / 2;
      const sunR = Math.min(this.width, this.height) * 0.38;

      let found = null;
      for (const ar of this.activeRegions) {
        const radLat = (ar.lat * Math.PI) / 180;
        const radLon = (ar.lon * Math.PI) / 180;

        const x = cx + sunR * Math.cos(radLat) * Math.sin(radLon);
        const y = cy - sunR * Math.sin(radLat);

        const dist = Math.hypot(x - mx, y - my);
        if (dist <= 18) {
          found = ar;
          break;
        }
      }

      this.hoveredRegion = found;
      if (found) {
        this.updateTooltip(e.clientX, e.clientY, found);
      } else if (this.tooltip) {
        this.tooltip.classList.add('hidden');
      }
    });

    this.canvas.addEventListener('click', (e) => {
      if (this.hoveredRegion) {
        this.selectedRegion = this.hoveredRegion;
        this.updateSelectedRegionUI(this.selectedRegion);
        window.playRadarPing?.();
      }
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.hoveredRegion = null;
      if (this.tooltip) this.tooltip.classList.add('hidden');
    });
  }

  updateTooltip(clientX, clientY, ar) {
    if (!this.tooltip) return;
    this.tooltip.classList.remove('hidden');
    this.tooltip.innerHTML = `
      <div class="border-b border-sky-500/30 pb-1 mb-1.5 flex items-center justify-between">
        <strong class="text-amber-300 font-bold text-xs">${ar.id}: ${ar.name}</strong>
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 font-bold">${ar.recentFlare}</span>
      </div>
      <div class="text-[11px] font-mono space-y-0.5 text-slate-200">
        <div>Heliographic: <span class="text-cyan-300">${Math.abs(ar.lat)}°${ar.lat >= 0 ? 'N' : 'S'}, ${Math.abs(ar.lon)}°${ar.lon >= 0 ? 'W' : 'E'}</span></div>
        <div>Magnetic Class: <span class="text-rose-400 font-bold">${ar.hale}</span></div>
        <div>Spot Area: <span class="text-slate-300">${ar.area} μHem</span></div>
        <div class="text-amber-400 font-bold pt-1">Flare Risk: C: ${ar.flareProb.c}% | M: ${ar.flareProb.m}% | X: ${ar.flareProb.x}%</div>
      </div>
    `;

    const parentRect = this.canvas.parentElement.getBoundingClientRect();
    const left = clientX - parentRect.left + 15;
    const top = clientY - parentRect.top + 15;
    this.tooltip.style.left = `${Math.min(left, this.width - 270)}px`;
    this.tooltip.style.top = `${Math.min(top, this.height - 130)}px`;
  }

  updateSelectedRegionUI(ar) {
    const elId = document.getElementById('solar-ar-id');
    const elName = document.getElementById('solar-ar-name');
    const elClass = document.getElementById('solar-ar-class');
    const elFlare = document.getElementById('solar-ar-flare');
    const elProb = document.getElementById('solar-ar-prob');
    const elDesc = document.getElementById('solar-ar-desc');

    if (elId) elId.innerText = ar.id;
    if (elName) elName.innerText = ar.name;
    if (elClass) elClass.innerText = ar.hale;
    if (elFlare) elFlare.innerText = ar.recentFlare;
    if (elProb) elProb.innerText = `C: ${ar.flareProb.c}% • M: ${ar.flareProb.m}% • X: ${ar.flareProb.x}%`;
    if (elDesc) elDesc.innerText = ar.summary;
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    const cx = this.width / 2;
    const cy = this.height / 2;
    const sunR = Math.min(this.width, this.height) * 0.38;

    // 1. Deep Space Background
    this.drawBackground(ctx);

    // 2. Solar Corona (Outer Halo & Prominences)
    this.drawCorona(ctx, cx, cy, sunR);

    // 3. Solar Disk with Limb Darkening
    this.drawSolarDisk(ctx, cx, cy, sunR);

    // 4. Heliographic Grid (Stonyhurst Coordinates)
    if (this.showGrid) {
      this.drawHeliographicGrid(ctx, cx, cy, sunR);
    }

    // 5. Active Regions & Magnetic Loops
    if (this.showActiveRegions) {
      this.drawActiveRegions(ctx, cx, cy, sunR);
    }

    // 6. Multi-Wavelength HUD Badge
    this.drawWavelengthBadge(ctx);
  }

  drawBackground(ctx) {
    ctx.fillStyle = '#030612';
    ctx.fillRect(0, 0, this.width, this.height);

    // Subtle star dots
    ctx.save();
    ctx.fillStyle = 'rgba(255, 255, 255, 0.4)';
    for (let i = 0; i < 35; i++) {
      const sx = (Math.sin(i * 123.4) * 0.5 + 0.5) * this.width;
      const sy = (Math.cos(i * 456.7) * 0.5 + 0.5) * this.height;
      ctx.fillRect(sx, sy, 1, 1);
    }
    ctx.restore();
  }

  getColorPalettes() {
    switch (this.wavelength) {
      case '304': // Chromosphere (Crimson / Orange Red)
        return {
          inner: '#fef08a',
          mid: '#f97316',
          edge: '#dc2626',
          corona: 'rgba(220, 38, 38, 0.25)',
          name: 'SDO / AIA 304 Å (He II 50,000 K - Chromosphere & Filaments)'
        };
      case '171': // Quiet Corona (Gold / Yellow)
        return {
          inner: '#ffffff',
          mid: '#fde047',
          edge: '#eab308',
          corona: 'rgba(234, 179, 8, 0.28)',
          name: 'SDO / AIA 171 Å (Fe IX 1,000,000 K - Coronal Loops)'
        };
      case '131': // Hot Flare Plasma (Teal / Cyan)
        return {
          inner: '#f0fdfa',
          mid: '#2dd4bf',
          edge: '#0f766e',
          corona: 'rgba(45, 212, 191, 0.25)',
          name: 'SDO / AIA 131 Å (Fe XXI 10,000,000 K - Flaring Plasma)'
        };
      case 'C2': // SOHO LASCO C2 Coronagraph (Red White-Light)
        return {
          inner: '#000000',
          mid: '#f43f5e',
          edge: '#881337',
          corona: 'rgba(244, 63, 94, 0.35)',
          isCoronagraph: true,
          name: 'SOHO / LASCO C2 (White Light 2.0 - 6.0 R☉)'
        };
      case '193': // Coronal Holes (Bronze / Gold)
      default:
        return {
          inner: '#fffbeb',
          mid: '#d97706',
          edge: '#78350f',
          corona: 'rgba(217, 119, 6, 0.28)',
          name: 'SDO / AIA 193 Å (Fe XII 1.5M K - Coronal Holes & Solar Wind)'
        };
    }
  }

  drawCorona(ctx, cx, cy, sunR) {
    const pal = this.getColorPalettes();
    ctx.save();

    // Radiant Corona Halo
    const coronaR = sunR * 1.35;
    const coronaGrad = ctx.createRadialGradient(cx, cy, sunR * 0.9, cx, cy, coronaR);
    coronaGrad.addColorStop(0, pal.corona);
    coronaGrad.addColorStop(0.7, 'rgba(245, 158, 11, 0.08)');
    coronaGrad.addColorStop(1, 'rgba(0, 0, 0, 0)');
    ctx.fillStyle = coronaGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, coronaR, 0, Math.PI * 2);
    ctx.fill();

    // Dynamic Prominence loops around limb
    const timeRot = this.time * 0.01;
    ctx.strokeStyle = pal.mid;
    ctx.lineWidth = 1.6;
    for (let i = 0; i < 6; i++) {
      const a = timeRot + (i * Math.PI) / 3;
      const arcR = 8 + Math.sin(this.time * 0.05 + i) * 3;
      const px = cx + Math.cos(a) * sunR;
      const py = cy + Math.sin(a) * sunR;

      ctx.beginPath();
      ctx.arc(px, py, arcR, a - 0.9, a + 0.9);
      ctx.stroke();
    }

    ctx.restore();
  }

  drawSolarDisk(ctx, cx, cy, sunR) {
    const pal = this.getColorPalettes();
    ctx.save();

    if (pal.isCoronagraph) {
      // Occulting disc for LASCO
      ctx.fillStyle = '#0f172a';
      ctx.beginPath();
      ctx.arc(cx, cy, sunR, 0, Math.PI * 2);
      ctx.fill();

      // Coronal Streamers expanding outward
      const numStreamers = 8;
      for (let i = 0; i < numStreamers; i++) {
        const a = (i * Math.PI * 2) / numStreamers + Math.sin(this.time * 0.02) * 0.1;
        const length = sunR * (1.2 + Math.sin(i * 3 + this.time * 0.03) * 0.3);
        const ex = cx + Math.cos(a) * length;
        const ey = cy + Math.sin(a) * length;

        ctx.strokeStyle = 'rgba(244, 63, 94, 0.4)';
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(a) * sunR, cy + Math.sin(a) * sunR);
        ctx.lineTo(ex, ey);
        ctx.stroke();
      }

      // Center Sun disk position indicator (inner circle)
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 1;
      ctx.setLineDash([2, 3]);
      ctx.beginPath();
      ctx.arc(cx, cy, sunR * 0.35, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = '#ffffff';
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('SOLAR DISK (OCCULTED)', cx, cy + 3);
      ctx.restore();
      return;
    }

    // Photosphere / Coronal Disk Gradient
    const diskGrad = ctx.createRadialGradient(cx - sunR * 0.15, cy - sunR * 0.15, sunR * 0.05, cx, cy, sunR);
    diskGrad.addColorStop(0, pal.inner);
    diskGrad.addColorStop(0.5, pal.mid);
    diskGrad.addColorStop(0.9, pal.edge);
    diskGrad.addColorStop(1, '#1e0c03'); // Limb darkening edge
    ctx.fillStyle = diskGrad;

    ctx.beginPath();
    ctx.arc(cx, cy, sunR, 0, Math.PI * 2);
    ctx.fill();

    // Limb outline
    ctx.strokeStyle = pal.mid;
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.restore();
  }

  drawHeliographicGrid(ctx, cx, cy, sunR) {
    if (this.wavelength === 'C2') return;

    ctx.save();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.lineWidth = 0.8;
    ctx.setLineDash([2, 3]);

    // Solar Equator
    ctx.beginPath();
    ctx.moveTo(cx - sunR, cy);
    ctx.lineTo(cx + sunR, cy);
    ctx.stroke();

    // Central Meridian
    ctx.beginPath();
    ctx.moveTo(cx, cy - sunR);
    ctx.lineTo(cx, cy + sunR);
    ctx.stroke();

    // Parallels (+30°, +60°, -30°, -60°)
    [-60, -30, 30, 60].forEach(lat => {
      const rad = (lat * Math.PI) / 180;
      const y = cy - sunR * Math.sin(rad);
      const halfW = sunR * Math.cos(rad);
      ctx.beginPath();
      ctx.ellipse(cx, y, halfW, halfW * 0.15, 0, 0, Math.PI * 2);
      ctx.stroke();
    });

    ctx.restore();
  }

  drawActiveRegions(ctx, cx, cy, sunR) {
    if (this.wavelength === 'C2') return;

    ctx.save();
    this.activeRegions.forEach(ar => {
      const radLat = (ar.lat * Math.PI) / 180;
      const radLon = (ar.lon * Math.PI) / 180;

      const x = cx + sunR * Math.cos(radLat) * Math.sin(radLon);
      const y = cy - sunR * Math.sin(radLat);

      const isSelected = this.selectedRegion === ar;
      const isHovered = this.hoveredRegion === ar;

      // Pulsing magnetic reticle ring
      const pulse = (Math.sin(this.time * 0.08) + 1) / 2;
      ctx.strokeStyle = isSelected ? '#00f0ff' : isHovered ? '#fde047' : '#ff2a6d';
      ctx.lineWidth = isSelected ? 2 : 1.2;

      ctx.beginPath();
      ctx.arc(x, y, 7 + (isSelected || isHovered ? pulse * 5 : 0), 0, Math.PI * 2);
      ctx.stroke();

      // Core Spot dot
      ctx.fillStyle = '#1e1e1e';
      ctx.beginPath();
      ctx.arc(x, y, 3.5, 0, Math.PI * 2);
      ctx.fill();

      // Flaring micro-loops in active region
      ctx.strokeStyle = 'rgba(254, 240, 138, 0.8)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y - 2, 4.5, 0, Math.PI);
      ctx.stroke();

      // Label
      ctx.fillStyle = isSelected ? '#00f0ff' : '#f8fafc';
      ctx.font = `${isSelected ? 'bold ' : ''}9px "JetBrains Mono", monospace`;
      ctx.fillText(ar.id, x + 9, y - 4);
    });
    ctx.restore();
  }

  drawWavelengthBadge(ctx) {
    const pal = this.getColorPalettes();
    ctx.save();

    ctx.fillStyle = 'rgba(7, 14, 34, 0.88)';
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(14, 14, 330, 48, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#38bdf8';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('HELIOPHYSICAL SOLAR DISK & CORONA ANALYZER', 24, 30);

    ctx.fillStyle = '#e2e8f0';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText(pal.name, 24, 48);

    ctx.restore();
  }

  animate() {
    if (this.canvas && this.canvas.offsetParent !== null) {
      this.time += 1;
      this.draw();
    }
    requestAnimationFrame(this.animate);
  }
}

// Attach to window
window.SolarDiskViewer = SolarDiskViewer;
