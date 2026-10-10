/**
 * HELIOS-L1: HIGH-RESOLUTION AURORAL OVAL & GEOMAGNETIC MAP ENGINE
 * Features:
 * - High-detail global continent cartography in Equirectangular projection
 * - Real-time Astronomical Solar Day/Night Terminator & Twilight Shadow Mask
 * - Dual-Hemisphere Dancing Auroral Curtains (557.7 nm Green, 630.0 nm Red, 427.8 nm Violet)
 * - Starkov (1994) auroral oval boundaries from the server, mapped for the current UTC
 * - Global Space Weather Ground Observation Station Network with live MLT
 * - Interactive HUD Telemetry Tooltips & Geomagnetic Coordinate Mapping
 */

class AuroralMapRenderer {
  constructor(canvasId, tooltipId) {
    this.canvas = document.getElementById(canvasId);
    this.tooltip = document.getElementById(tooltipId);
    if (!this.canvas) return;

    this.ctx = this.canvas.getContext('2d');
    this.width = 0;
    this.height = 0;

    // Simulation & Visual State
    this.time = 0;
    // No conditions until the first server answer (the overlay shows n/a, not example values)
    this.kpIndex = null;
    this.imfBz = 0;
    this.hemisphericPower = null; // GW
    this.showNightShadow = true;
    this.showSouthernOval = true;
    this.showStations = true;
    this.showTerminator = true;
    this.showGrid = true;
    this.hoveredStation = null;
    this.mouseGeo = null;

    // North & South Geomagnetic (centred dipole) Poles, IGRF-14 for 2025
    this.magPoleNorth = { lat: 80.8, lon: -72.8 };
    this.magPoleSouth = { lat: -80.8, lon: 107.2 };
    // Starkov (1994) boundaries in geographic coordinates from /api/aurora (null until loaded)
    this.ovalBoundaries = null;

    // Ground Magnetometer & Auroral Observatories
    this.stations = [
      { id: 'TRO', name: 'Tromsø Geophysical Observatory', country: 'Norway', lat: 69.66, lon: 18.94, magLat: 66.8, type: 'Magnetometer & All-Sky Imager' },
      { id: 'PKR', name: 'Poker Flat Research Range', country: 'Alaska, USA', lat: 65.12, lon: -147.48, magLat: 65.4, type: 'Sounding Rockets & LIDAR' },
      { id: 'REK', name: 'Reykjavik Auroral Station', country: 'Iceland', lat: 64.14, lon: -21.94, magLat: 64.9, type: 'Geomagnetic Observatory' },
      { id: 'YEL', name: 'Yellowknife Dark Sky Observatory', country: 'Canada', lat: 62.45, lon: -114.37, magLat: 69.2, type: 'CANOPUS Riometer Array' },
      { id: 'KIR', name: 'Kiruna Space Campus', country: 'Sweden', lat: 67.86, lon: 20.22, magLat: 65.1, type: 'EISCAT Incoherent Scatter' },
      { id: 'SOD', name: 'Sodankylä Geophysical Observatory', country: 'Finland', lat: 67.37, lon: 26.63, magLat: 64.2, type: 'VLF & Ionospheric Radar' },
      { id: 'ABK', name: 'Abisko Scientific Station', country: 'Sweden', lat: 68.35, lon: 18.82, magLat: 65.7, type: 'Aurora Station' },
      { id: 'DUN', name: 'Dunedin Dark Sky Station', country: 'New Zealand', lat: -45.87, lon: 170.50, magLat: -53.2, type: 'Southern Lights Watch' },
      { id: 'SYO', name: 'Syowa Station', country: 'Antarctica (Japan)', lat: -69.00, lon: 39.58, magLat: -70.5, type: 'SuperDARN Radar Array' },
      { id: 'HAL', name: 'Halley VI Research Station', country: 'Antarctica (UK)', lat: -75.58, lon: -26.22, magLat: -66.1, type: 'Geospace Observation' },
      { id: 'SPT', name: 'Amundsen-Scott South Pole', country: 'Antarctica (USA)', lat: -90.00, lon: 0.00, magLat: -74.2, type: 'Cusp Magnetometer' }
    ];

    // High-Resolution World Continents Geo-polygons (Equirectangular lon/lat pairs)
    this.continents = this.initContinentsData();

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

  initEventListeners() {
    window.addEventListener('resize', () => this.resize());

    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const lon = (x / this.width) * 360 - 180;
      const lat = 90 - (y / this.height) * 180;
      this.mouseGeo = { lon, lat, x, y };

      // Station proximity test (radius 10px)
      let foundStation = null;
      for (const st of this.stations) {
        const sx = ((st.lon + 180) / 360) * this.width;
        const sy = ((90 - st.lat) / 180) * this.height;
        const dist = Math.hypot(sx - x, sy - y);
        if (dist <= 12) {
          foundStation = st;
          break;
        }
      }
      this.hoveredStation = foundStation;
      this.updateTooltip(e.clientX, e.clientY);
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.hoveredStation = null;
      this.mouseGeo = null;
      if (this.tooltip) this.tooltip.classList.add('hidden');
    });
  }

  setConditions(kp, bz, power, eqMidnightLat, ovalBoundaries, alUsed, mapTimeUtc) {
    // kp / power are null when the oval comes from OMNI AL for a past time (no Kp used)
    this.kpIndex = (kp === null || kp === undefined) ? null : Math.max(0, Math.min(9, kp));
    this.imfBz = bz ?? null;
    this.hemisphericPower = (power === null || power === undefined) ? null : power;
    this.alUsed = (alUsed === null || alUsed === undefined) ? null : Number(alUsed);
    // Terminator, subsolar point and MLT follow the oval time when a past time was chosen
    this.mapTime = mapTimeUtc ? new Date(String(mapTimeUtc).replace(' ', 'T') + 'Z') : null;
    // Equatorward midnight boundary from the server model, so the map label matches the card
    this.eqMidnightLat = (eqMidnightLat !== undefined && eqMidnightLat !== null) ? Number(eqMidnightLat) : null;
    this.ovalBoundaries = (ovalBoundaries && ovalBoundaries.north) ? ovalBoundaries : null;
  }

  // Converts geographic (lon, lat) to canvas (x, y)
  geoToXY(lon, lat) {
    const x = ((lon + 180) / 360) * this.width;
    const y = ((90 - lat) / 180) * this.height;
    return { x, y };
  }

  // Converts canvas (x, y) to geographic (lon, lat)
  xyToGeo(x, y) {
    const lon = (x / this.width) * 360 - 180;
    const lat = 90 - (y / this.height) * 180;
    return { lon, lat };
  }

  // Calculate Sun subsolar coordinates for current UTC time
  getSubsolarPoint() {
    const now = this.mapTime || new Date();
    const utcHours = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600;
    
    // Subsolar longitude: noon (12:00 UTC) corresponds to 0° longitude
    let sunLon = (12 - utcHours) * 15;
    while (sunLon > 180) sunLon -= 360;
    while (sunLon < -180) sunLon += 360;

    // Subsolar latitude (declination): varies between -23.44° and +23.44°
    const startOfYear = new Date(Date.UTC(now.getUTCFullYear(), 0, 1));
    const dayOfYear = Math.floor((now - startOfYear) / (1000 * 60 * 60 * 24)) + 1;
    const sunLat = -23.44 * Math.cos((2 * Math.PI * (dayOfYear + 10)) / 365.25);

    return { lon: sunLon, lat: sunLat };
  }

  // Compute Solar Zenith Angle for any lat/lon
  getSolarZenith(lon, lat, sun) {
    const deg2rad = Math.PI / 180;
    const latRad = lat * deg2rad;
    const lonRad = lon * deg2rad;
    const sunLatRad = sun.lat * deg2rad;
    const sunLonRad = sun.lon * deg2rad;

    const cosZenith = Math.sin(latRad) * Math.sin(sunLatRad) +
                      Math.cos(latRad) * Math.cos(sunLatRad) * Math.cos(lonRad - sunLonRad);
    return Math.acos(Math.max(-1, Math.min(1, cosZenith))) * (180 / Math.PI);
  }

  // Magnetic Local Time (centred dipole) at a geographic point for the current UTC:
  // MLT = 12 h + (magnetic longitude of the point - magnetic longitude of the Sun) / 15
  getMLT(lon, lat = 65) {
    const d = Math.PI / 180;
    const unit = (la, lo) => [Math.cos(la * d) * Math.cos(lo * d), Math.cos(la * d) * Math.sin(lo * d), Math.sin(la * d)];
    const dot = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const p = unit(this.magPoleNorth.lat, this.magPoleNorth.lon);
    const yNorm = Math.hypot(p[0], p[1]);
    const ym = [-p[1] / yNorm, p[0] / yNorm, 0];  // Z_geo x pole
    const xm = [ym[1] * p[2] - ym[2] * p[1], ym[2] * p[0] - ym[0] * p[2], ym[0] * p[1] - ym[1] * p[0]];
    const sun = this.getSubsolarPoint();
    const mlon = (v) => Math.atan2(dot(v, ym), dot(v, xm)) / d;
    let mlt = (12 + (mlon(unit(lat, lon)) - mlon(unit(sun.lat, sun.lon))) / 15) % 24;
    if (mlt < 0) mlt += 24;
    return mlt;
  }

  // Auroral oval band: Starkov (1994) equatorward boundary west to east, then the poleward
  // boundary back east to west (both from the server). Before the first server answer a
  // schematic Kp ring is drawn around the geomagnetic pole.
  generateAuroralOval(isNorth = true) {
    if (this.ovalBoundaries) {
      const hemi = this.ovalBoundaries[isNorth ? 'north' : 'south'];
      if (hemi && hemi.equatorward && hemi.poleward) {
        return hemi.equatorward.concat(hemi.poleward.slice().reverse());
      }
    }
    const pole = isNorth ? this.magPoleNorth : this.magPoleSouth;
    const kp = this.kpIndex ?? 3.5;
    const bzTerm = this.imfBz < 0 ? Math.abs(this.imfBz) * 0.45 : 0;
    
    // Equatorward expansion driven by Kp and southward Bz
    const radiusBase = 18 + kp * 2.2 + bzTerm; 
    const midnightShift = 4 + kp * 0.6; // Oval is shifted towards magnetic midnight

    const points = [];
    const steps = 72;
    const shimmer = Math.sin(this.time * 0.003) * 0.6;

    for (let i = 0; i <= steps; i++) {
      const angle = (i / steps) * Math.PI * 2;
      const degAngle = (angle * 180) / Math.PI;

      // Elliptical deformation: elongated along day-night meridian
      const dayNightMod = Math.cos(angle) * midnightShift;
      const flutter = Math.sin(angle * 6 + this.time * 0.005) * (0.8 + shimmer);
      const r = radiusBase + dayNightMod + flutter;

      // Angular coordinates around geomagnetic pole
      const pLon = pole.lon + r * Math.cos(angle) * 1.5;
      const pLat = pole.lat + (isNorth ? -r * Math.sin(angle) : r * Math.sin(angle));

      points.push({ lon: pLon, lat: Math.max(-89.9, Math.min(89.9, pLat)) });
    }

    return points;
  }

  draw() {
    this.ctx.clearRect(0, 0, this.width, this.height);

    // 1. Deep Ocean Background with Space Texture
    const oceanGrad = this.ctx.createRadialGradient(
      this.width / 2, this.height / 2, 50,
      this.width / 2, this.height / 2, this.width * 0.75
    );
    oceanGrad.addColorStop(0, '#0a1636');
    oceanGrad.addColorStop(0.6, '#060d24');
    oceanGrad.addColorStop(1, '#020512');
    this.ctx.fillStyle = oceanGrad;
    this.ctx.fillRect(0, 0, this.width, this.height);

    // 2. Equirectangular Graticule Grid
    if (this.showGrid) {
      this.drawGraticule();
    }

    // 3. Render Continents
    this.drawContinents();

    // 4. Solar Day / Night Terminator & Night Shadow Mask
    const sun = this.getSubsolarPoint();
    if (this.showTerminator) {
      this.drawSolarTerminator(sun);
    }

    // 5. Dual Auroral Ovals with Shimmering Plasma Luminescence
    this.drawAuroralOvalLayer(true); // Northern Aurora (Aurora Borealis)
    if (this.showSouthernOval) {
      this.drawAuroralOvalLayer(false); // Southern Aurora (Aurora Australis)
    }

    // 6. Geomagnetic Poles
    this.drawPoles();

    // 7. Ground Observation Network Stations
    if (this.showStations) {
      this.drawStations(sun);
    }

    // 8. Dynamic Telemetry Watermark & HUD Coordinates
    this.drawHUDInfo(sun);
  }

  drawGraticule() {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.12)';
    ctx.lineWidth = 0.8;
    ctx.setLineDash([2, 3]);

    // Parallels (Latitudes)
    [-60, -30, 0, 30, 60].forEach((lat) => {
      const { y } = this.geoToXY(0, lat);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();

      ctx.fillStyle = lat === 0 ? 'rgba(0, 240, 255, 0.7)' : 'rgba(100, 116, 139, 0.6)';
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText(lat === 0 ? 'EQUATOR 0°' : `${Math.abs(lat)}°${lat > 0 ? 'N' : 'S'}`, 8, y - 3);
    });

    // Meridians (Longitudes)
    [-150, -120, -90, -60, -30, 0, 30, 60, 90, 120, 150].forEach((lon) => {
      const { x } = this.geoToXY(lon, 0);
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, this.height);
      ctx.stroke();

      if (lon === 0) {
        ctx.fillStyle = 'rgba(255, 183, 3, 0.7)';
        ctx.font = '9px "JetBrains Mono", monospace';
        ctx.fillText('PRIME MERIDIAN 0°', x + 4, this.height - 8);
      }
    });

    // Arctic / Antarctic Circles (66.5° N / S)
    ctx.strokeStyle = 'rgba(0, 255, 157, 0.22)';
    ctx.setLineDash([4, 4]);
    [66.5, -66.5].forEach(lat => {
      const { y } = this.geoToXY(0, lat);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();
      ctx.fillStyle = 'rgba(0, 255, 157, 0.45)';
      ctx.fillText(lat > 0 ? 'ARCTIC CIRCLE 66.5°N' : 'ANTARCTIC CIRCLE 66.5°S', 8, y - 3);
    });

    ctx.restore();
  }

  drawContinents() {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = 'rgba(17, 30, 62, 0.82)';
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
    ctx.lineWidth = 1.2;
    ctx.shadowColor = 'rgba(56, 189, 248, 0.15)';
    ctx.shadowBlur = 4;

    for (const poly of this.continents) {
      if (poly.length < 3) continue;
      ctx.beginPath();
      poly.forEach((pt, idx) => {
        const { x, y } = this.geoToXY(pt[0], pt[1]);
        if (idx === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
    }
    ctx.restore();
  }

  drawSolarTerminator(sun) {
    const ctx = this.ctx;
    const deg2rad = Math.PI / 180;
    const rad2deg = 180 / Math.PI;
    const delta = sun.lat * deg2rad;

    ctx.save();

    // Calculate twilight terminator polygon
    // For each longitude lambda, zenith = 90° gives:
    // tan(lat) = - cos(lambda - lambda_sun) / tan(delta)
    const points = [];
    const step = 2; // every 2 degrees of longitude
    const tanDelta = Math.tan(delta);

    for (let lon = -180; lon <= 180; lon += step) {
      const lambda = (lon - sun.lon) * deg2rad;
      let termLat;
      if (Math.abs(tanDelta) < 0.001) {
        termLat = (Math.cos(lambda) > 0 ? -90 : 90);
      } else {
        termLat = Math.atan(-Math.cos(lambda) / tanDelta) * rad2deg;
      }
      points.push({ lon, lat: Math.max(-89.9, Math.min(89.9, termLat)) });
    }

    // Build the night mask polygon depending on solar declination hemisphere
    ctx.beginPath();
    if (sun.lat >= 0) {
      // North is illuminated, South has night pole
      ctx.moveTo(0, this.height);
      points.forEach(pt => {
        const { x, y } = this.geoToXY(pt.lon, pt.lat);
        ctx.lineTo(x, y);
      });
      ctx.lineTo(this.width, this.height);
    } else {
      // South is illuminated, North has night pole
      ctx.moveTo(0, 0);
      points.forEach(pt => {
        const { x, y } = this.geoToXY(pt.lon, pt.lat);
        ctx.lineTo(x, y);
      });
      ctx.lineTo(this.width, 0);
    }
    ctx.closePath();

    // Night shadow fill
    ctx.fillStyle = 'rgba(2, 6, 23, 0.62)';
    ctx.fill();

    // Glowing Golden Twilight Boundary Line
    ctx.beginPath();
    points.forEach((pt, idx) => {
      const { x, y } = this.geoToXY(pt.lon, pt.lat);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = 'rgba(255, 183, 3, 0.45)';
    ctx.lineWidth = 1.8;
    ctx.shadowColor = 'rgba(255, 183, 3, 0.6)';
    ctx.shadowBlur = 8;
    ctx.stroke();

    // Subsolar Point Indicator (Day Center)
    const { x: sx, y: sy } = this.geoToXY(sun.lon, sun.lat);
    const sunGrad = ctx.createRadialGradient(sx, sy, 2, sx, sy, 18);
    sunGrad.addColorStop(0, '#fef08a');
    sunGrad.addColorStop(0.3, '#f59e0b');
    sunGrad.addColorStop(1, 'rgba(245, 158, 11, 0)');
    ctx.fillStyle = sunGrad;
    ctx.beginPath();
    ctx.arc(sx, sy, 18, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#fbbf24';
    ctx.beginPath();
    ctx.arc(sx, sy, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#fde68a';
    ctx.font = 'bold 9px "JetBrains Mono", monospace';
    ctx.fillText('SUBSOLAR PT', sx + 10, sy + 3);

    ctx.restore();
  }

  drawAuroralOvalLayer(isNorth) {
    const ctx = this.ctx;
    const oval = this.generateAuroralOval(isNorth);
    if (!oval || oval.length < 3) return;

    ctx.save();

    // Outer Layer: 630.0 nm Atomic Oxygen High-Altitude Red Diffuse Halo
    ctx.beginPath();
    oval.forEach((pt, i) => {
      const { x, y } = this.geoToXY(pt.lon, pt.lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = 'rgba(244, 63, 94, 0.22)';
    ctx.lineWidth = 12;
    ctx.stroke();

    // Mid Layer: 557.7 nm Atomic Oxygen Emerald-Green Main Ionization Curtain
    ctx.beginPath();
    oval.forEach((pt, i) => {
      const { x, y } = this.geoToXY(pt.lon, pt.lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = 'rgba(34, 197, 94, 0.14)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(34, 197, 94, 0.7)';
    ctx.lineWidth = 3.0;
    ctx.stroke();

    // Core Layer: 427.8 nm N2+ Molecular Ion Violet Ribbon
    ctx.beginPath();
    oval.forEach((pt, i) => {
      const { x, y } = this.geoToXY(pt.lon, pt.lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = 'rgba(168, 85, 247, 0.5)';
    ctx.lineWidth = 1.2;
    ctx.stroke();

    // Equatorward edge of the diffuse aurora (Starkov 1994), dashed
    const diffuse = this.ovalBoundaries && this.ovalBoundaries[isNorth ? 'north' : 'south']
      ? this.ovalBoundaries[isNorth ? 'north' : 'south'].diffuse : null;
    if (diffuse && diffuse.length > 1) {
      ctx.beginPath();
      diffuse.forEach((pt, i) => {
        const { x, y } = this.geoToXY(pt.lon, pt.lat);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.setLineDash([4, 4]);
      ctx.strokeStyle = 'rgba(250, 204, 21, 0.6)';
      ctx.lineWidth = 1.2;
      ctx.stroke();
      ctx.setLineDash([]);
    }

    // Pulsing auroral nodes / rays along the oval
    const pulseIndex = Math.floor((this.time * 0.05) % oval.length);
    const pulsePt = oval[pulseIndex];
    if (pulsePt) {
      const { x: px, y: py } = this.geoToXY(pulsePt.lon, pulsePt.lat);
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(px, py, 3, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = 'rgba(0, 255, 157, 0.8)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(px, py, 9, 0, Math.PI * 2);
      ctx.stroke();
    }

    ctx.restore();
  }

  drawPoles() {
    const ctx = this.ctx;
    ctx.save();
    [
      { pole: this.magPoleNorth, label: 'N. MAG POLE', color: '#ff2a6d' },
      { pole: this.magPoleSouth, label: 'S. MAG POLE', color: '#00f0ff' }
    ].forEach(p => {
      const { x, y } = this.geoToXY(p.pole.lon, p.pole.lat);
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();

      ctx.strokeStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.stroke();

      ctx.fillStyle = '#f8fafc';
      ctx.font = 'bold 9px "JetBrains Mono", monospace';
      ctx.fillText(p.label, x + 10, y + 3);
    });
    ctx.restore();
  }

  drawStations(sun) {
    const ctx = this.ctx;
    const pulse = (Math.sin(this.time * 0.08) + 1) / 2;

    this.stations.forEach(st => {
      const { x, y } = this.geoToXY(st.lon, st.lat);
      const zenith = this.getSolarZenith(st.lon, st.lat, sun);
      const isNight = zenith > 96; // Night or Nautical/Astronomical Twilight
      const isCivilTwilight = zenith >= 90 && zenith <= 96;

      const isHovered = this.hoveredStation === st;
      const baseColor = isNight ? '#00ff9d' : isCivilTwilight ? '#ffb703' : '#64748b';

      ctx.save();

      // Radar ping ring
      if (isNight || isHovered) {
        ctx.strokeStyle = isHovered ? '#00f0ff' : baseColor;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(x, y, 5 + pulse * 7, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Center station dot
      ctx.fillStyle = isHovered ? '#ffffff' : baseColor;
      ctx.beginPath();
      ctx.arc(x, y, isHovered ? 4.5 : 3, 0, Math.PI * 2);
      ctx.fill();

      // Label
      if (isHovered || isNight) {
        ctx.fillStyle = isHovered ? '#00f0ff' : '#cbd5e1';
        ctx.font = `${isHovered ? 'bold ' : ''}9px "JetBrains Mono", monospace`;
        ctx.fillText(st.id, x + 7, y - 4);
      }

      ctx.restore();
    });
  }

  drawHUDInfo(sun) {
    const ctx = this.ctx;
    ctx.save();

    // Top-Left Mini HUD
    ctx.fillStyle = 'rgba(7, 14, 34, 0.85)';
    ctx.strokeStyle = 'rgba(56, 189, 248, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(10, 10, 260, 56, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#38bdf8';
    ctx.font = '600 10px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
    ctx.fillText(this.ovalBoundaries ? 'AURORAL OVAL (STARKOV 1994)' : 'AURORAL OVAL (SCHEMATIC, LOADING)', 18, 26);

    ctx.fillStyle = '#94a3b8';
    ctx.font = '9px "JetBrains Mono", monospace';
    const eqMid = this.eqMidnightLat !== null && this.eqMidnightLat !== undefined ? this.eqMidnightLat : null;
    ctx.fillText(`EQUATORWARD MIDNIGHT: ${eqMid === null ? 'n/a' : eqMid.toFixed(1) + '° CGM LAT'}`, 18, 40);
    const kpText = this.kpIndex === null ? 'n/a' : this.kpIndex.toFixed(1);
    const alText = this.alUsed === null || this.alUsed === undefined ? '' : `|AL| ${this.alUsed.toFixed(0)} nT • `;
    ctx.fillText(`${alText}KP: ${kpText} • HPI: ${this.hemisphericPower === null ? 'n/a' : this.hemisphericPower + ' GW'}` +
      (this.mapTime ? ` • ${this.mapTime.toISOString().slice(0, 16).replace('T', ' ')} UTC` : ` • IMF BZ: ${this.imfBz === null ? 'n/a' : this.imfBz.toFixed(1) + ' nT'}`), 18, 54);

    // Bottom-Right Mouse Geo Readout
    if (this.mouseGeo) {
      const mlt = this.getMLT(this.mouseGeo.lon, this.mouseGeo.lat);
      const text = `GEO: ${Math.abs(this.mouseGeo.lat).toFixed(1)}°${this.mouseGeo.lat >= 0 ? 'N' : 'S'}, ${Math.abs(this.mouseGeo.lon).toFixed(1)}°${this.mouseGeo.lon >= 0 ? 'E' : 'W'} | MLT: ${mlt.toFixed(1)}h`;
      ctx.fillStyle = 'rgba(7, 14, 34, 0.85)';
      ctx.beginPath();
      ctx.roundRect(this.width - 280, this.height - 30, 270, 22, 6);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#38bdf8';
      ctx.font = '9px "JetBrains Mono", monospace';
      ctx.fillText(text, this.width - 272, this.height - 15);
    }

    ctx.restore();
  }

  updateTooltip(clientX, clientY) {
    if (!this.tooltip) return;

    if (this.hoveredStation) {
      const st = this.hoveredStation;
      const sun = this.getSubsolarPoint();
      const zenith = this.getSolarZenith(st.lon, st.lat, sun);
      const mlt = this.getMLT(st.lon, st.lat);

      let skyStatus = 'DAYLIGHT (No Optical Sightings)';
      let statusColor = 'text-slate-400';
      if (zenith > 102) {
        skyStatus = 'OPTIMAL DARK NIGHT (High Sighting Likelihood)';
        statusColor = 'text-emerald-400 font-bold';
      } else if (zenith > 90) {
        skyStatus = 'TWILIGHT HORIZON (Visible for Strong Storms)';
        statusColor = 'text-amber-400 font-bold';
      }

      this.tooltip.classList.remove('hidden');
      this.tooltip.innerHTML = `
        <div class="border-b border-sky-500/30 pb-1 mb-1.5 flex items-center justify-between">
          <strong class="text-sky-300 font-bold text-xs">${st.name} [${st.id}]</strong>
          <span class="text-[10px] px-1.5 py-0.5 rounded bg-space-800 text-sky-400 border border-slate-700">${st.country}</span>
        </div>
        <div class="text-[11px] font-mono space-y-0.5 text-slate-200">
          <div>Geographic: <span class="text-amber-300">${st.lat.toFixed(2)}°, ${st.lon.toFixed(2)}°</span></div>
          <div>Geomagnetic Lat: <span class="text-emerald-300">${st.magLat.toFixed(1)}° MLat</span></div>
          <div>Magnetic Local Time: <span class="text-cyan-300">${mlt.toFixed(1)} hrs MLT</span></div>
          <div>Payload: <span class="text-slate-300">${st.type}</span></div>
          <div class="pt-1 mt-1 border-t border-slate-800 ${statusColor}">• ${skyStatus}</div>
        </div>
      `;

      const parentRect = this.canvas.parentElement.getBoundingClientRect();
      const left = clientX - parentRect.left + 15;
      const top = clientY - parentRect.top + 15;
      this.tooltip.style.left = `${Math.min(left, this.width - 290)}px`;
      this.tooltip.style.top = `${Math.min(top, this.height - 140)}px`;
    } else {
      this.tooltip.classList.add('hidden');
    }
  }

  animate() {
    this.time += 1;
    this.draw();
    requestAnimationFrame(this.animate);
  }

  // Cartographic Continental Outlines (Optimized Multi-point Paths)
  initContinentsData() {
    return [
      // North America & Canada & Alaska
      [
        [-168, 65], [-160, 71], [-140, 70], [-125, 69], [-110, 68], [-85, 70], [-78, 62],
        [-65, 58], [-55, 52], [-60, 46], [-66, 44], [-75, 38], [-80, 25], [-82, 23],
        [-97, 26], [-97, 18], [-105, 20], [-115, 30], [-124, 40], [-125, 49], [-135, 58],
        [-142, 60], [-160, 56], [-168, 65]
      ],
      // Greenland
      [
        [-55, 60], [-45, 60], [-25, 65], [-18, 76], [-28, 83], [-55, 82], [-60, 75], [-55, 60]
      ],
      // South America
      [
        [-75, 10], [-60, 8], [-50, -2], [-35, -5], [-37, -12], [-48, -28], [-58, -38],
        [-65, -54], [-75, -52], [-72, -40], [-80, -10], [-80, 5], [-75, 10]
      ],
      // Eurasia (Europe, Russia, Asia)
      [
        [-10, 36], [-5, 43], [-4, 48], [8, 54], [10, 58], [25, 60], [28, 70], [40, 68],
        [60, 72], [80, 73], [105, 76], [130, 72], [160, 70], [175, 66], [170, 60],
        [140, 52], [130, 42], [120, 32], [115, 22], [105, 10], [90, 22], [80, 10],
        [70, 20], [60, 25], [50, 28], [35, 32], [28, 41], [15, 40], [0, 42], [-10, 36]
      ],
      // Scandinavia & Finland
      [
        [5, 58], [12, 57], [18, 56], [22, 60], [30, 70], [25, 71], [18, 69], [12, 64], [5, 62], [5, 58]
      ],
      // British Isles
      [
        [-5, 50], [1, 51], [0, 58], [-5, 58], [-5, 50]
      ],
      // Iceland
      [
        [-24, 63], [-14, 64], [-14, 66], [-24, 66], [-24, 63]
      ],
      // Africa
      [
        [-17, 15], [-5, 36], [10, 37], [32, 31], [42, 12], [50, 10], [40, -5],
        [32, -28], [25, -34], [18, -34], [12, -15], [8, 4], [-15, 10], [-17, 15]
      ],
      // Australia
      [
        [114, -22], [125, -14], [136, -12], [148, -19], [153, -28], [148, -38],
        [138, -35], [125, -34], [115, -34], [114, -22]
      ],
      // New Zealand (North & South)
      [
        [172, -34], [178, -38], [175, -42], [170, -46], [166, -46], [172, -34]
      ],
      // Japan
      [
        [130, 32], [136, 35], [141, 42], [145, 44], [140, 36], [130, 32]
      ],
      // Antarctica
      [
        [-180, -78], [-120, -74], [-60, -64], [0, -68], [60, -66], [120, -66], [160, -72], [180, -78],
        [180, -89], [-180, -89], [-180, -78]
      ]
    ];
  }
}

// Attach to window
window.AuroralMapRenderer = AuroralMapRenderer;
