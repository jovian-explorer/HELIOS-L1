/**
 * HELIOS-L1: HIGH-RESOLUTION AURORAL OVAL & GEOMAGNETIC MAP ENGINE
 * Features:
 * - High-detail global continent cartography in Equirectangular projection
 * - Real-time Astronomical Solar Day/Night Terminator & Twilight Shadow Mask
 * - Auroral oval band of both hemispheres from the server (no oval until it answers)
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
    // NOAA OVATION Prime nowcast (live probability layer); the Starkov oval for past times and offline
    this.ovation = null;
    this.showOvation = true;
    this.mapIsNow = true;
    this.showSouthernOval = true;
    this.showStations = true;
    this.showGrid = true;
    this.hoveredStation = null;
    this.mouseGeo = null;
    // The user's own place ({lat, lon}, set by clicking the map), kept in this browser
    this.home = null;
    try { this.home = JSON.parse(localStorage.getItem('helios-aurora-home')); } catch (e) { /* none */ }

    // North & South Geomagnetic (centred dipole) Poles, IGRF-14 for 2025
    this.magPoleNorth = { lat: 80.8, lon: -72.8 };
    this.magPoleSouth = { lat: -80.8, lon: 107.2 };
    // Starkov (1994) boundaries in geographic coordinates from /api/aurora (null until loaded)
    this.ovalBoundaries = null;

    // Ground Magnetometer & Auroral Observatories
    this.stations = [
      { id: 'TRO', name: 'Tromsø Geophysical Observatory', country: 'Norway', lat: 69.66, lon: 18.94, type: 'Magnetometer & All-Sky Imager' },
      { id: 'PKR', name: 'Poker Flat Research Range', country: 'Alaska, USA', lat: 65.12, lon: -147.48, type: 'Sounding Rockets & LIDAR' },
      { id: 'REK', name: 'Reykjavik Auroral Station', country: 'Iceland', lat: 64.14, lon: -21.94, type: 'Geomagnetic Observatory' },
      { id: 'YEL', name: 'Yellowknife Dark Sky Observatory', country: 'Canada', lat: 62.45, lon: -114.37, type: 'CANOPUS Riometer Array' },
      { id: 'KIR', name: 'Kiruna Space Campus', country: 'Sweden', lat: 67.86, lon: 20.22, type: 'EISCAT Incoherent Scatter' },
      { id: 'SOD', name: 'Sodankylä Geophysical Observatory', country: 'Finland', lat: 67.37, lon: 26.63, type: 'VLF & Ionospheric Radar' },
      { id: 'ABK', name: 'Abisko Scientific Station', country: 'Sweden', lat: 68.35, lon: 18.82, type: 'Aurora Station' },
      { id: 'DUN', name: 'Dunedin Dark Sky Station', country: 'New Zealand', lat: -45.87, lon: 170.50, type: 'Southern Lights Watch' },
      { id: 'SYO', name: 'Syowa Station', country: 'Antarctica (Japan)', lat: -69.00, lon: 39.58, type: 'SuperDARN Radar Array' },
      { id: 'HAL', name: 'Halley VI Research Station', country: 'Antarctica (UK)', lat: -75.58, lon: -26.22, type: 'Geospace Observation' },
      { id: 'SPT', name: 'Amundsen-Scott South Pole', country: 'Antarctica (USA)', lat: -90.00, lon: 0.00, type: 'Cusp Magnetometer' }
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

    this.canvas.addEventListener('click', () => {
      if (this.mouseGeo) this.setHome(this.mouseGeo.lat, this.mouseGeo.lon);
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.hoveredStation = null;
      this.mouseGeo = null;
      if (this.tooltip) this.tooltip.classList.add('hidden');
    });
  }

  setConditions(kp, bz, power, eqMidnightLat, ovalBoundaries, alUsed, mapTimeUtc, stormEdgeLat = null) {
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
    // From Kp 5 the server names Starkov's diffuse boundary as the edge of the precipitation
    // (DMSP: within 0.6 deg at Kp 7-9, the oval boundary 9 deg poleward): it is then the edge
    // drawn first and the one "your place" is measured from.
    this.stormEdgeLat = (stormEdgeLat === null || stormEdgeLat === undefined) ? null : Number(stormEdgeLat);
    this.stormEdge = this.stormEdgeLat !== null && !!this.ovalBoundaries;
    this.showHomeOutlook();
  }

  setHome(lat, lon) {
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90) {
      // An empty or out-of-range entry used to do nothing at all.
      const el = typeof document !== 'undefined' && document.getElementById('aurora-home-note');
      if (el) el.textContent = 'Enter a latitude from -90 to 90 (north positive) and a longitude (east positive), e.g. 51.5 and -0.1 for London.';
      return;
    }
    lon = ((lon + 540) % 360) - 180;
    this.home = { lat, lon };
    try { localStorage.setItem('helios-aurora-home', JSON.stringify(this.home)); } catch (e) { /* not kept */ }
    this.showHomeOutlook();
  }

  // Sky darkness in plain words from the solar zenith angle (deg)
  skyText(zenith) {
    if (zenith > 108) return 'dark night';
    if (zenith > 96) return 'deep twilight (bright aurora can be seen)';
    if (zenith > 90) return 'civil twilight (only very bright aurora)';
    return 'daylight (aurora cannot be seen)';
  }

  // Where the place lies relative to the oval drawn on the map. The equatorward boundary point
  // nearest in magnetic local time is compared in dipole latitude. Aurora 120 km up is 5 deg
  // above the horizon from about 7 deg of latitude away (central angle
  // acos(R cos 5deg / (R + 120 km)) - 5deg), so within 7 deg it may be seen low in the sky.
  homeOutlook() {
    const h = this.home;
    if (!h) return null;
    const sky = this.skyText(this.getSolarZenith(h.lon, h.lat, this.getSubsolarPoint()));
    if (this.ovationLive()) {
      const p = this.ovationAt(h.lat, h.lon);
      const t = String(this.ovation.forecastTime || '').replace('T', ' ').slice(0, 16);
      // Below 10 % the distance to the nearest 10 % cell poleward decides, as for the drawn oval
      // (seen low in the sky from up to ~7 deg away). Every place below 10 % used to read
      // "may still be seen low on the horizon", London at Kp 2 included.
      let where = 'aurora overhead when the sky is dark';
      if (p < 10) {
        const step = h.lat >= 0 ? 1 : -1;
        let edge = null;
        for (let la = Math.round(h.lat) + step; Math.abs(la) <= 90 && edge === null; la += step) {
          if (this.ovationAt(la, h.lon) >= 10) edge = la;
        }
        const gap = edge === null ? null : Math.abs(edge - h.lat);
        const side = h.lat >= 0 ? 'northern' : 'southern';
        where = gap === null ? 'no 10 % region poleward of you: aurora unlikely'
          : `the 10 % region is ${gap.toFixed(0)}° of latitude poleward: ` +
            (gap <= 7 ? `aurora possible low on the ${side} horizon` : 'aurora unlikely');
      }
      return { sky, oval: `NOAA OVATION nowcast for ${t} UTC: ${p} % probability of aurora at your place; ${where}` };
    }
    const hemi = this.ovalBoundaries && this.ovalBoundaries[h.lat >= 0 ? 'north' : 'south'];
    if (!hemi || !hemi.equatorward || !hemi.equatorward.length) return { sky, oval: 'the oval is not loaded yet' };
    const storm = this.stormEdge && hemi.diffuse && hemi.diffuse.length;
    const edgePts = storm ? hemi.diffuse : hemi.equatorward;
    const what = storm ? 'the storm-time edge' : 'the oval';
    const mlt = this.getMLT(h.lon, h.lat);
    let best = null, bestDt = 99;
    for (const pt of edgePts) {
      let dt = Math.abs(this.getMLT(pt.lon, pt.lat) - mlt);
      dt = Math.min(dt, 24 - dt);
      if (dt < bestDt) { bestDt = dt; best = pt; }
    }
    const gap = Math.abs(this.getDipoleLatitude(best.lon, best.lat)) - Math.abs(this.getDipoleLatitude(h.lon, h.lat));
    const side = h.lat >= 0 ? 'northern' : 'southern';
    let oval;
    if (gap <= 0) oval = `inside or poleward of ${what}: aurora overhead when the sky is dark`;
    else if (gap <= 7) oval = `${gap.toFixed(0)}° of latitude from ${what}: aurora possible low on the ${side} horizon`;
    else oval = `${gap.toFixed(0)}° of latitude from ${what}: aurora unlikely`;
    return { sky, oval };
  }

  showHomeOutlook() {
    const el = typeof document !== 'undefined' && document.getElementById('aurora-home-note');
    if (!el) return;
    const o = this.homeOutlook();
    el.textContent = o
      ? `Your place (${this.home.lat.toFixed(1)}°, ${this.home.lon.toFixed(1)}°): sky ${o.sky}; ${o.oval}. ` +
        'Rough guide: the drawn oval can be several degrees off, and clouds and city lights are not included.'
      : 'Click the map, or enter your latitude and longitude, to see whether the aurora may be visible at your place.';
  }

  // Converts geographic (lon, lat) to canvas (x, y)
  // NOAA OVATION Prime nowcast from /api/aurora/ovation: cells [lon 0-359 E, lat, %]
  setOvation(data) {
    if (!data || !Array.isArray(data.cells)) { this.ovation = null; return; }
    const lookup = new Map(data.cells.map(([lo, la, p]) => [`${lo},${la}`, p]));
    this.ovation = { cells: data.cells, lookup, forecastTime: data.forecast_time, observationTime: data.observation_time };
    this.showHomeOutlook();
  }

  // Live: a nowcast for within 3 h, shown while the map is at the present (not a past oval time)
  ovationLive() {
    if (!this.ovation || !this.showOvation || !this.mapIsNow) return false;
    const t = Date.parse(this.ovation.forecastTime);
    return Number.isFinite(t) && Math.abs(Date.now() - t) < 3 * 3600 * 1000;
  }

  ovationAt(lat, lon) {
    if (!this.ovation) return null;
    const key = `${((Math.round(lon) % 360) + 360) % 360},${Math.max(-90, Math.min(90, Math.round(lat)))}`;
    return this.ovation.lookup.get(key) || 0;
  }

  drawOvation() {
    const ctx = this.ctx;
    const w = this.width / 360, h = this.height / 180;
    ctx.save();
    for (const [lo, la, p] of this.ovation.cells) {
      if (p < 3) continue;  // NOAA's map starts its colour scale near here
      const { x, y } = this.geoToXY(lo > 180 ? lo - 360 : lo, la);
      ctx.fillStyle = p >= 50 ? `rgba(215, 126, 126, ${0.35 + 0.5 * p / 100})`
        : `rgba(109, 180, 135, ${0.2 + 0.6 * p / 50})`;
      ctx.fillRect(x - w / 2, y - h / 2, w + 0.5, h + 0.5);
    }
    ctx.restore();
  }

  geoToXY(lon, lat) {
    const x = ((lon + 180) / 360) * this.width;
    const y = ((90 - lat) / 180) * this.height;
    return { x, y };
  }

  // Converts canvas (x, y) to geographic (lon, lat)

  // Calculate Sun subsolar coordinates for current UTC time
  // Subsolar point with the equation of time and the declination of the NOAA solar position
  // formulas (Spencer 1971 series; about 0.1 deg): without the equation of time the subsolar
  // longitude was up to 4 deg off, and the terminator and MLT disagreed with the server's oval.
  // Subsolar point from the low-precision solar ephemeris of Hapgood (1992), the same as the
  // server's helios.core.coordinates.sun_direction_geo (about 0.01 deg; the Spencer series used
  // before was up to 0.44 deg off in latitude).
  getSubsolarPoint() {
    const now = this.mapTime || new Date();
    const d = Math.PI / 180;
    const mjd = now.getTime() / 86400000 + 40587;
    const mjd0 = Math.floor(mjd);
    const hours = (mjd - mjd0) * 24;
    const t0 = (mjd0 - 51544.5) / 36525;
    const eps = (23.439 - 0.013 * t0) * d;
    const m = (357.528 + 35999.050 * t0 + 0.04107 * hours) * d;
    const lam = (280.460 + 36000.772 * t0 + 0.04107 * hours + (1.915 - 0.0048 * t0) * Math.sin(m) + 0.020 * Math.sin(2 * m)) * d;
    const xi = Math.cos(lam), yi = Math.cos(eps) * Math.sin(lam), zi = Math.sin(eps) * Math.sin(lam);
    const theta = (100.461 + 36000.770 * t0 + 15.04107 * hours) * d;
    const x = Math.cos(theta) * xi + Math.sin(theta) * yi, y = -Math.sin(theta) * xi + Math.cos(theta) * yi;
    return { lon: Math.atan2(y, x) / d, lat: Math.asin(Math.max(-1, Math.min(1, zi))) / d };
  }

  // Centred-dipole latitude (the frame the oval is drawn in; corrected geomagnetic latitude,
  // in which Starkov's boundaries are given, differs from it by up to about 5 deg).
  getDipoleLatitude(lon, lat) {
    const d = Math.PI / 180;
    const p = this.magPoleNorth;
    const c = Math.sin(lat * d) * Math.sin(p.lat * d) + Math.cos(lat * d) * Math.cos(p.lat * d) * Math.cos((lon - p.lon) * d);
    return Math.asin(Math.max(-1, Math.min(1, c))) / d;
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
  // boundary back east to west (both from the server); nothing until it has answered.
  generateAuroralOval(isNorth = true) {
    if (this.ovalBoundaries) {
      const hemi = this.ovalBoundaries[isNorth ? 'north' : 'south'];
      if (hemi && hemi.equatorward && hemi.poleward) {
        return hemi.equatorward.concat(hemi.poleward.slice().reverse());
      }
    }
    return null;  // no invented ring before the server's oval arrives
  }

  draw() {
    this.ctx.clearRect(0, 0, this.width, this.height);

    // 1. Deep Ocean Background with Space Texture
    const oceanGrad = this.ctx.createRadialGradient(
      this.width / 2, this.height / 2, 50,
      this.width / 2, this.height / 2, this.width * 0.75
    );
    oceanGrad.addColorStop(0, '#141518');
    oceanGrad.addColorStop(0.6, '#141518');
    oceanGrad.addColorStop(1, '#141518');
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
    if (this.showNightShadow) {  // the Night Shadow checkbox (it set a flag nothing read)
      this.drawSolarTerminator(sun);
    }

    // 5. Dual Auroral Ovals with Shimmering Plasma Luminescence
    if (this.ovationLive()) {
      this.drawOvation();  // NOAA's live probability in place of the Starkov band
    } else {
      this.drawAuroralOvalLayer(true); // Northern Aurora (Aurora Borealis)
      if (this.showSouthernOval) this.drawAuroralOvalLayer(false); // Southern Aurora (Aurora Australis)
    }

    // 6. Geomagnetic Poles
    this.drawPoles();

    // 7. Ground Observation Network Stations
    if (this.showStations) {
      this.drawStations(sun);
    }

    if (this.home) {
      const { x, y } = this.geoToXY(this.home.lon, this.home.lat);
      this.ctx.save();
      this.ctx.strokeStyle = '#d2aa57';
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.arc(x, y, 6, 0, Math.PI * 2);
      this.ctx.stroke();
      this.ctx.fillStyle = '#d2aa57';
      this.ctx.font = 'bold 9px system-ui, sans-serif';
      this.ctx.fillText('You', x + 8, y + 3);
      this.ctx.restore();
    }

    // 8. Dynamic Telemetry Watermark & HUD Coordinates
    this.drawHUDInfo(sun);
  }

  drawGraticule() {
    const ctx = this.ctx;
    ctx.save();
    ctx.strokeStyle = 'rgba(127, 165, 207, 0.12)';
    ctx.lineWidth = 0.8;
    ctx.setLineDash([2, 3]);

    // Parallels (Latitudes)
    [-60, -30, 0, 30, 60].forEach((lat) => {
      const { y } = this.geoToXY(0, lat);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();

      ctx.fillStyle = lat === 0 ? 'rgba(127, 165, 207, 0.7)' : 'rgba(131, 135, 143, 0.6)';
      ctx.font = '9px system-ui, sans-serif';
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
        ctx.fillStyle = 'rgba(210, 170, 87, 0.7)';
        ctx.font = '9px system-ui, sans-serif';
        ctx.fillText('Prime meridian 0°', x + 4, this.height - 8);
      }
    });

    // Arctic / Antarctic Circles (66.5° N / S)
    ctx.strokeStyle = 'rgba(109, 180, 135, 0.22)';
    ctx.setLineDash([4, 4]);
    [66.5, -66.5].forEach(lat => {
      const { y } = this.geoToXY(0, lat);
      ctx.beginPath();
      ctx.moveTo(0, y);
      ctx.lineTo(this.width, y);
      ctx.stroke();
      ctx.fillStyle = 'rgba(109, 180, 135, 0.45)';
      ctx.fillText(lat > 0 ? 'Arctic Circle 66.5°N' : 'Antarctic Circle 66.5°S', 8, y - 3);
    });

    ctx.restore();
  }

  drawContinents() {
    const ctx = this.ctx;
    ctx.save();
    ctx.fillStyle = 'rgba(17, 30, 62, 0.82)';
    ctx.strokeStyle = 'rgba(127, 165, 207, 0.35)';
    ctx.lineWidth = 1.2;
    ctx.shadowColor = 'rgba(127, 165, 207, 0.15)';
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
    ctx.fillStyle = 'rgba(20, 21, 24, 0.62)';
    ctx.fill();

    // Glowing Golden Twilight Boundary Line
    ctx.beginPath();
    points.forEach((pt, idx) => {
      const { x, y } = this.geoToXY(pt.lon, pt.lat);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = 'rgba(210, 170, 87, 0.45)';
    ctx.lineWidth = 1.8;
    ctx.shadowColor = 'rgba(210, 170, 87, 0.6)';
    ctx.shadowBlur = 8;
    ctx.stroke();

    // Subsolar Point Indicator (Day Center)
    const { x: sx, y: sy } = this.geoToXY(sun.lon, sun.lat);
    const sunGrad = ctx.createRadialGradient(sx, sy, 2, sx, sy, 18);
    sunGrad.addColorStop(0, '#ebd6a2');
    sunGrad.addColorStop(0.3, '#b98f3f');
    sunGrad.addColorStop(1, 'rgba(185, 143, 63, 0)');
    ctx.fillStyle = sunGrad;
    ctx.beginPath();
    ctx.arc(sx, sy, 18, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#d2aa57';
    ctx.beginPath();
    ctx.arc(sx, sy, 4, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = '#ebd6a2';
    ctx.font = 'bold 9px system-ui, sans-serif';
    ctx.fillText('Subsolar point', sx + 10, sy + 3);

    ctx.restore();
  }

  drawAuroralOvalLayer(isNorth) {
    const ctx = this.ctx;
    const oval = this.generateAuroralOval(isNorth);
    if (!oval || oval.length < 3) return;

    ctx.save();

    // The oval band between the equatorward and poleward boundaries
    ctx.beginPath();
    oval.forEach((pt, i) => {
      const { x, y } = this.geoToXY(pt.lon, pt.lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.fillStyle = 'rgba(82, 155, 110, 0.14)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(82, 155, 110, 0.7)';
    ctx.lineWidth = 3.0;
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
      // Storm-time edge (Kp 5 and above): solid and bold; otherwise a thin dashed line
      if (this.stormEdge) {
        ctx.strokeStyle = 'rgba(223, 192, 120, 0.95)';
        ctx.lineWidth = 2.6;
      } else {
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(210, 170, 87, 0.6)';
        ctx.lineWidth = 1.2;
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }

    ctx.restore();
  }

  drawPoles() {
    const ctx = this.ctx;
    ctx.save();
    [
      { pole: this.magPoleNorth, label: 'N. MAG POLE', color: '#d77e7e' },
      { pole: this.magPoleSouth, label: 'S. MAG POLE', color: '#7fa5cf' }
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

      ctx.fillStyle = '#f6f7f8';
      ctx.font = 'bold 9px system-ui, sans-serif';
      ctx.fillText(p.label, x + 10, y + 3);
    });
    ctx.restore();
  }

  drawStations(sun) {
    const ctx = this.ctx;

    this.stations.forEach(st => {
      const { x, y } = this.geoToXY(st.lon, st.lat);
      const zenith = this.getSolarZenith(st.lon, st.lat, sun);
      const isNight = zenith > 96; // Night or Nautical/Astronomical Twilight
      const isCivilTwilight = zenith >= 90 && zenith <= 96;

      const isHovered = this.hoveredStation === st;
      const baseColor = isNight ? '#6db487' : isCivilTwilight ? '#d2aa57' : '#83878f';

      ctx.save();

      // Radar ping ring
      if (isNight || isHovered) {
        ctx.strokeStyle = isHovered ? '#7fa5cf' : baseColor;
        ctx.lineWidth = 1.2;
        ctx.beginPath();
        ctx.arc(x, y, 9, 0, Math.PI * 2);
        ctx.stroke();
      }

      // Center station dot
      ctx.fillStyle = isHovered ? '#ffffff' : baseColor;
      ctx.beginPath();
      ctx.arc(x, y, isHovered ? 4.5 : 3, 0, Math.PI * 2);
      ctx.fill();

      // Label
      if (isHovered || isNight) {
        ctx.fillStyle = isHovered ? '#7fa5cf' : '#b9bcc1';
        ctx.font = `${isHovered ? 'bold ' : ''}9px system-ui, sans-serif`;
        ctx.fillText(st.id, x + 7, y - 4);
      }

      ctx.restore();
    });
  }

  drawHUDInfo(sun) {
    const ctx = this.ctx;
    ctx.save();

    // Top-Left Mini HUD
    ctx.fillStyle = 'rgba(20, 21, 24, 0.85)';
    ctx.strokeStyle = 'rgba(127, 165, 207, 0.3)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(10, 10, 320, this.stormEdge && !this.ovationLive() ? 70 : 56, 8);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = '#7fa5cf';
    ctx.font = '600 10px system-ui, sans-serif';
    const live = this.ovationLive();
    ctx.fillText(live ? `NOAA OVATION Prime nowcast for ${String(this.ovation.forecastTime).replace('T', ' ').slice(0, 16)} UTC`
      : (this.ovalBoundaries ? 'Auroral oval (Starkov 1994)' : 'Auroral oval: loading'), 18, 26);

    ctx.fillStyle = '#9a9ea5';
    ctx.font = '9px system-ui, sans-serif';
    const eqMid = this.eqMidnightLat !== null && this.eqMidnightLat !== undefined ? this.eqMidnightLat : null;
    if (live) ctx.fillText('Probability of visible aurora: green 3-50 %, red above 50 %', 18, 40);
    else ctx.fillText(this.stormEdge
      ? `Storm-time edge (diffuse boundary) at midnight: ${this.stormEdgeLat.toFixed(1)}° CGM; oval ${eqMid === null ? 'n/a' : eqMid.toFixed(1) + '°'}`
      : `Equatorward midnight: ${eqMid === null ? 'n/a' : eqMid.toFixed(1) + '° CGM'}`, 18, 40);
    const kpText = this.kpIndex === null ? 'n/a' : this.kpIndex.toFixed(1);
    const alText = this.alUsed === null || this.alUsed === undefined ? '' : `|AL| ${this.alUsed.toFixed(0)} nT • `;
    ctx.fillText(`${alText}Kp ${kpText} • HPI ${this.hemisphericPower === null ? 'n/a' : this.hemisphericPower + ' GW'}` +
      (this.mapTime ? ` • ${this.mapTime.toISOString().slice(0, 16).replace('T', ' ')} UTC` : ` • IMF Bz ${this.imfBz === null ? 'n/a' : this.imfBz.toFixed(1) + ' nT'}`), 18, 54);
    if (this.stormEdge && !live) {  // legend of the storm-time edge
      ctx.strokeStyle = 'rgba(223, 192, 120, 0.95)';
      ctx.lineWidth = 2.6;
      ctx.beginPath(); ctx.moveTo(18, 64); ctx.lineTo(40, 64); ctx.stroke();
      ctx.fillStyle = '#dfc078';
      ctx.fillText('storm-time edge of the aurora (green band: oval)', 46, 67);
    }

    // Bottom-Right Mouse Geo Readout
    if (this.mouseGeo) {
      const mlt = this.getMLT(this.mouseGeo.lon, this.mouseGeo.lat);
      const text = `GEO: ${Math.abs(this.mouseGeo.lat).toFixed(1)}°${this.mouseGeo.lat >= 0 ? 'N' : 'S'}, ${Math.abs(this.mouseGeo.lon).toFixed(1)}°${this.mouseGeo.lon >= 0 ? 'E' : 'W'} | MLT: ${mlt.toFixed(1)}h`;
      ctx.fillStyle = 'rgba(20, 21, 24, 0.85)';
      ctx.beginPath();
      ctx.roundRect(this.width - 280, this.height - 30, 270, 22, 6);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = '#7fa5cf';
      ctx.font = '9px system-ui, sans-serif';
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

      // The sky only: whether aurora is there depends on the oval drawn on the map.
      let skyStatus = 'DAYLIGHT (no optical aurora)';
      let statusColor = 'text-slate-400';
      if (zenith > 108) {
        skyStatus = 'DARK NIGHT (Sun more than 18° below the horizon)';
        statusColor = 'text-emerald-400 font-bold';
      } else if (zenith > 96) {
        skyStatus = 'NAUTICAL OR ASTRONOMICAL TWILIGHT (bright aurora visible)';
        statusColor = 'text-amber-400 font-bold';
      } else if (zenith > 90) {
        skyStatus = 'CIVIL TWILIGHT (only very bright aurora)';
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
          <div>Dipole latitude: <span class="text-emerald-300">${this.getDipoleLatitude(st.lon, st.lat).toFixed(1)}°</span> <span class="text-slate-500">(CGM within ~5°)</span></div>
          <div>Magnetic Local Time: <span class="text-cyan-300">${mlt.toFixed(1)} h MLT</span></div>
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
