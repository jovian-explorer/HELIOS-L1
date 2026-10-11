/**
 * HELIOS-L1: solar image archive (coronagraph tab). Images of one instrument over an
 * interval from /api/solar_images (Helioviewer Project), shown frame by frame; science FITS
 * files of the same interval through /api/solar_images/fits (SunPy Fido).
 */

let archiveFrames = [];
let archiveIndex = 0;
let archiveTimer = null;
let archiveMeta = null;

async function initImageArchive() {
  const sel = document.getElementById('ia-instrument');
  if (!sel) return;
  try {
    const res = await fetch('/api/solar_images/sources');
    const data = await res.json();
    sel.innerHTML = data.instruments.map(i =>
      `<option value="${i.key}" ${i.key === 'lasco_c2' ? 'selected' : ''}>${i.label}</option>`).join('');
    document.getElementById('ia-credit').innerText = data.credit +
      (data.fits_available ? '' : ' FITS search needs SunPy (pip install "helios-l1[solar]").');
  } catch (err) {
    document.getElementById('ia-info').innerText = 'Instrument list unavailable.';
  }
}

function imageArchiveQuery() {
  const v = id => document.getElementById(id).value;
  return `instrument=${encodeURIComponent(v('ia-instrument'))}&start=${encodeURIComponent(v('ia-start'))}` +
    `&end=${encodeURIComponent(v('ia-end'))}`;
}

async function loadImageArchive() {
  const info = document.getElementById('ia-info');
  info.innerText = 'Loading the frame list...';
  stopArchivePlay();
  try {
    const n = document.getElementById('ia-n').value || 12;
    const res = await fetch(`/api/solar_images/frames?${imageArchiveQuery()}&n=${n}`);
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    archiveMeta = data;
    archiveFrames = data.frames;
    const slider = document.getElementById('ia-slider');
    slider.max = Math.max(0, archiveFrames.length - 1);
    slider.value = 0;
    if (!archiveFrames.length) {
      info.innerText = `No ${data.label} images in this interval.`;
      return;
    }
    // Load every frame once so that playing does not wait on the network.
    archiveFrames.forEach(f => { const im = new Image(); im.src = f.image_url; });
    showArchiveFrame(0);
  } catch (err) {
    info.innerText = `Images unavailable: ${err.message}`;
  }
}

function showArchiveFrame(i) {
  if (!archiveFrames.length) return;
  archiveIndex = Math.max(0, Math.min(archiveFrames.length - 1, i));
  const f = archiveFrames[archiveIndex];
  const img = document.getElementById('ia-image');
  const diff = document.getElementById('ia-diff')?.checked && archiveIndex > 0;
  img.src = diff
    ? `/api/coronagraph/difference?instrument=${encodeURIComponent(archiveMeta.instrument)}` +
      `&date=${encodeURIComponent(f.date)}&previous=${encodeURIComponent(archiveFrames[archiveIndex - 1].date)}&size=${f.size_px}`
    : f.image_url;
  img.classList.remove('hidden');
  document.getElementById('ia-placeholder').classList.add('hidden');
  document.getElementById('ia-slider').value = archiveIndex;
  document.getElementById('ia-frame-label').innerText = `${f.date} UTC (${archiveIndex + 1}/${archiveFrames.length})`;
  document.getElementById('ia-info').innerHTML =
    `<div class="font-semibold text-slate-100">${archiveMeta.label}</div>` +
    `<div>Image taken ${f.date} UTC</div>` +
    `<div>Field of view ±${archiveMeta.half_width_rsun} R☉, Sun centred; ${f.scale_arcsec_per_px.toFixed(2)}″ per pixel, ` +
    `R☉ = ${f.rsun_arcsec}″ (${f.rsun_px.toFixed(1)} px)</div>` +
    `<div class="text-slate-500">${archiveFrames.length} of ${archiveMeta.requested} requested times gave distinct images in the interval.</div>`;
}

function stopArchivePlay() {
  if (archiveTimer) clearInterval(archiveTimer);
  archiveTimer = null;
  const b = document.getElementById('ia-play');
  if (b) b.innerText = 'Play';
}

function toggleImageArchivePlay() {
  if (archiveTimer) return stopArchivePlay();
  if (archiveFrames.length < 2) return;
  document.getElementById('ia-play').innerText = 'Pause';
  archiveTimer = setInterval(() => showArchiveFrame((archiveIndex + 1) % archiveFrames.length), 600);
}

