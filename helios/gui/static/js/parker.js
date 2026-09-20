/**
 * HELIOS-L1: HELIOSPHERIC PARKER SPIRAL INTERACTIVE ENGINE
 * Features:
 * - Real-time Magnetohydrodynamic (MHD) Parker Spiral Field Line Solver
 * - Animated Solar Rotation & Outward Streaming Solar Wind Plasma Packets
 * - Corotating Interaction Region (CIR) Shock Front & Stream Interface Visualization
 * - Magnetic Polarity Sectors (Away/Toward Heliospheric Current Sheet Sectors)
 * - Fleet & Planetary Orbits (Mercury, Venus, Earth/L1, Mars, STEREO-A, Parker Solar Probe)
 * - Interactive Speed Slider & High-Speed Stream Presets
 * - Well-Connected Solar Footpoint Telemetry for Solar Energetic Particle (SEP) Forecasts
 */

class ParkerSpiralRenderer {
  constructor(canvasId, tooltipId) {
    this.canvas = document.getElementById(canvasId);
    this.tooltip = document.getElementById(tooltipId);
    if (!this.canvas) return;

    this.ctx = this.canvas.getContext('2d');
    this.width = 0;
    this.height = 0;

    // Simulation Parameters
    this.speedKms = 440; // Solar wind speed [km/s]
    this.omegaSun = 2.87e-6; // Solar sidereal rotation rate [rad/s]
    this.auKm = 149597870.7; // 1 AU in km
    this.rSunKm = 696340; // Solar radius in km

    // Animation & View State
    this.time = 0;
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this.isDragging = false;
    this.dragStart = { x: 0, y: 0 };
    this.mouseWorld = null;

    // Display Toggles
    this.showPlasmaFlow = true;
    this.showCIR = true;
    this.showSectors = true;
    this.showOrbits = true;
    this.showSpacecraft = true;

    // Streaming Plasma Particles Pool
    this.numParticles = 240;
    this.particles = [];
    this.initParticles();

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

  initParticles() {
    this.particles = [];
    for (let i = 0; i < this.numParticles; i++) {
      this.particles.push({
        r_au: 0.05 + Math.random() * 1.5,
        phi_0: (Math.random() * Math.PI * 2),
        streamIndex: Math.floor(Math.random() * 8),
        speedMult: 0.95 + Math.random() * 0.1,
        size: 1.2 + Math.random() * 1.6,
        hue: Math.random() > 0.3 ? 190 : 45
      });
    }
  }

  setSpeed(speedKms) {
    this.speedKms = Math.max(250, Math.min(1200, speedKms));
    this.updatePitchAndFootpointUI();
  }

  updatePitchAndFootpointUI() {
    const pitchRad = Math.atan((this.omegaSun * this.auKm) / this.speedKms);
    const pitchDeg = (pitchRad * 180) / Math.PI;
    const footpointDeg = (this.omegaSun * this.auKm / this.speedKms) * (180 / Math.PI);

    const pitchEl = document.getElementById('parker-pitch-val');
    if (pitchEl) pitchEl.innerText = `${pitchDeg.toFixed(1)}°`;

    const fpEl = document.getElementById('parker-footpoint-val');
    if (fpEl) fpEl.innerText = `~${footpointDeg.toFixed(1)}° W`;
  }

  initEventListeners() {
    window.addEventListener('resize', () => this.resize());

    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.dragStart = { x: e.clientX - this.panX, y: e.clientY - this.panY };
    });

