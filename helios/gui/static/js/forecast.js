/**
 * HELIOS-L1: MAGNETOSPHERIC COUPLING & STORM TRAJECTORY CONTROLLER
 * Features:
 * - Newell Solar Wind Magnetosphere Coupling Function Monitor
 * - O'Brien & McPherron (2000) ring current Dst trajectory, started from observed Kyoto Dst
 * - 12 h Newell et al. (2008) Kp trajectory with the Kp range of the last 3 h, and NOAA SWPC's Kp forecast
 * - NOAA SWPC storm probabilities for the next UTC day (G1, G2, G3-G5)
 * - Critical Infrastructure Hazard Advisories (GIC, Aviation, Satellites)
 */

let chartMLForecast = null;

async function loadMLForecast() {
  const satSelect = document.getElementById('forecast-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  const current = latestRequest('forecast');

  try {
    const res = await fetch(`/api/forecast/ml?mission_id=${sat}`);
    const data = await res.json().catch(() => ({}));
    if (!current()) return;
    if (!res.ok) throw new Error(apiErrorText(data, res));

    // 1. Current Coupling & Indicators
    const c = data.current_coupling;
    const newellEl = document.getElementById('forecast-newell-val');
    const newellStateEl = document.getElementById('forecast-newell-state');
    const dstEstEl = document.getElementById('forecast-dst-val');

    // The unit was only in a tooltip; dΦ/dt has no common unit, so it is shown with the value.
    if (newellEl) newellEl.innerHTML = `${escapeHtml(c.newell_coupling_rate.toLocaleString())}` +
      (c.newell_units ? ` <span class="text-[10px] font-mono font-normal text-slate-400">${escapeHtml(c.newell_units)}</span>` : '');
    if (newellStateEl) newellStateEl.innerText = `${c.coupling_state}` + (c.newell_kp_now !== null && c.newell_kp_now !== undefined ? ` • Newell Kp ${c.newell_kp_now}` : '');
    if (dstEstEl) dstEstEl.innerText = `${c.estimated_dst_nt} nT`;
    const dstSrcEl = document.getElementById('forecast-dst-source');
    if (dstSrcEl && c.dst_source) dstSrcEl.innerText = c.dst_source;

    // 2. Storm Scale Probabilities
    const probs = data.storm_probabilities;
    setGaugeValue('gauge-g1', probs.minor_storm_g1_percent);
    setGaugeValue('gauge-g3', probs.moderate_storm_g2_percent);
    setGaugeValue('gauge-g5', probs.strong_extreme_storm_g3_g5_percent);
    const gSrc = document.getElementById('gauge-source');
    if (gSrc) gSrc.innerText = probs.day ? `NOAA SWPC forecast for ${probs.day} (issued ${probs.issued})` : probs.source;
    const notes = document.getElementById('forecast-assumptions');
    if (notes) notes.innerHTML = (data.assumptions || []).map(a => `<div>• ${a}</div>`).join('');

    // 3. Hazard Assessment Cards
    const h = data.hazard_assessment;
    updateHazardCard('hazard-gic', h.power_grid_gic);
    updateHazardCard('hazard-aviation', h.aviation_hf);
    updateHazardCard('hazard-satellite', h.satellite_ops);

    // 4. Render 12-Hour Forecast Chart
    renderForecastChart(data.predictions_timeline, data.noaa_kp_forecast || []);

  } catch (err) {
    console.error('Error loading ML forecast:', err);
    const notes = document.getElementById('forecast-assumptions');
    if (notes) notes.innerHTML = `<div class="text-rose-400">Forecast unavailable: ${escapeHtml(err.message)}</div>`;
  }
}

function setGaugeValue(id, pct) {
  const bar = document.getElementById(`${id}-bar`);
  const val = document.getElementById(`${id}-val`);
  // null when NOAA's forecast could not be loaded: no number is shown
  const ok = pct !== null && pct !== undefined;
  if (bar) bar.style.width = ok ? `${Math.min(100, Math.max(0, pct))}%` : '0%';
  if (val) val.innerText = ok ? `${pct}%` : 'n/a';
}

function updateHazardCard(id, info) {
  const card = document.getElementById(id);
  const badge = document.getElementById(`${id}-level`);
  const desc = document.getElementById(`${id}-desc`);
  if (badge) {
    badge.innerText = info.risk_level;
    badge.style.color = info.color;
    badge.style.borderColor = info.color;
  }
  if (desc) desc.innerText = info.advisory;
}

// NOAA predicted Kp of the 3-hour bin containing a time (ISO string), or null
function noaaKpAt(noaaKp, iso) {
  const t = Date.parse(iso);
  for (const k of noaaKp) {
    const t0 = Date.parse(String(k.time_tag).replace(' ', 'T') + 'Z');
    if (t >= t0 && t < t0 + 3 * 3600 * 1000) return k.kp;
  }
  return null;
}

function renderForecastChart(timeline, noaaKp = []) {
  const ctx = document.getElementById('chart-ml-timeline')?.getContext('2d');
  if (!ctx || !timeline) return;

  if (chartMLForecast) chartMLForecast.destroy();

  const labels = timeline.map(t => t.time_label);
  const kpVals = timeline.map(t => t.predicted_kp);
  const kpUpper = timeline.map(t => t.kp_confidence_interval[1]);
  const kpLower = timeline.map(t => t.kp_confidence_interval[0]);
  const dstVals = timeline.map(t => t.predicted_dst_nt);
  const noaaVals = timeline.map(t => noaaKpAt(noaaKp, t.time_iso));

  chartMLForecast = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Kp, Newell et al. (2008) from persisted L1 wind',
          data: kpVals,
          borderColor: '#ff2a6d',
          backgroundColor: 'rgba(255, 42, 109, 0.15)',
          fill: false,
          borderWidth: 2.5,
          pointRadius: 3,
          yAxisID: 'yKp'
        },
        {
          label: 'Kp range of the last 3 h (upper)',
          data: kpUpper,
          borderColor: 'rgba(255, 42, 109, 0.35)',
          borderDash: [3, 3],
          fill: '+1',
          backgroundColor: 'rgba(255, 42, 109, 0.08)',
          borderWidth: 1.2,
          pointRadius: 0,
          yAxisID: 'yKp'
        },
        {
          label: 'Kp range of the last 3 h (lower)',
          data: kpLower,
          borderColor: 'rgba(255, 42, 109, 0.35)',
          borderDash: [3, 3],
          fill: false,
          borderWidth: 1.2,
          pointRadius: 0,
          yAxisID: 'yKp'
        },
        {
          label: 'NOAA SWPC Kp forecast (estimated today, predicted after)',
          data: noaaVals,
          borderColor: '#facc15',
          stepped: true,
          fill: false,
          borderWidth: 1.8,
          pointRadius: 0,
          spanGaps: false,
          yAxisID: 'yKp'
        },
        {
          label: "O'Brien-McPherron Dst [nT]",
          data: dstVals,
          borderColor: '#00f0ff',
          backgroundColor: 'rgba(0, 240, 255, 0.08)',
          fill: false,
          borderWidth: 2,
          pointRadius: 2.5,
          yAxisID: 'yDst'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#94a3b8', font: { size: 10, weight: 'bold' } } },
        tooltip: {
          backgroundColor: '#0f172a',
          borderColor: '#334155',
          borderWidth: 1,
          titleColor: '#38bdf8',
          bodyColor: '#f1f5f9'
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(51, 65, 85, 0.25)' },
          ticks: { color: '#64748b', font: { size: 9 } }
        },
        yKp: {
          type: 'linear',
          position: 'left',
          min: 0,
          max: 9,
          grid: { color: 'rgba(51, 65, 85, 0.25)' },
          ticks: { color: '#ff2a6d', stepSize: 1 },
          title: { display: true, text: 'Geomagnetic Kp Index', color: '#ff2a6d' }
        },
        yDst: {
          type: 'linear',
          position: 'right',
          grid: { drawOnChartArea: false },
          ticks: { color: '#00f0ff' },
          title: { display: true, text: "O'Brien-McPherron Dst [nT]", color: '#00f0ff' }
        }
      }
    }
  });
}

window.loadMLForecast = loadMLForecast;
