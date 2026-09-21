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

let currentDomain = 'fleet';
let currentTab = 'dashboard';
let clockMode = 'UTC';

const DOMAINS = {
  fleet: {
    id: 'fleet',
    name: 'L1 Fleet & Telemetry',
    badge: '4 SENSORS',
    context: 'DOMAIN: L1 FLEET & TELEMETRY // REAL-TIME IN-SITU OBSERVATORY',
    views: [
      { id: 'dashboard', label: 'L1 Telemetry', icon: 'fa-gauge-high', color: 'text-sky-400' },
      { id: 'comparator', label: 'Multi-Satellite Comparator', icon: 'fa-code-compare', color: 'text-cyan-400' },
      { id: 'orbits', label: 'Position of Probes & Orbits', icon: 'fa-circle-nodes', color: 'text-sky-400' },
      { id: 'missions', label: 'Fleet Catalog', icon: 'fa-satellite', color: 'text-blue-400' }
    ]
  },
  heliosphere: {
    id: 'heliosphere',
    name: 'Solar & Heliosphere',
    badge: '3 MODELS',
    context: 'DOMAIN: SOLAR & HELIOSPHERE // CORONA, PARKER SPIRAL & TURBULENCE',
    views: [
      { id: 'coronagraph', label: 'Coronagraph & CME', icon: 'fa-sun', color: 'text-amber-400' },
      { id: 'parker', label: 'Parker Spiral & CIR', icon: 'fa-wind', color: 'text-cyan-400' },
      { id: 'turbulence', label: 'FFT Turbulence & PSD', icon: 'fa-wave-square', color: 'text-purple-400' }
    ]
  },
  geospace: {
    id: 'geospace',
    name: 'Geospace & Hazards',
    badge: '4 MODULES',
    context: 'DOMAIN: GEOSPACE & HAZARDS // OVATION, ML FORECAST, D-RAP & GIC',
    views: [
      { id: 'aurora', label: 'Auroral Oval & Map', icon: 'fa-earth-americas', color: 'text-emerald-400' },
      { id: 'forecast', label: 'AI / ML Storm Forecast', icon: 'fa-chart-line', color: 'text-blue-400' },
      { id: 'hazards', label: 'Terrestrial Hazards & Solar Cycle', icon: 'fa-tower-broadcast', color: 'text-amber-400' },
      { id: 'events', label: 'Storms Archive', icon: 'fa-clock-rotate-left', color: 'text-rose-400' }
    ]
  },
  data: {
    id: 'data',
    name: 'Data Studio & Science',
    badge: 'OPEN SCI',
    context: 'DOMAIN: DATA STUDIO & SCIENCE // CUSTOM OMNI & PEER-REVIEWED DOIS',
    views: [
      { id: 'import', label: 'Custom Ingestion & OMNI', icon: 'fa-database', color: 'text-indigo-400' },
      { id: 'references', label: 'References & Portals', icon: 'fa-book-atlas', color: 'text-emerald-400', isModal: true }
    ]
  }
};

const TAB_TO_DOMAIN = {
  dashboard: 'fleet',
  comparator: 'fleet',
  orbits: 'fleet',
  missions: 'fleet',
  coronagraph: 'heliosphere',
  parker: 'heliosphere',
  turbulence: 'heliosphere',
  aurora: 'geospace',
  forecast: 'geospace',
  hazards: 'geospace',
  events: 'geospace',
  import: 'data',
  references: 'data'
};

