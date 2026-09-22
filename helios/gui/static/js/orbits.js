/**
 * High-Tech Interactive 2D/3D Orbit and Lagrange Point Canvas Renderer for HELIOS-L1
 * Real-time solar wind flux simulation, Roche lobe equipotentials,
 * magnetopause compression dynamics, 3D out-of-plane Halo projection,
 * and high-precision spacecraft ephemeris rendering.
 */

class OrbitRenderer {
  constructor(canvasId, tooltipId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.tooltip = document.getElementById(tooltipId);

    this.scale = 1.0;
    this.offsetX = 0;
    this.offsetY = 0;
    this.isDragging = false;
    this.startX = 0;
    this.startY = 0;

    // View mode: '2d' (ecliptic GSE) or '3d' (isometric halo view)
    this.viewMode = '2d';
    this.viewAngleZ = 0.55; // Tilt angle for 3D projection

    // Stars background
    this.stars = [];
    this.numStars = 140;

    // Solar wind particles
    this.particles = [];
    this.numParticles = 90;
    this.solarWindSpeed = 450; // km/s
    this.dynamicPressure = 1.8; // nPa
    this.bz = 0.0; // nT (GSM)
    this.machNumber = 8.0; // upstream Mach number
    this.boundaryModel = 'chao'; // 'chao' (Chao et al. 2002) or 'shue' (Shue et al. 1997)
    this.lastComputedBoundaries = null;

    this.timeStep = 0;
    this.orbitsData = null;
    this.lagrangeData = null;
    this.hoveredItem = null;

    // GSE Coordinate Grid, Spacecraft Filter Sets, and Dipole Field
    this.showGseGrid = true;
    this.showDipoleField = true;
    this.visibleSatellites = new Set(['DSCOVR', 'ACE', 'ADITYA_L1', 'WIND', 'SOHO', 'STEREO_A', 'GOES_16', 'PARKER_SOLAR_PROBE', 'SOLAR_ORBITER']);

    this.initStars();
    this.initParticles();
    this.initEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
  }

  setGseGrid(show) {
    this.showGseGrid = !!show;
  }

  setDipoleField(show) {
    this.showDipoleField = !!show;
  }

  setSatelliteVisibility(key, visible) {
    if (visible) {
      this.visibleSatellites.add(key);
    } else {
      this.visibleSatellites.delete(key);
    }
  }

  isSatelliteVisible(key) {
    return this.visibleSatellites.has(key);
  }

  toggleAllSatellites(visible) {
    if (visible) {
      this.visibleSatellites = new Set(['DSCOVR', 'ACE', 'ADITYA_L1', 'WIND', 'SOHO', 'STEREO_A', 'GOES_16', 'PARKER_SOLAR_PROBE', 'SOLAR_ORBITER']);
    } else {
      this.visibleSatellites.clear();
    }
  }

  initStars() {
    this.stars = [];
    for (let i = 0; i < this.numStars; i++) {
      this.stars.push({
        x: (Math.random() - 0.5) * 2400,
        y: (Math.random() - 0.5) * 1600,
        size: Math.random() * 1.6 + 0.4,
        alpha: Math.random() * 0.7 + 0.3,
        twinkleSpeed: Math.random() * 0.04 + 0.01,
        color: Math.random() > 0.8 ? '#38bdf8' : (Math.random() > 0.6 ? '#fef08a' : '#f8fafc')
      });
    }
  }

  initParticles() {
    this.particles = [];
    for (let i = 0; i < this.numParticles; i++) {
      // Distribute radially from the Sun's coronal surface (r = 36px) outward towards Earth (r ~ 680px)
      this.particles.push({
        dist: 36 + Math.random() * 660,
        angle: (Math.random() - 0.5) * 0.92, // ~ +-26 degrees Earthward heliospheric sector
        z: (Math.random() - 0.5) * 50,
        speed: 1.6 + Math.random() * 2.0,
        size: 1.0 + Math.random() * 1.3,
        alpha: 0.25 + Math.random() * 0.55
      });
    }
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width;
    this.canvas.height = rect.height;
    if (this.offsetX === 0 && this.offsetY === 0) {
      this.resetView();
    }
  }

  resetView() {
    this.scale = 1.05;
    this.offsetX = this.canvas.width * 0.58;
    this.offsetY = this.canvas.height * 0.5;
  }

  setViewMode(mode) {
    this.viewMode = mode;
  }

  setBoundaryModel(model) {
    this.boundaryModel = model === 'shue' ? 'shue' : 'chao';
  }

  setSolarWindConditions(speed, pdyn, bz, mach) {
    if (speed !== undefined && speed !== null && !isNaN(speed)) this.solarWindSpeed = Number(speed);
    if (pdyn !== undefined && pdyn !== null && !isNaN(pdyn)) this.dynamicPressure = Math.max(0.05, Number(pdyn));
    if (bz !== undefined && bz !== null && !isNaN(bz)) this.bz = Number(bz);
    if (mach !== undefined && mach !== null && !isNaN(mach)) this.machNumber = Math.max(1.15, Number(mach));
  }

