/**
 * HELIOS-L1: INTERACTIVE CME SHOCK KINEMATICS & PROPAGATION SIMULATOR
 * Features:
 * - Real-time Aerodynamic Drag Model (Gopalswamy / Vrsnak DBM Formulation)
 * - Animated 2D Solar-Interplanetary Shock Wave Propagation (Sun -> L1 -> Earth)
 * - Magnetic Cloud (Flux Rope) & Turbulent Compression Sheath Visualization
 * - Interactive Scrub Timeline (0h to 72h) with Play / Pause / Step Controls
 * - Live Shock Distance R(t), Velocity V(t), and L1/Earth Impact Alert HUD
 */

class CMESimulator {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;

    this.ctx = this.canvas.getContext('2d');
    this.width = 0;
    this.height = 0;

    // Physics & Kinematics State
    this.v0 = 1250; // Initial plane-of-sky velocity [km/s]
    this.vAmbient = 420; // Ambient solar wind velocity [km/s]
    this.gamma = 1.0e-7; // DBM drag parameter [km^-1], the server default until a result arrives
    this.rSunKm = 696340;
    this.l1Km = 149597870.7 - 1496000.0; // same L1 distance as coronagraph.py
    this.earthKm = 149597870.7;

    // Simulation Timeline (in hours)
    this.timeHrs = 0;
    this.maxHrs = 60;
    this.isPlaying = false;
    this.playbackSpeed = 1.0; // hrs per real second

    // Shock Status
    this.transitL1Hrs = 32.5;
    this.transitEarthHrs = 33.3;
    this.reachedL1 = false;
    this.reachedEarth = false;

    this.recomputeTrajectory();
    this.resize();
    this.initEventListeners();
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  resize() {
    if (!this.canvas) return;
    const parent = this.canvas.parentElement;
    if (!parent) return;
    const rect = parent.getBoundingClientRect();
    if (rect.width === 0 || rect.height === 0) return;
    const dpr = window.devicePixelRatio || 1;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.canvas.style.width = `${rect.width}px`;
    this.canvas.style.height = `${rect.height}px`;
    this.ctx.setTransform(1, 0, 0, 1, 0, 0);
    this.ctx.scale(dpr, dpr);
    this.width = rect.width;
    this.height = rect.height;
  }

  initEventListeners() {
    window.addEventListener('resize', () => this.resize());
  }

  setInitialSpeed(vInit) {
    this.v0 = Math.max(300, Math.min(3000, vInit));
    this.recomputeTrajectory();
    this.timeHrs = 0;
    this.isPlaying = true;
  }

  updateFromBackendResult(cme) {
    if (!cme) return;
    this.v0 = cme.initial_speed_kms || this.v0;
    if (cme.transit_to_l1_hours) this.transitL1Hrs = Number(cme.transit_to_l1_hours);
    if (cme.transit_to_earth_hours) this.transitEarthHrs = Number(cme.transit_to_earth_hours);
    if (cme.ambient_wind_kms) this.vAmbient = Number(cme.ambient_wind_kms);
    if (cme.drag_parameter_gamma) this.gamma = Number(cme.drag_parameter_gamma);  // same DBM drag as the server
    this.maxHrs = Math.max(48, Math.ceil(this.transitEarthHrs * 1.25));
    this.timeHrs = 0;
    this.isPlaying = true;

    const slider = document.getElementById('cme-timeline-slider');
    if (slider) {
      slider.max = this.maxHrs;
      slider.value = 0;
    }
  }

  recomputeTrajectory() {
    this.transitL1Hrs = this.solveTransitHours(this.l1Km);
    this.transitEarthHrs = this.solveTransitHours(this.earthKm);
    this.maxHrs = Math.max(48, Math.ceil(this.transitEarthHrs * 1.25));
  }

  solveTransitHours(targetDistKm) {
    const w = this.vAmbient;
    const gamma = this.gamma;
    const u0 = this.v0 - w;
    const r0 = this.rSunKm;
    if (targetDistKm <= r0) return 0;

    // Initial guess based on arithmetic mean velocity
    let tSec = (targetDistKm - r0) / Math.max(250, (this.v0 + w) / 2);
    for (let iter = 0; iter < 25; iter++) {
      let r, v;
      if (Math.abs(u0) < 1e-4) {
        r = r0 + w * tSec;
        v = w;
      } else if (u0 > 0) {
        const denom = 1.0 + gamma * u0 * tSec;
        r = r0 + w * tSec + (1.0 / gamma) * Math.log(denom);
        v = w + u0 / denom;
      } else {
        const absU0 = Math.abs(u0);
        const denom = 1.0 + gamma * absU0 * tSec;
        r = r0 + w * tSec - (1.0 / gamma) * Math.log(denom);
        v = w - absU0 / denom;
      }
      const diff = r - targetDistKm;
      if (Math.abs(diff) < 50) break;
      tSec = Math.max(0, tSec - diff / Math.max(100, v));
    }
    return tSec / 3600;
  }

