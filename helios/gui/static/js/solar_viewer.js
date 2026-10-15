/**
 * HELIOS-L1: HIGH-RESOLUTION SOLAR DISK & ACTIVE REGION ANALYZER
 * Features:
 * - Schematic disk drawn in EUV / white-light colour scales (not images; real images are in the feed panels)
 * - True Solar Limb Darkening & Coronal Loop Arcs
 * - Real-time Stonyhurst / Carrington Heliographic Coordinate Grid
 * - Observed active regions (NOAA SWPC solar region summary): position, Mount Wilson class, area
 * - SWPC 24 h C/M/X flare probabilities per region
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

    // Observed active regions from the NOAA SWPC solar region summary (/api/solar/regions).
    // Until it loads, or when it is unavailable, a few historical regions are shown and
    // labelled as such: their disk positions are schematic, not observations.
    this.regionSource = 'historical';
    this.regionDate = null;
    this.historicalRegions = [
      {
        id: 'AR 3664', name: 'Historical example (May 2024)', lat: -18.5, lon: -15.0, area: null,
        hale: 'β-γ-δ', flareProb: null, recentFlare: 'X8.7 (14 May 2024)',
        summary: 'Source of the flares and CMEs behind the G5 storm of 10-11 May 2024. Position on this disk is schematic.'
      },
      {
        id: 'AR 3697', name: 'Historical example (May-June 2024)', lat: -19.2, lon: 32.0, area: null,
        hale: 'β-γ-δ', flareProb: null, recentFlare: null,
        summary: 'AR 3664 returning after one solar rotation. Position on this disk is schematic.'
      },
      {
        id: 'AR 3842', name: 'Historical example (October 2024)', lat: 14.5, lon: -42.0, area: null,
        hale: 'β-γ', flareProb: null, recentFlare: 'X9.0 (3 Oct 2024)',
        summary: 'Produced the X7.1 flare of 1 October and the X9.0 flare of 3 October 2024. Position on this disk is schematic.'
      },
      {
        id: 'AR 3848', name: 'Historical example (October 2024)', lat: -12.0, lon: 10.0, area: null,
        hale: 'β-γ-δ', flareProb: null, recentFlare: 'X1.8 (9 Oct 2024)',
        summary: 'Its X1.8 flare and CME of 9 October 2024 drove the G4 storm of 10 October. Position on this disk is schematic.'
      }
    ];
    this.activeRegions = this.historicalRegions;
    this.loadObservedRegions();

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

  // NOAA SRS regions: longitude east of the central meridian is positive in the product,
  // this viewer draws west (positive lon) to the right as seen from Earth.
  async loadObservedRegions() {
    try {
      const res = await fetch('/api/solar/regions');
      if (!res.ok) return;
      const data = await res.json();
      if (!data.regions || !data.regions.length) return;
      this.regionSource = 'observed';
      this.regionDate = data.observed_date;
      this.activeRegions = data.regions.filter(r => Math.abs(r.longitude_east) <= 90).map(r => {
        const p = r.flare_probability_pct || {};
        const f = r.flares_today || {};
        const flares = ['X', 'M', 'C'].filter(k => f[k]).map(k => `${f[k]} ${k}`).join(', ');
        return {
          id: `AR ${r.region}`,
          name: `${r.location} • ${r.spot_class || 'no spot class'}`,
          lat: r.latitude,
          lon: -r.longitude_east,
          area: r.area_msh,
          hale: r.mag_class || 'n/a',
          flareProb: (p.C !== null && p.C !== undefined) ? { c: p.C, m: p.M, x: p.X } : null,
          recentFlare: flares ? `${flares} flare(s) on ${data.observed_date}` : `No C/M/X flares on ${data.observed_date}`,
          summary: `NOAA SWPC region summary for ${data.observed_date}: ${r.number_spots ?? '?'} spots, area ${r.area_msh ?? '?'} μHem, Mount Wilson class ${r.mag_class || 'n/a'}, McIntosh class ${r.spot_class || 'n/a'}.` +
            (r.proton_probability_pct !== null && r.proton_probability_pct !== undefined ? ` Proton event probability ${r.proton_probability_pct}%.` : '')
        };
      });
      const note = document.getElementById('solar-ar-source');
      if (note) note.innerText = `Regions: NOAA SWPC solar region summary for ${data.observed_date} (positions valid for that date). The disk itself is a schematic drawing, not an image.`;
      if (this.activeRegions.length) this.updateSelectedRegionUI(this.activeRegions[0]);
    } catch (err) {
      // Network or server unavailable: the historical examples stay, labelled.
    }
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
        <span class="text-[10px] px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800 font-bold">${ar.recentFlare || ''}</span>
      </div>
      <div class="text-[11px] font-mono space-y-0.5 text-slate-200">
        <div>Heliographic: <span class="text-cyan-300">${Math.abs(ar.lat)}°${ar.lat >= 0 ? 'N' : 'S'}, ${Math.abs(ar.lon)}°${ar.lon >= 0 ? 'W' : 'E'}</span></div>
        <div>Magnetic Class: <span class="text-rose-400 font-bold">${ar.hale}</span></div>
        <div>Spot Area: <span class="text-slate-300">${ar.area !== null && ar.area !== undefined ? ar.area + ' μHem' : 'n/a'}</span></div>
        <div class="text-amber-400 font-bold pt-1">${ar.flareProb ? `SWPC 24 h flare probability: C ${ar.flareProb.c}% | M ${ar.flareProb.m}% | X ${ar.flareProb.x}%` : 'Historical example: no current forecast'}</div>
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
    if (elFlare) elFlare.innerText = ar.recentFlare || 'n/a';
    if (elProb) elProb.innerText = ar.flareProb ? `C: ${ar.flareProb.c}% • M: ${ar.flareProb.m}% • X: ${ar.flareProb.x}%` : 'n/a (historical example)';
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
    ctx.fillStyle = '#141518';
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
          inner: '#ebd6a2',
          mid: '#b98f3f',
          edge: '#a44e4e',
          corona: 'rgba(164, 78, 78, 0.25)',
          name: 'Schematic disk, 304 Å colours (He II ~50,000 K: chromosphere, filaments)'
        };
      case '171': // Quiet Corona (Gold / Yellow)
        return {
          inner: '#ffffff',
          mid: '#dfc078',
          edge: '#b98f3f',
          corona: 'rgba(185, 143, 63, 0.28)',
          name: 'Schematic disk, 171 Å colours (Fe IX ~0.6 MK: quiet corona, loops)'
        };
      case '131': // Hot Flare Plasma (Teal / Cyan)
        return {
          inner: '#eff4fa',
          mid: '#7fa5cf',
          edge: '#3f5f83',
          corona: 'rgba(127, 165, 207, 0.25)',
          name: 'Schematic disk, 131 Å colours (Fe XXI ~10 MK: flaring plasma)'
        };
      case 'C2': // SOHO LASCO C2 Coronagraph (Red White-Light)
        return {
          inner: '#000000',
          mid: '#c26262',
          edge: '#5b2f2f',
          corona: 'rgba(194, 98, 98, 0.35)',
          isCoronagraph: true,
          name: 'Schematic corona, LASCO C2 style (white light 2-6 R☉)'
        };
      case '193': // Coronal Holes (Bronze / Gold)
      default:
        return {
          inner: '#fbf6ea',
          mid: '#9a7332',
          edge: '#523c21',
          corona: 'rgba(154, 115, 50, 0.28)',
          name: 'Schematic disk, 193 Å colours (Fe XII ~1.5 MK: coronal holes)'
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
    coronaGrad.addColorStop(0.7, 'rgba(185, 143, 63, 0.08)');
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
      ctx.fillStyle = '#1e2024';
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

        ctx.strokeStyle = 'rgba(194, 98, 98, 0.4)';
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
      ctx.font = '9px system-ui, sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText('Solar disk (occulted)', cx, cy + 3);
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
      ctx.strokeStyle = isSelected ? '#7fa5cf' : isHovered ? '#dfc078' : '#d77e7e';
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
      ctx.strokeStyle = 'rgba(235, 214, 162, 0.8)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y - 2, 4.5, 0, Math.PI);
      ctx.stroke();

      // Label
      ctx.fillStyle = isSelected ? '#7fa5cf' : '#f6f7f8';
      ctx.font = `${isSelected ? 'bold ' : ''}9px system-ui, sans-serif`;
      ctx.fillText(ar.id, x + 9, y - 4);
    });
    ctx.restore();
  }

  drawWavelengthBadge(ctx) {
    const pal = this.getColorPalettes();
    ctx.save();

    ctx.fillStyle = 'rgba(20, 21, 24, 0.88)';
    ctx.strokeStyle = 'rgba(127, 165, 207, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(14, 14, 330, 48, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#7fa5cf';
    ctx.font = '600 10px system-ui, sans-serif';
    ctx.fillText(this.regionSource === 'observed' ? `NOAA ACTIVE REGIONS ${this.regionDate} (SCHEMATIC DISK)` : 'HISTORICAL REGIONS (SCHEMATIC DISK)', 24, 30);

    ctx.fillStyle = '#d6d8db';
    ctx.font = '9px system-ui, sans-serif';
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
