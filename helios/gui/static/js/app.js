/**
 * HELIOS-L1 Main Frontend Application Controller (v1.2)
 * Multi-panel telemetry plotting, statistical cross-calibration,
 * global auroral oval world map, CME kinematics solver, Parker spiral modeling,
 * and custom telemetry/OMNI data ingestion.
 */

let chartMag = null;
let chartPlasma = null;
let chartMagnetosphere = null;
let chartCompOverlay = null;
let chartCompLag = null;
let chartCompScatter = null;
let chartCompResidual = null;
let chartEventTelemetry = null;
let chartSpectrum = null;
let chartDst = null;
let orbitViewer = null;
let auroralRenderer = null;
let parkerRenderer = null;
let cmeSimulator = null;
let solarDiskViewer = null;

const darkChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 400 },
  plugins: {
    legend: {
      labels: { color: '#94a3b8', font: { size: 10, weight: 'bold' } }
    },
    tooltip: {
      backgroundColor: '#0f172a',
      borderColor: '#334155',
      borderWidth: 1,
      titleColor: '#38bdf8',
      bodyColor: '#f1f5f9',
      padding: 8
    }
  },
  scales: {
    x: {
      grid: { color: 'rgba(51, 65, 85, 0.25)' },
      ticks: { color: '#64748b', font: { size: 9 }, maxTicksLimit: 12 }
    },
    y: {
      grid: { color: 'rgba(51, 65, 85, 0.25)' },
      ticks: { color: '#64748b', font: { size: 9 } }
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  startClock();
  initCharts();
  loadTelemetry();
  loadMissions();
  loadEvents();
  initOrbits();
  animateOrbits();
  initVisualizers();
});

function initVisualizers() {
  if (window.AuroralMapRenderer && document.getElementById('aurora-map-canvas')) {
    auroralRenderer = new AuroralMapRenderer('aurora-map-canvas', 'aurora-tooltip');
  }
  if (window.ParkerSpiralRenderer && document.getElementById('parker-canvas')) {
    parkerRenderer = new ParkerSpiralRenderer('parker-canvas', 'parker-tooltip');
  }
  if (window.CMESimulator && document.getElementById('cme-radar-canvas')) {
    cmeSimulator = new CMESimulator('cme-radar-canvas');
  }
  if (window.SolarDiskViewer && document.getElementById('solar-disk-canvas')) {
    solarDiskViewer = new SolarDiskViewer('solar-disk-canvas', 'solar-tooltip');
  }
}

function startClock() {
  function update() {
    const el = document.getElementById('utc-clock');
    if (el) {
      const now = new Date();
      el.innerText = now.toUTCString().slice(17, 25) + ' UTC';
    }
  }
  update();
  setInterval(update, 1000);
}

function toggleOrbitViewMode(mode) {
  if (orbitViewer) {
    orbitViewer.setViewMode(mode);
    const btn2d = document.getElementById('btn-orbit-2d');
    const btn3d = document.getElementById('btn-orbit-3d');
    if (mode === '2d') {
      btn2d?.classList.add('bg-sky-600', 'text-white');
      btn2d?.classList.remove('text-slate-400');
      btn3d?.classList.remove('bg-sky-600', 'text-white');
      btn3d?.classList.add('text-slate-400');
    } else {
      btn3d?.classList.add('bg-sky-600', 'text-white');
      btn3d?.classList.remove('text-slate-400');
      btn2d?.classList.remove('bg-sky-600', 'text-white');
      btn2d?.classList.add('text-slate-400');
    }
  }
}

function zoomOrbit(factor) {
  if (orbitViewer) {
    orbitViewer.scale = Math.min(Math.max(0.3, orbitViewer.scale * factor), 4.5);
  }
}

function switchTab(tabId) {
  window.playBlip?.();

  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
    btn.classList.remove('border-sky-400', 'text-sky-400');
    btn.classList.add('border-transparent', 'text-slate-400');
  });

  const targetTab = document.getElementById(`tab-${tabId}`);
  if (targetTab) targetTab.classList.remove('hidden');

  const clickedBtn = Array.from(document.querySelectorAll('.tab-btn')).find(b => b.getAttribute('onclick')?.includes(tabId));
  if (clickedBtn) {
    clickedBtn.classList.add('active');
    clickedBtn.classList.add('border-sky-400', 'text-sky-400');
    clickedBtn.classList.remove('border-transparent', 'text-slate-400');
  }

  if (tabId === 'orbits' && orbitViewer) {
    setTimeout(() => {
      orbitViewer.resize();
      orbitViewer.resetView();
    }, 50);
  } else if (tabId === 'aurora') {
    setTimeout(() => {
      if (auroralRenderer) auroralRenderer.resize();
    }, 50);
    loadAuroralForecast();
  } else if (tabId === 'parker') {
    setTimeout(() => {
      if (parkerRenderer) parkerRenderer.resize();
    }, 50);
    loadParkerSpiral();
  } else if (tabId === 'coronagraph') {
    setTimeout(() => {
      if (cmeSimulator) cmeSimulator.resize();
      if (solarDiskViewer) solarDiskViewer.resize();
    }, 50);
  } else if (tabId === 'comparator') {
    loadFleetMatrix();
  } else if (tabId === 'forecast') {
    loadMLForecast();
  } else if (tabId === 'turbulence') {
    loadSpectralAnalysis();
  }
}

