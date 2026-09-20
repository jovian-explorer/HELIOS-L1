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

    this.timeStep = 0;
    this.orbitsData = null;
    this.lagrangeData = null;
    this.hoveredItem = null;

    this.initStars();
    this.initParticles();
    this.initEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
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
      this.particles.push({
        x: Math.random() * 850 - 680,
        y: (Math.random() - 0.5) * 420,
        z: (Math.random() - 0.5) * 80,
        speed: 1.5 + Math.random() * 2.2,
        size: 1.0 + Math.random() * 1.5,
        alpha: 0.2 + Math.random() * 0.7
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

  setSolarWindConditions(speed, pdyn) {
    if (speed) this.solarWindSpeed = speed;
    if (pdyn) this.dynamicPressure = pdyn;
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

    this.hoveredItem = found;

    if (found && this.tooltip) {
      this.tooltip.classList.remove('hidden');
      this.tooltip.style.left = `${mouseX + 16}px`;
      this.tooltip.style.top = `${mouseY + 16}px`;

      if (found.type === 'sat') {
        const s = found.data;
        this.tooltip.innerHTML = `
          <div class="flex items-center space-x-2 border-b border-sky-500/30 pb-1 mb-1">
            <span class="w-2 h-2 rounded-full" style="background:${s.color}"></span>
            <strong class="text-sky-300 font-bold">${s.name}</strong>
          </div>
          <div class="text-slate-300 text-[11px]">${s.type}</div>
          <div class="text-slate-400 text-[10px] mt-1 font-mono">
            X: ${s.current_pos.x.toLocaleString()} km<br>
            Y: ${s.current_pos.y.toLocaleString()} km<br>
            Z: ${(s.current_pos.z || 0).toLocaleString()} km
          </div>
        `;
      } else if (found.type === 'earth') {
        this.tooltip.innerHTML = `
          <div class="font-bold text-blue-400 border-b border-blue-500/30 pb-1 mb-1">Earth (Terra)</div>
          <div class="text-slate-300 text-[11px]">Radius: ~6,371 km • 1.0 AU from Sun</div>
          <div class="text-emerald-400 text-[10px] mt-1">Dipole Magnetosphere Standoff: ~${(10.5 * (2.0 / Math.max(0.8, this.dynamicPressure))**(1/6)).toFixed(1)} R_E</div>
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

    // 4. Draw Animated Solar Wind Streamflow Particles
    const animToggle = document.getElementById('orbit-anim-toggle');
    const isAnim = animToggle ? animToggle.checked : true;
    if (isAnim) {
      const speedMultiplier = (this.solarWindSpeed / 400.0) * 1.2;
      for (const p of this.particles) {
        p.x += p.speed * speedMultiplier;
        if (p.x > 80) {
          p.x = -680;
          p.y = (Math.random() - 0.5) * 420;
        }

        // Plasma deflection around Earth's magnetopause (~ -35px)
        let drawY = p.y;
        if (p.x > -80 && p.x < 20 && Math.abs(p.y) < 90) {
          const deflection = (90 - Math.abs(p.y)) * 0.35 * Math.sign(p.y || 1);
          drawY += deflection;
        }

        const proj = this.project(p.x, drawY, p.z);
        ctx.beginPath();
        ctx.arc(proj.x, proj.y, p.size, 0, Math.PI * 2);

        // Gradient from solar gold near sun to energetic cyan at Earth
        const progress = Math.min(1, Math.max(0, (p.x + 600) / 600));
        ctx.fillStyle = progress < 0.4 ? `rgba(251, 191, 36, ${p.alpha * 0.7})` : `rgba(56, 189, 248, ${p.alpha * 0.8})`;
        ctx.fill();
      }
    }

    // 5. Sun Core and Multi-Layer Radiant Corona
    ctx.save();
    const sunPos = this.project(-580, 0, 0);

    // Multi-layer corona radial glow
    const coronaGlow = ctx.createRadialGradient(sunPos.x, sunPos.y, 20, sunPos.x, sunPos.y, 180);
    coronaGlow.addColorStop(0, 'rgba(251, 191, 36, 0.95)');
    coronaGlow.addColorStop(0.2, 'rgba(245, 158, 11, 0.6)');
    coronaGlow.addColorStop(0.5, 'rgba(239, 68, 68, 0.25)');
    coronaGlow.addColorStop(1, 'rgba(245, 158, 11, 0)');
    ctx.fillStyle = coronaGlow;
    ctx.beginPath();
    ctx.arc(sunPos.x, sunPos.y, 180, 0, Math.PI * 2);
    ctx.fill();

    // Prominence plasma arcs
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.4)';
    ctx.lineWidth = 2;
    for (let a = 0; a < 6; a++) {
      const angle = this.timeStep * 0.3 + (a * Math.PI / 3);
      ctx.beginPath();
      ctx.arc(sunPos.x, sunPos.y, 42 + 8 * Math.sin(this.timeStep + a), angle, angle + 0.4);
      ctx.stroke();
    }

    // Solid Sun Core
    const sunCore = ctx.createRadialGradient(sunPos.x - 5, sunPos.y - 5, 4, sunPos.x, sunPos.y, 35);
    sunCore.addColorStop(0, '#ffffff');
    sunCore.addColorStop(0.4, '#fde047');
    sunCore.addColorStop(0.85, '#f59e0b');
    sunCore.addColorStop(1, '#b45309');
    ctx.fillStyle = sunCore;
    ctx.beginPath();
    ctx.arc(sunPos.x, sunPos.y, 34, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#fef08a';
    ctx.font = 'bold 11px "Chakra Petch", sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('SUN (1.0 AU)', sunPos.x, sunPos.y + 52);

    // Sun-Earth Interplanetary Axis line
    ctx.strokeStyle = 'rgba(251, 191, 36, 0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(sunPos.x, sunPos.y);
    const earthCenter = this.project(0, 0, 0);
    ctx.lineTo(earthCenter.x, earthCenter.y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.restore();

    // 6. Earth & Magnetospheric Cavity (Bow Shock & Magnetopause)
    ctx.save();
    const earthP = this.project(0, 0, 0);

    // Dynamic magnetopause standoff calculation based on dynamic pressure
    // Standoff ~ 10.5 * (2.0 / Pdyn)^(1/6.6)
    const rmpRe = 10.5 * Math.pow(2.0 / Math.max(0.6, this.dynamicPressure), 1.0 / 6.6);
    const bowShockX = -Math.min(55, Math.max(22, rmpRe * 3.4));

    // Glowing Bow Shock Wave
    ctx.strokeStyle = 'rgba(0, 240, 255, 0.7)';
    ctx.lineWidth = 2.2;
    ctx.shadowColor = 'rgba(0, 240, 255, 0.8)';
    ctx.shadowBlur = 10;
    ctx.beginPath();
    for (let y = -110; y <= 110; y += 4) {
      const x = bowShockX + (y * y) / 190;
      const proj = this.project(x, y, 0);
      if (y === -110) ctx.moveTo(proj.x, proj.y);
      else ctx.lineTo(proj.x, proj.y);
    }
    ctx.stroke();
    ctx.shadowBlur = 0;

    // Van Allen Radiation Belts (glowing magenta toroidal lobes)
    ctx.fillStyle = 'rgba(192, 132, 252, 0.18)';
    ctx.strokeStyle = 'rgba(192, 132, 252, 0.45)';
    ctx.lineWidth = 1;
    for (const side of [-1, 1]) {
      ctx.beginPath();
      const beltP = this.project(0, side * 22, 0);
      ctx.ellipse(beltP.x, beltP.y, 10, 18, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.stroke();
    }

    // Geostationary Orbit (GEO ~ 42k km = 25px radius)
    ctx.strokeStyle = 'rgba(236, 72, 153, 0.4)';
    ctx.lineWidth = 1.2;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.ellipse(earthP.x, earthP.y, 25, this.viewMode === '3d' ? 16 : 25, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

    // Earth Sphere with Atmosphere Glow
    const earthGlow = ctx.createRadialGradient(earthP.x, earthP.y, 8, earthP.x, earthP.y, 20);
    earthGlow.addColorStop(0, 'rgba(56, 189, 248, 0.8)');
    earthGlow.addColorStop(0.6, 'rgba(37, 99, 235, 0.3)');
    earthGlow.addColorStop(1, 'rgba(30, 58, 138, 0)');
    ctx.fillStyle = earthGlow;
    ctx.beginPath();
    ctx.arc(earthP.x, earthP.y, 20, 0, Math.PI * 2);
    ctx.fill();

    const earthGrad = ctx.createRadialGradient(earthP.x - 3, earthP.y - 3, 2, earthP.x, earthP.y, 11);
    earthGrad.addColorStop(0, '#93c5fd');
    earthGrad.addColorStop(0.45, '#2563eb');
    earthGrad.addColorStop(0.85, '#1e3a8a');
    earthGrad.addColorStop(1, '#0f172a');
    ctx.fillStyle = earthGrad;
    ctx.beginPath();
    ctx.arc(earthP.x, earthP.y, 11, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = '#60a5fa';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    ctx.fillStyle = '#93c5fd';
    ctx.font = 'bold 10px "Chakra Petch", sans-serif';
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

      // Pulsing diamond marker
      ctx.strokeStyle = lp.color;
      ctx.lineWidth = 1.5;
      ctx.shadowColor = lp.color;
      ctx.shadowBlur = 8;

      ctx.beginPath();
      const s = 7 + 2 * Math.sin(this.timeStep * 3);
      ctx.moveTo(proj.x, proj.y - s);
      ctx.lineTo(proj.x + s, proj.y);
      ctx.lineTo(proj.x, proj.y + s);
      ctx.lineTo(proj.x - s, proj.y);
      ctx.closePath();
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.fillStyle = lp.color;
      ctx.font = 'bold 10px "Chakra Petch", sans-serif';
      ctx.textAlign = 'center';
      ctx.fillText(lp.id, proj.x, proj.y - 12);
    }
    ctx.restore();

    // 8. Spacecraft Orbits and Fleet Rendering
    if (this.orbitsData) {
      for (const [key, sat] of Object.entries(this.orbitsData)) {
        if (!sat.path || sat.path.length === 0) continue;

        ctx.save();
        const satColor = sat.color || '#38bdf8';
        ctx.strokeStyle = satColor;
        ctx.lineWidth = 1.4;
        ctx.globalAlpha = 0.65;

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

        // Current Satellite Bead with Pulsing Beacon
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

          // Outer pulsing ping
          ctx.globalAlpha = 0.4 + 0.4 * Math.sin(this.timeStep * 4);
          ctx.strokeStyle = satColor;
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.arc(proj.x, proj.y, 8 + 3 * Math.sin(this.timeStep * 4), 0, Math.PI * 2);
          ctx.stroke();

          // Satellite Body Dot
          ctx.globalAlpha = 1.0;
          ctx.fillStyle = satColor;
          ctx.shadowColor = satColor;
          ctx.shadowBlur = 10;
          ctx.beginPath();
          ctx.arc(proj.x, proj.y, 5, 0, Math.PI * 2);
          ctx.fill();
          ctx.shadowBlur = 0;

          ctx.strokeStyle = '#ffffff';
          ctx.lineWidth = 1.2;
          ctx.stroke();

          // High-Tech Callout Tag
          ctx.fillStyle = '#f8fafc';
          ctx.font = 'bold 9.5px "Chakra Petch", sans-serif';
          ctx.textAlign = 'left';
          ctx.fillText(sat.name, proj.x + 9, proj.y + 3);
        }

        ctx.restore();
      }
    }

    ctx.restore();
  }
}
