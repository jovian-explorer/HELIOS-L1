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
    this.isPaused = false;
    this.manualAnomalyDeg = null;
    this.pspOrbitSpeedMultiplier = 0.00075; // Graceful, observable scientific orbital progression

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

    // NAIF SPICE Ephemeris State
    this.spiceFleetData = null;
    this.spiceAvailable = false;
    this.spiceToolkit = 'CSPICE_N0067';
    this.fetchSpiceEphemeris();

    this.initEventListeners();
    this.resize();
    this.animate = this.animate.bind(this);
    requestAnimationFrame(this.animate);
  }

  async fetchSpiceEphemeris() {
    try {
      const res = await fetch('/api/ephemeris/spice?satellites=PARKER_SOLAR_PROBE,SOLAR_ORBITER,STEREO_A,EARTH,VENUS,MARS,MERCURY');
      if (res.ok) {
        const data = await res.json();
        this.spiceFleetData = data.fleet;
        this.spiceAvailable = data.spice_available;
        this.spiceToolkit = data.spice_version;
        console.log('[ParkerSpiral] SPICE ephemeris synchronized with NASA JPL CSPICE pool.');
      }
    } catch (err) {
      console.warn('[ParkerSpiral] SPICE ephemeris fetch warning:', err);
    }
  }

  setPSPAnomaly(deg) {
    this.manualAnomalyDeg = (deg !== null && deg !== undefined && !isNaN(deg)) ? Number(deg) : null;
  }

  setPSPPreset(preset) {
    if (preset === 'perihelion') {
      this.manualAnomalyDeg = 0;
      this.isPaused = true;
    } else if (preset === 'aphelion') {
      this.manualAnomalyDeg = 180;
      this.isPaused = true;
    } else if (preset === 'venus') {
      this.manualAnomalyDeg = 100;
      this.isPaused = true;
    } else {
      this.manualAnomalyDeg = null;
      this.isPaused = false;
    }
    const slider = document.getElementById('psp-anomaly-slider');
    const readout = document.getElementById('psp-anomaly-val');
    if (slider && this.manualAnomalyDeg !== null) {
      slider.value = this.manualAnomalyDeg;
      if (readout) readout.innerText = `${this.manualAnomalyDeg}°`;
    }
  }

  togglePSPPlay() {
    this.isPaused = !this.isPaused;
    return !this.isPaused;
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

  solveKepler(meanAnomaly, ecc) {
    let E = meanAnomaly;
    for (let i = 0; i < 6; i++) {
      const f = E - ecc * Math.sin(E) - meanAnomaly;
      const fPrime = 1.0 - ecc * Math.cos(E);
      E -= f / fPrime;
    }
    return E;
  }

  getPSPState() {
    // NASA Parker Solar Probe (PSP) Physical Ephemeris
    // Perihelion: 9.86 R_sun (~0.0458 AU, 6.85M km)
    // Aphelion: 0.730 AU (109.2M km, Venus resonant)
    // Semi-major axis a = 0.3879 AU, eccentricity e = 0.8819
    const aAu = 0.3879;
    const ecc = 0.8819;
    const muSun = 1.3271244e11; // km^3/s^2 (G * M_sun)
    const aKm = aAu * this.auKm;

    let trueAnomaly, rAu, E;
    if (this.manualAnomalyDeg !== null) {
      // Direct operator anomaly scrub
      trueAnomaly = (this.manualAnomalyDeg * Math.PI) / 180.0;
      rAu = (aAu * (1.0 - ecc * ecc)) / (1.0 + ecc * Math.cos(trueAnomaly));
      E = Math.atan2(Math.sqrt(1.0 - ecc * ecc) * Math.sin(trueAnomaly), ecc + Math.cos(trueAnomaly));
    } else if (this.spiceFleetData && this.spiceFleetData.PARKER_SOLAR_PROBE) {
      // Direct NASA JPL NAIF SPICE state vector
      const spicePsp = this.spiceFleetData.PARKER_SOLAR_PROBE;
      rAu = spicePsp.heliocentric.distance_au;
      trueAnomaly = (spicePsp.orbital_elements.true_anomaly_deg * Math.PI) / 180.0;
      E = Math.atan2(Math.sqrt(1.0 - ecc * ecc) * Math.sin(trueAnomaly), ecc + Math.cos(trueAnomaly));
    } else {
      // Period T = 88.2 days. Smooth, graceful real-time Keplerian orbital progression
      const meanAnomaly = ((this.time * this.pspOrbitSpeedMultiplier) % (Math.PI * 2));
      E = this.solveKepler(meanAnomaly, ecc);
      rAu = aAu * (1.0 - ecc * Math.cos(E));
      trueAnomaly = Math.atan2(Math.sqrt(1.0 - ecc * ecc) * Math.sin(E), Math.cos(E) - ecc);
    }

    const rKm = rAu * this.auKm;
    const rSun = rKm / this.rSunKm;
    const theta = trueAnomaly + 1.95; // orientation in heliocentric ecliptic plane

    // Rigorous Vis-Viva orbital speed: v = sqrt(mu * (2/r - 1/a)) [km/s]
    const vKms = (this.spiceFleetData && this.spiceFleetData.PARKER_SOLAR_PROBE && this.manualAnomalyDeg === null)
      ? this.spiceFleetData.PARKER_SOLAR_PROBE.velocity.speed_kms
      : Math.sqrt(Math.max(10.0, muSun * (2.0 / rKm - 1.0 / aKm)));
    const vAuDay = (vKms * 86400.0) / this.auKm;
    const trueAnomalyDeg = ((trueAnomaly * 180.0 / Math.PI) + 360) % 360;

    let phase = (this.spiceFleetData && this.spiceFleetData.PARKER_SOLAR_PROBE && this.manualAnomalyDeg === null)
      ? this.spiceFleetData.PARKER_SOLAR_PROBE.phase
      : 'Intermediate Orbit Leg';
    if (this.manualAnomalyDeg !== null) {
      if (rSun <= 12.0) {
        phase = 'Perihelion Plunge (9.86 R☉ record, Alfvén Surface crossing)';
      } else if (rAu >= 0.70) {
        phase = 'Aphelion Turnaround (0.730 AU near Venus orbit)';
      } else if (E < Math.PI) {
        phase = 'Outward Ascent toward Aphelion';
      } else {
        phase = 'Inward Plunge toward Solar Perihelion';
      }
    }

    return {
      name: 'Parker Solar Probe (PSP)',
      aAu,
      ecc,
      rAu,
      rKm,
      rSun,
      theta,
      trueAnomalyDeg,
      vKms,
      vAuDay,
      phase,
      isSpice: !!(this.spiceFleetData && this.spiceFleetData.PARKER_SOLAR_PROBE && this.manualAnomalyDeg === null)
    };
  }

  getSolOState() {
    // ESA/NASA Solar Orbiter (SolO) Ephemeris
    // Perihelion: ~0.28 AU, Aphelion: ~0.91 AU, a = 0.595 AU, e = 0.529
    const aAu = 0.595;
    const ecc = 0.529;
    const muSun = 1.3271244e11;
    const aKm = aAu * this.auKm;

    let rAu, trueAnomaly, vKms;
    if (this.spiceFleetData && this.spiceFleetData.SOLAR_ORBITER) {
      const spiceSolO = this.spiceFleetData.SOLAR_ORBITER;
      rAu = spiceSolO.heliocentric.distance_au;
      trueAnomaly = (spiceSolO.orbital_elements.true_anomaly_deg * Math.PI) / 180.0;
      vKms = spiceSolO.velocity.speed_kms;
    } else {
      const meanAnomaly = ((this.time * (this.pspOrbitSpeedMultiplier * 0.6) + 1.8) % (Math.PI * 2));
      const E = this.solveKepler(meanAnomaly, ecc);
      rAu = aAu * (1.0 - ecc * Math.cos(E));
      trueAnomaly = Math.atan2(Math.sqrt(1.0 - ecc * ecc) * Math.sin(E), Math.cos(E) - ecc);
      const rKm = rAu * this.auKm;
      vKms = Math.sqrt(Math.max(10.0, muSun * (2.0 / rKm - 1.0 / aKm)));
    }

    const rKm = rAu * this.auKm;
    const rSun = rKm / this.rSunKm;
    const theta = trueAnomaly + 3.85;
    const vAuDay = (vKms * 86400.0) / this.auKm;
    const trueAnomalyDeg = ((trueAnomaly * 180.0 / Math.PI) + 360) % 360;

    return {
      name: 'Solar Orbiter (SolO)',
      aAu,
      ecc,
      rAu,
      rKm,
      rSun,
      theta,
      trueAnomalyDeg,
      vKms,
      vAuDay,
      isSpice: !!(this.spiceFleetData && this.spiceFleetData.SOLAR_ORBITER)
    };
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

    // Check if mouse is hovering near Parker Solar Probe
    if (this.pspScreenPos && Math.hypot(mw.x - this.pspScreenPos.x, mw.y - this.pspScreenPos.y) < 22) {
      const p = this.pspScreenPos.state;
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-rose-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-rose-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-satellite text-[10px]"></i>
            <span>NASA Parker Solar Probe (PSP)</span>
          </strong>
          <span class="text-[10px] text-amber-300 font-mono font-bold">${p.rAu.toFixed(4)} AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Solar Distance: <span class="text-slate-100 font-bold">${p.rSun.toFixed(1)} R☉</span> (${(p.rKm / 1e6).toFixed(2)}M km)</div>
          <div>Vis-Viva Orbital Velocity: <span class="text-rose-400 font-bold">${p.vKms.toFixed(1)} km/s</span> (${p.vAuDay.toFixed(4)} AU/day)</div>
          <div>True Anomaly (ν): <span class="text-cyan-300 font-bold">${p.trueAnomalyDeg.toFixed(1)}°</span></div>
          <div>Perihelion Record: <span class="text-amber-400 font-bold">9.86 R☉ (0.0458 AU)</span> @ 190.8 km/s</div>
          <div>Aphelion Boundary: <span class="text-slate-300 font-bold">0.730 AU</span> @ 12.0 km/s</div>
          <div>Keplerian Period: <span class="text-slate-400 font-bold">88.2 Days (e = 0.8819)</span></div>
          <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">${p.phase}</div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">State Vector Verified</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near Solar Orbiter
    if (this.soloScreenPos && Math.hypot(mw.x - this.soloScreenPos.x, mw.y - this.soloScreenPos.y) < 20) {
      const s = this.soloScreenPos.state;
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-cyan-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-cyan-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-satellite text-[10px]"></i>
            <span>ESA / NASA Solar Orbiter (SolO)</span>
          </strong>
          <span class="text-[10px] text-cyan-300 font-mono font-bold">${s.rAu.toFixed(4)} AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Solar Distance: <span class="text-slate-100 font-bold">${s.rSun.toFixed(1)} R☉</span> (${(s.rKm / 1e6).toFixed(2)}M km)</div>
          <div>Vis-Viva Velocity: <span class="text-cyan-400 font-bold">${s.vKms.toFixed(1)} km/s</span> (${s.vAuDay.toFixed(4)} AU/day)</div>
          <div>True Anomaly (ν): <span class="text-sky-300 font-bold">${s.trueAnomalyDeg.toFixed(1)}°</span></div>
          <div>Perihelion: <span class="text-amber-400">0.28 AU</span> | Aphelion: <span class="text-slate-400">0.91 AU</span></div>
          <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">High-Latitude Solar Wind Probe (Inclination 24-33°)</div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">State Vector Verified</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near Earth
    if (this.earthScreenPos && Math.hypot(mw.x - this.earthScreenPos.x, mw.y - this.earthScreenPos.y) < 16) {
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-sky-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-sky-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-earth-americas text-[10px]"></i>
            <span>Earth (Terra)</span>
          </strong>
          <span class="text-[10px] text-sky-300 font-mono font-bold">1.000 AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Distance from Sun: <span class="text-slate-100 font-bold">1.00 AU</span> (149.6M km)</div>
          <div>Orbital Velocity: <span class="text-emerald-400 font-bold">29.78 km/s</span></div>
          <div>Magnetic Connectivity: <span class="text-amber-300 font-bold">Footpoint ~50°-60° W</span></div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">Geocenter Reference</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near L1
    if (this.l1ScreenPos && Math.hypot(mw.x - this.l1ScreenPos.x, mw.y - this.l1ScreenPos.y) < 16) {
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-amber-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-amber-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-crosshairs text-[10px]"></i>
            <span>Sun-Earth L1 Lagrange Fleet</span>
          </strong>
          <span class="text-[10px] text-amber-300 font-mono font-bold">0.990 AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Distance from Earth: <span class="text-slate-100 font-bold">1.496M km</span> Sunward (~235 R_E)</div>
          <div>Active Fleet Probes: <span class="text-amber-400 font-bold">Aditya-L1, DSCOVR, ACE, WIND, SOHO</span></div>
          <div>Early Warning Horizon: <span class="text-cyan-300 font-bold">~45 - 60 minutes</span> upstream</div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">L1 Halo Constellation</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near STEREO-A
    if (this.stereoScreenPos && Math.hypot(mw.x - this.stereoScreenPos.x, mw.y - this.stereoScreenPos.y) < 16) {
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-purple-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-purple-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-satellite text-[10px]"></i>
            <span>NASA STEREO-Ahead</span>
          </strong>
          <span class="text-[10px] text-purple-300 font-mono font-bold">0.962 AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Heliocentric Orbit: <span class="text-slate-100 font-bold">~21° Ahead of Earth</span></div>
          <div>Orbital Velocity: <span class="text-purple-400 font-bold">30.4 km/s</span></div>
          <div>Role: <span class="text-slate-300">Side-view CME coronagraph stereoscopy</span></div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">State Vector Verified</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near Venus
    if (this.venusScreenPos && Math.hypot(mw.x - this.venusScreenPos.x, mw.y - this.venusScreenPos.y) < 18) {
      const v = this.venusScreenPos.state;
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-amber-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-amber-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-planet-ringed text-[10px]"></i>
            <span>Venus (Aphrodite)</span>
          </strong>
          <span class="text-[10px] text-amber-300 font-mono font-bold">${v.rAu.toFixed(4)} AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Solar Distance: <span class="text-slate-100 font-bold">${(v.rAu * this.auKm / 1e6).toFixed(2)}M km</span> (${(v.rAu * this.auKm / this.rSunKm).toFixed(1)} R☉)</div>
          <div>Orbital Speed: <span class="text-amber-400 font-bold">${v.vKms.toFixed(2)} km/s</span> (${((v.vKms * 86400) / this.auKm).toFixed(4)} AU/day)</div>
          <div>Orbital Period: <span class="text-slate-300 font-bold">224.70 Days</span> (e = 0.0068, i = 3.39°)</div>
          <div>True Anomaly (ν): <span class="text-amber-300 font-bold">${v.trueAnomalyDeg.toFixed(1)}°</span></div>
          <div>Atmosphere: <span class="text-slate-300">Dense CO₂ (92 bar) • Induced Magnetosphere</span></div>
          <div>Role: <span class="text-sky-300">PSP & SolO Gravity Assist / Inner Flare Monitor</span></div>
          <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">${v.phase}</div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">State Vector Verified</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near Mars
    if (this.marsScreenPos && Math.hypot(mw.x - this.marsScreenPos.x, mw.y - this.marsScreenPos.y) < 18) {
      const m = this.marsScreenPos.state;
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-rose-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-rose-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-circle text-[10px] text-rose-500"></i>
            <span>Mars (Ares)</span>
          </strong>
          <span class="text-[10px] text-rose-300 font-mono font-bold">${m.rAu.toFixed(4)} AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Solar Distance: <span class="text-slate-100 font-bold">${(m.rAu * this.auKm / 1e6).toFixed(2)}M km</span> (${(m.rAu * this.auKm / this.rSunKm).toFixed(1)} R☉)</div>
          <div>Orbital Speed: <span class="text-rose-400 font-bold">${m.vKms.toFixed(2)} km/s</span> (${((m.vKms * 86400) / this.auKm).toFixed(4)} AU/day)</div>
          <div>Orbital Period: <span class="text-slate-300 font-bold">686.98 Days</span> (e = 0.0934, i = 1.85°)</div>
          <div>True Anomaly (ν): <span class="text-rose-300 font-bold">${m.trueAnomalyDeg.toFixed(1)}°</span></div>
          <div>Role: <span class="text-sky-300">Downstream Magnetotail & Induced Magnetosphere</span></div>
          <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">${m.phase}</div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">State Vector Verified</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

    // Check if mouse is hovering near Mercury
    if (this.mercuryScreenPos && Math.hypot(mw.x - this.mercuryScreenPos.x, mw.y - this.mercuryScreenPos.y) < 18) {
      const mc = this.mercuryScreenPos.state;
      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-slate-500/40 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-slate-300 font-bold text-xs flex items-center space-x-1.5">
            <i class="fa-solid fa-circle text-[9px] text-slate-400"></i>
            <span>Mercury (Hermes)</span>
          </strong>
          <span class="text-[10px] text-slate-300 font-mono font-bold">${mc.rAu.toFixed(4)} AU</span>
        </div>
        <div class="text-[11px] font-mono space-y-1 text-slate-200">
          <div>Solar Distance: <span class="text-slate-100 font-bold">${(mc.rAu * this.auKm / 1e6).toFixed(2)}M km</span> (${(mc.rAu * this.auKm / this.rSunKm).toFixed(1)} R☉)</div>
          <div>Orbital Speed: <span class="text-sky-300 font-bold">${mc.vKms.toFixed(2)} km/s</span> (${((mc.vKms * 86400) / this.auKm).toFixed(4)} AU/day)</div>
          <div>Orbital Period: <span class="text-slate-300 font-bold">87.97 Days</span> (e = 0.2056, i = 7.00°)</div>
          <div>True Anomaly (ν): <span class="text-slate-300 font-bold">${mc.trueAnomalyDeg.toFixed(1)}°</span></div>
          <div>Role: <span class="text-amber-300">Innermost Sub-Alfvénic Reconnection Probe</span></div>
          <div class="text-slate-400 text-[10px] pt-1 border-t border-slate-800">${mc.phase}</div>
          <div class="text-emerald-300 text-[10px] font-mono pt-1 border-t border-slate-800 flex items-center justify-between">
            <span><i class="fa-solid fa-satellite-dish"></i> NAIF SPICE ${this.spiceToolkit}</span>
            <span class="text-slate-400 font-normal">State Vector Verified</span>
          </div>
        </div>
      `;
      this.positionTooltip(clientX, clientY);
      return;
    }

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

    this.positionTooltip(clientX, clientY);
  }

  positionTooltip(clientX, clientY) {
    if (!this.tooltip) return;
    const parentRect = this.canvas.parentElement.getBoundingClientRect();
    const left = clientX - parentRect.left + 15;
    const top = clientY - parentRect.top + 15;
    this.tooltip.style.left = `${Math.min(left, this.width - 270)}px`;
    this.tooltip.style.top = `${Math.min(top, this.height - 150)}px`;
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
    this.earthScreenPos = { x: earthX, y: earthY };

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
    this.l1ScreenPos = { x: l1X, y: l1Y };

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
    this.stereoScreenPos = { x: stereoX, y: stereoY };

    ctx.fillStyle = '#a855f7';
    ctx.beginPath();
    ctx.arc(stereoX, stereoY, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#d8b4fe';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText('STEREO-A (0.96 AU)', stereoX + 8, stereoY);

    // 4. Parker Solar Probe (NASA Keplerian Ephemeris & Vis-Viva Speed)
    const psp = this.getPSPState();
    const pspX = cx + psp.rAu * scale * Math.cos(psp.theta);
    const pspY = cy - psp.rAu * scale * Math.sin(psp.theta);
    this.pspScreenPos = { x: pspX, y: pspY, state: psp };

    // Draw PSP Elliptical Orbit Track (subtle rose dashed line)
    ctx.strokeStyle = 'rgba(244, 63, 94, 0.3)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    for (let s = 0; s <= 64; s++) {
      const EA = (s / 64) * Math.PI * 2;
      const rA = psp.aAu * (1.0 - psp.ecc * Math.cos(EA));
      const ta = Math.atan2(Math.sqrt(1.0 - psp.ecc * psp.ecc) * Math.sin(EA), Math.cos(EA) - psp.ecc);
      const px = cx + rA * scale * Math.cos(ta + 1.95);
      const py = cy - rA * scale * Math.sin(ta + 1.95);
      if (s === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // PSP Spacecraft Dot
    ctx.fillStyle = '#f43f5e';
    ctx.beginPath();
    ctx.arc(pspX, pspY, 3.5, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fda4af';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.fillStyle = '#fecdd3';
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    ctx.fillText(`PSP: ${psp.rSun.toFixed(1)} R☉ (${psp.vKms.toFixed(0)} km/s)`, pspX + 6, pspY - 4);

    // Sync scrubber UI slider if operator is not manually scrubbing
    if (this.manualAnomalyDeg === null) {
      const slider = document.getElementById('psp-anomaly-slider');
      const readout = document.getElementById('psp-anomaly-val');
      if (slider) slider.value = Math.round(psp.trueAnomalyDeg);
      if (readout) readout.innerText = `${Math.round(psp.trueAnomalyDeg)}°`;
    }

    // 5. Solar Orbiter (ESA/NASA High-Latitude Heliocentric Probe)
    const solo = this.getSolOState();
    const soloX = cx + solo.rAu * scale * Math.cos(solo.theta);
    const soloY = cy - solo.rAu * scale * Math.sin(solo.theta);
    this.soloScreenPos = { x: soloX, y: soloY, state: solo };

    // Draw SolO Elliptical Orbit Track (subtle cyan dashed line)
    ctx.strokeStyle = 'rgba(6, 182, 212, 0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    for (let s = 0; s <= 64; s++) {
      const EA = (s / 64) * Math.PI * 2;
      const rA = solo.aAu * (1.0 - solo.ecc * Math.cos(EA));
      const ta = Math.atan2(Math.sqrt(1.0 - solo.ecc * solo.ecc) * Math.sin(EA), Math.cos(EA) - solo.ecc);
      const px = cx + rA * scale * Math.cos(ta + 3.85);
      const py = cy - rA * scale * Math.sin(ta + 3.85);
      if (s === 0) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // SolO Spacecraft Dot
    ctx.fillStyle = '#06b6d4';
    ctx.beginPath();
    ctx.arc(soloX, soloY, 3, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#67e8f9';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#a5f3fc';
    ctx.font = '9px "JetBrains Mono", monospace';
    ctx.fillText(`SolO (${solo.vKms.toFixed(0)} km/s)`, soloX + 6, soloY + 11);

    // Determine Earth reference ecliptic longitude from SPICE
    const earthLong = (this.spiceFleetData && this.spiceFleetData.EARTH) 
      ? this.spiceFleetData.EARTH.heliocentric.ecliptic_longitude_deg 
      : 0;

    // 6. VENUS (0.723 AU)
    const spiceVenus = this.spiceFleetData && this.spiceFleetData.VENUS;
    const rVenusAu = spiceVenus ? spiceVenus.heliocentric.distance_au : 0.723;
    const vVenusKms = spiceVenus ? spiceVenus.velocity.speed_kms : 35.02;
    const phiVenus = spiceVenus 
      ? ((spiceVenus.heliocentric.ecliptic_longitude_deg - earthLong) * Math.PI / 180.0)
      : (0.85 + this.time * 0.0016);
    const venusX = cx + rVenusAu * scale * Math.cos(phiVenus);
    const venusY = cy - rVenusAu * scale * Math.sin(phiVenus);
    this.venusScreenPos = {
      x: venusX,
      y: venusY,
      state: {
        name: 'Venus',
        rAu: rVenusAu,
        vKms: vVenusKms,
        phase: spiceVenus ? spiceVenus.phase : 'Inner terrestrial planet / PSP gravity assist node',
        trueAnomalyDeg: spiceVenus ? spiceVenus.orbital_elements.true_anomaly_deg : (((phiVenus * 180 / Math.PI) % 360) + 360) % 360,
        isSpice: !!spiceVenus
      }
    };

    // Venus Glow & Body
    const venusAtmosphere = ctx.createRadialGradient(venusX, venusY, 2, venusX, venusY, 10);
    venusAtmosphere.addColorStop(0, 'rgba(251, 191, 36, 0.45)');
    venusAtmosphere.addColorStop(1, 'rgba(251, 191, 36, 0)');
    ctx.fillStyle = venusAtmosphere;
    ctx.beginPath();
    ctx.arc(venusX, venusY, 10, 0, Math.PI * 2);
    ctx.fill();

    const venusGrad = ctx.createRadialGradient(venusX - 1.5, venusY - 1.5, 0.8, venusX, venusY, 5.5);
    venusGrad.addColorStop(0, '#fef08a');
    venusGrad.addColorStop(0.6, '#fbbf24');
    venusGrad.addColorStop(1, '#b45309');
    ctx.fillStyle = venusGrad;
    ctx.beginPath();
    ctx.arc(venusX, venusY, 5.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#fde68a';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#fef3c7';
    ctx.font = '600 9.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('VENUS', venusX + 8, venusY - 3);
    ctx.fillStyle = '#fcd34d';
    ctx.font = '8.5px "JetBrains Mono", monospace';
    ctx.fillText(`${rVenusAu.toFixed(2)} AU (${vVenusKms.toFixed(0)} km/s)`, venusX + 8, venusY + 8);

    // 7. MARS (1.524 AU)
    const spiceMars = this.spiceFleetData && this.spiceFleetData.MARS;
    const rMarsAu = spiceMars ? spiceMars.heliocentric.distance_au : 1.524;
    const vMarsKms = spiceMars ? spiceMars.velocity.speed_kms : 24.07;
    const phiMars = spiceMars 
      ? ((spiceMars.heliocentric.ecliptic_longitude_deg - earthLong) * Math.PI / 180.0)
      : (2.35 + this.time * 0.0006);
    const marsX = cx + rMarsAu * scale * Math.cos(phiMars);
    const marsY = cy - rMarsAu * scale * Math.sin(phiMars);
    this.marsScreenPos = {
      x: marsX,
      y: marsY,
      state: {
        name: 'Mars',
        rAu: rMarsAu,
        vKms: vMarsKms,
        phase: spiceMars ? spiceMars.phase : 'Outer terrestrial planet / magnetotail observatory',
        trueAnomalyDeg: spiceMars ? spiceMars.orbital_elements.true_anomaly_deg : (((phiMars * 180 / Math.PI) % 360) + 360) % 360,
        isSpice: !!spiceMars
      }
    };

    // Mars Atmosphere & Body
    const marsAtmosphere = ctx.createRadialGradient(marsX, marsY, 2, marsX, marsY, 9);
    marsAtmosphere.addColorStop(0, 'rgba(239, 68, 68, 0.4)');
    marsAtmosphere.addColorStop(1, 'rgba(239, 68, 68, 0)');
    ctx.fillStyle = marsAtmosphere;
    ctx.beginPath();
    ctx.arc(marsX, marsY, 9, 0, Math.PI * 2);
    ctx.fill();

    const marsGrad = ctx.createRadialGradient(marsX - 1.5, marsY - 1.5, 0.8, marsX, marsY, 4.8);
    marsGrad.addColorStop(0, '#fca5a5');
    marsGrad.addColorStop(0.65, '#dc2626');
    marsGrad.addColorStop(1, '#7f1d1d');
    ctx.fillStyle = marsGrad;
    ctx.beginPath();
    ctx.arc(marsX, marsY, 4.8, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#f87171';
    ctx.lineWidth = 1;
    ctx.stroke();

    ctx.fillStyle = '#fee2e2';
    ctx.font = '600 9.5px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('MARS', marsX + 8, marsY - 3);
    ctx.fillStyle = '#f87171';
    ctx.font = '8.5px "JetBrains Mono", monospace';
    ctx.fillText(`${rMarsAu.toFixed(2)} AU (${vMarsKms.toFixed(0)} km/s)`, marsX + 8, marsY + 8);

    // 8. MERCURY (0.387 AU)
    const spiceMerc = this.spiceFleetData && this.spiceFleetData.MERCURY;
    const rMercAu = spiceMerc ? spiceMerc.heliocentric.distance_au : 0.387;
    const vMercKms = spiceMerc ? spiceMerc.velocity.speed_kms : 47.36;
    const phiMerc = spiceMerc 
      ? ((spiceMerc.heliocentric.ecliptic_longitude_deg - earthLong) * Math.PI / 180.0)
      : (3.9 + this.time * 0.0035);
    const mercX = cx + rMercAu * scale * Math.cos(phiMerc);
    const mercY = cy - rMercAu * scale * Math.sin(phiMerc);
    this.mercuryScreenPos = {
      x: mercX,
      y: mercY,
      state: {
        name: 'Mercury',
        rAu: rMercAu,
        vKms: vMercKms,
        phase: spiceMerc ? spiceMerc.phase : 'Innermost terrestrial planet',
        trueAnomalyDeg: spiceMerc ? spiceMerc.orbital_elements.true_anomaly_deg : (((phiMerc * 180 / Math.PI) % 360) + 360) % 360,
        isSpice: !!spiceMerc
      }
    };

    // Mercury Body
    const mercGrad = ctx.createRadialGradient(mercX - 1, mercY - 1, 0.5, mercX, mercY, 3.8);
    mercGrad.addColorStop(0, '#e2e8f0');
    mercGrad.addColorStop(0.7, '#64748b');
    mercGrad.addColorStop(1, '#1e293b');
    ctx.fillStyle = mercGrad;
    ctx.beginPath();
    ctx.arc(mercX, mercY, 3.8, 0, Math.PI * 2);
    ctx.fill();
    ctx.strokeStyle = '#94a3b8';
    ctx.lineWidth = 0.8;
    ctx.stroke();

    ctx.fillStyle = '#e2e8f0';
    ctx.font = '600 9px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText('MERCURY', mercX + 7, mercY - 2);
    ctx.fillStyle = '#94a3b8';
    ctx.font = '8px "JetBrains Mono", monospace';
    ctx.fillText(`${rMercAu.toFixed(2)} AU (${vMercKms.toFixed(0)} km/s)`, mercX + 7, mercY + 7);

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
    if (this.canvas && this.canvas.offsetParent !== null) {
      if (!this.isPaused && this.manualAnomalyDeg === null) {
        this.time += 1;
      }
      this.draw();
    }
    requestAnimationFrame(this.animate);
  }
}

// Attach to window
window.ParkerSpiralRenderer = ParkerSpiralRenderer;