function initCharts() {
  const ctxMag = document.getElementById('chart-mag')?.getContext('2d');
  if (ctxMag) {
    const bzGradient = ctxMag.createLinearGradient(0, 0, 0, 240);
    bzGradient.addColorStop(0, 'rgba(244, 63, 94, 0.28)');
    bzGradient.addColorStop(1, 'rgba(244, 63, 94, 0.0)');

    chartMag = new Chart(ctxMag, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'IMF Bz (GSM)', data: [], borderColor: '#f43f5e', backgroundColor: bzGradient, fill: true, borderWidth: 2, pointRadius: 0, tension: 0.2 },
          { label: 'IMF By (GSM)', data: [], borderColor: '#38bdf8', borderWidth: 1.2, pointRadius: 0, borderDash: [3, 3], tension: 0.2 },
          { label: 'Total |B|', data: [], borderColor: '#cbd5e1', borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
        ]
      },
      options: {
        ...darkChartOptions,
        scales: {
          ...darkChartOptions.scales,
          y: {
            ...darkChartOptions.scales.y,
            title: { display: true, text: 'Magnetic Field Vector [nT]', color: '#94a3b8', font: { size: 10, weight: 'bold' } }
          }
        }
      }
    });
  }

  const ctxPlasma = document.getElementById('chart-plasma')?.getContext('2d');
  if (ctxPlasma) {
    const speedGradient = ctxPlasma.createLinearGradient(0, 0, 0, 240);
    speedGradient.addColorStop(0, 'rgba(245, 158, 11, 0.25)');
    speedGradient.addColorStop(1, 'rgba(245, 158, 11, 0.0)');

    chartPlasma = new Chart(ctxPlasma, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Solar Wind Speed Vsw [km/s]', data: [], borderColor: '#f59e0b', backgroundColor: speedGradient, fill: true, yAxisID: 'ySpeed', borderWidth: 2, pointRadius: 0, tension: 0.2 },
          { label: 'Proton Density Np [cm⁻³]', data: [], borderColor: '#10b981', yAxisID: 'yDensity', borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
        ]
      },
      options: {
        ...darkChartOptions,
        scales: {
          x: darkChartOptions.scales.x,
          ySpeed: {
            type: 'linear',
            position: 'left',
            grid: { color: 'rgba(51, 65, 85, 0.25)' },
            ticks: { color: '#f59e0b', font: { size: 9, family: 'JetBrains Mono' } },
            title: { display: true, text: 'Bulk Speed [km/s]', color: '#f59e0b', font: { size: 10, weight: 'bold' } }
          },
          yDensity: {
            type: 'linear',
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { color: '#10b981', font: { size: 9, family: 'JetBrains Mono' } },
            title: { display: true, text: 'Ion Density [cm⁻³]', color: '#10b981', font: { size: 10, weight: 'bold' } }
          }
        }
      }
    });
  }

  const ctxMagSphere = document.getElementById('chart-magnetosphere')?.getContext('2d');
  if (ctxMagSphere) {
    const rmpGradient = ctxMagSphere.createLinearGradient(0, 0, 0, 240);
    rmpGradient.addColorStop(0, 'rgba(56, 189, 248, 0.22)');
    rmpGradient.addColorStop(1, 'rgba(56, 189, 248, 0.0)');

    chartMagnetosphere = new Chart(ctxMagSphere, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Magnetopause Standoff (R_mp) [R_E]', data: [], borderColor: '#38bdf8', backgroundColor: rmpGradient, fill: true, yAxisID: 'yRmp', borderWidth: 2, pointRadius: 0, tension: 0.2 },
          { label: 'Akasofu Epsilon [GW]', data: [], borderColor: '#a855f7', yAxisID: 'yEps', borderWidth: 1.5, pointRadius: 0, tension: 0.2 }
        ]
      },
      options: {
        ...darkChartOptions,
        scales: {
          x: darkChartOptions.scales.x,
          yRmp: {
            type: 'linear',
            position: 'left',
            grid: { color: 'rgba(51, 65, 85, 0.25)' },
            ticks: { color: '#38bdf8', font: { size: 9, family: 'JetBrains Mono' } },
            title: { display: true, text: 'Standoff Distance [Earth Radii]', color: '#38bdf8', font: { size: 10, weight: 'bold' } }
          },
          yEps: {
            type: 'linear',
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { color: '#a855f7', font: { size: 9, family: 'JetBrains Mono' } },
            title: { display: true, text: 'Energy Coupling [GW]', color: '#a855f7', font: { size: 10, weight: 'bold' } }
          }
        }
      }
    });
  }

  const ctxDst = document.getElementById('chart-dst')?.getContext('2d');
  if (ctxDst) {
    chartDst = new Chart(ctxDst, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Predicted Dst [nT]', data: [], borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.1)', fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0.1 }
        ]
      },
      options: {
        ...darkChartOptions,
        scales: {
          ...darkChartOptions.scales,
          y: {
            ...darkChartOptions.scales.y,
            title: { display: true, text: 'Dst Index [nT]', color: '#f43f5e' }
          }
        }
      }
    });
  }
}