  getShockAtTime(tHrs) {
    const tSec = tHrs * 3600;
    const w = this.vAmbient;
    const gamma = this.gamma;
    const u0 = this.v0 - w;
    const r0 = this.rSunKm;

    let v, distFromSunKm, dragA;
    if (Math.abs(u0) < 1e-4) {
      v = w;
      distFromSunKm = r0 + w * tSec;
      dragA = 0;
    } else if (u0 > 0) {
      // Decelerating fast CME (Vršnak et al. 2013 DBM closed-form)
      const denom = 1.0 + gamma * u0 * tSec;
      v = w + u0 / denom;
      distFromSunKm = r0 + w * tSec + (1.0 / gamma) * Math.log(denom);
      dragA = -gamma * Math.pow(v - w, 2);
    } else {
      // Accelerating slow CME
      const absU0 = Math.abs(u0);
      const denom = 1.0 + gamma * absU0 * tSec;
      v = w - absU0 / denom;
      distFromSunKm = r0 + w * tSec - (1.0 / gamma) * Math.log(denom);
      dragA = gamma * Math.pow(w - v, 2);
    }

    const distRsun = distFromSunKm / this.rSunKm;
    const distAu = distFromSunKm / this.earthKm;

    return {
      rKm: distFromSunKm,
      rSun: distRsun,
      rAu: distAu,
      vKms: v,
      dragAccelMs2: dragA * 1000.0,
      isL1Hit: distFromSunKm >= this.l1Km,
      isEarthHit: distFromSunKm >= this.earthKm
    };
  }

  setTime(tHrs) {
    this.timeHrs = Math.max(0, Math.min(this.maxHrs, tHrs));
  }

  play() {
    this.isPlaying = true;
  }

  pause() {
    this.isPlaying = false;
  }

  reset() {
    this.timeHrs = 0;
    this.isPlaying = false;
  }

