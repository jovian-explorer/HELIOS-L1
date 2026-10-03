/**
 * HELIOS-L1: MACHINE LEARNING & ADVANCED MAGNETOSPHERIC COUPLING CONTROLLER
 * Features:
 * - Newell Solar Wind Magnetosphere Coupling Function Monitor
 * - O'Brien & McPherron (2000) ring current Dst forecast, started from observed Kyoto Dst
 * - Multi-Horizon (1h to 12h) Kp Confidence Interval Charting
 * - Probabilistic NOAA Geomagnetic Storm Scale Gauges (G1, G3, G5)
 * - Critical Infrastructure Hazard Advisories (GIC, Aviation, Satellites)
 */

let chartMLForecast = null;

async function loadMLForecast() {
  const satSelect = document.getElementById('forecast-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';

  try {
    const res = await fetch(`/api/forecast/ml?mission_id=${sat}`);
    if (!res.ok) throw new Error('Forecast API failed');
    const data = await res.json();

    // 1. Current Coupling & Indicators
    const c = data.current_coupling;
    const newellEl = document.getElementById('forecast-newell-val');
    const newellStateEl = document.getElementById('forecast-newell-state');
    const dstEstEl = document.getElementById('forecast-dst-val');

    if (newellEl) newellEl.innerText = `${c.newell_coupling_rate.toLocaleString()} Wb/s`;
    if (newellStateEl) newellStateEl.innerText = c.coupling_state;
    if (dstEstEl) dstEstEl.innerText = `${c.estimated_dst_nt} nT`;
    const dstSrcEl = document.getElementById('forecast-dst-source');
    if (dstSrcEl && c.dst_source) dstSrcEl.innerText = c.dst_source;

    // 2. Storm Scale Probabilities
    const probs = data.storm_probabilities;
    setGaugeValue('gauge-g1', probs.minor_storm_g1_kp5_percent);
    setGaugeValue('gauge-g3', probs.strong_storm_g3_kp7_percent);
    setGaugeValue('gauge-g5', probs.extreme_storm_g5_kp9_percent);

    // 3. Hazard Assessment Cards
    const h = data.hazard_assessment;
    updateHazardCard('hazard-gic', h.power_grid_gic);
    updateHazardCard('hazard-aviation', h.aviation_hf);
    updateHazardCard('hazard-satellite', h.satellite_ops);

    // 4. Render 12-Hour Forecast Chart
    renderForecastChart(data.predictions_timeline);

  } catch (err) {
    console.error('Error loading ML forecast:', err);
  }
}

function setGaugeValue(id, pct) {
  const bar = document.getElementById(`${id}-bar`);
  const val = document.getElementById(`${id}-val`);
  if (bar) bar.style.width = `${Math.min(100, Math.max(0, pct))}%`;
  if (val) val.innerText = `${pct}%`;
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

function renderForecastChart(timeline) {
  const ctx = document.getElementById('chart-ml-timeline')?.getContext('2d');
  if (!ctx || !timeline) return;

  if (chartMLForecast) chartMLForecast.destroy();

  const labels = timeline.map(t => t.time_label);
  const kpVals = timeline.map(t => t.predicted_kp);
  const kpUpper = timeline.map(t => t.kp_confidence_interval[1]);
  const kpLower = timeline.map(t => t.kp_confidence_interval[0]);
  const dstVals = timeline.map(t => t.predicted_dst_nt);

  chartMLForecast = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Predicted Kp Index',
          data: kpVals,
          borderColor: '#ff2a6d',
          backgroundColor: 'rgba(255, 42, 109, 0.15)',
          fill: false,
          borderWidth: 2.5,
          pointRadius: 3,
          yAxisID: 'yKp'
        },
        {
          label: 'Kp Upper Confidence (95%)',
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
          label: 'Kp Lower Confidence (95%)',
          data: kpLower,
          borderColor: 'rgba(255, 42, 109, 0.35)',
          borderDash: [3, 3],
          fill: false,
          borderWidth: 1.2,
          pointRadius: 0,
          yAxisID: 'yKp'
        },
        {
          label: 'Ring Current Dst Forecast [nT]',
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