async function loadTelemetry() {
  const satSelect = document.getElementById('telemetry-satellite-select');
  const spanSelect = document.getElementById('telemetry-span-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  const span = spanSelect ? spanSelect.value : '1';

  try {
    const res = await fetch(`/api/telemetry/${sat}?span_days=${span}`);
    if (!res.ok) throw new Error('Failed to fetch telemetry');
    const data = await res.json();
    updateTelemetryUI(data);
  } catch (err) {
    console.error('Error fetching telemetry:', err);
  }
}

function updateTelemetryUI(data) {
  const mission = data.mission;
  const latest = data.latest || {};
  const cls = data.classification || {};
  const records = data.records || [];

  document.getElementById('sat-name-full').innerText = mission.full_name;
  document.getElementById('sat-agency-orbit').innerText = `${mission.agency} • ${mission.location}`;

  // Update Top Alert Badges
  const gBadge = document.getElementById('noaa-g-badge');
  const gText = document.getElementById('g-scale-text');
  if (gBadge && gText) {
    gText.innerText = cls.g_scale || 'G0 Quiet';
    gBadge.style.color = cls.g_color || '#10b981';
    gBadge.style.borderColor = (cls.g_color || '#10b981') + '66';
    gBadge.style.backgroundColor = (cls.g_color || '#10b981') + '1a';
  }

  const bzBadge = document.getElementById('bz-alert-badge');
  const bzText = document.getElementById('bz-alert-text');
  if (bzBadge && bzText) {
    bzText.innerText = (latest.bz_gsm !== undefined ? `Bz: ${latest.bz_gsm} nT` : 'Bz Nominal');
    bzBadge.style.color = cls.bz_color || '#10b981';
    bzBadge.style.borderColor = (cls.bz_color || '#10b981') + '66';
    bzBadge.style.backgroundColor = (cls.bz_color || '#10b981') + '1a';
  }

  // Update Top Space Weather Condition Ticker
  const tickG = document.getElementById('ticker-g-scale');
  if (tickG) {
    tickG.innerText = cls.g_scale ? cls.g_scale.toUpperCase() : 'G0 QUIET';
    tickG.style.color = cls.g_color || '#10b981';
  }
  const tickR = document.getElementById('ticker-r-scale');
  if (tickR) tickR.innerText = cls.r_scale ? cls.r_scale.toUpperCase() : 'R0 NONE';
  const tickRmp = document.getElementById('ticker-rmp');
  if (tickRmp && latest.magnetopause_re !== undefined) tickRmp.innerText = `${latest.magnetopause_re} RE`;
  const tickEps = document.getElementById('ticker-epsilon');
  if (tickEps && latest.akasofu_gw !== undefined) tickEps.innerText = `${latest.akasofu_gw} GW`;

  // Update KPI Gauge Numbers
  document.getElementById('metric-speed').innerText = latest.speed !== undefined ? latest.speed : '---';
  document.getElementById('metric-speed-status').innerText = (latest.speed > 600 ? 'Severe High-Speed Stream!' : (latest.speed > 480 ? 'Elevated solar wind' : 'Nominal slow wind'));

  document.getElementById('metric-bz').innerText = latest.bz_gsm !== undefined ? latest.bz_gsm : '---';
  document.getElementById('metric-bz-status').innerText = (latest.bz_gsm < -10 ? 'Intense Southward (Storm Trigger)!' : (latest.bz_gsm < 0 ? 'Weak Southward' : 'Northward (Shielded)'));

  document.getElementById('metric-bt').innerText = latest.bt !== undefined ? latest.bt : '---';
  document.getElementById('metric-density').innerText = latest.density !== undefined ? latest.density : '---';
  document.getElementById('metric-pdyn').innerText = latest.dynamic_pressure !== undefined ? latest.dynamic_pressure : '---';
  document.getElementById('metric-delay').innerText = latest.l1_travel_time_min !== undefined ? latest.l1_travel_time_min : '---';

  // Dynamic KPI Mini-Progress Bars
  const barSpeed = document.getElementById('bar-speed');
  if (barSpeed && latest.speed) barSpeed.style.width = `${Math.min(100, Math.max(10, (latest.speed / 800) * 100))}%`;

  const barBz = document.getElementById('bar-bz');
  if (barBz && latest.bz_gsm !== undefined) {
    const bzPct = Math.min(100, Math.max(5, ((latest.bz_gsm + 20) / 40) * 100));
    barBz.style.width = `${bzPct}%`;
  }

  const barBt = document.getElementById('bar-bt');
  if (barBt && latest.bt) barBt.style.width = `${Math.min(100, Math.max(10, (latest.bt / 35) * 100))}%`;

  const barDensity = document.getElementById('bar-density');
  if (barDensity && latest.density) barDensity.style.width = `${Math.min(100, Math.max(10, (latest.density / 40) * 100))}%`;

  const barPdyn = document.getElementById('bar-pdyn');
  if (barPdyn && latest.dynamic_pressure) barPdyn.style.width = `${Math.min(100, Math.max(10, (latest.dynamic_pressure / 15) * 100))}%`;

  const barDelay = document.getElementById('bar-delay');
  if (barDelay && latest.l1_travel_time_min) barDelay.style.width = `${Math.min(100, Math.max(15, (latest.l1_travel_time_min / 60) * 100))}%`;

  // Feed Live Physical Telemetry to Orbit Simulator & HUD
  if (orbitViewer) {
    orbitViewer.setSolarWindConditions(latest.speed, latest.dynamic_pressure);
    const hudFlux = document.getElementById('hud-flux-speed');
    if (hudFlux && latest.speed) hudFlux.innerText = `${latest.speed} km/s`;
    const hudBow = document.getElementById('hud-bow-standoff');
    if (hudBow && latest.magnetopause_re) hudBow.innerText = `${latest.magnetopause_re} R_E`;
  }

  const times = records.map(r => r.time_tag.slice(5, 16));
  const bzVals = records.map(r => r.bz_gsm);
  const byVals = records.map(r => r.by_gsm);
  const btVals = records.map(r => r.bt);

  if (chartMag) {
    chartMag.data.labels = times;
    chartMag.data.datasets[0].data = bzVals;
    chartMag.data.datasets[1].data = byVals;
    chartMag.data.datasets[2].data = btVals;
    chartMag.update();
  }

  const vVals = records.map(r => r.speed);
  const nVals = records.map(r => r.density);
  if (chartPlasma) {
    chartPlasma.data.labels = times;
    chartPlasma.data.datasets[0].data = vVals;
    chartPlasma.data.datasets[1].data = nVals;
    chartPlasma.update();
  }

  const rmpVals = records.map(r => r.magnetopause_re);
  const epsVals = records.map(r => r.akasofu_gw);
  if (chartMagnetosphere) {
    chartMagnetosphere.data.labels = times;
    chartMagnetosphere.data.datasets[0].data = rmpVals;
    chartMagnetosphere.data.datasets[1].data = epsVals;
    chartMagnetosphere.update();
  }

  updateShocksTable(data.detected_shocks || []);
}

function updateShocksTable(shocks) {
  const badge = document.getElementById('shock-count-badge');
  const tbody = document.getElementById('shocks-table-body');
  if (!badge || !tbody) return;

  badge.innerText = `${shocks.length} shock${shocks.length === 1 ? '' : 's'} detected`;
  if (shocks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="py-4 text-center text-slate-500 italic">No abrupt CME shock discontinuities detected in the current window.</td></tr>`;
    return;
  }

  tbody.innerHTML = shocks.map(s => `
    <tr class="hover:bg-slate-800/40 transition">
      <td class="py-2.5 px-3 font-mono text-slate-300 font-bold">${s.time}</td>
      <td class="py-2.5 px-3 font-semibold text-rose-400 flex items-center space-x-1.5">
        <i class="fa-solid fa-triangle-exclamation"></i>
        <span>${s.classification}</span>
      </td>
      <td class="py-2.5 px-3 font-mono text-sky-400 font-bold">+${s.delta_speed_kms} km/s</td>
      <td class="py-2.5 px-3 font-mono text-emerald-400">${s.density_ratio}x</td>
      <td class="py-2.5 px-3 font-mono text-amber-400">${s.magnetic_ratio}x</td>
      <td class="py-2.5 px-3 font-mono text-purple-400 font-bold">${s.mach_proxy}</td>
    </tr>
  `).join('');
}

async function runComparison() {
  const satA = document.getElementById('comp-sat-a').value;
  const satB = document.getElementById('comp-sat-b').value;
  const param = document.getElementById('comp-param').value;

  try {
    const res = await fetch(`/api/compare?mission_a=${satA}&mission_b=${satB}&parameter=${param}&span_days=1`);
    if (!res.ok) throw new Error('Failed to run comparison');
    const comp = await res.json();

    if (comp.status !== 'success') {
      alert('Insufficient overlapping telemetry data between selected spacecraft.');
      return;
    }

    const m = comp.metrics;
    document.getElementById('stat-r').innerText = m.correlation_r;
    document.getElementById('stat-r2').innerText = m.r_squared;
    document.getElementById('stat-rmse').innerText = m.rmse;
    document.getElementById('stat-bias').innerText = (m.bias > 0 ? `+${m.bias}` : `${m.bias}`);
    document.getElementById('stat-lag').innerText = `${comp.lag_analysis?.optimal_lag_minutes || 0} min`;
    document.getElementById('stat-fit').innerText = `A = ${m.slope}*B ${m.intercept >= 0 ? '+' : ''}${m.intercept}`;

    renderCompOverlayChart(comp);
    renderCompLagChart(comp.lag_analysis);
    renderCompScatterChart(comp);
    renderCompResidualChart(comp);

  } catch (err) {
    console.error('Error running comparison:', err);
  }
}

function renderCompOverlayChart(comp) {
  const ctx = document.getElementById('chart-comp-overlay')?.getContext('2d');
  if (!ctx) return;
  if (chartCompOverlay) chartCompOverlay.destroy();

  const labels = comp.scatter_points.map(p => p.time.slice(11, 16));
  const dataA = comp.scatter_points.map(p => p.y);
  const dataB = comp.scatter_points.map(p => p.x);

  chartCompOverlay = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        { label: `${comp.mission_a} (${comp.parameter})`, data: dataA, borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
        { label: `${comp.mission_b} (${comp.parameter})`, data: dataB, borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, borderDash: [3, 2], tension: 0.1 }
      ]
    },
    options: darkChartOptions
  });
}

function renderCompLagChart(lagData) {
  const ctx = document.getElementById('chart-comp-lag')?.getContext('2d');
  if (!ctx || !lagData) return;
  if (chartCompLag) chartCompLag.destroy();

  chartCompLag = new Chart(ctx, {
    type: 'line',
    data: {
      labels: lagData.lags_minutes.map(l => `${l}m`),
      datasets: [
        { label: 'Cross-Correlation r(τ)', data: lagData.correlation, borderColor: '#10b981', backgroundColor: 'rgba(16, 185, 129, 0.1)', fill: true, borderWidth: 1.5, pointRadius: 1.5 }
      ]
    },
    options: {
      ...darkChartOptions,
      scales: {
        x: { ...darkChartOptions.scales.x, title: { display: true, text: 'Time Lag τ [minutes]', color: '#64748b' } },
        y: { ...darkChartOptions.scales.y, title: { display: true, text: 'Correlation r', color: '#64748b' }, min: -1, max: 1 }
      }
    }
  });
}

function renderCompScatterChart(comp) {
  const ctx = document.getElementById('chart-comp-scatter')?.getContext('2d');
  if (!ctx) return;
  if (chartCompScatter) chartCompScatter.destroy();

  const pts = comp.scatter_points.map(p => ({ x: p.x, y: p.y }));
  const minX = Math.min(...pts.map(p => p.x));
  const maxX = Math.max(...pts.map(p => p.x));
  const m = comp.metrics;
  const linePts = [
    { x: minX, y: m.slope * minX + m.intercept },
    { x: maxX, y: m.slope * maxX + m.intercept }
  ];

  const allVals = [...pts.map(p => p.x), ...pts.map(p => p.y)];
  const globalMin = Math.min(...allVals);
  const globalMax = Math.max(...allVals);
  const identityLine = [
    { x: globalMin, y: globalMin },
    { x: globalMax, y: globalMax }
  ];

  chartCompScatter = new Chart(ctx, {
    type: 'scatter',
    data: {
      datasets: [
        { label: 'Paired Sensor Readings', data: pts, backgroundColor: 'rgba(0, 240, 255, 0.75)', borderColor: 'rgba(0, 240, 255, 0.3)', borderWidth: 1, pointRadius: 3.5, pointHoverRadius: 6 },
        { label: `Linear Fit: A = ${m.slope}B ${m.intercept >= 0 ? '+' : ''}${m.intercept} (R² = ${m.r_squared})`, data: linePts, type: 'line', borderColor: '#ff2a6d', borderWidth: 2.2, pointRadius: 0 },
        { label: 'Ideal 1:1 Identity Reference (A = B)', data: identityLine, type: 'line', borderColor: 'rgba(148, 163, 184, 0.45)', borderDash: [4, 4], borderWidth: 1.2, pointRadius: 0 }
      ]
    },
    options: {
      ...darkChartOptions,
      scales: {
        x: { ...darkChartOptions.scales.x, title: { display: true, text: `${comp.mission_b} [${comp.parameter}]`, color: '#64748b' } },
        y: { ...darkChartOptions.scales.y, title: { display: true, text: `${comp.mission_a} [${comp.parameter}]`, color: '#64748b' } }
      }
    }
  });
}

function renderCompResidualChart(comp) {
  const ctx = document.getElementById('chart-comp-residual')?.getContext('2d');
  if (!ctx) return;
  if (chartCompResidual) chartCompResidual.destroy();

  const labels = comp.times.map(t => t.slice(11, 16));
  chartCompResidual = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Sensor Residual (A - B)', data: comp.residuals, backgroundColor: comp.residuals.map(r => r >= 0 ? '#38bdf8cc' : '#f43f5ecc') }
      ]
    },
    options: darkChartOptions
  });
}

// AURORAL FORECAST & DUAL-HEMISPHERE OVAL
async function loadAuroralForecast() {
  try {
    const res = await fetch('/api/aurora');
    const data = await res.json();
    const b = data.boundaries;

    document.getElementById('aurora-midnight-lat').innerText = `${b.equatorward_midnight_lat}° N/S`;
    document.getElementById('aurora-power-gw').innerText = `${b.hemispheric_power_gw} GW`;
    document.getElementById('aurora-flank-lat').innerText = `${b.equatorward_flanks_lat}°`;

    const regList = document.getElementById('aurora-regions-list');
    if (regList && b.visible_regions) {
      regList.innerHTML = b.visible_regions.map(r => `
        <li class="p-2.5 rounded-lg bg-space-900/80 border border-slate-700/60 flex items-center space-x-2">
          <i class="fa-solid fa-sparkles text-emerald-400"></i>
          <span>${r}</span>
        </li>
      `).join('');
    }

    if (chartDst && data.dst_evolution) {
      const times = data.dst_evolution.map(d => d.time_tag.slice(11, 16));
      const dstVals = data.dst_evolution.map(d => d.dst_predicted_nt);
      chartDst.data.labels = times;
      chartDst.data.datasets[0].data = dstVals;
      chartDst.update();

      const latestDst = dstVals[dstVals.length - 1];
      const curDstEl = document.getElementById('dst-current-val');
      if (curDstEl) curDstEl.innerText = `Dst: ${latestDst} nT`;
    }

    // Feed real-time geomagnetic parameters to high-resolution Auroral Renderer
    if (auroralRenderer) {
      auroralRenderer.resize();
      auroralRenderer.setConditions(data.kp || 3.5, -3.2, b.hemispheric_power_gw || 45);
    }
  } catch (err) {
    console.error('Error loading auroral forecast:', err);
  }
}

function toggleAuroraLayer(layer, state) {
  if (!auroralRenderer) return;
  if (layer === 'shadow') auroralRenderer.showNightShadow = state;
  else if (layer === 'south') auroralRenderer.showSouthernOval = state;
  else if (layer === 'stations') auroralRenderer.showStations = state;
}

// CME KINEMATICS SOLVER & INTERPLANETARY SHOCK SIMULATOR
async function calculateCMEKinematics() {
  const r1 = parseFloat(document.getElementById('cme-r1').value);
  const r2 = parseFloat(document.getElementById('cme-r2').value);
  const dt = parseFloat(document.getElementById('cme-dt').value);

  try {
    const res = await fetch('/api/coronagraph/kinematics', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ r1_rsun: r1, r2_rsun: r2, dt_minutes: dt })
    });
    const cme = await res.json();
    if (cme.error) {
      alert(cme.error);
      return;
    }

    const panel = document.getElementById('cme-results-panel');
    panel.classList.remove('hidden');
    document.getElementById('cme-v-init').innerText = `${cme.initial_speed_kms} km/s`;
    document.getElementById('cme-class').innerText = cme.speed_classification;
    document.getElementById('cme-transit-l1').innerText = `${cme.transit_to_l1_hours} hrs`;
    document.getElementById('cme-arrival-l1').innerText = cme.predicted_l1_arrival;
    document.getElementById('cme-transit-earth').innerText = `${cme.transit_to_earth_hours} hrs`;
    document.getElementById('cme-arrival-earth').innerText = cme.predicted_earth_arrival;
    document.getElementById('cme-lead-time').innerText = `+${cme.l1_to_earth_lead_time_minutes} min`;

    // Initialize 2D Interplanetary Propagation Radar Simulation
    if (cmeSimulator) {
      setTimeout(() => {
        cmeSimulator.resize();
        cmeSimulator.setInitialSpeed(cme.initial_speed_kms);
        const playIcon = document.getElementById('icon-cme-play');
        const playText = document.getElementById('text-cme-play');
        if (playIcon) playIcon.className = 'fa-solid fa-pause';
        if (playText) playText.innerText = 'Pause';
      }, 50);
    }
  } catch (err) {
    console.error('Error computing CME kinematics:', err);
  }
}

function toggleCMEPlay() {
  if (!cmeSimulator) return;
  cmeSimulator.isPlaying = !cmeSimulator.isPlaying;
  const playIcon = document.getElementById('icon-cme-play');
  const playText = document.getElementById('text-cme-play');
  if (cmeSimulator.isPlaying) {
    if (playIcon) playIcon.className = 'fa-solid fa-pause';
    if (playText) playText.innerText = 'Pause';
  } else {
    if (playIcon) playIcon.className = 'fa-solid fa-play';
    if (playText) playText.innerText = 'Play';
  }
}

function resetCMESim() {
  if (!cmeSimulator) return;
  cmeSimulator.reset();
  const slider = document.getElementById('cme-timeline-slider');
  if (slider) slider.value = 0;
  const playIcon = document.getElementById('icon-cme-play');
  const playText = document.getElementById('text-cme-play');
  if (playIcon) playIcon.className = 'fa-solid fa-play';
  if (playText) playText.innerText = 'Play';
}

function onCMESliderChange(val) {
  if (!cmeSimulator) return;
  cmeSimulator.setTime(parseFloat(val));
}

// HELIOSPHERIC PARKER SPIRAL INTERACTIVE SIMULATOR
async function loadParkerSpiral() {
  try {
    const speed = parkerRenderer ? parkerRenderer.speedKms : 440;
    const res = await fetch(`/api/parker_spiral?speed_kms=${speed}`);
    const data = await res.json();

    document.getElementById('parker-pitch-val').innerText = `${data.spiral_pitch_angle_deg}°`;
    document.getElementById('parker-footpoint-val').innerText = `~${data.connected_footpoint_deg_west}° W`;

    if (parkerRenderer) {
      parkerRenderer.resize();
    }
  } catch (err) {
    console.error('Error rendering Parker spiral:', err);
  }
}

function onParkerSpeedChange(speed) {
  const s = parseFloat(speed);
  const readout = document.getElementById('parker-speed-readout');
  if (readout) readout.innerText = `${s} km/s`;
  if (parkerRenderer) parkerRenderer.setSpeed(s);
}

function setParkerSpeedPreset(speed) {
  const slider = document.getElementById('parker-speed-slider');
  if (slider) slider.value = speed;
  onParkerSpeedChange(speed);
}

function toggleParkerFeature(feature, state) {
  if (!parkerRenderer) return;
  if (feature === 'cir') parkerRenderer.showCIR = state;
  else if (feature === 'flow') parkerRenderer.showPlasmaFlow = state;
  else if (feature === 'sectors') parkerRenderer.showSectors = state;
}

// CUSTOM INGESTION STUDIO
function loadSampleCSV() {
  const sample = `time,speed,density,bz_gsm,bt
2026-09-20 00:00:00,360.2,4.8,2.1,5.2
2026-09-20 01:00:00,380.5,5.1,-1.2,4.9
2026-09-20 02:00:00,450.0,8.2,-8.5,10.1
2026-09-20 03:00:00,680.4,22.4,-19.6,24.8
2026-09-20 04:00:00,750.1,18.0,-14.2,18.5
2026-09-20 05:00:00,710.0,12.5,-6.4,12.1`;
  document.getElementById('import-content').value = sample;
}

function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('import-content').value = e.target.result;
    document.getElementById('import-mission-name').value = file.name.replace(/\.[^/.]+$/, "");
  };
  reader.readAsText(file);
}

async function submitCustomImport() {
  const missionName = document.getElementById('import-mission-name').value;
  const content = document.getElementById('import-content').value;
  if (!content.trim()) {
    alert("Please enter or upload telemetry data first.");
    return;
  }

  try {
    const res = await fetch('/api/custom/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content, mission_name: missionName })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Import failed');

    const resultBox = document.getElementById('import-result-box');
    resultBox.classList.remove('hidden');
    document.getElementById('import-result-title').innerText = `Ingested ${data.total_records} data records for "${data.mission_name}"!`;
    document.getElementById('import-result-details').innerHTML = `
      <div>Time coverage: ${data.records[0]?.time_tag} to ${data.records[data.records.length - 1]?.time_tag}</div>
      <div>Shocks detected: ${data.detected_shocks.length}</div>
      <div class="text-sky-400 mt-1">Available for cross-comparison and analysis.</div>
    `;
  } catch (err) {
    alert("Ingestion error: " + err.message);
  }
}

async function loadMissions() {
  try {
    const res = await fetch('/api/missions');
    const missions = await res.json();
    const container = document.getElementById('fleet-cards-container');
    if (!container) return;

    container.innerHTML = missions.map(m => `
      <div class="mission-card bg-space-800/80 p-5 rounded-xl border border-slate-800 shadow-lg flex flex-col justify-between">
        <div>
          <div class="flex items-center justify-between mb-3">
            <span class="text-xs font-bold px-2.5 py-1 rounded bg-slate-700/80 text-sky-400 border border-slate-600">${m.name}</span>
            <span class="text-[11px] font-semibold text-emerald-400 flex items-center space-x-1">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              <span>${m.status.split(' ')[0]}</span>
            </span>
          </div>
          <h4 class="font-bold text-sm text-slate-100 mb-1">${m.full_name}</h4>
          <p class="text-xs text-slate-400 mb-3">${m.agency} • Launched ${m.launch_year}</p>
          <div class="text-xs text-slate-300 bg-space-900/60 p-2.5 rounded-lg border border-slate-800 mb-3">
            <strong class="text-sky-400">Orbit / Location:</strong> ${m.location}
          </div>
          <div class="space-y-1.5">
            <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400">Key Scientific Payloads:</div>
            ${m.instruments.map(inst => `
              <div class="text-xs text-slate-300 flex items-start space-x-1.5">
                <span class="text-amber-400 font-bold">• ${inst.name}:</span>
                <span class="text-slate-400">${inst.measures}</span>
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `).join('');
  } catch (err) {
    console.error('Error loading missions catalog:', err);
  }
}

async function loadEvents() {
  try {
    const res = await fetch('/api/events');
    const events = await res.json();
    const container = document.getElementById('event-cards-container');
    if (!container) return;

    container.innerHTML = events.map(ev => `
      <div onclick="selectEvent('${ev.id}')" class="cursor-pointer bg-space-800/80 hover:bg-space-700/80 p-4 rounded-xl border border-slate-800 hover:border-sky-400 transition shadow-md">
        <div class="flex items-center space-x-2 text-rose-400 text-sm mb-1 font-bold">
          <i class="fa-solid ${ev.icon}"></i>
          <span>${ev.severity}</span>
        </div>
        <div class="text-xs font-bold text-slate-200">${ev.title}</div>
      </div>
    `).join('');

    if (events.length > 0) {
      selectEvent(events[0].id);
    }
  } catch (err) {
    console.error('Error loading events:', err);
  }
}

async function selectEvent(eventId) {
  try {
    const res = await fetch(`/api/event/${eventId}`);
    const ev = await res.json();
    const meta = ev.metadata;

    document.getElementById('event-title').innerText = meta.title;
    document.getElementById('event-desc').innerText = meta.summary;
    document.getElementById('event-peak-kp').innerText = meta.peak_kp;
    document.getElementById('event-min-bz').innerText = `${meta.min_bz} nT`;
    document.getElementById('event-peak-v').innerText = `${meta.peak_speed} km/s`;
    document.getElementById('event-peak-pdyn').innerText = `${meta.peak_dyn_pressure} nPa`;

    const ctx = document.getElementById('chart-event-telemetry')?.getContext('2d');
    if (!ctx) return;
    if (chartEventTelemetry) chartEventTelemetry.destroy();

    const labels = ev.telemetry.map(r => r.time_tag.slice(11, 16));
    const bzVals = ev.telemetry.map(r => r.bz_gsm);
    const vVals = ev.telemetry.map(r => r.speed);

    chartEventTelemetry = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          { label: 'IMF Bz [nT]', data: bzVals, borderColor: '#f43f5e', yAxisID: 'yBz', borderWidth: 1.5, pointRadius: 0 },
          { label: 'Solar Wind Speed [km/s]', data: vVals, borderColor: '#38bdf8', yAxisID: 'yV', borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: {
        ...darkChartOptions,
        scales: {
          x: darkChartOptions.scales.x,
          yBz: {
            type: 'linear',
            position: 'left',
            grid: { color: 'rgba(51, 65, 85, 0.25)' },
            ticks: { color: '#f43f5e' },
            title: { display: true, text: 'IMF Bz [nT]', color: '#f43f5e' }
          },
          yV: {
            type: 'linear',
            position: 'right',
            grid: { drawOnChartArea: false },
            ticks: { color: '#38bdf8' },
            title: { display: true, text: 'Vsw [km/s]', color: '#38bdf8' }
          }
        }
      }
    });

  } catch (err) {
    console.error('Error selecting event:', err);
  }
}

async function loadSpectralAnalysis() {
  try {
    const res = await fetch('/api/spectrum?mission_id=DSCOVR&parameter=bz_gsm');
    const psd = await res.json();
    const ctx = document.getElementById('chart-spectrum')?.getContext('2d');
    if (!ctx || !psd.frequencies_hz) return;
    if (chartSpectrum) chartSpectrum.destroy();

    chartSpectrum = new Chart(ctx, {
      type: 'line',
      data: {
        labels: psd.frequencies_hz.map(f => (f * 1000).toFixed(2) + ' mHz'),
        datasets: [
          { label: 'IMF Fluctuations Power Density (nT²/Hz)', data: psd.power_density, borderColor: '#a855f7', backgroundColor: 'rgba(168, 85, 247, 0.1)', fill: true, borderWidth: 1.5, pointRadius: 0 }
        ]
      },
      options: {
        ...darkChartOptions,
        scales: {
          x: { ...darkChartOptions.scales.x, title: { display: true, text: 'Frequency (mHz)', color: '#64748b' } },
          y: { ...darkChartOptions.scales.y, type: 'logarithmic', title: { display: true, text: 'Power Spectral Density', color: '#64748b' } }
        }
      }
    });
  } catch (err) {
    console.error('Error loading spectral analysis:', err);
  }
}

async function initOrbits() {
  try {
    const res = await fetch('/api/orbits');
    const data = await res.json();
    orbitViewer = new OrbitRenderer('orbit-canvas', 'orbit-tooltip');
    orbitViewer.setOrbitsData(data);
  } catch (err) {
    console.error('Error initializing orbits:', err);
  }
}

function animateOrbits() {
  if (orbitViewer) {
    orbitViewer.draw();
  }
  requestAnimationFrame(animateOrbits);
}

function resetOrbitView() {
  if (orbitViewer) orbitViewer.resetView();
}

function refreshCurrentView() {
  const refreshIcon = document.getElementById('refresh-icon');
  if (refreshIcon) refreshIcon.classList.add('fa-spin');
  loadTelemetry().then(() => {
    setTimeout(() => {
      if (refreshIcon) refreshIcon.classList.remove('fa-spin');
    }, 600);
  });
}

function exportData(format) {
  const satSelect = document.getElementById('telemetry-satellite-select');
  const spanSelect = document.getElementById('telemetry-span-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  const span = spanSelect ? spanSelect.value : '1';

  if (format === 'csv') {
    window.location.href = `/api/export/csv?mission_id=${sat}&span_days=${span}`;
  } else if (format === 'plot') {
    window.location.href = `/api/export/plot?mission_id=${sat}&span_days=${span}`;
  }
}

// SOLAR WAVELENGTH SELECTOR
function setSolarWavelength(wl) {
  if (solarDiskViewer) solarDiskViewer.setWavelength(wl);
  ['193', '304', '171', '131', 'c2'].forEach(w => {
    const btn = document.getElementById(`btn-wl-${w}`);
    if (btn) {
      if (w.toUpperCase() === wl.toUpperCase()) {
        btn.className = 'px-2.5 py-1 rounded bg-amber-600 text-white font-bold transition';
      } else {
        btn.className = 'px-2.5 py-1 rounded text-slate-300 hover:text-white transition';
      }
    }
  });
}

// SPACE WEATHER BULLETIN MODAL & EXPORT
async function openBulletinModal() {
  const modal = document.getElementById('bulletin-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  window.playBlip?.();

  const satSelect = document.getElementById('telemetry-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';

  try {
    const res = await fetch(`/api/report/html?mission_id=${sat}`);
    const html = await res.text();
    const container = document.getElementById('bulletin-content');
    if (container) {
      container.innerHTML = html;
    }
  } catch (err) {
    const container = document.getElementById('bulletin-content');
    if (container) container.innerHTML = `<div class="text-rose-400">Failed to load bulletin: ${err.message}</div>`;
  }
}

function closeBulletinModal() {
  const modal = document.getElementById('bulletin-modal');
  if (modal) modal.classList.add('hidden');
}

function downloadBulletinHTML() {
  const satSelect = document.getElementById('telemetry-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  window.location.href = `/api/report/html?mission_id=${sat}`;
}