  calculateBoundaries() {
    const pdyn = Math.max(0.05, this.dynamicPressure || 2.0);
    const bz = this.bz || 0.0;
    const m = Math.max(1.15, this.machNumber || 8.0);
    const mod = this.boundaryModel || 'chao';

    let r0_mp, alpha_mp, r0_bs, alpha_bs, modelName;

    if (mod === 'shue') {
      // Shue et al. (1997, 1998)
      r0_mp = (10.22 + 1.29 * Math.tanh(0.184 * (bz + 8.14))) * Math.pow(pdyn, -1.0 / 6.6);
      alpha_mp = (0.58 - 0.007 * bz) * (1.0 + 0.024 * Math.log(pdyn + 1.0));
      alpha_mp = Math.max(0.40, Math.min(0.90, alpha_mp));
      r0_bs = r0_mp * (1.0 + 1.1 * ((2.0 / 3.0 * (m * m) + 2.0) / (8.0 / 3.0 * (m * m - 1.0))));
      alpha_bs = 0.60;
      modelName = 'Shue et al. (1997, 1998)';
    } else {
      // Chao et al. (2002) Empirical Bilinear Model
      const pFactor = Math.pow(pdyn, -1.0 / 6.6);
      if (bz >= 0.0) {
        r0_mp = (11.12 + 0.057 * bz) * pFactor;
      } else {
        r0_mp = (11.12 + 0.541 * bz) * pFactor;
      }
      r0_mp = Math.max(3.5, Math.min(16.0, r0_mp));
      alpha_mp = (0.58 - 0.007 * bz) * (1.0 + 0.024 * pdyn);
      alpha_mp = Math.max(0.35, Math.min(0.95, alpha_mp));

      const gamma = 5.0 / 3.0;
      const machFactor = 1.0 + 0.8 * (((gamma - 1.0) * (m * m) + 2.0) / ((gamma + 1.0) * (m * m - 1.0)));
      r0_bs = (14.5 + 0.08 * bz) * pFactor * (machFactor / 1.25);
      r0_bs = Math.max(5.0, Math.min(25.0, r0_bs));
      alpha_bs = 0.61 * (1.0 + 0.015 * pdyn);
      alpha_bs = Math.max(0.40, Math.min(0.90, alpha_bs));
      modelName = 'Chao et al. (2002)';
    }

    // Scale conversion: Earth radii to canvas world pixels
    // GEO is at 6.6 R_E = 25px -> scaleRe = 25.0 / 6.6 ~ 3.788 px / R_E
    const scaleRe = 25.0 / 6.6;

    // Generate discrete polar boundary profiles: theta in [-2.35 rad, +2.35 rad] (~ -135 deg to +135 deg)
    const numPoints = 65;
    const minTh = -2.356;
    const maxTh = 2.356;
    const step = (maxTh - minTh) / (numPoints - 1);

    const mpPts = [];
    const bsPts = [];

    for (let i = 0; i < numPoints; i++) {
      const th = minTh + i * step;
      const denMp = 1.0 + Math.cos(th);
      const rMp = r0_mp * Math.pow(2.0 / Math.max(0.001, denMp), alpha_mp);
      // In canvas world coordinates, Sun is towards -X.
      // Subsolar theta = 0 -> X = -r * scaleRe, Y = 0
      const xMp = -rMp * Math.cos(th) * scaleRe;
      const yMp = rMp * Math.sin(th) * scaleRe;
      mpPts.push({ x: xMp, y: yMp, r: rMp, th });

      const denBs = 1.0 + Math.cos(th);
      const rBs = r0_bs * Math.pow(2.0 / Math.max(0.001, denBs), alpha_bs);
      const xBs = -rBs * Math.cos(th) * scaleRe;
      const yBs = rBs * Math.sin(th) * scaleRe;
      bsPts.push({ x: xBs, y: yBs, r: rBs, th });
    }

    const sheathRe = r0_bs - r0_mp;

    const data = {
      modelName,
      r0_mp,
      alpha_mp,
      r0_bs,
      alpha_bs,
      sheathRe,
      insideGeo: r0_mp < 6.6,
      mpPts,
      bsPts,
      scaleRe
    };
    this.lastComputedBoundaries = data;
    return data;
  }

