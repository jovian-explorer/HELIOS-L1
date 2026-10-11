/**
 * HELIOS-L1: radio occultation panel (coronagraph tab): spacecraft-station ray geometry and
 * the coronal plasma effects along it (/api/occultation), and the 180-degree correction of
 * measured polarization angles (/api/occultation/unwrap).
 */

let occChart = null;
let occLastRows = [];

async function initOccultation() {
  const sc = document.getElementById('occ-spacecraft');
  if (!sc) return;
  try {
    const data = await (await fetch('/api/occultation/options')).json();
    sc.innerHTML = Object.entries(data.spacecraft).map(([id, name]) => `<option value="${id}">${name} (${id})</option>`).join('');
    document.getElementById('occ-station').innerHTML = data.stations.map(s => `<option ${s === 'DSS-63' ? 'selected' : ''}>${s}</option>`).join('');
  } catch (err) { /* options stay empty; the request reports the error */ }
}

async function runOccultation() {
  const out = document.getElementById('occ-result');
  const v = id => document.getElementById(id).value;
  out.innerText = 'Computing (the first run downloads about 60 MB of SPICE kernels)...';
  try {
    const res = await fetch('/api/occultation', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spacecraft: v('occ-spacecraft'), spk_url: v('occ-spk') || null, station: v('occ-station'),
        start: v('occ-start'), end: v('occ-end'), step_minutes: parseFloat(v('occ-step')), freq_mhz: parseFloat(v('occ-freq')),
        density_model: v('occ-density'), field_model: v('occ-field'), polarity: parseInt(v('occ-polarity')),
        wind_kms: parseFloat(v('occ-wind')) })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    occLastRows = data.rows;
    const c = data.closest_approach;
    out.innerHTML =
      `<div class="font-semibold text-slate-100">${escapeHtml(data.spacecraft_name)} to ${escapeHtml(data.station)}, ${data.freq_mhz} MHz</div>` +
      (c ? `<div>Closest approach of the ray: ${c.impact_rsun} R☉ (elongation ${c.elongation_deg}°) at ${c.time} UTC, over ` +
        `${c.closest_lon_deg}° IAU_SUN longitude, ${c.closest_lat_deg}° latitude${c.blocked_by_sun ? ' — the ray goes through the Sun (no signal)' : ''}.</div>` : '') +
      `<div>Largest Faraday rotation: ${data.max_abs_faraday_deg ?? 'n/a'}°. Density: ${escapeHtml(data.density_model)}; field: ${escapeHtml(data.field_model)}.</div>` +
      `<div class="text-slate-500">Kernels: ${data.kernels.map(escapeHtml).join(', ')} (spacecraft: ${escapeHtml(data.spacecraft_kernel_source)}).</div>`;
    drawOccultationChart(data.rows);
  } catch (err) {
    out.innerText = `Occultation unavailable: ${err.message}`;
  }
}

function drawOccultationChart(rows) {
  const ctx = document.getElementById('occ-chart')?.getContext('2d');
  if (!ctx) return;
  if (occChart) occChart.destroy();
  const labels = rows.map(r => formatTimestampToTimezone(r.time));
  occChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        { label: 'Impact parameter (R☉)', data: rows.map(r => r.impact_rsun), borderColor: '#38bdf8', yAxisID: 'y', pointRadius: 0 },
        { label: 'Faraday rotation (°)', data: rows.map(r => r.faraday_rotation_deg), borderColor: '#f472b6', yAxisID: 'y1', pointRadius: 0 },
        { label: 'Plasma Doppler (Hz)', data: rows.map(r => r.doppler_plasma_hz), borderColor: '#facc15', yAxisID: 'y1', pointRadius: 0, hidden: true }
      ]
    },
    options: {
      animation: false, responsive: true, maintainAspectRatio: false,
      scales: {
        y: { type: 'logarithmic', title: { display: true, text: 'R☉' }, ticks: { color: '#94a3b8' } },
        y1: { position: 'right', title: { display: true, text: '° / Hz' }, grid: { drawOnChartArea: false }, ticks: { color: '#94a3b8' } },
        x: { ticks: { color: '#94a3b8', maxTicksLimit: 10 } }
      },
      plugins: { legend: { labels: { color: '#cbd5e1' } } }
    }
  });
}

async function unwrapPolarization() {
  const out = document.getElementById('occ-unwrap-result');
  const nums = id => document.getElementById(id).value.split(/[\s,;]+/).filter(Boolean).map(Number);
  const measured = nums('occ-measured');
  const model = document.getElementById('occ-use-model').checked
    ? occLastRows.map(r => r.faraday_rotation_deg).slice(0, measured.length) : null;
  try {
    const res = await fetch('/api/occultation/unwrap', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ measured_deg: measured, model_deg: model && model.length === measured.length ? model : null })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    out.innerText = `Corrected: ${data.corrected_deg.join(', ')} (${data.jumps_removed} jump(s) of 180° removed; ` +
      `shifted by ${data.shift_multiples_of_180} × 180° towards the model).`;
  } catch (err) {
    out.innerText = err.message;
  }
}

document.addEventListener('DOMContentLoaded', initOccultation);