  draw() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);

    // Background gradient
    const bgGrad = ctx.createLinearGradient(0, 0, this.width, 0);
    bgGrad.addColorStop(0, '#060d26');
    bgGrad.addColorStop(0.7, '#040817');
    bgGrad.addColorStop(1, '#02040d');
    ctx.fillStyle = bgGrad;
    ctx.fillRect(0, 0, this.width, this.height);

    const marginX = 80;
    const marginY = 40;
    const plotWidth = this.width - marginX - 100;
    const plotCenterY = this.height / 2;

    // Coordinate mapping: 0 AU to 1.15 AU along X axis
    const maxAU = 1.12;
    const auToX = (au) => marginX + (au / maxAU) * plotWidth;

    // 1. Grid & Distance Markers
    this.drawScaleGrid(ctx, auToX, plotCenterY);

    // 2. The Sun at origin (0 AU)
    this.drawSunOrigin(ctx, marginX, plotCenterY);

    // 3. Targets: L1 Point & Earth
    this.drawTargets(ctx, auToX, plotCenterY);

    // 4. Current CME Shock Position & Geometry
    const shock = this.getShockAtTime(this.timeHrs);
    this.drawCMECloud(ctx, shock, auToX, plotCenterY, marginX);

    // 5. Impact Alert Badges & HUD Readout
    this.drawHUD(ctx, shock);
  }

  drawScaleGrid(ctx, auToX, plotCenterY) {
    ctx.save();
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.12)';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 4]);

    // Distance ticks: 0.2, 0.4, 0.6, 0.8, 1.0 AU
    [0.2, 0.4, 0.6, 0.8, 1.0].forEach(au => {
      const x = auToX(au);
      ctx.beginPath();
      ctx.moveTo(x, 30);
      ctx.lineTo(x, this.height - 30);
      ctx.stroke();

      ctx.fillStyle = 'rgba(100, 116, 139, 0.6)';
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText(`${au} AU`, x - 12, this.height - 14);
      ctx.fillText(`${(au * 215).toFixed(0)} R☉`, x - 12, 22);
    });

    // Central Propagation Axis
    ctx.strokeStyle = 'rgba(255, 183, 3, 0.25)';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(auToX(0), plotCenterY);
    ctx.lineTo(auToX(1.1), plotCenterY);
    ctx.stroke();

    ctx.restore();
  }

  drawSunOrigin(ctx, sunX, plotCenterY) {
    ctx.save();
    const sunR = 24;

    // Sun Corona Flare
    const corona = ctx.createRadialGradient(sunX, plotCenterY, 4, sunX, plotCenterY, sunR);
    corona.addColorStop(0, '#fef08a');
    coronaGrad: corona.addColorStop(0.4, '#f59e0b');
    corona.addColorStop(1, 'rgba(245, 158, 11, 0)');
    ctx.fillStyle = corona;
    ctx.beginPath();
    ctx.arc(sunX, plotCenterY, sunR, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(sunX, plotCenterY, 8, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#fef08a';
    ctx.font = '600 9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('SUN', sunX, plotCenterY + 22);

    ctx.restore();
  }

  drawTargets(ctx, auToX, plotCenterY) {
    ctx.save();

    // 1. Earth at 1.0 AU
    const earthX = auToX(1.0);
    // Earth Bow Shock
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.7)';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.arc(earthX, plotCenterY, 14, Math.PI * 0.6, Math.PI * 1.4);
    ctx.stroke();

    ctx.fillStyle = '#38bdf8';
    ctx.beginPath();
    ctx.arc(earthX, plotCenterY, 6, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#f8fafc';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText('EARTH', earthX + 12, plotCenterY - 4);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText('1.00 AU', earthX + 12, plotCenterY + 8);

    // 2. Sun-Earth L1 at 0.99 AU (~1.5M km sunward)
    const l1X = auToX(0.99);
    ctx.fillStyle = '#ffb703';
    ctx.beginPath();
    ctx.arc(l1X, plotCenterY, 3.5, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = 'rgba(255, 183, 3, 0.8)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.arc(l1X, plotCenterY, 7, 0, Math.PI * 2);
    ctx.stroke();

    ctx.fillStyle = '#ffb703';
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    ctx.textAlign = 'right';
    ctx.fillText('L1 (DSCOVR/Aditya)', l1X - 8, plotCenterY - 10);

    ctx.restore();
  }

  drawCMECloud(ctx, shock, auToX, plotCenterY, sunX) {
    if (shock.rAu <= 0.03) return;

    ctx.save();
    const shockX = auToX(shock.rAu);
    const coneAngle = 0.45; // ~50° angular expansion half-width
    const distPx = shockX - sunX;

    // Expanding CME Conical Sheath
    ctx.beginPath();
    ctx.moveTo(sunX, plotCenterY);
    ctx.lineTo(shockX, plotCenterY - distPx * Math.tan(coneAngle));
    // Curved shock front
    ctx.arc(sunX, plotCenterY, distPx, -coneAngle, coneAngle);
    ctx.lineTo(sunX, plotCenterY);
    ctx.closePath();

    // Translucent plasma sheath gradient
    const sheathGrad = ctx.createRadialGradient(sunX, plotCenterY, distPx * 0.5, sunX, plotCenterY, distPx);
    sheathGrad.addColorStop(0, 'rgba(244, 63, 94, 0.05)');
    sheathGrad.addColorStop(0.7, 'rgba(244, 63, 94, 0.2)');
    sheathGrad.addColorStop(1, 'rgba(255, 183, 3, 0.35)');
    ctx.fillStyle = sheathGrad;
    ctx.fill();

    // Shock Wave Arc (Leading Edge)
    ctx.beginPath();
    ctx.arc(sunX, plotCenterY, distPx, -coneAngle, coneAngle);
    ctx.strokeStyle = '#ef4444';
    ctx.lineWidth = 2.4;
    ctx.stroke();

    // Magnetic Flux Rope Core (Toroidal Cloud)
    const coreX = sunX + distPx * 0.78;
    const coreRadiusY = distPx * 0.22;
    const coreRadiusX = distPx * 0.14;

    ctx.beginPath();
    ctx.ellipse(coreX, plotCenterY, coreRadiusX, coreRadiusY, 0, 0, Math.PI * 2);
    ctx.fillStyle = 'rgba(168, 85, 247, 0.22)';
    ctx.fill();
    ctx.strokeStyle = '#a855f7';
    ctx.lineWidth = 1.4;
    ctx.stroke();

    // Helical Magnetic Field Lines in Flux Rope Core
    ctx.strokeStyle = 'rgba(216, 180, 254, 0.5)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 3]);
    for (let k = -2; k <= 2; k++) {
      ctx.beginPath();
      ctx.ellipse(coreX, plotCenterY + k * (coreRadiusY * 0.35), coreRadiusX * 0.65, coreRadiusY * 0.2, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.setLineDash([]);

    // Shock Label
    ctx.fillStyle = '#f87171';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'left';
    ctx.fillText(`CME SHOCK FRONT (V = ${shock.vKms.toFixed(0)} km/s)`, shockX + 8, plotCenterY - distPx * Math.tan(coneAngle) + 12);

    ctx.restore();
  }

  drawHUD(ctx, shock) {
    ctx.save();

    // Top Right Kinematic Telemetry HUD
    const hudW = 290;
    const hudH = 106;
    const hudX = this.width - hudW - 14;
    const hudY = 14;

    ctx.fillStyle = 'rgba(7, 14, 34, 0.92)';
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.25)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(hudX, hudY, hudW, hudH, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#38bdf8';
    ctx.font = '600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('VRŠNAK (2013) DBM HELIOSPHERIC PROPAGATION', hudX + 10, hudY + 18);

    ctx.fillStyle = '#f8fafc';
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillText(`ELAPSED TIME: ${this.timeHrs.toFixed(1)} hrs / ${this.maxHrs.toFixed(0)} hrs`, hudX + 10, hudY + 34);
    ctx.fillText(`HELIOCENTRIC DIST: ${shock.rAu.toFixed(3)} AU (${shock.rSun.toFixed(1)} R☉)`, hudX + 10, hudY + 50);
    ctx.fillText(`SHOCK VELOCITY: ${shock.vKms.toFixed(0)} km/s | a = ${shock.dragAccelMs2.toFixed(2)} m/s²`, hudX + 10, hudY + 66);
    
    ctx.fillStyle = '#34d399';
    const leadMin = Math.max(0, (this.transitEarthHrs - this.transitL1Hrs) * 60).toFixed(0);
    ctx.fillText(`TRANSIT: L1 ${this.transitL1Hrs.toFixed(1)}h | Earth ${this.transitEarthHrs.toFixed(1)}h (Lead ${leadMin}m)`, hudX + 10, hudY + 82);
    
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`AMBIENT WIND: ${this.vAmbient} km/s | Γ: ${this.gamma.toExponential(1)} km⁻¹`, hudX + 10, hudY + 98);

    // Alerts for L1 & Earth Interception
    if (shock.isEarthHit) {
      this.drawAlertBanner(ctx, 'GEOMAGNETIC SUDDEN COMMENCEMENT (SC) - EARTH IMPACT!', '#ef4444');
    } else if (shock.isL1Hit) {
      const remainingMin = ((this.transitEarthHrs - this.timeHrs) * 60).toFixed(0);
      this.drawAlertBanner(ctx, `L1 INTERCEPTION - EARLY WARNING ACTIVE: +${remainingMin} MIN TO EARTH`, '#f59e0b');
    }

    ctx.restore();
  }

  drawAlertBanner(ctx, text, color) {
    ctx.save();
    const bx = this.width / 2 - 240;
    const by = 16;
    const bw = 480;
    const bh = 32;

    ctx.fillStyle = 'rgba(7, 14, 34, 0.95)';
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    ctx.roundRect(bx, by, bw, bh, 6);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = color;
    ctx.font = '600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(text, this.width / 2, by + 20);

    ctx.restore();
  }

  animate() {
    if (this.canvas && this.canvas.offsetParent !== null) {
      if (this.width === 0 || this.height === 0) {
        this.resize();
      }
      if (this.isPlaying) {
        // Advance by playback speed (1 real sec = 2.5 hrs of simulation)
        this.timeHrs += (1 / 60) * 2.5 * this.playbackSpeed;
        if (this.timeHrs > this.maxHrs) {
          this.timeHrs = this.maxHrs;
          this.isPlaying = false;
        }
        // Sync slider if present
        const slider = document.getElementById('cme-timeline-slider');
        if (slider) slider.value = this.timeHrs;
      }

      this.draw();
    }
    requestAnimationFrame(this.animate);
  }
}

// Attach to window
window.CMESimulator = CMESimulator;