async function searchArchiveFits(download) {
  const box = document.getElementById('ia-fits');
  box.innerText = download ? `Downloading up to ${download} FITS files...` : 'Searching FITS files...';
  try {
    const res = await fetch(`/api/solar_images/fits?${imageArchiveQuery()}&download=${download}`);
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    const rows = (data.listed || []).slice(0, 8).map(r =>
      `<div class="font-mono text-[10px]">${r['Start Time'] || ''} ${r['Provider'] || ''} ${r['Size'] || ''}</div>`).join('');
    const got = (data.downloaded || []).map(d => `<div class="font-mono text-[10px] text-emerald-300">${d.path}</div>`).join('');
    const errs = (data.download_errors || []).length ? `<div class="text-amber-300">${data.download_errors.length} file(s) failed to download.</div>` : '';
    box.innerHTML = `<div>${data.n_found} FITS file(s) found (${data.searched_with}).</div>${rows}${got}${errs}`;
  } catch (err) {
    box.innerText = err.message;
  }
}

// ---- Height-time map (J-map), front points, fit -------------------------------------
let jmapData = null;
let jmapImage = null;
let trackPoints = [];
let trackFit = null;

async function buildJmap() {
  const out = document.getElementById('jm-result');
  out.innerText = 'Building the J-map (the first time, every frame is fetched)...';
  const v = id => document.getElementById(id).value;
  try {
    const res = await fetch('/api/coronagraph/jmap', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ instrument: v('ia-instrument'), start: v('ia-start'), end: v('ia-end'),
        n: Math.max(3, parseInt(v('ia-n')) || 24), pa_deg: parseFloat(v('jm-pa')), r_min: parseFloat(v('jm-rmin')),
        r_max: parseFloat(v('jm-rmax')), mode: v('jm-mode') })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    jmapData = data;
    trackPoints = [];
    trackFit = null;
    jmapImage = new Image();
    jmapImage.onload = drawJmap;
    jmapImage.src = data.png_data_url;
    out.innerText = `${data.label}, PA ${data.pa_deg}°, ${data.n_frames} frames; automatic track: ${data.auto_track.length} points. ${data.method}.`;
  } catch (err) {
    out.innerText = `J-map unavailable: ${err.message}`;
  }
}

function jmapTimeMs(s) { return Date.parse(String(s).replace(' ', 'T') + 'Z'); }

// Plot geometry: time to the right (one column per frame), height up, inside axis margins.
function jmapAxes(canvas) {
  const m = { l: 46, r: 10, t: 8, b: 26 };
  const w = canvas.width - m.l - m.r, h = canvas.height - m.t - m.b;
  const r = jmapData.r_rsun, t = jmapData.times;
  const nCols = t.length;
  const col = time => t.indexOf(time);
  return {
    m, w, h, r, t, nCols,
    x: time => m.l + (Math.max(0, col(time)) + 0.5) * w / nCols,
    y: rr => m.t + h * (1 - (rr - r[0]) / (r[r.length - 1] - r[0]))
  };
}