document.addEventListener('DOMContentLoaded', () => {
  startClock();
  renderSubnav('fleet');
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
  updateClock();
  setInterval(updateClock, 1000);
}

function toggleClockMode() {
  clockMode = (clockMode === 'UTC') ? 'LOCAL' : 'UTC';
  updateClock();
}

function updateClock() {
  const el = document.getElementById('utc-clock');
  const badge = document.getElementById('clock-tz-badge');
  if (!el) return;
  const now = new Date();
  if (clockMode === 'UTC') {
    el.innerText = now.toUTCString().slice(17, 25) + ' UTC';
    if (badge) {
      badge.innerText = 'UTC';
      badge.className = 'text-[9px] px-1 py-0.2 rounded bg-sky-500/20 text-sky-300 uppercase font-mono';
    }
  } else {
    const offsetMin = -now.getTimezoneOffset();
    const sign = offsetMin >= 0 ? '+' : '-';
    const absMin = Math.abs(offsetMin);
    const hrs = String(Math.floor(absMin / 60)).padStart(2, '0');
    const mins = String(absMin % 60).padStart(2, '0');
    const tzStr = `UTC${sign}${hrs}:${mins}`;
    el.innerText = now.toLocaleTimeString();
    if (badge) {
      badge.innerText = tzStr;
      badge.className = 'text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 uppercase font-mono';
    }
  }
}

function renderSubnav(domainKey) {
  const container = document.getElementById('subnav-container');
  if (!container) return;
  const domain = DOMAINS[domainKey];
  if (!domain) return;

  const html = domain.views.map(v => {
    const isActive = v.id === currentTab;
    const activeClass = isActive ? 'active' : '';
    const clickHandler = v.isModal ? `openReferencesModal()` : `switchTab('${v.id}')`;
    return `
      <button onclick="${clickHandler}" id="subnav-btn-${v.id}" class="subnav-btn ${activeClass}" title="${v.label}">
        <i class="fa-solid ${v.icon} ${v.color}"></i>
        <span>${v.label}</span>
      </button>
    `;
  }).join('');

  container.innerHTML = html;

  const ctxLabel = document.getElementById('domain-context-label');
  if (ctxLabel) {
    ctxLabel.innerText = domain.context;
  }
}

function switchDomain(domainKey) {
  if (!DOMAINS[domainKey]) return;
  currentDomain = domainKey;

  // Update domain buttons in Tier 1
  document.querySelectorAll('#domain-tabs .domain-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  const domainBtn = document.getElementById(`domain-btn-${domainKey}`);
  if (domainBtn) domainBtn.classList.add('active');

  // If current tab is not in this domain, switch to first tab of new domain
  const domainViews = DOMAINS[domainKey].views;
  const viewExistsInDomain = domainViews.some(v => v.id === currentTab);
  if (!viewExistsInDomain) {
    const nextTab = domainViews.find(v => !v.isModal)?.id || domainViews[0].id;
    currentTab = nextTab;
  }

  renderSubnav(domainKey);
  switchTab(currentTab, false);
}

function switchTab(tabId, checkDomain = true) {
  window.playBlip?.();

  if (checkDomain) {
    const targetDomain = TAB_TO_DOMAIN[tabId] || 'fleet';
    if (targetDomain !== currentDomain) {
      currentDomain = targetDomain;
      document.querySelectorAll('#domain-tabs .domain-btn').forEach(btn => {
        btn.classList.remove('active');
      });
      const domainBtn = document.getElementById(`domain-btn-${targetDomain}`);
      if (domainBtn) domainBtn.classList.add('active');
    }
  }

  currentTab = tabId;
  renderSubnav(currentDomain);

  document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
  const targetTab = document.getElementById(`tab-${tabId}`);
  if (targetTab) targetTab.classList.remove('hidden');

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
  } else if (tabId === 'hazards') {
    loadHazardsAndCycle();
  } else if (tabId === 'turbulence') {
    loadSpectralAnalysis();
  }
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

let currentTelemetryData = null;
let currentTelemetryFilter = 'all';

async function loadTelemetry() {
  const satSelect = document.getElementById('telemetry-satellite-select');
  const spanSelect = document.getElementById('telemetry-span-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  const span = spanSelect ? spanSelect.value : '1';

  const t0 = performance.now();
  try {
    const res = await fetch(`/api/telemetry/${sat}?span_days=${span}`);
    if (!res.ok) throw new Error('Failed to fetch telemetry');
    const data = await res.json();
    currentTelemetryData = data;
    const latency = Math.round(performance.now() - t0);
    updateFeedStatus(data, latency);
    updateTelemetryUI(data);
  } catch (err) {
    console.error('Error fetching telemetry:', err);
    updateFeedStatus({ error: true });
  }
}

function setTelemetryFilter(filterKey) {
  window.playBlip?.();
  currentTelemetryFilter = filterKey;

  const btnKeys = ['all', 'bz_south', 'fast_wind', 'dense_plasma'];
  btnKeys.forEach(k => {
    const btn = document.getElementById(`btn-filter-${k}`);
    if (!btn) return;
    if (k === filterKey) {
      btn.className = 'px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-sky-600 text-white border border-sky-400/40 transition shadow-sm';
    } else {
      btn.className = 'px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 text-slate-300 hover:text-white border border-slate-700/60 transition';
    }
  });

  if (currentTelemetryData) {
    updateTelemetryUI(currentTelemetryData);
  }
}

function updateFeedStatus(data, latency = 0) {
  const badgeText = document.getElementById('feed-status-text');
  const badgeDot = document.getElementById('feed-status-dot');
  if (!badgeText || !badgeDot) return;

  if (data.error) {
    badgeText.innerText = 'Feed Offline';
    badgeText.className = 'text-rose-400 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-rose-500';
    return;
  }

  const recCount = (data.records || []).length;
  const isLive = (data.source || '').toLowerCase().includes('noaa') || (data.source || '').toLowerCase().includes('live');

  if (isLive) {
    badgeText.innerText = `NOAA SWPC (${recCount} pts • ${latency}ms)`;
    badgeText.className = 'text-emerald-300 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-emerald-400 pulse-beacon';
  } else {
    badgeText.innerText = `Physics Model (${recCount} pts • ${latency}ms)`;
    badgeText.className = 'text-amber-300 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-amber-400';
  }
}

function updateTelemetryUI(data) {
  const mission = data.mission;
  const latest = data.latest || {};
  const cls = data.classification || {};
  const allRecords = data.records || [];

  // Filter records if a physical regime filter is active
  let records = allRecords;
  if (currentTelemetryFilter === 'bz_south') {
    const filtered = allRecords.filter(r => typeof r.bz_gsm === 'number' && r.bz_gsm < 0);
    if (filtered.length > 0) records = filtered;
  } else if (currentTelemetryFilter === 'fast_wind') {
    const filtered = allRecords.filter(r => typeof r.speed === 'number' && r.speed >= 480);
    if (filtered.length > 0) records = filtered;
  } else if (currentTelemetryFilter === 'dense_plasma') {
    const filtered = allRecords.filter(r => typeof r.density === 'number' && r.density >= 8);
    if (filtered.length > 0) records = filtered;
  }

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
  const tickS = document.getElementById('ticker-s-scale');
  if (tickS) {
    tickS.innerText = cls.s_scale ? cls.s_scale.toUpperCase() : 'S0 NOMINAL';
    tickS.style.color = cls.s_color || '#10b981';
  }
  const tickR = document.getElementById('ticker-r-scale');
  if (tickR) {
    tickR.innerText = cls.r_scale ? cls.r_scale.toUpperCase() : 'R0 NONE';
    tickR.style.color = cls.r_level > 0 ? '#f59e0b' : '#10b981';
  }
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

  // Calculate Min, Avg, Max for numeric telemetry fields across records
  function calcStats(arr, key) {
    const vals = arr.map(r => r[key]).filter(v => typeof v === 'number' && !isNaN(v));
    if (vals.length === 0) return { min: '--', avg: '--', max: '--' };
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const avg = vals.reduce((a, b) => a + b, 0) / vals.length;
    return {
      min: min.toFixed(1),
      avg: avg.toFixed(1),
      max: max.toFixed(1)
    };
  }

  const spdStats = calcStats(records, 'speed');
  const bzStats = calcStats(records, 'bz_gsm');
  const btStats = calcStats(records, 'bt');
  const denStats = calcStats(records, 'density');
  const pdynStats = calcStats(records, 'dynamic_pressure');
  const delStats = calcStats(records, 'l1_travel_time_min');

  const setStatText = (prefix, s) => {
    const minEl = document.getElementById(`stat-${prefix}-min`);
    const avgEl = document.getElementById(`stat-${prefix}-avg`);
    const maxEl = document.getElementById(`stat-${prefix}-max`);
    if (minEl) minEl.innerText = s.min;
    if (avgEl) avgEl.innerText = s.avg;
    if (maxEl) maxEl.innerText = s.max;
  };

  setStatText('speed', spdStats);
  setStatText('bz', bzStats);
  setStatText('bt', btStats);
  setStatText('density', denStats);
  setStatText('pdyn', pdynStats);
  setStatText('delay', delStats);

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

  // Update IMF Clock Angle & Reconnection Compass Needle
  const by = latest.by_gsm !== undefined ? latest.by_gsm : 0;
  const bz = latest.bz_gsm !== undefined ? latest.bz_gsm : 0;
  let clockTheta = Math.round(Math.atan2(by, bz) * (180 / Math.PI));
  if (clockTheta < 0) clockTheta += 360;

  const needle = document.getElementById('clock-angle-needle');
  const clockText = document.getElementById('metric-clock-angle');
  const recBadge = document.getElementById('metric-reconnect-badge');

  if (needle) {
    needle.setAttribute('transform', `rotate(${clockTheta} 16 16)`);
  }
  if (clockText) {
    let dir = 'N';
    if (clockTheta > 337.5 || clockTheta <= 22.5) dir = 'N';
    else if (clockTheta > 22.5 && clockTheta <= 67.5) dir = 'NE';
    else if (clockTheta > 67.5 && clockTheta <= 112.5) dir = 'E';
    else if (clockTheta > 112.5 && clockTheta <= 157.5) dir = 'SE';
    else if (clockTheta > 157.5 && clockTheta <= 202.5) dir = 'S';
    else if (clockTheta > 202.5 && clockTheta <= 247.5) dir = 'SW';
    else if (clockTheta > 247.5 && clockTheta <= 292.5) dir = 'W';
    else if (clockTheta > 292.5 && clockTheta <= 337.5) dir = 'NW';

    clockText.innerText = `${clockTheta}° (${dir})`;
  }
  if (recBadge) {
    if (bz < -5) {
      recBadge.innerText = 'RECONNECTING';
      recBadge.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded bg-rose-500/25 text-rose-400 border border-rose-500/40 animate-pulse';
    } else if (bz < 0) {
      recBadge.innerText = 'WEAK REC';
      recBadge.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30';
    } else {
      recBadge.innerText = 'CLOSED';
      recBadge.className = 'text-[9px] font-bold px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
    }
  }

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

    // Update Spatial Baseline & Phase Delay HUD
    const base = comp.spatial_baseline || {};
    const distKmEl = document.getElementById('baseline-dist-km');
    const distReEl = document.getElementById('baseline-dist-re');
    const vecGseEl = document.getElementById('baseline-vec-gse');
    const theoryDelayEl = document.getElementById('baseline-theory-delay');
    const empLagEl = document.getElementById('baseline-empirical-lag');
    const fidelityEl = document.getElementById('baseline-fidelity-score');

    if (distKmEl) distKmEl.innerText = `${base.distance_km !== undefined ? base.distance_km.toLocaleString() : '---'} km`;
    if (distReEl) distReEl.innerText = `${base.distance_re !== undefined ? base.distance_re : '--'} R_E`;
    if (vecGseEl) vecGseEl.innerText = `ΔX: ${base.dx_km || 0}, ΔY: ${base.dy_km || 0}, ΔZ: ${base.dz_km || 0}`;
    if (theoryDelayEl) theoryDelayEl.innerText = `${base.theoretical_delay_min !== undefined ? (base.theoretical_delay_min > 0 ? `+${base.theoretical_delay_min}` : base.theoretical_delay_min) : '--'} min`;
    if (empLagEl) empLagEl.innerText = `${comp.lag_analysis?.optimal_lag_minutes !== undefined ? (comp.lag_analysis.optimal_lag_minutes > 0 ? `+${comp.lag_analysis.optimal_lag_minutes}` : comp.lag_analysis.optimal_lag_minutes) : '--'} min`;
    if (fidelityEl) {
      const score = m.fidelity_index_pct !== undefined ? m.fidelity_index_pct : 88.5;
      fidelityEl.innerText = `${score}% ${score >= 80 ? 'HIGH' : (score >= 60 ? 'MOD' : 'LOW')}`;
      fidelityEl.className = `font-bold font-hud text-sm ${score >= 80 ? 'text-emerald-400' : (score >= 60 ? 'text-amber-400' : 'text-rose-400')}`;
    }

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

function setCMEPreset(r1, r2, dt, label) {
  window.playBlip?.();
  const elR1 = document.getElementById('cme-r1');
  const elR2 = document.getElementById('cme-r2');
  const elDt = document.getElementById('cme-dt');
  if (elR1) elR1.value = r1;
  if (elR2) elR2.value = r2;
  if (elDt) elDt.value = dt;
  calculateCMEKinematics();
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
      <div class="mission-card bg-space-800/90 p-5 rounded-xl border border-slate-800 hover:border-slate-700 shadow-xl flex flex-col justify-between space-y-4">
        <div>
          <!-- Card Header -->
          <div class="flex items-center justify-between gap-2 mb-2.5 pb-2.5 border-b border-slate-800/80">
            <div class="flex items-center space-x-2">
              <span class="text-xs font-hud font-bold px-2.5 py-1 rounded bg-slate-900 text-sky-400 border border-slate-700">${m.name}</span>
              <span class="text-[11px] font-semibold text-slate-400">${m.agency}</span>
            </div>
            <div class="flex items-center space-x-1.5">
              <span class="text-[10px] font-medium px-2 py-0.5 rounded bg-sky-950/70 text-sky-300 border border-sky-800/40">${m.license_badge || 'Open Science'}</span>
              <span class="text-[11px] font-semibold text-emerald-400 flex items-center space-x-1 ml-1" title="${m.status}">
                <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
                <span>${m.status.split(' ')[0]}</span>
              </span>
            </div>
          </div>

          <!-- Mission Name & Launch -->
          <h4 class="font-bold text-sm text-slate-100 mb-1">${m.full_name}</h4>
          <p class="text-xs text-slate-400 mb-3 flex items-center space-x-2">
            <span>Launched: <strong class="text-slate-200">${m.launch_year}</strong></span>
            <span>•</span>
            <span>Ephemeris: <strong class="text-slate-200">${(m.orbit_distance_km || 0).toLocaleString()} km</strong></span>
          </p>

          <!-- Orbit, Coordinate System & Cadence Details -->
          <div class="grid grid-cols-1 gap-1.5 text-xs bg-space-950/70 p-3 rounded-lg border border-slate-800/80 mb-3.5">
            <div>
              <span class="text-slate-400 font-semibold">Orbit / Target:</span>
              <span class="text-slate-200 font-mono text-[11px] ml-1">${m.location}</span>
            </div>
            ${m.coordinate_system ? `
              <div>
                <span class="text-slate-400 font-semibold">Coordinate Frame:</span>
                <span class="text-sky-300 font-mono text-[11px] ml-1">${m.coordinate_system}</span>
              </div>
            ` : ''}
            ${m.cadence ? `
              <div>
                <span class="text-slate-400 font-semibold">Telemetry Cadence:</span>
                <span class="text-amber-300 font-mono text-[11px] ml-1">${m.cadence}</span>
              </div>
            ` : ''}
            ${m.data_license ? `
              <div>
                <span class="text-slate-400 font-semibold">Data Policy:</span>
                <span class="text-emerald-300 text-[11px] ml-1">${m.data_license}</span>
              </div>
            ` : ''}
          </div>

          <!-- Key Scientific Payloads -->
          <div class="space-y-1.5 mb-3.5">
            <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400 flex items-center justify-between">
              <span>Scientific Payloads &amp; Sensors:</span>
              <span class="text-slate-500 font-normal">(${m.instruments.length} onboard)</span>
            </div>
            ${m.instruments.map(inst => `
              <div class="text-xs text-slate-300 flex items-start space-x-1.5 bg-space-900/40 p-1.5 rounded border border-slate-800/50">
                <span class="text-amber-400 font-bold font-mono shrink-0">${inst.id}:</span>
                <span class="text-slate-300"><strong class="text-slate-200">${inst.name}</strong> — <span class="text-slate-400">${inst.measures}</span></span>
              </div>
            `).join('')}
          </div>

          <!-- Primary Literature Citation -->
          ${m.primary_citation ? `
            <div class="p-2.5 rounded-lg bg-space-900/50 border border-slate-800 text-[11px] text-slate-400 space-y-1">
              <div class="font-semibold text-slate-300 flex items-center space-x-1.5">
                <i class="fa-solid fa-graduation-cap text-sky-400"></i>
                <span>Primary Literature Citation:</span>
              </div>
              <p class="italic text-slate-400 leading-snug">${m.primary_citation}</p>
            </div>
          ` : ''}
        </div>

        <!-- Card Footer Actions: DOI & Official Data Portal -->
        <div class="pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2">
          ${m.doi ? `
            <a href="https://doi.org/${m.doi}" target="_blank" rel="noopener" class="text-sky-400 hover:text-sky-300 text-xs font-mono flex items-center space-x-1 bg-sky-950/50 hover:bg-sky-900/50 px-2.5 py-1 rounded border border-sky-800/40 transition">
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
              <span>DOI: ${m.doi}</span>
            </a>
          ` : `<span></span>`}

          ${m.data_portal_url ? `
            <a href="${m.data_portal_url}" target="_blank" rel="noopener" class="text-emerald-400 hover:text-emerald-300 text-xs font-semibold flex items-center space-x-1.5 bg-emerald-950/50 hover:bg-emerald-900/50 px-3 py-1 rounded border border-emerald-800/40 transition">
              <i class="fa-solid fa-satellite-dish text-[11px]"></i>
              <span>Official Data Portal</span>
            </a>
          ` : ''}
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
      <div id="card-event-${ev.id}" onclick="selectEvent('${ev.id}')" class="event-benchmark-card cursor-pointer bg-space-900/90 hover:bg-space-800 p-3 rounded-xl border border-slate-800 hover:border-sky-400/80 transition shadow-md flex flex-col justify-between">
        <div>
          <div class="flex items-center space-x-1.5 text-xs font-bold font-mono mb-1" style="color: ${ev.badge_color || '#f43f5e'}">
            <i class="fa-solid ${ev.icon}"></i>
            <span class="text-[10px]">${ev.severity}</span>
          </div>
          <div class="text-[11px] font-bold text-slate-200 leading-snug">${ev.title}</div>
        </div>
        <div class="mt-2 text-[10px] text-slate-500 font-mono flex items-center justify-between border-t border-slate-800/60 pt-1">
          <span>Benchmark</span>
          <i class="fa-solid fa-chevron-right text-[9px] text-slate-500"></i>
        </div>
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
    // Highlight active card
    document.querySelectorAll('.event-benchmark-card').forEach(el => {
      el.classList.remove('border-sky-400', 'bg-space-800', 'ring-1', 'ring-sky-400/50');
      el.classList.add('border-slate-800', 'bg-space-900/90');
    });
    const activeCard = document.getElementById(`card-event-${eventId}`);
    if (activeCard) {
      activeCard.classList.remove('border-slate-800', 'bg-space-900/90');
      activeCard.classList.add('border-sky-400', 'bg-space-800', 'ring-1', 'ring-sky-400/50');
    }

    const res = await fetch(`/api/event/${eventId}`);
    const ev = await res.json();
    const meta = ev.metadata;

    document.getElementById('event-title').innerText = meta.title;
    document.getElementById('event-desc').innerText = meta.summary;
    document.getElementById('event-peak-kp').innerText = meta.peak_kp;
    document.getElementById('event-min-bz').innerText = `${meta.min_bz} nT`;
    document.getElementById('event-peak-v').innerText = `${meta.peak_speed} km/s`;
    document.getElementById('event-peak-pdyn').innerText = `${meta.peak_dyn_pressure} nPa`;

    const sevBadge = document.getElementById('event-severity-badge');
    if (sevBadge) {
      const isExtreme = meta.peak_kp >= 9.0;
      sevBadge.innerText = isExtreme ? `Extreme G5 (Kp=${meta.peak_kp})` : (meta.peak_kp >= 8.0 ? `Severe G4 (Kp=${meta.peak_kp})` : `Nominal (Kp=${meta.peak_kp})`);
      sevBadge.className = `px-3 py-1 rounded-full text-xs font-bold ${isExtreme ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' : 'bg-amber-500/20 text-amber-400 border border-amber-500/30'}`;
    }

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
    const satSelect = document.getElementById('turbulence-sat-select');
    const paramSelect = document.getElementById('turbulence-param-select');
    const spanSelect = document.getElementById('turbulence-span-select');

    const sat = satSelect ? satSelect.value : 'DSCOVR';
    const param = paramSelect ? paramSelect.value : 'bz_gsm';
    const span = spanSelect ? spanSelect.value : '1';

    const res = await fetch(`/api/spectrum?mission_id=${sat}&parameter=${param}&span_days=${span}`);
    const psd = await res.json();
    const ctx = document.getElementById('chart-spectrum')?.getContext('2d');
    if (!ctx || !psd.frequencies_hz) return;

    // Update Diagnostics HUD cards
    const alphaEl = document.getElementById('psd-stat-alpha');
    const regimeEl = document.getElementById('psd-stat-regime');
    const r2El = document.getElementById('psd-stat-r2');
    const rmsEl = document.getElementById('psd-stat-rms');
    const rmsUnitEl = document.getElementById('psd-stat-rms-unit');
    const taylorKmEl = document.getElementById('psd-stat-taylor-km');
    const taylorReEl = document.getElementById('psd-stat-taylor-re');

    if (alphaEl) alphaEl.innerText = psd.spectral_slope_alpha !== undefined ? psd.spectral_slope_alpha.toFixed(2) : '---';
    if (regimeEl) {
      regimeEl.innerText = psd.cascade_regime || 'Inertial Cascade';
      const a = psd.spectral_slope_alpha || 1.67;
      regimeEl.className = `text-[11px] font-semibold mt-1 truncate ${a >= 1.55 && a <= 1.80 ? 'text-cyan-400' : (a >= 1.4 && a < 1.55 ? 'text-emerald-400' : 'text-amber-400')}`;
    }
    if (r2El) r2El.innerText = psd.r_squared !== undefined ? psd.r_squared.toFixed(2) : '---';
    if (rmsEl) rmsEl.innerText = psd.fluctuation_rms !== undefined ? psd.fluctuation_rms.toFixed(2) : '---';
    if (rmsUnitEl) {
      rmsUnitEl.innerText = param === 'speed' ? 'km/s' : (param === 'density' ? 'cm⁻³' : 'nT');
    }
    if (taylorKmEl) taylorKmEl.innerText = psd.taylor_scale_km_1mhz ? psd.taylor_scale_km_1mhz.toLocaleString() : '---';
    if (taylorReEl) taylorReEl.innerText = psd.taylor_scale_re_1mhz !== undefined ? psd.taylor_scale_re_1mhz : '--';

    if (chartSpectrum) chartSpectrum.destroy();

    const unit = param === 'speed' ? '(km/s)²/Hz' : (param === 'density' ? '(cm⁻³)²/Hz' : 'nT²/Hz');

    const datasets = [
      {
        label: `Observed PSD [${sat} • ${param}] (${unit})`,
        data: psd.power_density,
        borderColor: '#a855f7',
        backgroundColor: 'rgba(168, 85, 247, 0.12)',
        fill: true,
        borderWidth: 2.0,
        pointRadius: 0,
        tension: 0.1
      }
    ];

    if (psd.kolmogorov_psd && psd.kolmogorov_psd.length === psd.frequencies_hz.length) {
      datasets.push({
        label: 'Kolmogorov Inertial Cascade (f⁻⁵/³)',
        data: psd.kolmogorov_psd,
        borderColor: '#38bdf8',
        borderWidth: 1.6,
        borderDash: [5, 5],
        fill: false,
        pointRadius: 0
      });
    }

    if (psd.iroshnikov_psd && psd.iroshnikov_psd.length === psd.frequencies_hz.length) {
      datasets.push({
        label: 'Iroshnikov-Kraichnan MHD (f⁻³/²)',
        data: psd.iroshnikov_psd,
        borderColor: '#10b981',
        borderWidth: 1.6,
        borderDash: [3, 4],
        fill: false,
        pointRadius: 0
      });
    }

    chartSpectrum = new Chart(ctx, {
      type: 'line',
      data: {
        labels: psd.frequencies_hz.map(f => (f * 1000).toFixed(2) + ' mHz'),
        datasets: datasets
      },
      options: {
        ...darkChartOptions,
        scales: {
          x: {
            ...darkChartOptions.scales.x,
            title: { display: true, text: 'Frequency (mHz) — [Taylor frozen scale λ = v_sw / f]', color: '#94a3b8' }
          },
          y: {
            ...darkChartOptions.scales.y,
            type: 'logarithmic',
            title: { display: true, text: `Power Spectral Density (${unit})`, color: '#94a3b8' }
          }
        },
        plugins: {
          ...darkChartOptions.plugins,
          tooltip: {
            callbacks: {
              label: function(context) {
                return `${context.dataset.label}: ${context.raw.toExponential(3)}`;
              }
            }
          }
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

function toggleOrbitGrid(show) {
  if (orbitViewer) orbitViewer.setGseGrid(show);
}

function toggleOrbitSat(key, visible) {
  if (orbitViewer) orbitViewer.setSatelliteVisibility(key, visible);
}

function toggleAllOrbitSatellites(visible) {
  if (orbitViewer) orbitViewer.toggleAllSatellites(visible);
  ['DSCOVR', 'ACE', 'ADITYA_L1', 'WIND', 'SOHO', 'GOES_16', 'STEREO_A'].forEach(k => {
    const chk = document.getElementById(`orbit-chk-${k}`);
    if (chk) chk.checked = visible;
  });
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

// SPACE WEATHER BULLETIN & EXECUTIVE SUMMARY SYSTEM
let currentBulletinFormat = 'html';
let bulletinCache = { html: '', md: '', sat: '' };

async function openBulletinModal() {
  const modal = document.getElementById('bulletin-modal');
  if (!modal) return;
  modal.classList.remove('hidden');
  window.playBlip?.();

  const satSelect = document.getElementById('telemetry-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';

  const container = document.getElementById('bulletin-content');
  if (container) {
    container.innerHTML = '<div class="text-center text-slate-400 py-12"><i class="fa-solid fa-spinner fa-spin mr-2"></i> Generating scientific space weather bulletin...</div>';
  }

  try {
    const [resHtml, resMd] = await Promise.all([
      fetch(`/api/report/html?mission_id=${sat}`),
      fetch(`/api/report/markdown?mission_id=${sat}`)
    ]);
    bulletinCache.html = await resHtml.text();
    bulletinCache.md = await resMd.text();
    bulletinCache.sat = sat;

    renderBulletinContent();
  } catch (err) {
    if (container) container.innerHTML = `<div class="text-rose-400 p-4">Failed to generate bulletin: ${err.message}</div>`;
  }
}

function setBulletinViewFormat(fmt) {
  currentBulletinFormat = fmt;
  const btnHtml = document.getElementById('btn-bulletin-fmt-html');
  const btnMd = document.getElementById('btn-bulletin-fmt-md');
  if (btnHtml && btnMd) {
    if (fmt === 'html') {
      btnHtml.className = 'px-3 py-1 rounded-md bg-sky-600 text-white font-semibold transition shadow-sm';
      btnMd.className = 'px-3 py-1 rounded-md text-slate-400 hover:text-white font-semibold transition';
    } else {
      btnHtml.className = 'px-3 py-1 rounded-md text-slate-400 hover:text-white font-semibold transition';
      btnMd.className = 'px-3 py-1 rounded-md bg-sky-600 text-white font-semibold transition shadow-sm';
    }
  }
  renderBulletinContent();
}

function renderBulletinContent() {
  const container = document.getElementById('bulletin-content');
  if (!container) return;

  if (currentBulletinFormat === 'html') {
    container.innerHTML = bulletinCache.html;
  } else {
    // High-contrast clean monospace Markdown view
    container.innerHTML = `<pre class="bg-space-950 p-4 rounded-xl border border-slate-800 text-slate-200 text-xs font-mono leading-relaxed whitespace-pre-wrap select-text">${escapeHtmlReport(bulletinCache.md)}</pre>`;
  }
}

function escapeHtmlReport(text) {
  if (!text) return '';
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function closeBulletinModal() {
  const modal = document.getElementById('bulletin-modal');
  if (modal) modal.classList.add('hidden');
}

function downloadBulletinHTML() {
  const satSelect = document.getElementById('telemetry-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  window.location.href = `/api/report/html?mission_id=${sat}&download=true`;
}

function downloadExecutiveSummaryMD() {
  const satSelect = document.getElementById('telemetry-satellite-select');
  const sat = satSelect ? satSelect.value : 'DSCOVR';
  window.location.href = `/api/report/markdown?mission_id=${sat}&download=true`;
}

async function copyExecutiveSummaryMarkdown() {
  try {
    let md = bulletinCache.md;
    if (!md) {
      const satSelect = document.getElementById('telemetry-satellite-select');
      const sat = satSelect ? satSelect.value : 'DSCOVR';
      const res = await fetch(`/api/report/markdown?mission_id=${sat}`);
      md = await res.text();
      bulletinCache.md = md;
    }
    await navigator.clipboard.writeText(md);
    const label = document.getElementById('btn-copy-md-label');
    if (label) {
      const orig = label.innerText;
      label.innerText = 'Copied!';
      setTimeout(() => { label.innerText = orig; }, 2000);
    }
  } catch (err) {
    console.error('Clipboard copy error:', err);
  }
}

// =============================================================================
// SCIENTIFIC LITERATURE, DATA OBSERVATORIES & OPEN LICENSES SYSTEM
// =============================================================================
let referencesCache = null;
let currentRefTab = 'equations';
let refSearchQuery = '';

async function openReferencesModal(initialTab = 'equations') {
  const modal = document.getElementById('modal-references');
  if (!modal) return;
  modal.classList.remove('hidden');
  window.playBlip?.();

  currentRefTab = initialTab;
  refSearchQuery = '';
  const searchInput = document.getElementById('ref-search-input');
  if (searchInput) searchInput.value = '';

  updateRefTabButtons();

  if (!referencesCache) {
    try {
      const res = await fetch('/api/references');
      referencesCache = await res.json();
    } catch (err) {
      console.error('Error fetching references repository:', err);
      const body = document.getElementById('modal-references-body');
      if (body) {
        body.innerHTML = `<div class="p-6 text-center text-rose-400">Failed to load scientific references: ${err.message}</div>`;
      }
      return;
    }
  }

  renderReferencesContent();
}

function closeReferencesModal() {
  const modal = document.getElementById('modal-references');
  if (modal) modal.classList.add('hidden');
}

function switchReferencesTab(tabKey) {
  window.playBlip?.();
  currentRefTab = tabKey;
  refSearchQuery = '';
  const searchInput = document.getElementById('ref-search-input');
  if (searchInput) searchInput.value = '';
  updateRefTabButtons();
  renderReferencesContent();
}

function updateRefTabButtons() {
  const tabs = ['equations', 'providers', 'licenses', 'handbook'];
  tabs.forEach(t => {
    const btn = document.getElementById(`tab-btn-ref-${t}`);
    if (btn) {
      if (t === currentRefTab) {
        btn.className = 'px-3 py-1.5 rounded-lg font-semibold bg-sky-600 text-white transition flex items-center space-x-1.5 shadow-sm';
      } else {
        btn.className = 'px-3 py-1.5 rounded-lg font-semibold text-slate-400 hover:text-slate-200 transition flex items-center space-x-1.5';
      }
    }
  });
}

function onRefSearchInput(val) {
  refSearchQuery = (val || '').toLowerCase().trim();
  renderReferencesContent();
}

function showParameterDetail(paramKey) {
  openReferencesModal('handbook');
  refSearchQuery = (paramKey || '').toLowerCase();
  const searchInput = document.getElementById('ref-search-input');
  if (searchInput) searchInput.value = paramKey;
  renderReferencesContent();
}

function renderReferencesContent() {
  const body = document.getElementById('modal-references-body');
  if (!body || !referencesCache) return;

  if (currentRefTab === 'equations') {
    renderEquationsTab(body);
  } else if (currentRefTab === 'providers') {
    renderProvidersTab(body);
  } else if (currentRefTab === 'licenses') {
    renderLicensesTab(body);
  } else if (currentRefTab === 'handbook') {
    renderHandbookTab(body);
  }
}

function renderEquationsTab(container) {
  const refs = referencesCache.scientific_references || [];
  const q = refSearchQuery;
  const filtered = refs.filter(r => {
    if (!q) return true;
    return (
      (r.title && r.title.toLowerCase().includes(q)) ||
      (r.authors && r.authors.toLowerCase().includes(q)) ||
      (r.category && r.category.toLowerCase().includes(q)) ||
      (r.formula && r.formula.toLowerCase().includes(q)) ||
      (r.doi && r.doi.toLowerCase().includes(q)) ||
      (r.physical_meaning && r.physical_meaning.toLowerCase().includes(q))
    );
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No scientific papers matched "${refSearchQuery}".</div>`;
    return;
  }

  container.innerHTML = `
    <div class="mb-3 flex items-center justify-between text-xs text-slate-400">
      <span>Found <strong class="text-sky-400">${filtered.length}</strong> foundational peer-reviewed heliophysics papers:</span>
      <span class="text-[11px] text-slate-500">Direct DOI cross-references to original academic literature</span>
    </div>
    <div class="space-y-4">
      ${filtered.map(r => `
        <div class="bg-space-800/80 p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition shadow-lg space-y-3">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2.5">
            <span class="text-[11px] font-bold px-2.5 py-0.5 rounded bg-sky-950/80 text-sky-300 border border-sky-800/50 uppercase tracking-wider">${r.category}</span>
            <div class="text-xs text-slate-400 font-medium">
              <span class="text-slate-200 font-semibold">${r.journal}</span> (${r.year})
              ${r.volume ? `• Vol. ${r.volume}` : ''}
              ${r.pages ? `• pp. ${r.pages}` : ''}
            </div>
          </div>

          <div>
            <h4 class="text-sm font-bold text-slate-100">${r.title}</h4>
            <p class="text-xs text-slate-400 mt-1 font-medium"><i class="fa-solid fa-user-pen text-slate-500 mr-1.5"></i>${r.authors}</p>
          </div>

          <!-- Mathematical Formulation -->
          <div class="bg-space-950/90 p-3 rounded-lg border border-slate-800 font-mono text-xs space-y-1.5">
            <div class="text-[10px] uppercase font-bold tracking-wider text-amber-400 flex items-center space-x-1.5">
              <i class="fa-solid fa-square-root-variable"></i>
              <span>Governing Mathematical Formulation:</span>
            </div>
            <div class="text-amber-300 text-xs font-semibold pl-2 border-l-2 border-amber-500/50 py-0.5 overflow-x-auto">${r.formula}</div>
            ${r.parameters ? `
              <div class="text-[11px] text-slate-400 pt-1 border-t border-slate-800/80">
                <span class="font-bold text-slate-300">Variables:</span> ${r.parameters.join(' • ')}
              </div>
            ` : ''}
          </div>

          <!-- Physical Meaning -->
          <p class="text-xs text-slate-300 leading-relaxed"><strong class="text-slate-200">Physical Significance:</strong> ${r.physical_meaning}</p>

          <!-- Action Footer -->
          <div class="pt-2.5 border-t border-slate-800 flex flex-wrap items-center justify-between gap-2">
            ${r.doi ? `
              <a href="${r.doi_url || ('https://doi.org/' + r.doi)}" target="_blank" rel="noopener" class="text-sky-400 hover:text-sky-300 text-xs font-mono font-semibold flex items-center space-x-1.5 bg-sky-950/60 hover:bg-sky-900/60 px-3 py-1.5 rounded-lg border border-sky-800/50 transition shadow-sm">
                <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                <span>doi:${r.doi}</span>
              </a>
            ` : '<span></span>'}
            <span class="text-[11px] text-slate-500 font-mono">ID: ${r.id}</span>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderProvidersTab(container) {
  const providers = referencesCache.data_providers || [];
  const q = refSearchQuery;
  const filtered = providers.filter(p => {
    if (!q) return true;
    return (
      (p.name && p.name.toLowerCase().includes(q)) ||
      (p.agency && p.agency.toLowerCase().includes(q)) ||
      (p.country && p.country.toLowerCase().includes(q)) ||
      (p.data_license && p.data_license.toLowerCase().includes(q)) ||
      (p.terms_of_use && p.terms_of_use.toLowerCase().includes(q)) ||
      (p.data_products && p.data_products.some(prod => prod.toLowerCase().includes(q)))
    );
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No data observatories matched "${refSearchQuery}".</div>`;
    return;
  }

  container.innerHTML = `
    <div class="mb-3 flex items-center justify-between text-xs text-slate-400">
      <span>Active Open Science Observatories &amp; Data Centers (<strong class="text-emerald-400">${filtered.length}</strong>):</span>
      <span class="text-[11px] text-slate-500">Live operational &amp; archival scientific portals</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      ${filtered.map(p => `
        <div class="bg-space-800/80 p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition shadow-lg flex flex-col justify-between space-y-4">
          <div>
            <div class="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-slate-800">
              <span class="text-xs font-bold px-2.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/50">${p.id}</span>
              <div class="flex items-center space-x-2">
                <span class="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700">${p.country}</span>
                <span class="text-[10px] font-semibold px-2 py-0.5 rounded bg-sky-950/80 text-sky-300 border border-sky-800/40">${p.license_badge || 'Open Data'}</span>
              </div>
            </div>

            <h4 class="text-sm font-bold text-slate-100">${p.name}</h4>
            <p class="text-xs text-slate-400 mb-3 font-medium">${p.agency}</p>

            <div class="space-y-1.5 mb-3.5">
              <div class="text-[11px] font-bold uppercase tracking-wider text-slate-400">Data Products &amp; Telemetry Sets:</div>
              ${p.data_products ? p.data_products.map(prod => `
                <div class="text-xs text-slate-300 flex items-start space-x-1.5 bg-space-950/60 p-1.5 rounded border border-slate-800/50">
                  <i class="fa-solid fa-satellite-dish text-sky-400 text-[10px] mt-0.5 shrink-0"></i>
                  <span>${prod}</span>
                </div>
              `).join('') : ''}
            </div>

            <div class="p-2.5 rounded-lg bg-space-900/60 border border-slate-800 text-[11px] text-slate-400 space-y-1">
              <div class="font-semibold text-slate-300 flex items-center space-x-1.5">
                <i class="fa-solid fa-scale-balanced text-emerald-400"></i>
                <span>License &amp; Terms of Use:</span>
              </div>
              <p class="text-slate-300 leading-snug"><strong class="text-emerald-300">${p.data_license}</strong>: ${p.terms_of_use}</p>
            </div>
          </div>

          <div class="pt-2 border-t border-slate-800 flex justify-end">
            <a href="${p.url}" target="_blank" rel="noopener" class="text-emerald-400 hover:text-emerald-300 text-xs font-semibold flex items-center space-x-1.5 bg-emerald-950/60 hover:bg-emerald-900/60 px-3 py-1.5 rounded-lg border border-emerald-800/50 transition">
              <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
              <span>Access Official Portal</span>
            </a>
          </div>
        </div>
      `).join('')}
    </div>
  `;
}

function renderLicensesTab(container) {
  container.innerHTML = `
    <div class="space-y-5">
      <div class="bg-space-950/80 p-4 rounded-xl border border-emerald-500/30">
        <div class="flex items-center space-x-2 text-emerald-400 font-bold text-sm mb-1">
          <i class="fa-solid fa-certificate"></i>
          <span>Open Science &amp; Multi-Agency Data Compliance Framework</span>
        </div>
        <p class="text-xs text-slate-300 leading-relaxed">
          HELIOS-L1 integrates observational data from six premier sovereign space agencies and institutes. All telemetry access strictly adheres to the open data policies, academic fair use charters, and Creative Commons licensing established by each provider.
        </p>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- NOAA -->
        <div class="bg-space-800/80 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-slate-100 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
              <span>NOAA Space Weather Prediction Center</span>
            </h4>
            <span class="text-[10px] px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">Public Domain</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">
            <strong>Policy:</strong> U.S. Federal Government Works (17 U.S.C. § 105). Data is in the public domain worldwide and may be distributed, processed, and utilized freely for commercial, educational, and scientific endeavors.
          </p>
          <div class="text-[11px] text-slate-400 bg-space-950 p-2 rounded border border-slate-800 font-mono">
            Attribution: NOAA Space Weather Prediction Center (SWPC), Boulder, Colorado, USA.
          </div>
        </div>

        <!-- NASA -->
        <div class="bg-space-800/80 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-slate-100 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-cyan-400"></span>
              <span>NASA CDAWeb / SPDF</span>
            </h4>
            <span class="text-[10px] px-2 py-0.5 rounded bg-cyan-950 text-cyan-300 border border-cyan-800">CC0 1.0 Universal</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">
            <strong>Policy:</strong> NASA Open Data Policy &amp; Creative Commons CC0 1.0 Universal Public Domain Dedication. Archival solar wind sets from ACE, WIND, and OMNI are freely accessible.
          </p>
          <div class="text-[11px] text-slate-400 bg-space-950 p-2 rounded border border-slate-800 font-mono">
            Attribution: NASA Goddard Space Flight Center Space Physics Data Facility (SPDF) / CDAWeb.
          </div>
        </div>

        <!-- ISRO -->
        <div class="bg-space-800/80 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-slate-100 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-amber-400"></span>
              <span>ISRO Aditya-L1 / ISSDC PRADAN</span>
            </h4>
            <span class="text-[10px] px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">ISRO Open Science</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">
            <strong>Policy:</strong> ISRO Science Data Policy for Aditya-L1 Payloads. Data is released via PRADAN for academic research, education, and international heliophysics collaborative studies.
          </p>
          <div class="text-[11px] text-slate-400 bg-space-950 p-2 rounded border border-slate-800 font-mono">
            Attribution: Indian Space Research Organisation (ISRO) &amp; Aditya-L1 Science Teams (ASPEX, PAPA, MAG, VELC).
          </div>
        </div>

        <!-- ESA -->
        <div class="bg-space-800/80 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-slate-100 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-purple-400"></span>
              <span>European Space Agency (ESA) SOAR</span>
            </h4>
            <span class="text-[10px] px-2 py-0.5 rounded bg-purple-950 text-purple-300 border border-purple-800">CC-BY-SA 3.0 IGO</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">
            <strong>Policy:</strong> ESA Open Access Policy under Creative Commons Attribution-ShareAlike 3.0 Intergovernmental Organisation (CC-BY-SA 3.0 IGO).
          </p>
          <div class="text-[11px] text-slate-400 bg-space-950 p-2 rounded border border-slate-800 font-mono">
            Attribution: European Space Agency (ESA) Solar and Heliospheric Science Archive (SOAR / ESAC).
          </div>
        </div>

        <!-- GFZ -->
        <div class="bg-space-800/80 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-slate-100 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-rose-400"></span>
              <span>GFZ German Research Centre for Geosciences</span>
            </h4>
            <span class="text-[10px] px-2 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-800">CC-BY 4.0</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">
            <strong>Policy:</strong> Creative Commons Attribution 4.0 International (CC-BY 4.0). Real-time and definitive planetary Kp geomagnetic indices.
          </p>
          <div class="text-[11px] text-slate-400 bg-space-950 p-2 rounded border border-slate-800 font-mono">
            Citation: Matzka, J., et al. (2021). The Geomagnetic Kp Index. doi:10.5880/Hpo.0001.
          </div>
        </div>

        <!-- WDC Kyoto -->
        <div class="bg-space-800/80 p-4 rounded-xl border border-slate-800 space-y-2">
          <div class="flex items-center justify-between">
            <h4 class="text-xs font-bold text-slate-100 flex items-center space-x-2">
              <span class="w-2 h-2 rounded-full bg-blue-400"></span>
              <span>WDC for Geomagnetism, Kyoto University</span>
            </h4>
            <span class="text-[10px] px-2 py-0.5 rounded bg-blue-950 text-blue-300 border border-blue-800">ICSU Fair Use</span>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed">
            <strong>Policy:</strong> ICSU World Data System Fair Use Policy. Definitive and quicklook ring current Dst and Auroral Electrojet (AE) indices.
          </p>
          <div class="text-[11px] text-slate-400 bg-space-950 p-2 rounded border border-slate-800 font-mono">
            Attribution: World Data Center for Geomagnetism, Kyoto, Japan (Sugiura &amp; Kamei).
          </div>
        </div>
      </div>
    </div>
  `;
}

function renderHandbookTab(container) {
  const params = referencesCache.parameter_definitions || {};
  const q = refSearchQuery;
  const entries = Object.entries(params).filter(([k, v]) => {
    if (!q) return true;
    return (
      k.toLowerCase().includes(q) ||
      (v.name && v.name.toLowerCase().includes(q)) ||
      (v.symbol && v.symbol.toLowerCase().includes(q)) ||
      (v.unit && v.unit.toLowerCase().includes(q)) ||
      (v.formula && v.formula.toLowerCase().includes(q)) ||
      (v.description && v.description.toLowerCase().includes(q)) ||
      (v.instrument && v.instrument.toLowerCase().includes(q))
    );
  });

  if (entries.length === 0) {
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No physical parameters matched "${refSearchQuery}".</div>`;
    return;
  }

  container.innerHTML = `
    <div class="mb-3 flex items-center justify-between text-xs text-slate-400">
      <span>Physical Parameters &amp; Sensor Origins (<strong class="text-sky-400">${entries.length}</strong>):</span>
      <span class="text-[11px] text-slate-500">Standardized heliophysics units, typical ranges, and formulations</span>
    </div>
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      ${entries.map(([k, p]) => `
        <div id="param-card-${k}" class="bg-space-800/80 p-5 rounded-xl border border-slate-800 hover:border-sky-500/50 transition shadow-lg flex flex-col justify-between space-y-3">
          <div>
            <div class="flex items-center justify-between gap-2 mb-2 pb-2 border-b border-slate-800">
              <div class="flex items-baseline space-x-2">
                <span class="font-hud font-black text-lg text-sky-400">${p.symbol}</span>
                <span class="text-xs font-hud text-slate-400 font-semibold">[${p.unit}]</span>
              </div>
              <span class="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 text-slate-300 border border-slate-700">${k}</span>
            </div>

            <h4 class="text-sm font-bold text-slate-100 mb-2">${p.name}</h4>

            <div class="grid grid-cols-1 gap-1.5 text-xs bg-space-950/70 p-3 rounded-lg border border-slate-800 mb-3 font-sans">
              <div>
                <span class="text-slate-400 font-semibold">Nominal Solar Wind:</span>
                <span class="text-emerald-300 text-[11px] ml-1 font-medium">${p.nominal_range}</span>
              </div>
              <div>
                <span class="text-slate-400 font-semibold">Disturbed / Storm:</span>
                <span class="text-rose-300 text-[11px] ml-1 font-medium">${p.disturbed_range}</span>
              </div>
              ${p.formula ? `
                <div class="pt-1 border-t border-slate-800 font-mono text-[11px] text-amber-300">
                  <span class="text-slate-400 font-semibold">Equation:</span> ${p.formula}
                </div>
              ` : ''}
              ${p.instrument ? `
                <div class="pt-1 border-t border-slate-800 text-[11px] text-slate-300">
                  <span class="text-slate-400 font-semibold">Payload Sensors:</span> ${p.instrument}
                </div>
              ` : ''}
            </div>

            <p class="text-xs text-slate-300 leading-relaxed">${p.description}</p>
          </div>

          ${p.doi ? `
            <div class="pt-2 border-t border-slate-800 flex justify-end">
              <a href="https://doi.org/${p.doi}" target="_blank" rel="noopener" class="text-sky-400 hover:text-sky-300 text-xs font-mono font-semibold flex items-center space-x-1 bg-sky-950/50 hover:bg-sky-900/50 px-2.5 py-1 rounded border border-sky-800/40 transition">
                <i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i>
                <span>doi:${p.doi}</span>
              </a>
            </div>
          ` : ''}
        </div>
      `).join('')}
    </div>
  `;
}

// =============================================================================
// TERRESTRIAL HAZARDS, D-RAP IONOSPHERE & SOLAR CYCLE 25 ENGINE
// =============================================================================
let chartSolarCycle = null;
let chartDrapSpectrum = null;
let currentDrapXray = 1e-4;
let currentDrapZenith = 30.0;
let currentGicDbDt = 180.0;
let currentGicGeology = 'precambrian_shield';

async function loadHazardsAndCycle() {
  try {
    const [resCycle, resDrap, resGic] = await Promise.all([
      fetch('/api/solar_cycle'),
      fetch(`/api/ionosphere/absorption?xray_flux=${currentDrapXray}&zenith_angle=${currentDrapZenith}`),
      fetch(`/api/gic/hazard?db_dt=${currentGicDbDt}&geology=${currentGicGeology}`)
    ]);

    const sc = await resCycle.json();
    const drap = await resDrap.json();
    const gic = await resGic.json();

    // 1. Update Solar Cycle 25 Gauges
    const ssnEl = document.getElementById('sc25-ssn');
    if (ssnEl) ssnEl.innerText = sc.smoothed_sunspot_number;

    const f107El = document.getElementById('sc25-f107');
    if (f107El) f107El.innerText = sc.f107_radio_flux_sfu;

    const progEl = document.getElementById('sc25-progress');
    if (progEl) progEl.innerText = `${sc.cycle_progress_percent}%`;

    const progBar = document.getElementById('sc25-progress-bar');
    if (progBar) progBar.style.width = `${sc.cycle_progress_percent}%`;

    const revEl = document.getElementById('sc25-reversal');
    if (revEl) revEl.innerText = sc.polar_magnetic_reversal;

    renderSolarCycleChart(sc.timeline || []);

    // 2. Update D-RAP Absorption Metrics
    updateDrapReadouts(drap);
    renderDrapSpectrumChart(drap.absorption_spectrum || []);

    // 3. Update GIC Hazard Metrics
    updateGicReadouts(gic);

  } catch (err) {
    console.error('Error loading terrestrial hazards & solar cycle:', err);
  }
}

function updateDrapReadouts(drap) {
  const rScaleEl = document.getElementById('drap-r-scale');
  if (rScaleEl) rScaleEl.innerText = drap.r_scale;

  const hazDescEl = document.getElementById('drap-hazard-desc');
  if (hazDescEl) hazDescEl.innerText = drap.hazard_level;

  const hafEl = document.getElementById('drap-haf');
  if (hafEl) hafEl.innerText = `${drap.highest_affected_frequency_mhz} MHz`;

  const att10El = document.getElementById('drap-att10');
  if (att10El) att10El.innerText = `${drap.attenuation_at_10mhz_db} dB`;

  const atcEl = document.getElementById('drap-atc-impact');
  if (atcEl) atcEl.innerText = drap.polar_aviation_impact;
}

function updateGicReadouts(gic) {
  const eFieldEl = document.getElementById('gic-efield');
  if (eFieldEl) {
    eFieldEl.innerText = `${gic.geoelectric_field_v_km} V/km`;
    eFieldEl.style.color = gic.status_color || '#38bdf8';
  }

  const vEl = document.getElementById('gic-voltage');
  if (vEl) vEl.innerText = `${gic.induced_voltage_volts} V`;

  const ampsEl = document.getElementById('gic-neutral-amps');
  if (ampsEl) ampsEl.innerText = `${gic.transformer_neutral_current_amps} A`;

  const statEl = document.getElementById('gic-hazard-status');
  if (statEl) {
    statEl.innerText = gic.hazard_classification;
    statEl.style.color = gic.status_color || '#eab308';
  }

  const descEl = document.getElementById('gic-hazard-desc');
  if (descEl) descEl.innerText = gic.grid_impact_assessment;
}

async function setDrapXrayPreset(flux) {
  currentDrapXray = flux;
  try {
    const res = await fetch(`/api/ionosphere/absorption?xray_flux=${currentDrapXray}&zenith_angle=${currentDrapZenith}`);
    const drap = await res.json();
    updateDrapReadouts(drap);
    renderDrapSpectrumChart(drap.absorption_spectrum || []);
    window.playBlip?.();
  } catch (err) {
    console.error('Error updating D-RAP X-ray preset:', err);
  }
}

async function onDrapZenithChange(deg) {
  currentDrapZenith = parseFloat(deg);
  const valEl = document.getElementById('drap-zenith-val');
  if (valEl) valEl.innerText = `${currentDrapZenith}°`;

  try {
    const res = await fetch(`/api/ionosphere/absorption?xray_flux=${currentDrapXray}&zenith_angle=${currentDrapZenith}`);
    const drap = await res.json();
    updateDrapReadouts(drap);
    renderDrapSpectrumChart(drap.absorption_spectrum || []);
  } catch (err) {
    console.error('Error updating D-RAP zenith angle:', err);
  }
}

async function onGicDbDtChange(val) {
  currentGicDbDt = parseFloat(val);
  const valEl = document.getElementById('gic-dbdt-val');
  if (valEl) valEl.innerText = `${currentGicDbDt} nT/min`;

  try {
    const res = await fetch(`/api/gic/hazard?db_dt=${currentGicDbDt}&geology=${currentGicGeology}`);
    const gic = await res.json();
    updateGicReadouts(gic);
  } catch (err) {
    console.error('Error updating GIC dB/dt:', err);
  }
}

async function onGicGeologyChange(geology) {
  currentGicGeology = geology;
  try {
    const res = await fetch(`/api/gic/hazard?db_dt=${currentGicDbDt}&geology=${currentGicGeology}`);
    const gic = await res.json();
    updateGicReadouts(gic);
    window.playBlip?.();
  } catch (err) {
    console.error('Error updating GIC geology:', err);
  }
}

function renderSolarCycleChart(timeline) {
  const ctx = document.getElementById('chart-solar-cycle')?.getContext('2d');
  if (!ctx || !timeline || timeline.length === 0) return;

  if (chartSolarCycle) chartSolarCycle.destroy();

  const labels = timeline.map(t => t.year_month);
  const ssnVals = timeline.map(t => t.ssn_smoothed);
  const c24Vals = timeline.map(t => t.cycle_24_comparison_ssn);

  chartSolarCycle = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Solar Cycle 25 (Observed / Modeled SSN)',
          data: ssnVals,
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245, 158, 11, 0.15)',
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3
        },
        {
          label: 'Cycle 24 Baseline (Smoothed SSN Comparison)',
          data: c24Vals,
          borderColor: '#64748b',
          borderDash: [4, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3
        }
      ]
    },
    options: {
      ...darkChartOptions,
      scales: {
        x: {
          ...darkChartOptions.scales.x,
          ticks: {
            ...darkChartOptions.scales.x.ticks,
            maxTicksLimit: 12
          }
        },
        y: {
          ...darkChartOptions.scales.y,
          title: { display: true, text: 'Smoothed Sunspot Number', color: '#94a3b8' }
        }
      }
    }
  });
}

function renderDrapSpectrumChart(spectrum) {
  const ctx = document.getElementById('chart-drap-spectrum')?.getContext('2d');
  if (!ctx || !spectrum || spectrum.length === 0) return;

  if (chartDrapSpectrum) chartDrapSpectrum.destroy();

  const freqs = spectrum.map(s => `${s.frequency_mhz} MHz`);
  const atts = spectrum.map(s => s.attenuation_db);

  chartDrapSpectrum = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: freqs,
      datasets: [
        {
          label: 'HF Signal Attenuation (dB)',
          data: atts,
          backgroundColor: atts.map(a => a >= 10.0 ? 'rgba(244, 63, 94, 0.75)' : (a >= 3.0 ? 'rgba(245, 158, 11, 0.75)' : 'rgba(56, 189, 248, 0.65)')),
          borderColor: atts.map(a => a >= 10.0 ? '#f43f5e' : (a >= 3.0 ? '#f59e0b' : '#38bdf8')),
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      ...darkChartOptions,
      scales: {
        x: darkChartOptions.scales.x,
        y: {
          ...darkChartOptions.scales.y,
          beginAtZero: true,
          title: { display: true, text: 'Signal Attenuation [dB]', color: '#f43f5e' }
        }
      }
    }
  });
}

/* ========================================================================= */
/* KEYBOARD SHORTCUTS & MODAL MANAGEMENT                                    */
/* ========================================================================= */

function openShortcutsModal() {
  const m = document.getElementById('modal-shortcuts');
  if (m) m.classList.remove('hidden');
}

function closeShortcutsModal() {
  const m = document.getElementById('modal-shortcuts');
  if (m) m.classList.add('hidden');
}

function toggleShortcutsModal() {
  const m = document.getElementById('modal-shortcuts');
  if (m) {
    if (m.classList.contains('hidden')) {
      m.classList.remove('hidden');
    } else {
      m.classList.add('hidden');
    }
  }
}

function closeAllModals() {
  closeBulletinModal();
  closeReferencesModal();
  closeShortcutsModal();
  const paramModal = document.getElementById('modal-parameter');
  if (paramModal) paramModal.classList.add('hidden');
}

// Global hotkeys listener
window.addEventListener('keydown', (e) => {
  const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    if (e.key === 'Escape') closeAllModals();
    return;
  }

  if (e.key === 'Escape') {
    closeAllModals();
  } else if (e.key === '?' || (e.key === '/' && e.shiftKey) || e.key === 'F1') {
    e.preventDefault();
    toggleShortcutsModal();
  } else if (e.key === '1') {
    switchDomain('fleet');
  } else if (e.key === '2') {
    switchDomain('heliosphere');
  } else if (e.key === '3') {
    switchDomain('geospace');
  } else if (e.key === '4') {
    switchDomain('data');
  } else if (e.key === 'r' || e.key === 'R') {
    refreshCurrentView();
  } else if (e.key === 'a' || e.key === 'A') {
    toggleAudio();
  } else if (e.key === 'b' || e.key === 'B') {
    openBulletinModal();
  } else if (e.key === 'p' || e.key === 'P') {
    openReferencesModal();
  } else if (e.key === 't' || e.key === 'T') {
    toggleClockMode();
  }
});