  initEvents() {
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      this.startX = e.clientX - this.offsetX;
      this.startY = e.clientY - this.offsetY;
      this.canvas.style.cursor = 'grabbing';
    });

    window.addEventListener('mousemove', (e) => {
      if (this.isDragging) {
        this.offsetX = e.clientX - this.startX;
        this.offsetY = e.clientY - this.startY;
      } else {
        this.handleHover(e);
      }
    });

    window.addEventListener('mouseup', () => {
      this.isDragging = false;
      if (this.canvas) this.canvas.style.cursor = 'grab';
    });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
      this.scale = Math.min(Math.max(0.3, this.scale * zoomFactor), 4.5);
    });
  }

  project(x, y, z = 0) {
    if (this.viewMode === '3d') {
      // Oblique axonometric projection for 3D Halo orbits
      const px = x - z * 0.35;
      const py = y * 0.85 - z * 0.65;
      return { x: px, y: py };
    }
    return { x, y };
  }

  handleHover(e) {
    if (!this.canvas || !this.orbitsData) return;
    const rect = this.canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;

    const worldX = (mouseX - this.offsetX) / this.scale;
    const worldY = (mouseY - this.offsetY) / this.scale;

    let found = null;

    // Check spacecraft current positions
    for (const [key, sat] of Object.entries(this.orbitsData)) {
      if (this.visibleSatellites && !this.visibleSatellites.has(key)) continue;
      const pos = sat.current_pos;
      if (!pos) continue;

      let cx, cy;
      if (key === 'GOES_16') {
        cx = (pos.x / 42.164) * 25;
        cy = (pos.y / 42.164) * 25;
      } else {
        cx = (pos.x / 1496.0) * 260;
        cy = (pos.y / 280.0) * 70;
      }
      const proj = this.project(cx, cy, pos.z ? (pos.z / 150.0) * 40 : 0);
      const dist = Math.hypot(worldX - proj.x, worldY - proj.y);
      if (dist < 18) {
        found = { type: 'sat', data: sat, key };
        break;
      }
    }

    // Check Earth
    if (!found && Math.hypot(worldX, worldY) < 22) {
      found = { type: 'earth' };
    }

    // Check L1
    const l1Proj = this.project(-260, 0, 0);
    if (!found && Math.hypot(worldX - l1Proj.x, worldY - l1Proj.y) < 20) {
      found = { type: 'l1' };
    }

    // Check Sun
    const sunProj = this.project(-580, 0, 0);
    if (!found && Math.hypot(worldX - sunProj.x, worldY - sunProj.y) < 60) {
      found = { type: 'sun' };
    }

    // Check Magnetopause & Bow Shock Stand-offs
    if (!found && this.lastComputedBoundaries) {
      const b = this.lastComputedBoundaries;
      const mpStandoffX = -b.r0_mp * b.scaleRe;
      const bsStandoffX = -b.r0_bs * b.scaleRe;
      const distToMp = Math.hypot(worldX - mpStandoffX, worldY);
      const distToBs = Math.hypot(worldX - bsStandoffX, worldY);

      if (distToMp < 15) {
        found = { type: 'magnetopause', data: b };
      } else if (distToBs < 15) {
        found = { type: 'bow_shock', data: b };
      } else if (worldX <= mpStandoffX && worldX >= bsStandoffX && Math.abs(worldY) < 32) {
        found = { type: 'magnetosheath', data: b };
      }
    }

    this.hoveredItem = found;

    if (found && this.tooltip) {
      this.tooltip.classList.remove('hidden');
      this.tooltip.style.left = `${mouseX + 16}px`;
      this.tooltip.style.top = `${mouseY + 16}px`;

      if (found.type === 'sat') {
        const s = found.data;
        const spice = s.spice_telemetry;
        let spiceBlock = '';
        if (spice) {
          spiceBlock = `
            <div class="mt-2 pt-1.5 border-t border-slate-700/60 text-[10px] space-y-0.5">
              <div class="flex justify-between"><span class="text-slate-400">Orbital Speed:</span> <span class="font-mono text-emerald-400 font-semibold">${spice.velocity.speed_kms.toFixed(2)} km/s</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Earth Distance:</span> <span class="font-mono text-slate-300">${(spice.earth_relative.distance_km / 1000).toLocaleString(undefined, {maximumFractionDigits: 1})}k km (${spice.earth_relative.distance_re.toFixed(1)} R_E)</span></div>
              <div class="flex justify-between"><span class="text-slate-400">Solar Distance:</span> <span class="font-mono text-amber-300">${spice.heliocentric.distance_au.toFixed(4)} AU</span></div>
              <div class="flex justify-between"><span class="text-slate-400">True Anomaly (ν):</span> <span class="font-mono text-cyan-300">${spice.orbital_elements.true_anomaly_deg.toFixed(1)}°</span></div>
              <div class="mt-1 text-[9px] text-emerald-300/90 font-mono flex items-center justify-between border-t border-slate-800/80 pt-1">
                <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${spice.spice_toolkit}</span>
                <span class="text-slate-400">JPL Ephemeris</span>
              </div>
            </div>
          `;
        }
        this.tooltip.innerHTML = `
          <div class="flex items-center space-x-2 border-b border-sky-500/30 pb-1 mb-1">
            <span class="w-2 h-2 rounded-full" style="background:${s.color}"></span>
            <strong class="text-sky-300 font-bold">${s.name}</strong>
          </div>
          <div class="text-slate-300 text-[11px]">${s.type}</div>
          <div class="text-slate-400 text-[10px] mt-1 font-mono">
            GSE X: ${s.current_pos.x.toLocaleString()}k km<br>
            GSE Y: ${s.current_pos.y.toLocaleString()}k km<br>
            GSE Z: ${(s.current_pos.z || 0).toLocaleString()}k km
          </div>
          ${spiceBlock}
        `;
      } else if (found.type === 'earth') {
        const b = this.lastComputedBoundaries;
        const mpText = b ? `${b.r0_mp.toFixed(1)} R_E (${b.modelName})` : '10.5 R_E';
        this.tooltip.innerHTML = `
          <div class="font-bold text-blue-400 border-b border-blue-500/30 pb-1 mb-1">Earth (Terra)</div>
          <div class="text-slate-300 text-[11px]">Radius: ~6,371 km • 1.0 AU from Sun</div>
          <div class="text-emerald-400 text-[10px] mt-1">Dayside Standoff: ~${mpText}</div>
          <div class="text-slate-400 text-[10px]">GEO Orbit: 6.6 R_E (~42,164 km)</div>
        `;
      } else if (found.type === 'l1') {
        this.tooltip.innerHTML = `
          <div class="font-bold text-amber-400 border-b border-amber-500/30 pb-1 mb-1">Sun-Earth L1 Lagrange Point</div>
          <div class="text-slate-300 text-[11px]">Distance: ~1,496,000 km Sunward</div>
          <div class="text-slate-400 text-[10px] mt-1">Gravitational equilibrium saddle point</div>
          <div class="text-sky-300 text-[10px] mt-0.5">Fleet: DSCOVR, ACE, Aditya-L1, WIND, SOHO</div>
        `;
      } else if (found.type === 'sun') {
        this.tooltip.innerHTML = `
          <div class="font-bold text-amber-300 border-b border-amber-500/30 pb-1 mb-1">The Sun (Sol)</div>
          <div class="text-slate-300 text-[11px]">Primary Driver of Heliospheric Space Weather</div>
          <div class="text-amber-400 text-[10px] mt-1">V_sw Speed: ~${this.solarWindSpeed} km/s</div>
        `;
      } else if (found.type === 'magnetopause') {
        const b = found.data;
        this.tooltip.innerHTML = `
          <div class="font-bold text-amber-400 border-b border-amber-500/30 pb-1 mb-1 flex items-center justify-between">
            <span>Magnetopause Current Sheet</span>
            <span class="text-[9px] px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 font-mono">${b.modelName}</span>
          </div>
          <div class="text-slate-300 text-[11px]">Dynamic dayside pressure balance: P_dyn vs B²/2μ₀</div>
          <div class="text-amber-300 text-[11px] font-mono mt-1.5 space-y-0.5">
            <div>Subsolar Standoff (r₀,mp): <strong>${b.r0_mp.toFixed(2)} R_E</strong> (~${Math.round(b.r0_mp * 6371).toLocaleString()} km)</div>
            <div>Flaring Parameter (α_mp): <strong>${b.alpha_mp.toFixed(3)}</strong></div>
            <div>Dynamic Pressure: <strong>${this.dynamicPressure.toFixed(2)} nPa</strong> • Bz: <strong>${this.bz.toFixed(1)} nT</strong></div>
            <div>GEO Clearance (r₀ - 6.6 R_E): <strong class="${b.insideGeo ? 'text-rose-400 font-bold' : 'text-emerald-400'}">${(b.r0_mp - 6.6).toFixed(2)} R_E</strong></div>
          </div>
          ${b.insideGeo ? '<div class="text-rose-400 text-[10px] font-bold mt-1.5 bg-rose-950/60 p-1 rounded border border-rose-700/60"><i class="fa-solid fa-triangle-exclamation mr-1"></i>SUB-GEO COMPRESSION: Geostationary satellites inside sheath!</div>' : ''}
        `;
      } else if (found.type === 'bow_shock') {
        const b = found.data;
        this.tooltip.innerHTML = `
          <div class="font-bold text-sky-400 border-b border-sky-500/30 pb-1 mb-1 flex items-center justify-between">
            <span>Collisionless Bow Shock Front</span>
            <span class="text-[9px] px-1.5 py-0.2 rounded bg-sky-500/20 text-sky-300 font-mono">${b.modelName}</span>
          </div>
          <div class="text-slate-300 text-[11px]">Rankine-Hugoniot supersonic plasma deceleration</div>
          <div class="text-sky-300 text-[11px] font-mono mt-1.5 space-y-0.5">
            <div>Subsolar Standoff (R₀,bs): <strong>${b.r0_bs.toFixed(2)} R_E</strong> (~${Math.round(b.r0_bs * 6371).toLocaleString()} km)</div>
            <div>Flaring Parameter (α_bs): <strong>${b.alpha_bs.toFixed(3)}</strong></div>
            <div>Upstream Mach Number (M_A): <strong>${this.machNumber.toFixed(1)}</strong></div>
            <div>Polytropic Index: <strong>γ = 5/3</strong></div>
          </div>
        `;
      } else if (found.type === 'magnetosheath') {
        const b = found.data;
        this.tooltip.innerHTML = `
          <div class="font-bold text-cyan-300 border-b border-cyan-500/30 pb-1 mb-1">Magnetosheath Transition Region</div>
          <div class="text-slate-300 text-[11px]">Decelerated, shocked, turbulent interplanetary plasma</div>
          <div class="text-cyan-300 text-[11px] font-mono mt-1.5 space-y-0.5">
            <div>Sheath Thickness (ΔR): <strong>${b.sheathRe.toFixed(2)} R_E</strong> (~${Math.round(b.sheathRe * 6371).toLocaleString()} km)</div>
            <div>Separation: Bow Shock (${b.r0_bs.toFixed(1)} R_E) - Magnetopause (${b.r0_mp.toFixed(1)} R_E)</div>
          </div>
        `;
      }
    } else if (this.tooltip) {
      this.tooltip.classList.add('hidden');
    }
  }

  setOrbitsData(data) {
    this.orbitsData = data.orbits;
    this.lagrangeData = data.lagrange_points;
  }

  draw() {
    if (!this.canvas || !this.ctx) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;

    this.timeStep += 0.02;

    ctx.clearRect(0, 0, w, h);

    // Coordinate Transform
    ctx.save();
    ctx.translate(this.offsetX, this.offsetY);
    ctx.scale(this.scale, this.scale);

    // 1. Draw Twinkling Cosmic Starfield
    for (const s of this.stars) {
      const alpha = s.alpha * (0.6 + 0.4 * Math.sin(this.timeStep * s.twinkleSpeed * 10));
      ctx.fillStyle = s.color;
      ctx.globalAlpha = alpha;
      ctx.beginPath();
      ctx.arc(s.x, s.y, s.size, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.globalAlpha = 1.0;

    // 2. Draw Subtle Heliocentric Radial Grid
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.07)';
    ctx.lineWidth = 1;
    for (let r = 100; r <= 800; r += 140) {
      ctx.beginPath();
      ctx.arc(0, 0, r, 0, Math.PI * 2);
      ctx.stroke();
    }

    // 3. Equipotential Hill Curves / Roche Lobe around L1
    ctx.save();
    ctx.strokeStyle = 'rgba(245, 158, 11, 0.12)';
    ctx.lineWidth = 1.5;
    ctx.setLineDash([4, 6]);
    for (let eq = 1; eq <= 3; eq++) {
      ctx.beginPath();
      const rx = 50 * eq;
      const ry = 80 * eq;
      const l1P = this.project(-260, 0, 0);
      ctx.ellipse(l1P.x, l1P.y, rx, ry, 0, 0, Math.PI * 2);
      ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.restore();

    // 3.5 GSE Metric Coordinate Grid & Principal Axes
    if (this.showGseGrid) {
      ctx.save();
      ctx.lineWidth = 1;
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.08)';
      ctx.setLineDash([2, 5]);

      // Orthogonal grid lines along X (every 500k km ~ 87px)
      for (let gx = -600; gx <= 300; gx += 87) {
        const pTop = this.project(gx, -180, 0);
        const pBot = this.project(gx, 180, 0);
        ctx.beginPath();
        ctx.moveTo(pTop.x, pTop.y);
        ctx.lineTo(pBot.x, pBot.y);
        ctx.stroke();

        // Distance label along ecliptic
        const pLabel = this.project(gx, 192, 0);
        ctx.fillStyle = 'rgba(148, 163, 184, 0.45)';
        ctx.font = '500 8.5px "JetBrains Mono", monospace';
        ctx.textAlign = 'center';
        const distKmK = Math.round((gx / 260) * 1496);
        ctx.fillText(`${distKmK > 0 ? '+' : ''}${distKmK}k km`, pLabel.x, pLabel.y);
      }

      // Orthogonal grid lines along Y (every 250k km ~ 62px)
      for (let gy = -180; gy <= 180; gy += 60) {
        if (gy === 0) continue;
        const pLeft = this.project(-600, gy, 0);
        const pRight = this.project(300, gy, 0);
        ctx.beginPath();
        ctx.moveTo(pLeft.x, pLeft.y);
        ctx.lineTo(pRight.x, pRight.y);
        ctx.stroke();
      }
      ctx.setLineDash([]);

      // Principal GSE Axis Vectors from Earth (0,0,0)
      const earthP = this.project(0, 0, 0);

      // +X_GSE (Sunward, -X in canvas geometry)
      const xGseEnd = this.project(-120, 0, 0);
      ctx.strokeStyle = 'rgba(234, 179, 8, 0.65)';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(earthP.x, earthP.y);
      ctx.lineTo(xGseEnd.x, xGseEnd.y);
      ctx.stroke();
      ctx.fillStyle = '#fde047';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'right';
      ctx.fillText('+X_GSE (Sunward)', xGseEnd.x - 6, xGseEnd.y - 4);

      // +Y_GSE (Duskward)
      const yGseEnd = this.project(0, 75, 0);
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.65)';
      ctx.lineWidth = 1.6;
      ctx.beginPath();
      ctx.moveTo(earthP.x, earthP.y);
      ctx.lineTo(yGseEnd.x, yGseEnd.y);
      ctx.stroke();
      ctx.fillStyle = '#38bdf8';
      ctx.textAlign = 'left';
      ctx.fillText('+Y_GSE (Dusk)', yGseEnd.x + 8, yGseEnd.y + 3);

      if (this.viewMode === '3d') {
        // +Z_GSE (Ecliptic Northward)
        const zGseEnd = this.project(0, 0, 65);
        ctx.strokeStyle = 'rgba(168, 85, 247, 0.7)';
        ctx.lineWidth = 1.6;
        ctx.beginPath();
        ctx.moveTo(earthP.x, earthP.y);
        ctx.lineTo(zGseEnd.x, zGseEnd.y);
        ctx.stroke();
        ctx.fillStyle = '#c084fc';
        ctx.textAlign = 'left';
        ctx.fillText('+Z_GSE (North)', zGseEnd.x + 8, zGseEnd.y + 3);
      }

      ctx.restore();
    }

    // 4. Draw Animated Solar Wind Streamflow Particles (Strictly emanating from Sun)
    const animToggle = document.getElementById('orbit-anim-toggle');
    const isAnim = animToggle ? animToggle.checked : true;
    if (isAnim) {
      const sunX = -580;
      const sunY = 0;
      const speedMultiplier = (this.solarWindSpeed / 400.0) * 1.3;

      for (const p of this.particles) {
        // Advance radially outward from the Sun
        p.dist += p.speed * speedMultiplier;

        // Reset condition: particle propagates past Earth downstream (+80px in X or dist > 700px)
        if (p.dist > 710) {
          // Re-emerge directly from the Sun's coronal surface
          p.dist = 36 + Math.random() * 8;
          p.angle = (Math.random() - 0.5) * 0.92;
          p.z = (Math.random() - 0.5) * 50;
        }

        // Unperturbed radial heliospheric coordinate
        const unperturbedX = sunX + p.dist * Math.cos(p.angle);
        let unperturbedY = sunY + p.dist * Math.sin(p.angle);

        // Hydrodynamic deflection around Earth's magnetosphere (Earth is at 0, 0)
        let drawY = unperturbedY;
        if (unperturbedX > -65 && unperturbedX < 30 && Math.abs(unperturbedY) < 65) {
          const sign = Math.sign(unperturbedY) || 1;
          const factor = Math.exp(-((unperturbedX + 15) * (unperturbedX + 15)) / 600);
          const deflection = (65 - Math.min(65, Math.abs(unperturbedY))) * 0.42 * factor;
          drawY += sign * deflection;
        }

        const proj = this.project(unperturbedX, drawY, p.z);
        const normDist = Math.max(0, Math.min(1, (p.dist - 36) / 670));

        // Velocity streamline dash vector
        const prevDist = Math.max(36, p.dist - p.speed * speedMultiplier * 2.0);
        const prevX = sunX + prevDist * Math.cos(p.angle);
        const prevY = sunY + prevDist * Math.sin(p.angle);
        const prevProj = this.project(prevX, prevY, p.z);

        // Color transition: Warm coronal amber near Sun -> subtle celestial ion cyan/white at 1 AU
        const rVal = Math.round(245 - normDist * 50);
        const gVal = Math.round(180 + normDist * 25);
        const bVal = Math.round(50 + normDist * 180);
        const currentAlpha = p.alpha * (0.8 - normDist * 0.35);

        ctx.strokeStyle = `rgba(${rVal}, ${gVal}, ${bVal}, ${currentAlpha * 0.7})`;
        ctx.lineWidth = p.size;
        ctx.lineCap = 'round';
        ctx.beginPath();
        ctx.moveTo(prevProj.x, prevProj.y);
        ctx.lineTo(proj.x, proj.y);
        ctx.stroke();

        ctx.fillStyle = `rgba(${rVal}, ${gVal}, ${bVal}, ${currentAlpha})`;
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, p.size * 0.75, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // 5. Sun Core and Realistic Coronal Atmosphere
    ctx.save();
    const sunPos = this.project(-580, 0, 0);

    // Soft solar corona
    const coronaGlow = ctx.createRadialGradient(sunPos.x, sunPos.y, 25, sunPos.x, sunPos.y, 110);
    coronaGlow.addColorStop(0, 'rgba(245, 158, 11, 0.45)');
    coronaGlow.addColorStop(0.35, 'rgba(245, 158, 11, 0.15)');
    coronaGlow.addColorStop(0.7, 'rgba(234, 179, 8, 0.05)');
    coronaGlow.addColorStop(1, 'rgba(245, 158, 11, 0)');
    ctx.fillStyle = coronaGlow;
    ctx.beginPath();
    ctx.arc(sunPos.x, sunPos.y, 110, 0, Math.PI * 2);
    ctx.fill();

    // Solid Sun Core with Solar Limb Darkening
    const sunCore = ctx.createRadialGradient(sunPos.x - 5, sunPos.y - 5, 4, sunPos.x, sunPos.y, 34);
    sunCore.addColorStop(0, '#fffbeb');
    sunCore.addColorStop(0.3, '#fde047');
    sunCore.addColorStop(0.75, '#f59e0b');
    sunCore.addColorStop(1, '#b45309');
    ctx.fillStyle = sunCore;
    ctx.beginPath();
    ctx.arc(sunPos.x, sunPos.y, 34, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = 'rgba(253, 224, 71, 0.4)';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#fef08a';
    ctx.font = '600 11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('THE SUN (1.0 AU)', sunPos.x, sunPos.y + 50);

    // Sun-Earth Interplanetary Axis line
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.2)';
    ctx.lineWidth = 1;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(sunPos.x, sunPos.y);
    const earthCenter = this.project(0, 0, 0);
    ctx.lineTo(earthCenter.x, earthCenter.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    // 6. Earth & Magnetospheric Cavity (Chao et al. 2002 / Shue et al. 1997)
    ctx.save();
    const earthP = this.project(0, 0, 0);

    // Compute analytical boundaries
    const boundaries = this.calculateBoundaries();
    const scaleRe = boundaries.scaleRe;

    // A. Fill Magnetosheath Cavity (between Bow Shock and Magnetopause)
    if (boundaries.bsPts.length > 0 && boundaries.mpPts.length > 0) {
      ctx.save();
      ctx.beginPath();
      boundaries.bsPts.forEach((p, i) => {
        const proj = this.project(p.x, p.y, 0);
        if (i === 0) ctx.moveTo(proj.x, proj.y);
        else ctx.lineTo(proj.x, proj.y);
      });
      for (let i = boundaries.mpPts.length - 1; i >= 0; i--) {
        const proj = this.project(boundaries.mpPts[i].x, boundaries.mpPts[i].y, 0);
        ctx.lineTo(proj.x, proj.y);
      }
      ctx.closePath();

      const bsSubsolar = this.project(-boundaries.r0_bs * scaleRe, 0, 0);
      const mpSubsolar = this.project(-boundaries.r0_mp * scaleRe, 0, 0);
      const sheathGrad = ctx.createLinearGradient(bsSubsolar.x, 0, mpSubsolar.x, 0);
      sheathGrad.addColorStop(0, 'rgba(56, 189, 248, 0.16)');
      sheathGrad.addColorStop(0.5, 'rgba(14, 165, 233, 0.08)');
      sheathGrad.addColorStop(1, 'rgba(234, 179, 8, 0.04)');
      ctx.fillStyle = sheathGrad;
      ctx.fill();
      ctx.restore();
    }

    // B. Collisionless Planetary Bow Shock Front
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.85)';
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    boundaries.bsPts.forEach((p, i) => {
      const proj = this.project(p.x, p.y, 0);
      if (i === 0) ctx.moveTo(proj.x, proj.y);
      else ctx.lineTo(proj.x, proj.y);
    });
    ctx.stroke();

    // Subtle Bow Shock outer glow
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.2)';
    ctx.lineWidth = 4.0;
    ctx.stroke();

    // Bow Shock Subsolar Standoff Dot
    const bsSubsolarProj = this.project(-boundaries.r0_bs * scaleRe, 0, 0);
    ctx.fillStyle = '#38bdf8';
    ctx.beginPath();
    ctx.arc(bsSubsolarProj.x, bsSubsolarProj.y, 2.5, 0, Math.PI * 2);
    ctx.fill();

    // C. Terrestrial Magnetopause Boundary Current Sheet
    const mpColor = boundaries.insideGeo ? 'rgba(239, 68, 68, 0.9)' : 'rgba(234, 179, 8, 0.8)';
    ctx.strokeStyle = mpColor;
    ctx.lineWidth = 1.6;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    boundaries.mpPts.forEach((p, i) => {
      const proj = this.project(p.x, p.y, 0);
      if (i === 0) ctx.moveTo(proj.x, proj.y);
      else ctx.lineTo(proj.x, proj.y);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Magnetopause Subsolar Standoff Dot
    const mpSubsolarProj = this.project(-boundaries.r0_mp * scaleRe, 0, 0);
    ctx.fillStyle = boundaries.insideGeo ? '#ef4444' : '#f59e0b';
    ctx.beginPath();
    ctx.arc(mpSubsolarProj.x, mpSubsolarProj.y, 3, 0, Math.PI * 2);
    ctx.fill();

    // Subsolar Distance Label Callouts
    ctx.font = '600 8.5px "JetBrains Mono", monospace';
    ctx.fillStyle = '#38bdf8';
    ctx.textAlign = 'right';
    ctx.fillText(`BS: ${boundaries.r0_bs.toFixed(1)} RE`, bsSubsolarProj.x - 4, bsSubsolarProj.y - 6);

    ctx.fillStyle = boundaries.insideGeo ? '#f87171' : '#fbbf24';
    ctx.textAlign = 'left';
    ctx.fillText(`MP: ${boundaries.r0_mp.toFixed(1)} RE`, mpSubsolarProj.x + 4, mpSubsolarProj.y - 6);

    // D. Van Allen Radiation Belts (Muted scientific contours)
    ctx.fillStyle = 'rgba(147, 51, 234, 0.12)';
    ctx.strokeStyle = 'rgba(168, 85, 247, 0.3)';
    ctx.lineWidth = 1;
    for (const side of [-1, 1]) {
      ctx.beginPath();
      const beltP = this.project(0, side * 20, 0);
      ctx.ellipse(beltP.x, beltP.y, 8, 16, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    // Dipole Field Lines, Reconnection X-Point & Nightside Current Sheet
    this.drawDipoleAndMagnetotail(ctx, earthP, boundaries, scaleRe);

    // E. Geostationary Orbit (GEO ~ 42k km = 6.6 R_E = 25px radius)
    ctx.strokeStyle = boundaries.insideGeo ? 'rgba(239, 68, 68, 0.55)' : 'rgba(148, 163, 184, 0.35)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.ellipse(earthP.x, earthP.y, 25, this.viewMode === '3d' ? 16 : 25, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Sub-GEO Warning Callout if compressed
    if (boundaries.insideGeo) {
      ctx.fillStyle = '#ef4444';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText('SUB-GEO COMPRESSION', earthP.x, earthP.y - 32);
    }

    // Update DOM Telemetry HUD elements if present
    const hudBow = document.getElementById('hud-bow-standoff');
    if (hudBow) hudBow.innerText = `${boundaries.r0_bs.toFixed(1)} R_E`;
    const hudMp = document.getElementById('hud-mp-standoff');
    if (hudMp) {
      hudMp.innerText = `${boundaries.r0_mp.toFixed(1)} R_E`;
      hudMp.className = boundaries.insideGeo ? 'text-rose-400 font-bold animate-pulse' : 'text-amber-400 font-bold';
    }
    const hudSheath = document.getElementById('hud-sheath-thick');
    if (hudSheath) hudSheath.innerText = `${boundaries.sheathRe.toFixed(1)} R_E`;
    const hudMargin = document.getElementById('hud-geo-margin');
    if (hudMargin) {
      const margin = boundaries.r0_mp - 6.6;
      hudMargin.innerText = `${margin >= 0 ? '+' : ''}${margin.toFixed(1)} R_E`;
      hudMargin.className = margin < 0 ? 'text-rose-400 font-bold animate-pulse' : 'text-emerald-400 font-bold';
    }
    const hudModel = document.getElementById('hud-model-name');
    if (hudModel) hudModel.innerText = this.boundaryModel === 'shue' ? 'Shue 1997' : 'Chao 2002';

    // Earth Sphere with Day/Night Lighting (Sun on left illuminates -X)
    const earthGlow = ctx.createRadialGradient(earthP.x, earthP.y, 8, earthP.x, earthP.y, 18);
    earthGlow.addColorStop(0, 'rgba(56, 189, 248, 0.4)');
    earthGlow.addColorStop(0.7, 'rgba(37, 99, 235, 0.1)');
    earthGlow.addColorStop(1, 'rgba(30, 58, 138, 0)');
    ctx.fillStyle = earthGlow;
    ctx.beginPath();
    ctx.arc(earthP.x, earthP.y, 18, 0, Math.PI * 2);
    ctx.fill();

    // Day/Night shaded Earth body
    const earthGrad = ctx.createLinearGradient(earthP.x - 11, earthP.y, earthP.x + 11, earthP.y);
    earthGrad.addColorStop(0, '#93c5fd');
    earthGrad.addColorStop(0.45, '#2563eb');
    earthGrad.addColorStop(0.55, '#1e3a8a');
    earthGrad.addColorStop(1, '#090d16');
    ctx.fillStyle = earthGrad;
    ctx.beginPath();
    ctx.arc(earthP.x, earthP.y, 11, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = 'rgba(147, 197, 253, 0.6)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.fillStyle = '#bae6fd';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('EARTH', earthP.x, earthP.y + 24);
    ctx.restore();

    // 7. Lagrange Points (L1 & L2)
    ctx.save();
    const lagrangePoints = [
      { id: 'L1', x: -260, y: 0, label: 'L1 Lagrange (~1.5M km)', color: '#f59e0b' },
      { id: 'L2', x: 260, y: 0, label: 'L2 Lagrange (~1.5M km)', color: '#8b5cf6' }
    ];

    for (const lp of lagrangePoints) {
      const proj = this.project(lp.x, lp.y, 0);

      // Clean diamond marker
      ctx.strokeStyle = lp.color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      const s = 6.5;
      ctx.moveTo(proj.x, proj.y - s);
      ctx.lineTo(proj.x + s, proj.y);
      ctx.lineTo(proj.x, proj.y + s);
      ctx.lineTo(proj.x - s, proj.y);
      ctx.closePath();
      ctx.stroke();

      ctx.fillStyle = lp.color;
      ctx.font = '600 10px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(lp.id, proj.x, proj.y - 10);
    }
    ctx.restore();

    // 8. Spacecraft Orbits and Fleet Rendering
    if (this.orbitsData) {
      for (const [key, sat] of Object.entries(this.orbitsData)) {
        if (!sat.path || sat.path.length === 0) continue;
        if (this.visibleSatellites && !this.visibleSatellites.has(key)) continue;

        ctx.save();
        const satColor = sat.color || '#38bdf8';
        ctx.strokeStyle = satColor;
        ctx.lineWidth = 1.2;
        ctx.globalAlpha = 0.6;

        // Render full orbit path trace
        ctx.beginPath();
        sat.path.forEach((pt, i) => {
          let cx, cy;
          if (key === 'GOES_16') {
            cx = (pt.x / 42.164) * 25;
            cy = (pt.y / 42.164) * 25;
          } else {
            cx = (pt.x / 1496.0) * 260;
            cy = (pt.y / 280.0) * 70;
          }
          const proj = this.project(cx, cy, pt.z ? (pt.z / 150.0) * 40 : 0);
          if (i === 0) ctx.moveTo(proj.x, proj.y);
          else ctx.lineTo(proj.x, proj.y);
        });
        ctx.closePath();
        ctx.stroke();

        // Current Spacecraft Bead
        const cur = sat.current_pos;
        if (cur) {
          let px, py;
          if (key === 'GOES_16') {
            px = (cur.x / 42.164) * 25;
            py = (cur.y / 42.164) * 25;
          } else {
            px = (cur.x / 1496.0) * 260;
            py = (cur.y / 280.0) * 70;
          }
          const proj = this.project(px, py, cur.z ? (cur.z / 150.0) * 40 : 0);

          // Subtle locator ring
          ctx.globalAlpha = 0.3 + 0.2 * Math.sin(this.timeStep * 3);
          ctx.strokeStyle = satColor;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(proj.x, proj.y, 8, 0, Math.PI * 2);
          ctx.stroke();

          // Spacecraft Core Dot
          ctx.globalAlpha = 1.0;
          ctx.fillStyle = satColor;
          ctx.beginPath();
          ctx.arc(proj.x, proj.y, 4, 0, Math.PI * 2);
          ctx.fill();

          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1;
          ctx.stroke();

          // Crisp Monospace Label
          ctx.fillStyle = '#e2e8f0';
          ctx.font = '500 9.5px "JetBrains Mono", monospace';
          ctx.textAlign = 'left';
          ctx.fillText(sat.name, proj.x + 8, proj.y + 3);
        }

        ctx.restore();
      }
    }

    ctx.restore();
  }

  drawDipoleAndMagnetotail(ctx, earthP, boundaries, scaleRe) {
    if (!this.showDipoleField) return;

    ctx.save();
    const r0_mp = boundaries.r0_mp;
    const isReconnecting = this.bz < 0.0;
    const bzMag = Math.abs(this.bz || 0.0);

    // 1. Geomagnetic Dipole L-Shells (Closed loops: L = 2.2, 3.8, 5.2)
    // Formula: r(lat) = L * cos^2(lat)
    const lShells = [2.2, 3.8, 5.2];
    
    lShells.forEach((L, idx) => {
      const alpha = 0.32 - idx * 0.06;
      ctx.strokeStyle = `rgba(96, 165, 250, ${alpha})`;
      ctx.lineWidth = 1.0;
      ctx.setLineDash([3, 3]);

      // North & South lobes / hemispheres
      for (const hemi of [-1, 1]) {
        const maxLat = Math.acos(Math.sqrt(1.0 / Math.max(1.01, L)));
        const steps = 32;

        // Sunward branch (compressed inside r0_mp)
        ctx.beginPath();
        for (let i = 0; i <= steps; i++) {
          const lat = (i / steps) * maxLat * hemi;
          const r = L * Math.pow(Math.cos(lat), 2);
          const comp = Math.min(1.0, (r0_mp * 0.85) / Math.max(0.1, L));
          const xWorld = -r * Math.cos(lat) * scaleRe * comp;
          const yWorld = r * Math.sin(lat) * scaleRe;
          const proj = this.project(xWorld, yWorld, 0);
          if (i === 0) ctx.moveTo(proj.x, proj.y);
          else ctx.lineTo(proj.x, proj.y);
        }
        ctx.stroke();

        // Tailward branch (mild tailward stretch)
        ctx.beginPath();
        for (let i = 0; i <= steps; i++) {
          const lat = (i / steps) * maxLat * hemi;
          const r = L * Math.pow(Math.cos(lat), 2);
          const stretch = 1.0 + 0.18 * (L / 6.6);
          const xWorld = r * Math.cos(lat) * scaleRe * stretch;
          const yWorld = r * Math.sin(lat) * scaleRe;
          const proj = this.project(xWorld, yWorld, 0);
          if (i === 0) ctx.moveTo(proj.x, proj.y);
          else ctx.lineTo(proj.x, proj.y);
        }
        ctx.stroke();
      }
    });
    ctx.setLineDash([]);

    // 2. Open Magnetotail Lobe Field Lines (Stretching into nightside +X)
    const tailLengths = [18.0, 26.0, 34.0];
    tailLengths.forEach((tailRe, idx) => {
      const alpha = 0.24 - idx * 0.06;
      ctx.strokeStyle = `rgba(147, 197, 253, ${alpha})`;
      ctx.lineWidth = 1.1;

      for (const hemi of [-1, 1]) {
        ctx.beginPath();
        // Start from high-latitude polar cusp (r = 1.2 R_E)
        const startX = 1.2 * scaleRe * 0.45;
        const startY = hemi * 1.2 * scaleRe * 0.88;
        const startP = this.project(startX, startY, 0);
        ctx.moveTo(startP.x, startP.y);

        // Control point curving out and tailward
        const cpX = 5.5 * scaleRe;
        const cpY = hemi * (5.0 + idx * 3.0) * scaleRe;
        const cpP = this.project(cpX, cpY, 0);

        // End point far down magnetotail
        const endX = tailRe * scaleRe;
        const endY = hemi * (6.5 + idx * 3.5) * scaleRe;
        const endP = this.project(endX, endY, 0);

        ctx.quadraticCurveTo(cpP.x, cpP.y, endP.x, endP.y);
        ctx.stroke();
      }
    });

    // 3. Nightside Magnetotail Neutral Current Sheet (X > 0, Z ~ 0)
    const tailStart = this.project(3.5 * scaleRe, 0, 0);
    const tailEnd = this.project(34.0 * scaleRe, 0, 0);
    const sheetGrad = ctx.createLinearGradient(tailStart.x, tailStart.y, tailEnd.x, tailEnd.y);
    sheetGrad.addColorStop(0, 'rgba(245, 158, 11, 0.5)');
    sheetGrad.addColorStop(0.35, 'rgba(234, 88, 12, 0.3)');
    sheetGrad.addColorStop(1, 'rgba(239, 68, 68, 0)');

    ctx.strokeStyle = sheetGrad;
    ctx.lineWidth = 2.0;
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(tailStart.x, tailStart.y);
    ctx.lineTo(tailEnd.x, tailEnd.y);
    ctx.stroke();
    ctx.setLineDash([]);

    // Label: "MAGNETOTAIL CURRENT SHEET"
    const labelP = this.project(15.0 * scaleRe, 0, 0);
    ctx.fillStyle = 'rgba(251, 191, 36, 0.75)';
    ctx.font = '600 8px "JetBrains Mono", monospace';
    ctx.textAlign = 'center';
    ctx.fillText('NEUTRAL CURRENT SHEET', labelP.x, labelP.y + 11);

    // 4. Subsolar Magnetic Reconnection X-Point & Energy Influx (when Bz < 0)
    if (isReconnecting) {
      const mpSubsolarX = -r0_mp * scaleRe;
      const xPt = this.project(mpSubsolarX, 0, 0);
      const pulse = 0.5 + 0.5 * Math.sin(this.timeStep * 0.12);
      const intensity = Math.min(1.0, bzMag / 15.0);

      // Reconnection X-point glow
      const xGlow = ctx.createRadialGradient(xPt.x, xPt.y, 1, xPt.x, xPt.y, 14 + pulse * 6);
      xGlow.addColorStop(0, `rgba(239, 68, 68, ${0.7 + pulse * 0.3})`);
      xGlow.addColorStop(0.5, `rgba(249, 115, 22, ${0.35 * intensity})`);
      xGlow.addColorStop(1, 'rgba(239, 68, 68, 0)');
      ctx.fillStyle = xGlow;
      ctx.beginPath();
      ctx.arc(xPt.x, xPt.y, 20, 0, Math.PI * 2);
      ctx.fill();

      // Sharp Reconnection X-line separatrices
      ctx.strokeStyle = `rgba(254, 202, 202, ${0.85 + pulse * 0.15})`;
      ctx.lineWidth = 1.4;
      const xArm = 7.0 + pulse * 2.5;
      ctx.beginPath();
      ctx.moveTo(xPt.x - xArm, xPt.y - xArm);
      ctx.lineTo(xPt.x + xArm, xPt.y + xArm);
      ctx.moveTo(xPt.x - xArm, xPt.y + xArm);
      ctx.lineTo(xPt.x + xArm, xPt.y - xArm);
      ctx.stroke();

      // Dynamic Reconnection Annotation
      ctx.fillStyle = '#ef4444';
      ctx.font = 'bold 8.5px "JetBrains Mono", monospace';
      ctx.textAlign = 'center';
      ctx.fillText(`⚡ RECONNECTION X-POINT (Bz: ${this.bz.toFixed(1)} nT)`, xPt.x, xPt.y - 14);
    }

    ctx.restore();
  }
}