function drawJmap() {
  const canvas = document.getElementById('jm-canvas');
  if (!canvas || !jmapData) return;
  canvas.width = canvas.clientWidth;
  canvas.height = canvas.clientHeight;
  const ctx = canvas.getContext('2d');
  const A = jmapAxes(canvas);
  const { m, w, h, r, t } = A;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.imageSmoothingEnabled = false;
  if (jmapImage) ctx.drawImage(jmapImage, m.l, m.t, w, h);
  ctx.fillStyle = '#94a3b8';
  ctx.font = '10px "JetBrains Mono", monospace';
  for (let k = 0; k <= 4; k++) {
    const rr = r[0] + (r[r.length - 1] - r[0]) * k / 4;
    ctx.fillText(rr.toFixed(1), 4, A.y(rr) + 3);
  }
  ctx.fillText('R☉', 4, m.t + 10);
  ctx.fillText(`${t[0].slice(5, 16)} UTC`, m.l, canvas.height - 8);
  ctx.textAlign = 'right';
  ctx.fillText(t[t.length - 1].slice(5, 16), m.l + w, canvas.height - 8);
  ctx.textAlign = 'left';
  const dot = (p, color) => {
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(A.x(p.time), A.y(p.r_rsun), 3.5, 0, 2 * Math.PI);
    ctx.fill();
  };
  jmapData.auto_track.forEach(p => dot(p, 'rgba(250, 204, 21, 0.6)'));
  trackPoints.forEach(p => dot(p, '#22d3ee'));
  if (trackFit) {
    // Fitted curve through the columns of the fitted interval.
    const f = trackFit.fit;
    const te = jmapTimeMs(f.time_end), a = (f.acceleration_ms2 || 0) / 1000;
    ctx.strokeStyle = '#f472b6';
    ctx.beginPath();
    let started = false;
    t.forEach(time => {
      const ms = jmapTimeMs(time);
      if (ms < jmapTimeMs(f.time_start) || ms > te) return;
      const dtSec = (ms - te) / 1000;
      const rr = f.height_end_rsun + (f.speed_kms * dtSec + 0.5 * a * dtSec * dtSec) / 695700;  // IAU 2015 R_sun (constants.py)
      if (!started) { ctx.moveTo(A.x(time), A.y(rr)); started = true; } else ctx.lineTo(A.x(time), A.y(rr));
    });
    ctx.stroke();
  }
  canvas.onclick = ev => {
    const rect = canvas.getBoundingClientRect();
    const px = ev.clientX - rect.left, py = ev.clientY - rect.top;
    if (px < m.l || px > m.l + w || py < m.t || py > m.t + h) return;
    const col = Math.max(0, Math.min(A.nCols - 1, Math.floor((px - m.l) / w * A.nCols)));
    const rr = r[0] + (1 - (py - m.t) / h) * (r[r.length - 1] - r[0]);
    trackPoints = trackPoints.filter(p => p.time !== t[col]).concat([{ time: t[col], r_rsun: Math.round(rr * 1000) / 1000 }]);
    trackPoints.sort((p, q) => jmapTimeMs(p.time) - jmapTimeMs(q.time));
    drawJmap();
  };
}

function useAutoTrack() {
  if (!jmapData) return;
  trackPoints = jmapData.auto_track.slice();
  drawJmap();
}

function clearTrack() {
  trackPoints = [];
  trackFit = null;
  drawJmap();
}

async function fitTrack() {
  const out = document.getElementById('jm-result');
  const v = id => document.getElementById(id).value;
  const num = id => (v(id) === '' ? null : parseFloat(v(id)));
  try {
    const res = await fetch('/api/coronagraph/fit', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ points: trackPoints, order: parseInt(v('jm-order')), instrument: v('ia-instrument'),
        source_lon_deg: num('jm-lon'), source_lat_deg: num('jm-lat') })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    trackFit = data;
    drawJmap();
    const f = data.fit;
    const acc = f.acceleration_ms2 === null ? '' : `, acceleration ${f.acceleration_ms2} ± ${f.acceleration_err_ms2} m/s²`;
    const p = data.projection;
    const proj = !p ? 'No source position given: plane-of-sky speed only.'
      : (p.radial_speed_kms === null ? p.note
        : `Radial speed ${p.radial_speed_kms} km/s (ψ = ${p.psi_deg}° from the line of sight of ${data.observer.spacecraft}; ${p.method}).`);
    out.innerText = `Plane-of-sky speed ${f.speed_kms} ± ${f.speed_err_kms} km/s${acc} from ${f.n_points} points; ` +
      `front at ${f.height_end_rsun} R☉ at ${f.time_end} UTC (RMS residual ${f.rms_residual_rsun} R☉). ${proj}`;
  } catch (err) {
    out.innerText = `Fit failed: ${err.message}`;
  }
}

function sendTrackToSolver() {
  if (!trackFit) {
    document.getElementById('jm-result').innerText = 'Fit the front first.';
    return;
  }
  const s = trackFit.solver_inputs;
  document.getElementById('cme-r1').value = s.r1_rsun;
  document.getElementById('cme-r2').value = s.r2_rsun;
  document.getElementById('cme-dt').value = s.dt_minutes;
  document.getElementById('cme-t2').value = s.launch_time;
  calculateCMEKinematics();
  document.getElementById('cme-r1').scrollIntoView({ behavior: 'smooth', block: 'center' });
}

// ---- Corona to L1 (/api/link/l1) ----------------------------------------------------
let l1Chart = null;

function useSolverForL1() {
  if (!trackFit) {
    document.getElementById('ll-result').innerText = 'Fit a front on the J-map first.';
    return;
  }
  const s = trackFit.solver_inputs;
  document.getElementById('ll-mode').value = 'cme';
  document.getElementById('ll-time').value = s.launch_time;
  document.getElementById('ll-height').value = s.r2_rsun;
  document.getElementById('ll-speed').value = s.speed_kms;
}