    window.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        this.panX = e.clientX - this.dragStart.x;
        this.panY = e.clientY - this.dragStart.y;
      }
      this.handleMouseMove(e);
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
      this.zoom = Math.max(0.4, Math.min(3.5, this.zoom * zoomFactor));
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.mouseWorld = null;
      if (this.tooltip) this.tooltip.classList.add('hidden');
    });
  }

  handleMouseMove(e) {
    const rect = this.canvas.getBoundingClientRect();
    const cx = this.width / 2 + this.panX;
    const cy = this.height / 2 + this.panY;
    const scale = (this.height / 2) * 0.65 * this.zoom;

    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;

    const dx = (mx - cx) / scale;
    const dy = -(my - cy) / scale;
    const r_au = Math.hypot(dx, dy);
    let phi = Math.atan2(dy, dx);
    if (phi < 0) phi += Math.PI * 2;

    this.mouseWorld = { r_au, phi, x: mx, y: my };
    this.updateTooltip(e.clientX, e.clientY);
  }

  updateTooltip(clientX, clientY) {
    if (!this.tooltip || !this.mouseWorld) return;
    const mw = this.mouseWorld;

    if (mw.r_au > 1.8 || mw.r_au < 0.04) {
      this.tooltip.classList.add('hidden');
      return;
    }

    const distKm = mw.r_au * this.auKm;
    const pitchDeg = Math.atan((this.omegaSun * distKm) / this.speedKms) * (180 / Math.PI);
    const transitHrs = (distKm / this.speedKms) / 3600;
    const bMag = (5.0 / (mw.r_au * mw.r_au)).toFixed(1); // Dipolar/Parker falloff approximation

    this.tooltip.classList.remove('hidden');
    this.tooltip.innerHTML = `
      <div class="border-b border-sky-500/30 pb-1 mb-1.5 flex items-center justify-between">
        <strong class="text-sky-300 font-bold text-xs">Heliospheric Magnetic Point</strong>
        <span class="text-[10px] text-amber-400 font-mono font-bold">${mw.r_au.toFixed(2)} AU</span>
      </div>
      <div class="text-[11px] font-mono space-y-0.5 text-slate-200">
        <div>Heliocentric Dist: <span class="text-slate-300">${(distKm / 1e6).toFixed(1)}M km</span></div>
        <div>Parker Pitch Angle: <span class="text-cyan-300">${pitchDeg.toFixed(1)}°</span></div>
        <div>Solar Wind Transit: <span class="text-amber-300">${transitHrs.toFixed(1)} hours</span></div>
        <div>Model Field |B|: <span class="text-emerald-300">~${bMag} nT</span></div>
        <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">Spiral: Archimedean B-r/B-phi</div>
      </div>
    `;

    const parentRect = this.canvas.parentElement.getBoundingClientRect();
    const left = clientX - parentRect.left + 15;
    const top = clientY - parentRect.top + 15;
    this.tooltip.style.left = `${Math.min(left, this.width - 250)}px`;
    this.tooltip.style.top = `${Math.min(top, this.height - 130)}px`;
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    const cx = this.width / 2 + this.panX;
    const cy = this.height / 2 + this.panY;
    const scale = (this.height / 2) * 0.65 * this.zoom;

    // 1. Cosmic Background Starfield
    this.drawBackground();

    // 2. Heliospheric Magnetic Polarity Sectors (Toward / Away)
    if (this.showSectors) {
      this.drawPolaritySectors(cx, cy, scale);
    }

    // 3. Planetary Distance Rings (Mercury, Venus, 1 AU Earth, Mars)
    if (this.showOrbits) {
      this.drawPlanetaryOrbits(cx, cy, scale);
    }

    // 4. Corotating Interaction Region (CIR) Shock Waves
    if (this.showCIR) {
      this.drawCIRShocks(cx, cy, scale);
    }

    // 5. Magnetic Parker Spiral Streamlines
    this.drawParkerFieldLines(cx, cy, scale);

    // 6. Outward Streaming Plasma Packets
    if (this.showPlasmaFlow) {
      this.drawPlasmaFlow(cx, cy, scale);
    }

    // 7. Earth, L1 Constellation & Fleet Spacecraft
    if (this.showSpacecraft) {
      this.drawFleetAndPlanets(cx, cy, scale);
    }

    // 8. The Sun with Rotating Corona
    this.drawSun(cx, cy);

    // 9. Telemetry HUD Overlay
    this.drawHUDOverlay(cx, cy);
  }

  drawBackground() {
    const ctx = this.ctx;
    const grad = ctx.createRadialGradient(
      this.width / 2, this.height / 2, 40,
      this.width / 2, this.height / 2, this.width * 0.8
    );
    grad.addColorStop(0, '#060c22');
    grad.addColorStop(0.5, '#030714');
    grad.addColorStop(1, '#01030a');
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, this.width, this.height);

    // Coordinate concentric AU grid rings
    ctx.save();
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);
    const cx = this.width / 2 + this.panX;
    const cy = this.height / 2 + this.panY;
    const scale = (this.height / 2) * 0.65 * this.zoom;

    [0.25, 0.5, 0.75, 1.0, 1.25, 1.5].forEach(r => {
      ctx.beginPath();
      ctx.arc(cx, cy, r * scale, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = 'rgba(100, 116, 139, 0.5)';
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText(`${r} AU`, cx + r * scale + 4, cy - 4);
    });

    // Sun-Earth Ecliptic Axis
    ctx.strokeStyle = 'rgba(255, 183, 3, 0.2)';
    ctx.beginPath();
    ctx.moveTo(cx - 1.6 * scale, cy);
    ctx.lineTo(cx + 1.6 * scale, cy);
    ctx.moveTo(cx, cy - 1.6 * scale);
    ctx.lineTo(cx, cy + 1.6 * scale);
    ctx.stroke();
    ctx.restore();
  }

  drawPolaritySectors(cx, cy, scale) {
    const ctx = this.ctx;
    ctx.save();
    // 4-sector Parker magnetic field model (Away / Toward Sun)
    const rot = (this.time * 0.002);
    const numSectors = 4;
    const maxR = 1.6 * scale;

    for (let i = 0; i < numSectors; i++) {
      const aStart = rot + (i * Math.PI * 2) / numSectors;
      const aEnd = aStart + (Math.PI * 2) / numSectors;
      const isAway = i % 2 === 0;

      ctx.fillStyle = isAway ? 'rgba(56, 189, 248, 0.03)' : 'rgba(244, 63, 94, 0.03)';
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, maxR, aStart, aEnd);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  drawPlanetaryOrbits(cx, cy, scale) {
    const ctx = this.ctx;
    ctx.save();

    const orbits = [
      { name: 'Mercury (0.39 AU)', r: 0.387, color: 'rgba(148, 163, 184, 0.4)' },
      { name: 'Venus (0.72 AU)', r: 0.723, color: 'rgba(251, 191, 36, 0.4)' },
      { name: 'Earth (1.00 AU)', r: 1.000, color: 'rgba(56, 189, 248, 0.65)', isEarth: true },
      { name: 'Mars (1.52 AU)', r: 1.524, color: 'rgba(244, 63, 94, 0.4)' }
    ];

    orbits.forEach(orb => {
      ctx.strokeStyle = orb.color;
      ctx.lineWidth = orb.isEarth ? 1.5 : 1;
      ctx.setLineDash(orb.isEarth ? [5, 4] : [2, 3]);

      ctx.beginPath();
      ctx.arc(cx, cy, orb.r * scale, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = orb.color;
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText(orb.name, cx + 8, cy - orb.r * scale - 4);
    });

    ctx.restore();
  }

  drawCIRShocks(cx, cy, scale) {
    const ctx = this.ctx;
    ctx.save();
    // Corotating Interaction Region: Fast stream (750 km/s) overtaking Slow stream (400 km/s)
    const rot = (this.time * 0.002);
    const cirAngle = rot + 1.2;

    ctx.strokeStyle = 'rgba(255, 183, 3, 0.7)';
    ctx.lineWidth = 2.5;
    ctx.setLineDash([6, 3]);

    // Forward Shock
    ctx.beginPath();
    for (let r_au = 0.4; r_au <= 1.55; r_au += 0.02) {
      const deltaTheta = (this.omegaSun * r_au * this.auKm) / (this.speedKms * 0.85);
      const theta = cirAngle - deltaTheta;
      const x = cx + r_au * scale * Math.cos(theta);
      const y = cy - r_au * scale * Math.sin(theta);
      if (r_au === 0.4) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Compression Glow Region between Shocks
    ctx.fillStyle = 'rgba(255, 183, 3, 0.08)';
    ctx.beginPath();
    for (let r_au = 0.4; r_au <= 1.55; r_au += 0.02) {
      const deltaTheta = (this.omegaSun * r_au * this.auKm) / (this.speedKms * 0.85);
      const theta = cirAngle - deltaTheta;
      const x = cx + r_au * scale * Math.cos(theta);
      const y = cy - r_au * scale * Math.sin(theta);
      if (r_au === 0.4) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    for (let r_au = 1.55; r_au >= 0.4; r_au -= 0.02) {
      const deltaTheta = (this.omegaSun * r_au * this.auKm) / (this.speedKms * 1.15);
      const theta = cirAngle - deltaTheta + 0.15;
      const x = cx + r_au * scale * Math.cos(theta);
      const y = cy - r_au * scale * Math.sin(theta);
      ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.fill();

    // CIR Label
    const midR = 1.15;
    const midTheta = cirAngle - (this.omegaSun * midR * this.auKm) / (this.speedKms * 0.85);
    const lx = cx + midR * scale * Math.cos(midTheta);
    const ly = cy - midR * scale * Math.sin(midTheta);
    ctx.fillStyle = '#f59e0b';
    ctx.font = '600 9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('CIR FORWARD SHOCK', lx + 10, ly);

    ctx.restore();
  }

  drawParkerFieldLines(cx, cy, scale) {
    const ctx = this.ctx;
    ctx.save();

    const numLines = 8;
    const sunRot = (this.time * 0.002);

    // Calculate which line connects directly to Earth (at phi = 0, 1 AU)
    const earthTransitTheta = (this.omegaSun * 1.0 * this.auKm) / this.speedKms;

    for (let i = 0; i < numLines; i++) {
      const phi_0 = sunRot + (i * Math.PI * 2) / numLines;
      const isEarthConnected = i === 0;

      ctx.beginPath();
      const maxR = 1.55;
      const rStep = 0.02;

      for (let r_au = 0.05; r_au <= maxR; r_au += rStep) {
        // Parker spiral formula: theta(r) = phi_0 - (omega * r) / V_sw
        const distKm = r_au * this.auKm;
        const theta = phi_0 - (this.omegaSun * distKm) / this.speedKms;

        const x = cx + r_au * scale * Math.cos(theta);
        const y = cy - r_au * scale * Math.sin(theta);

        if (r_au === 0.05) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }

      if (isEarthConnected) {
        // High-priority SEP Highway to Earth
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 2.2;
        ctx.stroke();

        // Trace footpoint tag back on Sun
        const fpX = cx + 0.05 * scale * Math.cos(phi_0);
        const fpY = cy - 0.05 * scale * Math.sin(phi_0);
        ctx.fillStyle = '#38bdf8';
        ctx.beginPath();
        ctx.arc(fpX, fpY, 3, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.strokeStyle = 'rgba(100, 116, 139, 0.4)';
        ctx.lineWidth = 1.2;
        ctx.shadowBlur = 0;
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  drawPlasmaFlow(cx, cy, scale) {
    const ctx = this.ctx;
    ctx.save();

    const sunRot = (this.time * 0.002);
    const speedRatio = this.speedKms / 450;

    this.particles.forEach(p => {
      // Advance radially outward
      p.r_au += 0.003 * speedRatio * p.speedMult;
      if (p.r_au > 1.55) {
        p.r_au = 0.05;
        p.phi_0 = sunRot + (p.streamIndex * Math.PI * 2) / 8;
      }

      const distKm = p.r_au * this.auKm;
      const theta = p.phi_0 - (this.omegaSun * distKm) / this.speedKms;
      const x = cx + p.r_au * scale * Math.cos(theta);
      const y = cy - p.r_au * scale * Math.sin(theta);

      // Color shifts from solar gold to interplanetary cyan
      const alpha = Math.max(0.15, Math.min(0.9, 1.2 - p.r_au * 0.65));
      ctx.fillStyle = p.streamIndex === 0 
        ? `rgba(0, 240, 255, ${alpha})`
        : `rgba(255, 183, 3, ${alpha * 0.75})`;

      ctx.beginPath();
      ctx.arc(x, y, p.size, 0, Math.PI * 2);
      ctx.fill();
    });

    ctx.restore();
  }

  drawFleetAndPlanets(cx, cy, scale) {
    const ctx = this.ctx;
    ctx.save();

    // 1. Earth at 1 AU (x = cx + scale, y = cy)
    const earthX = cx + 1.0 * scale;
    const earthY = cy;

    // Magnetosphere bow shock front
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.75)';
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.arc(earthX, earthY, 14, Math.PI * 0.6, Math.PI * 1.4);
    ctx.stroke();

    // Earth Body
    const earthGrad = ctx.createRadialGradient(earthX - 2, earthY - 2, 1, earthX, earthY, 7);
    earthGrad.addColorStop(0, '#60a5fa');
    earthGrad.addColorStop(0.7, '#1d4ed8');
    earthGrad.addColorStop(1, '#0f172a');
    ctx.fillStyle = earthGrad;
    ctx.beginPath();
    ctx.arc(earthX, earthY, 6.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#93c5fd';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#f8fafc';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('EARTH', earthX + 12, earthY - 4);
    ctx.fillStyle = '#38bdf8';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText('1.00 AU', earthX + 12, earthY + 8);

    // 2. Sun-Earth L1 (0.99 AU) - DSCOVR, ACE, Aditya-L1
    const l1X = cx + 0.99 * scale;
    const l1Y = cy;

    ctx.fillStyle = '#ffb703';
    ctx.beginPath();
    ctx.arc(l1X, l1Y, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fef08a';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#ffb703';
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    ctx.fillText('L1 (DSCOVR/Aditya)', l1X - 35, l1Y - 12);

    // 3. STEREO-Ahead (Leading Earth in heliocentric orbit ~0.96 AU)
    const stereoAngle = 0.35; // ~20° ahead
    const stereoX = cx + 0.96 * scale * Math.cos(stereoAngle);
    const stereoY = cy - 0.96 * scale * Math.sin(stereoAngle);

    ctx.fillStyle = '#a855f7';
    ctx.beginPath();
    ctx.arc(stereoX, stereoY, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#d8b4fe';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText('STEREO-A (0.96 AU)', stereoX + 8, stereoY);

    // 4. Parker Solar Probe (Deep perihelion ~0.08 AU)
    const pspAngle = (this.time * 0.01) % (Math.PI * 2);
    const pspR = 0.12 + 0.06 * Math.sin(this.time * 0.02);
    const pspX = cx + pspR * scale * Math.cos(pspAngle);
    const pspY = cy - pspR * scale * Math.sin(pspAngle);

    ctx.fillStyle = '#ff2a6d';
    ctx.beginPath();
    ctx.arc(pspX, pspY, 2.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#fda4af';
    ctx.font = '8px "JetBrains Mono", monospace';
    ctx.fillText('PSP', pspX + 6, pspY - 3);

    ctx.restore();
  }

  drawSun(cx, cy) {
    const ctx = this.ctx;
    ctx.save();

    // Multi-layer glowing corona
    const coronaR = 26;
    const coronaGrad = ctx.createRadialGradient(cx, cy, 4, cx, cy, coronaR);
    coronaGrad.addColorStop(0, '#fef08a');
    coronaGrad.addColorStop(0.3, '#f59e0b');
    coronaGrad.addColorStop(0.7, 'rgba(245, 158, 11, 0.25)');
    coronaGrad.addColorStop(1, 'rgba(245, 158, 11, 0)');
    ctx.fillStyle = coronaGrad;
    ctx.beginPath();
    ctx.arc(cx, cy, coronaR, 0, Math.PI * 2);
    ctx.fill();

    // Solar Disk
    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(cx, cy, 9, 0, Math.PI * 2);
    ctx.fill();

    // Dynamic solar flares / prominence arcs
    const rot = this.time * 0.04;
    ctx.strokeStyle = '#fef08a';
    ctx.lineWidth = 1.2;
    for (let i = 0; i < 4; i++) {
      const a = rot + (i * Math.PI) / 2;
      ctx.beginPath();
      ctx.arc(cx + Math.cos(a) * 9, cy + Math.sin(a) * 9, 3.5, a - 0.8, a + 0.8);
      ctx.stroke();
    }

    ctx.fillStyle = '#fef08a';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('SUN', cx, cy + 24);

    ctx.restore();
  }

  drawHUDOverlay(cx, cy) {
    const ctx = this.ctx;
    ctx.save();

    // Top-Left Simulation Badge
    ctx.fillStyle = 'rgba(7, 14, 34, 0.85)';
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(14, 14, 280, 68, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#38bdf8';
    ctx.font = '600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('PARKER HELIOSPHERIC SPIRAL DYNAMICS', 24, 32);

    ctx.fillStyle = '#cbd5e1';
    ctx.font = '10px "JetBrains Mono", monospace';
    const pitch = Math.atan((this.omegaSun * this.auKm) / this.speedKms) * (180 / Math.PI);
    const fp = (this.omegaSun * this.auKm / this.speedKms) * (180 / Math.PI);
    ctx.fillText(`V_SW: ${this.speedKms} km/s • 1 AU PITCH: ${pitch.toFixed(1)}°`, 24, 48);
    ctx.fillText(`CONNECTED FOOTPOINT: ~${fp.toFixed(1)}° W (Solar Limb)`, 24, 64);

    // Well-connected highlight legend
    ctx.fillStyle = 'rgba(7, 14, 34, 0.85)';
    ctx.beginPath();
    ctx.roundRect(14, this.height - 42, 310, 28, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#00f0ff';
    ctx.fillRect(24, this.height - 30, 14, 3);
    ctx.fillStyle = '#e2e8f0';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillText('Cyan Spiral = Magnetic Highway to Earth/L1', 46, this.height - 24);

    ctx.restore();
  }

  animate() {
    this.time += 1;
    this.draw();
    requestAnimationFrame(this.animate);
  }
}

// Attach to window
window.ParkerSpiralRenderer = ParkerSpiralRenderer;
