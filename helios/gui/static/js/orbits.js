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

    // 6. Earth & Magnetospheric Cavity (Bow Shock & Magnetopause)
    ctx.save();
    const earthP = this.project(0, 0, 0);

    // Dynamic magnetopause standoff calculation based on dynamic pressure
    // Standoff ~ 10.5 * (2.0 / Pdyn)^(1/6.6)
    const rmpRe = 10.5 * Math.pow(2.0 / Math.max(0.6, this.dynamicPressure), 1.0 / 6.6);
    const bowShockX = -Math.min(55, Math.max(22, rmpRe * 3.4));

    // Crisp Bow Shock Front
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.75)';
    ctx.lineWidth = 1.8;
    ctx.beginPath();
    for (let y = -100; y <= 100; y += 4) {
      const x = bowShockX + (y * y) / 190;
      const proj = this.project(x, y, 0);
      if (y === -100) ctx.moveTo(proj.x, proj.y);
      else ctx.lineTo(proj.x, proj.y);
    }
    ctx.stroke();

    // Subtle Magnetopause Boundary
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.25)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    for (let y = -70; y <= 70; y += 4) {
      const x = (bowShockX * 0.72) + (y * y) / 150;
      const proj = this.project(x, y, 0);
      if (y === -70) ctx.moveTo(proj.x, proj.y);
      else ctx.lineTo(proj.x, proj.y);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // Van Allen Radiation Belts (Muted scientific contours)
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

    // Geostationary Orbit (GEO ~ 42k km = 25px radius)
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.35)';
    ctx.lineWidth = 1;
    ctx.setLineDash([3, 4]);
    ctx.beginPath();
    ctx.ellipse(earthP.x, earthP.y, 25, this.viewMode === '3d' ? 16 : 25, 0, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);

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
}