async function runL1Link() {
  const out = document.getElementById('ll-result');
  const v = id => document.getElementById(id).value;
  out.innerText = 'Following to L1 and reading the L1 data...';
  try {
    const res = await fetch('/api/link/l1', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode: v('ll-mode'), time: v('ll-time'), height_rsun: parseFloat(v('ll-height')),
        speed_kms: parseFloat(v('ll-speed')), ambient_wind_kms: parseFloat(v('ll-w')),
        gamma_drag: (parseFloat(v('ll-gamma')) || 1.0) * 1e-7, spacecraft: v('ll-sc') })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    const p = data.predicted, sh = data.observed_shock;
    setArrivalMarker('corona-link', p.arrival_l1, `Predicted L1 arrival (corona to L1) ${p.arrival_l1.slice(5, 16)}`);
    out.innerHTML =
      `<div class="font-semibold text-slate-100">Predicted at L1: ${p.arrival_l1} UTC, ${p.speed_l1_kms} km/s (${p.transit_hours} h; ${escapeHtml(p.model)})</div>` +
      (sh ? `<div class="text-sky-300">Observed shock: ${sh.time} UTC at ${sh.spacecraft}, downstream ${sh.downstream_speed_kms ?? '---'} km/s ` +
        `(upstream ${sh.upstream_speed_kms ?? '---'} km/s). Prediction ${data.arrival_error_hours > 0 ? 'late' : 'early'} by ` +
        `${Math.abs(data.arrival_error_hours)} h, speed ${data.speed_error_kms > 0 ? '+' : ''}${data.speed_error_kms ?? '---'} km/s.</div>`
        : `<div class="text-amber-300">No fast forward shock at L1 within ±24 h in the IPShocks database (${escapeHtml(data.shock_catalog_note)}).</div>`) +
      `<div>Measured ${escapeHtml(data.l1_data.spacecraft)} speed within 1 h of the predicted time: ${data.measured_speed_at_predicted_kms ?? '---'} km/s.</div>` +
      `<div class="text-slate-500">${escapeHtml(data.l1_data.provenance.description || '')}</div>`;
    const ctx = document.getElementById('ll-chart')?.getContext('2d');
    if (!ctx) return;
    if (l1Chart) l1Chart.destroy();
    const pts = data.series.filter(s => s.speed !== null).map(s => ({ x: s.hours_from_predicted, y: s.speed }));
    const ys = pts.map(q => q.y);
    const lo = Math.min(...ys, p.speed_l1_kms) - 50, hi = Math.max(...ys, p.speed_l1_kms) + 50;
    const shockX = sh ? (Date.parse(sh.time.replace(' ', 'T') + 'Z') - Date.parse(p.arrival_l1.replace(' ', 'T') + 'Z')) / 3.6e6 : null;
    const datasets = [
      { label: `${data.l1_data.spacecraft} speed (km/s)`, data: pts, borderColor: '#38bdf8', pointRadius: 0, showLine: true },
      { label: 'Predicted arrival and speed', data: [{ x: 0, y: lo }, { x: 0, y: hi }], borderColor: '#f472b6', borderDash: [6, 4], pointRadius: 0, showLine: true },
      { label: 'Predicted speed', data: [{ x: 0, y: p.speed_l1_kms }], borderColor: '#f472b6', backgroundColor: '#f472b6', pointRadius: 5, showLine: false }
    ];
    if (shockX !== null) datasets.push({ label: 'IPShocks shock', data: [{ x: shockX, y: lo }, { x: shockX, y: hi }], borderColor: '#facc15', pointRadius: 0, showLine: true });
    l1Chart = new Chart(ctx, {
      type: 'scatter', data: { datasets },
      options: { animation: false, responsive: true, maintainAspectRatio: false,
        scales: { x: { title: { display: true, text: 'hours from the predicted arrival' }, ticks: { color: '#94a3b8' } },
                  y: { min: lo, max: hi, title: { display: true, text: 'km/s' }, ticks: { color: '#94a3b8' } } },
        plugins: { legend: { labels: { color: '#cbd5e1' } } } }
    });
  } catch (err) {
    out.innerText = `Unavailable: ${err.message}`;
  }
}

window.addEventListener('resize', () => { if (jmapData) drawJmap(); });
document.addEventListener('DOMContentLoaded', initImageArchive);
