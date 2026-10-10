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
let chartEventDst = null;
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
let selectedTimezone = localStorage.getItem('helios_timezone') || 'UTC';
let currentTheme = localStorage.getItem('helios_theme') || 'mission-slate';
let currentFontSize = localStorage.getItem('helios_fontsize') || 'normal';
let currentProcessors = parseInt(localStorage.getItem('helios_processors') || '4', 10);
let totalCpuCores = 8;

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
    context: 'DOMAIN: GEOSPACE & HAZARDS // STARKOV OVAL, STORM FORECAST, D-RAP & GIC',
    views: [
      { id: 'aurora', label: 'Auroral Oval & Map', icon: 'fa-earth-americas', color: 'text-emerald-400' },
      { id: 'forecast', label: 'Storm Forecast', icon: 'fa-chart-line', color: 'text-blue-400' },
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
      { id: 'analysis', label: 'Event Analysis', icon: 'fa-microscope', color: 'text-indigo-400' },
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
  analysis: 'data',
  references: 'data'
};

document.addEventListener('DOMContentLoaded', () => {
  initSettingsAndPreferences();
  startClock();
  renderSubnav('fleet');
  initCharts();
  loadTelemetry();
  loadMissions();
  loadEvents();
  initOrbits();
  animateOrbits();
  initVisualizers();
  missionIncidentLogger = new MissionIncidentLogger();
  keepNavBelowHeader();
  keepUnitCase();
  document.getElementById('settings-auto-update')?.addEventListener('change', e => { e.target.dataset.touched = '1'; });
  showSettingsReview();

  // Click on the dark backdrop closes a dialog (three of these ids were wrong, so the guide, shortcuts
  // and incident dialogs ignored backdrop clicks).
  ['modal-settings', 'modal-about', 'modal-timezone', 'modal-shortcuts', 'modal-incidents', 'modal-references', 'bulletin-modal'].forEach(id => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener('click', (e) => {
        if (e.target === el) closeAllModals();
      });
    }
  });
});

// What's new after an update and what changed in the settings since the version the user
// last reviewed (GET /api/settings/review). Shown once per version; nothing stored is changed
// until the user keeps or changes the values.
const SETTING_LABELS = { processors: 'Worker threads', theme: 'Theme', font_size: 'Text size',
  timezone: 'Time zone', auto_update: 'Automatic updates' };
let settingsReview = null;

function describeRule(rule) {
  if (Array.isArray(rule)) return rule.map(v => (v === true ? 'on' : v === false ? 'off' : String(v))).join(', ');
  if (rule && typeof rule === 'object' && 'min' in rule) return `${rule.min} to ${rule.max}`;
  return String(rule ?? '');
}

function describeValue(v) {
  if (v === true) return 'on';
  if (v === false) return 'off';
  if (v === null || v === undefined) return '(not stored)';
  return typeof v === 'object' ? JSON.stringify(v) : String(v);
}

function reviewControl(key, rule, value) {
  const id = `review-input-${key}`;
  const cls = 'rounded px-2 py-1 text-xs font-mono bg-slate-950 border border-slate-700 text-slate-200';
  if (Array.isArray(rule)) {
    const opts = rule.map(v => `<option value="${escapeHtml(JSON.stringify(v))}" ${v === value ? 'selected' : ''}>${escapeHtml(describeValue(v))}</option>`).join('');
    return `<select id="${id}" data-key="${key}" class="${cls} review-input">${opts}</select>`;
  }
  if (rule && typeof rule === 'object' && 'min' in rule) {
    return `<input id="${id}" data-key="${key}" type="number" min="${rule.min}" max="${rule.max}" value="${escapeHtml(String(value))}" class="${cls} w-20 review-input">`;
  }
  return `<input id="${id}" data-key="${key}" type="text" value="${escapeHtml(String(value))}" class="${cls} w-48 review-input">`;
}

function renderSettingsReview(rev) {
  const body = document.getElementById('review-body');
  if (!body) return;
  const cur = rev.settings || {};
  const parts = [];
  if (rev.whats_new) {
    const n = rev.whats_new;
    parts.push(`<section class="space-y-1.5"><h4 class="font-bold text-slate-100 text-sm">What's new in ${escapeHtml(n.name || n.tag || rev.version)}</h4>
      <pre class="whitespace-pre-wrap font-sans text-[11px] text-slate-300 bg-slate-950 border border-slate-800 rounded-lg p-3 max-h-60 overflow-y-auto">${escapeHtml(n.notes || 'No release notes.')}</pre>
      ${n.url ? `<div class="text-[11px] text-slate-500">${escapeHtml(n.url)}</div>` : ''}
      ${n.releases_behind > 1 ? `<p class="text-[11px] text-amber-300">You were ${n.releases_behind} releases behind (${escapeHtml(n.previous_version || '?')} to ${escapeHtml(rev.version)}); the notes above are those of the newest only. ` +
        (n.compare_url ? `Everything that changed since your version: <a class="underline" href="${escapeHtml(n.compare_url)}" target="_blank" rel="noopener">${escapeHtml(n.compare_url)}</a>`
          : `See the CHANGELOG for every change: <a class="underline" href="${escapeHtml(n.changelog_url || '')}" target="_blank" rel="noopener">${escapeHtml(n.changelog_url || 'CHANGELOG.md')}</a>`) + '</p>' : ''}</section>`);
  }
  const ch = rev.changes || {};
  const row = (cells) => `<tr>${cells.map(c => `<td class="py-1.5 pr-3 align-top">${c}</td>`).join('')}</tr>`;
  const table = (title, note, head, rows) => rows.length ? `<section class="space-y-1.5"><h4 class="font-bold text-slate-100">${title}</h4>
      <p class="text-[11px] text-slate-400">${note}</p>
      <table class="w-full text-[11px]"><thead class="text-slate-500"><tr>${head.map(h => `<th class="text-left font-semibold pr-3">${h}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></section>` : '';
  const label = k => escapeHtml(SETTING_LABELS[k] || k);
  parts.push(table('New settings', 'Not in the version you used before; the default is used until you change it.',
    ['Setting', 'Default', 'Allowed', 'Use'],
    (ch.new || []).map(r => row([label(r.key), escapeHtml(describeValue(r.default)), escapeHtml(describeRule(r.rule)), reviewControl(r.key, r.rule, cur[r.key])]))));
  parts.push(table('Changed settings', 'The allowed values or the default changed.',
    ['Setting', 'Before', 'Now', 'Your value', 'Use'],
    (ch.changed || []).map(r => row([label(r.key),
      escapeHtml(`${describeRule(r.old_rule)} (default ${describeValue(r.old_default)})`),
      escapeHtml(`${describeRule(r.rule)} (default ${describeValue(r.default)})`),
      escapeHtml(describeValue(r.stored)) + (r.valid ? '' : ' <span class="text-amber-400">(not usable now)</span>'),
      reviewControl(r.key, r.rule, cur[r.key])]))));
  parts.push(table('Stored values this version cannot use', 'Kept in settings.json as they are; the value shown under Use applies until you pick another.',
    ['Setting', 'Stored', 'Allowed', 'Use'],
    (ch.invalid || []).map(r => row([label(r.key), escapeHtml(describeValue(r.stored)), escapeHtml(describeRule(r.rule)), reviewControl(r.key, r.rule, cur[r.key])]))));
  parts.push(table('Settings this version does not have', 'Kept in settings.json as they are, for the version that uses them.',
    ['Setting', 'Stored'],
    (ch.removed || []).map(r => row([escapeHtml(r.key), escapeHtml(describeValue(r.stored))]))));
  body.innerHTML = parts.filter(Boolean).join('');
  const title = document.getElementById('review-title');
  if (title) title.innerText = rev.whats_new ? `HELIOS-L1 ${rev.version}: what's new and what changed in the settings`
    : `HELIOS-L1 ${rev.version}: what changed in the settings`;
}

async function showSettingsReview() {
  try {
    const res = await fetch('/api/settings/review');
    if (!res.ok) return;
    const rev = await res.json();
    if (!rev.show) return;
    settingsReview = rev;
    renderSettingsReview(rev);
    document.getElementById('modal-review')?.classList.remove('hidden');
  } catch (e) {
    console.warn('Settings review unavailable:', e);
  }
}

function closeSettingsReview() {
  document.getElementById('modal-review')?.classList.add('hidden');
}

async function acknowledgeSettingsReview() {
  const cur = (settingsReview && settingsReview.settings) || {};
  const patch = {};
  document.querySelectorAll('#review-body .review-input').forEach(el => {
    const key = el.dataset.key;
    let v = el.value;
    if (el.tagName === 'SELECT') v = JSON.parse(v);
    else if (el.type === 'number') v = parseInt(v, 10);
    if (v !== cur[key]) patch[key] = v;
  });
  const status = document.getElementById('review-status');
  try {
    const res = await fetch('/api/settings/review', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: patch }) });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) { if (status) status.innerText = `Not saved: ${apiErrorText(body, res)}`; return; }
    if (body.theme) setTheme(body.theme);
    if (body.font_size) setFontSize(body.font_size);
    if (body.timezone) setTimezone(body.timezone);
    if (body.active_processors) onSettingsCoresChange(body.active_processors);
    closeSettingsReview();
  } catch (e) {
    if (status) status.innerText = `Not saved: ${e.message}`;
  }
}

// Many form labels are styled in capitals (CSS text-transform), which also capitalised their
// units and symbols: "1 mHz" read as "1 MHZ", "dB/dt" as "DB/DT" (decibels), "(s)" as "(S)",
// "nT" as "NT" and the Greek α as "Α". The bracketed part of such a label and symbols with a
// slash keep their case.
function keepUnitCase(root = document.body) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const parent = n.parentElement;
    if (!parent || !/\(|\//.test(n.textContent) || !/[a-zα-ωμ]/.test(n.textContent)) continue;
    if (getComputedStyle(parent).textTransform !== 'uppercase') continue;
    nodes.push(n);
  }
  nodes.forEach(n => {
    const parts = n.textContent.split(/(\([^()]*\)|\S+\/\S+)/);
    if (parts.length < 2) return;
    const frag = document.createDocumentFragment();
    parts.forEach((part, i) => {
      if (!part) return;
      if (i % 2 === 1) {
        const span = document.createElement('span');
        span.style.textTransform = 'none';
        span.textContent = part;
        frag.appendChild(span);
      } else {
        frag.appendChild(document.createTextNode(part));
      }
    });
    n.parentNode.replaceChild(frag, n);
  });
}

// The header is sticky and wraps onto two or three lines in narrow windows, so the sticky
// navigation bar is placed under its actual height (a fixed offset hid the domain buttons
// behind the header after scrolling below about 1300 px).
function keepNavBelowHeader() {
  const header = document.querySelector('body > header');
  const nav = document.querySelector('body > nav');
  if (!header || !nav) return;
  const place = () => { nav.style.top = header.offsetHeight + 'px'; };
  place();
  if (window.ResizeObserver) new ResizeObserver(place).observe(header);
  else window.addEventListener('resize', place);
}

// Readable text for an API error: FastAPI answers {"detail": "..."} for our own errors and
// {"detail": [{"loc": [...], "msg": "..."}]} for invalid parameters, which used to reach the
// user as "[object Object]" or as raw JSON.
function apiErrorText(body, res) {
  const d = body && body.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d) && d.length) {
    return d.map(e => {
      const field = Array.isArray(e.loc) ? e.loc.filter(x => x !== 'body' && x !== 'query').join('.') : '';
      return field ? `${field}: ${e.msg}` : String(e.msg || '');
    }).join('; ');
  }
  if (body && typeof body.error === 'string') return body.error;
  return res ? `Request failed (HTTP ${res.status})` : 'Request failed';
}

async function initSettingsAndPreferences() {
  // Apply initial theme and font scaling attributes
  document.documentElement.setAttribute('data-theme', currentTheme);
  document.documentElement.setAttribute('data-fontsize', currentFontSize);

  // Sync settings UI components
  setTheme(currentTheme);
  setFontSize(currentFontSize);
  onSettingsCoresChange(currentProcessors);

  const tzSelect = document.getElementById('settings-timezone-select');
  if (tzSelect) tzSelect.value = selectedTimezone;

  // Fetch server hardware specs and status
  try {
    const res = await fetch('/api/status');
    if (res.ok) {
      const data = await res.json();
      if (data.system) {
        totalCpuCores = data.system.total_cpu_cores || navigator.hardwareConcurrency || 8;
        // The server keeps the saved preferences (the desktop window's storage can be private).
        // Use them when they exist; otherwise hand this browser's preferences to the server.
        if (data.system.saved) {
          if (data.system.theme) setTheme(data.system.theme);
          if (data.system.font_size) setFontSize(data.system.font_size);
          if (data.system.timezone) setTimezone(data.system.timezone);
          if (data.system.active_processors) onSettingsCoresChange(data.system.active_processors);
        } else if (localStorage.getItem('helios_theme') || localStorage.getItem('helios_timezone')) {
          fetch('/api/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ processors: Math.min(currentProcessors, totalCpuCores), theme: currentTheme, font_size: currentFontSize, timezone: selectedTimezone })
          }).catch(() => {});
        }
        const maxCoresEl = document.getElementById('detected-max-cores-label');
        if (maxCoresEl) maxCoresEl.innerText = `Detected: ${totalCpuCores} logical cores`;
        const slider = document.getElementById('settings-cores-slider');
        if (slider) {
          slider.max = totalCpuCores;
          slider.value = currentProcessors;
        }
      }
    }
  } catch (e) {
    console.warn('Could not fetch server settings status:', e);
  }
}

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

function formatTimestampToTimezone(isoStr) {
  if (!isoStr) return '';
  try {
    // Server time stamps are UTC 'YYYY-MM-DD HH:MM:SS'. Use the ISO 'T' separator: WebKit
    // (macOS/Linux windows) rejects 'YYYY-MM-DD HH:MM:SSZ' and the label silently stayed UTC.
    const iso = String(isoStr).trim().replace(' ', 'T');
    const raw = /([zZ]|[+-]\d\d:?\d\d)$/.test(iso) ? iso : iso + 'Z';
    const d = new Date(raw);
    if (isNaN(d.getTime())) return isoStr.slice(5, 16);
    if (selectedTimezone === 'UTC') {
      return isoStr.slice(5, 16);
    } else if (selectedTimezone === 'LOCAL') {
      const m = String(d.getMonth() + 1).padStart(2, '0');
      const day = String(d.getDate()).padStart(2, '0');
      const h = String(d.getHours()).padStart(2, '0');
      const min = String(d.getMinutes()).padStart(2, '0');
      return `${m}-${day} ${h}:${min}`;
    } else {
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: selectedTimezone,
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        hourCycle: 'h23'
      });
      const parts = formatter.formatToParts(d);
      const m = parts.find(p => p.type === 'month')?.value || '01';
      const day = parts.find(p => p.type === 'day')?.value || '01';
      const h = parts.find(p => p.type === 'hour')?.value || '00';
      const min = parts.find(p => p.type === 'minute')?.value || '00';
      return `${m}-${day} ${h}:${min}`;
    }
  } catch (e) {
    return isoStr.slice(5, 16);
  }
}

function updateClock() {
  const el = document.getElementById('utc-clock');
  const badge = document.getElementById('clock-tz-badge');
  const preview = document.getElementById('tz-modal-clock-preview');
  const previewBadge = document.getElementById('tz-modal-current-badge');
  const settingsTzPreview = document.getElementById('settings-tz-preview');
  if (!el && !preview) return;

  const now = new Date();
  let timeStr = '';
  let badgeStr = 'UTC';

  if (selectedTimezone === 'UTC') {
    timeStr = now.toUTCString().slice(17, 25) + ' UTC';
    badgeStr = 'UTC';
  } else if (selectedTimezone === 'LOCAL') {
    timeStr = now.toLocaleTimeString();
    const offsetMin = -now.getTimezoneOffset();
    const sign = offsetMin >= 0 ? '+' : '-';
    const absMin = Math.abs(offsetMin);
    const hrs = String(Math.floor(absMin / 60)).padStart(2, '0');
    const mins = String(absMin % 60).padStart(2, '0');
    badgeStr = `UTC${sign}${hrs}:${mins}`;
  } else {
    try {
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: selectedTimezone,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
        timeZoneName: 'short'
      });
      const parts = formatter.formatToParts(now);
      const h = parts.find(p => p.type === 'hour')?.value || '00';
      const m = parts.find(p => p.type === 'minute')?.value || '00';
      const s = parts.find(p => p.type === 'second')?.value || '00';
      const tzName = parts.find(p => p.type === 'timeZoneName')?.value || selectedTimezone.split('/').pop().replace('_', ' ');
      timeStr = `${h}:${m}:${s} ${tzName}`;
      badgeStr = tzName;
    } catch (err) {
      timeStr = now.toUTCString().slice(17, 25) + ' UTC';
      badgeStr = 'UTC';
    }
  }

  if (el) el.innerText = timeStr;
  if (badge) {
    badge.innerText = badgeStr;
    badge.className = selectedTimezone === 'UTC'
      ? 'text-[9px] px-1 py-0.2 rounded bg-sky-500/20 text-sky-300 uppercase font-mono'
      : 'text-[9px] px-1 py-0.2 rounded bg-amber-500/20 text-amber-300 uppercase font-mono';
  }
  if (preview) preview.innerText = timeStr;
  if (previewBadge) previewBadge.innerText = badgeStr;
  if (settingsTzPreview) settingsTzPreview.innerText = timeStr;
  const dockBadge = document.getElementById('dock-tz-badge');
  if (dockBadge) dockBadge.innerText = badgeStr;
}

// Modal open/close methods for Settings, About, and Timezones
function openSettingsModal() {
  window.playBlip?.();
  const modal = document.getElementById('modal-settings');
  if (modal) {
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    modal.style.zIndex = '99999';
  }
  refreshUpdateStatus();
}

// Automatic updates of a published build (GET /api/updates, POST /api/updates/check).
let updatePollTimer = null;

function describeUpdateStatus(st) {
  const fmt = t => (t ? new Date(t * 1000).toISOString().slice(0, 16).replace('T', ' ') + ' UTC' : 'never');
  const parts = [`This is HELIOS-L1 ${st.version} (${st.platform}).`];
  if (st.problem) parts.push(`This copy does not update itself: ${st.problem}. New builds: ${st.releases}`);
  else parts.push(`Last check: ${fmt(st.last_check)}` + (st.enabled && st.next_check ? `; next: ${fmt(st.next_check)}.` : '.'));
  if (st.staged) parts.push(`${st.staged.name || st.staged.tag} is downloaded and will be installed the next time HELIOS-L1 starts.`);
  if (st.failed) parts.push(`Installing ${st.failed.tag} failed on ${fmt(st.failed.at)} (attempt ${st.failed.attempts} of 3): ${st.failed.reason}. The previous build is in use.`);
  const job = st.job || {};
  if (job.running) {
    const pct = job.total ? ` ${Math.round(100 * job.done / job.total)} %` : '';
    parts.push(`${job.message}${pct}...`);
  } else if (job.error) {
    parts.push(`The last check failed: ${job.error}`);
  } else if (job.message) {
    parts.push(job.message);
  }
  return parts.join(' ');
}

async function refreshUpdateStatus() {
  const el = document.getElementById('settings-update-status');
  try {
    const res = await fetch('/api/updates');
    if (!res.ok) return;
    const st = await res.json();
    const box = document.getElementById('settings-auto-update');
    if (box && !box.dataset.touched) box.checked = !!st.enabled;
    if (el) el.innerText = describeUpdateStatus(st);
    clearTimeout(updatePollTimer);
    if (st.job && st.job.running) updatePollTimer = setTimeout(refreshUpdateStatus, 1000);
  } catch (e) {
    if (el) el.innerText = `Update status unavailable: ${e.message}`;
  }
}

async function checkForUpdateNow() {
  const el = document.getElementById('settings-update-status');
  try {
    const res = await fetch('/api/updates/check', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      if (el) el.innerText = `Check failed: ${apiErrorText(body, res)}`;
      return;
    }
    refreshUpdateStatus();
  } catch (e) {
    if (el) el.innerText = `Check failed: ${e.message}`;
  }
}

function closeSettingsModal() {
  const modal = document.getElementById('modal-settings');
  if (modal) {
    modal.classList.add('hidden');
    modal.style.display = 'none';
  }
}

function openAboutModal() {
  window.playBlip?.();
  const modal = document.getElementById('modal-about');
  if (modal) {
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    modal.style.zIndex = '99999';
  }
}

function closeAboutModal() {
  const modal = document.getElementById('modal-about');
  if (modal) {
    modal.classList.add('hidden');
    modal.style.display = 'none';
  }
}

function openTimezoneModal() {
  window.playBlip?.();
  const modal = document.getElementById('modal-timezone');
  if (modal) {
    modal.classList.remove('hidden');
    modal.style.display = 'flex';
    modal.style.zIndex = '99999';
  }
}

function closeTimezoneModal() {
  const modal = document.getElementById('modal-timezone');
  if (modal) {
    modal.classList.add('hidden');
    modal.style.display = 'none';
  }
}

function setTheme(themeName) {
  currentTheme = themeName;
  document.documentElement.setAttribute('data-theme', themeName);
  localStorage.setItem('helios_theme', themeName);

  // Inactive buttons keep their own border tint (amber, emerald) or slate; only one border
  // colour class at a time, so the result does not depend on the order of the CSS rules.
  document.querySelectorAll('.theme-option-btn').forEach(btn => {
    const idle = btn.dataset.idleBorder || 'border-slate-800';
    btn.classList.remove('border-sky-500/50', 'bg-slate-800/80', 'border-slate-800', 'border-amber-900/40', 'border-emerald-900/40');
    btn.classList.add(idle);
  });
  const activeBtn = document.getElementById(`theme-btn-${themeName}`);
  if (activeBtn) {
    activeBtn.classList.remove(activeBtn.dataset.idleBorder || 'border-slate-800');
    activeBtn.classList.add('border-sky-500/50', 'bg-slate-800/80');
  }

  const label = document.getElementById('current-theme-label');
  if (label) {
    const names = {
      'mission-slate': 'Mission Slate (Default)',
      'deep-space': 'Deep Space Obsidian',
      'solar-amber': 'Solar Amber',
      'high-contrast': 'High-Contrast Terminal'
    };
    label.innerText = names[themeName] || themeName;
  }
}

function setFontSize(sizeName) {
  currentFontSize = sizeName;
  document.documentElement.setAttribute('data-fontsize', sizeName);
  localStorage.setItem('helios_fontsize', sizeName);

  document.querySelectorAll('.fontsize-option-btn').forEach(btn => {
    btn.classList.remove('border-sky-500/50', 'bg-slate-800');
    btn.classList.add('border-slate-700/80', 'bg-slate-800/60');
  });
  const activeBtn = document.getElementById(`fontsize-btn-${sizeName}`);
  if (activeBtn) {
    activeBtn.classList.remove('border-slate-700/80', 'bg-slate-800/60');
    activeBtn.classList.add('border-sky-500/50', 'bg-slate-800');
  }

  const label = document.getElementById('current-fontsize-label');
  if (label) {
    const names = {
      compact: 'Compact (88%)',
      normal: 'Standard (100%)',
      large: 'Large (112%)'
    };
    label.innerText = names[sizeName] || sizeName;
  }
}

function onSettingsCoresChange(val) {
  currentProcessors = parseInt(val, 10);
  const readout = document.getElementById('settings-cores-readout');
  const display = document.getElementById('settings-cores-display');
  if (readout) readout.innerText = `${currentProcessors} Cores Active`;
  if (display) display.innerText = currentProcessors;
}

function selectTzPreset(tz) {
  setTimezone(tz);
}

function setTimezone(tz) {
  selectedTimezone = tz;
  localStorage.setItem('helios_timezone', tz);
  const sel = document.getElementById('settings-timezone-select');
  if (sel) sel.value = tz;
  updateClock();
  if (typeof currentTelemetryData !== 'undefined' && currentTelemetryData) {
    updateTelemetryUI(currentTelemetryData);
  }
}

function applyCustomTimezone() {
  const input = document.getElementById('tz-custom-input');
  const err = document.getElementById('tz-custom-error');
  if (!input) return;
  const tz = input.value.trim();
  try {
    Intl.DateTimeFormat(undefined, { timeZone: tz });
    if (err) err.classList.add('hidden');
    setTimezone(tz);
    input.value = '';
    closeTimezoneModal();
  } catch (e) {
    if (err) err.classList.remove('hidden');
  }
}

async function saveAndApplySettings() {
  localStorage.setItem('helios_theme', currentTheme);
  localStorage.setItem('helios_fontsize', currentFontSize);
  localStorage.setItem('helios_processors', currentProcessors);
  localStorage.setItem('helios_timezone', selectedTimezone);

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        processors: currentProcessors,
        theme: currentTheme,
        font_size: currentFontSize,
        timezone: selectedTimezone,
        auto_update: document.getElementById('settings-auto-update')?.checked ?? true
      })
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      alert(`Settings not saved: ${apiErrorText(body, res)}`);
      return;
    }
    const saved = await res.json().catch(() => ({}));
    if (saved.save_error) {
      alert(`The settings apply to this session but could not be saved for the next start: ${saved.save_error}`);
    }
  } catch (err) {
    console.warn('Backend settings persist error:', err);
  }

  closeSettingsModal();
}

function resetSettingsDefaults() {
  setTheme('mission-slate');
  setFontSize('normal');
  onSettingsCoresChange(4);
  const slider = document.getElementById('settings-cores-slider');
  if (slider) slider.value = 4;
  setTimezone('UTC');
}

function renderSubnav(domainKey) {
  const container = document.getElementById('subnav-container');
  if (!container) return;
  const domain = DOMAINS[domainKey];
  if (!domain) return;

  const html = domain.views.map(v => {
    let clickHandler = `switchTab('${v.id}')`;
    if (v.id === 'references') clickHandler = 'openReferencesModal()';
    else if (v.id === 'settings') clickHandler = 'openSettingsModal()';
    else if (v.id === 'about') clickHandler = 'openAboutModal()';
    const activeClass = v.id === currentTab ? 'active' : '';
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

  if (tabId === 'orbits') {
    setTimeout(() => {
      if (orbitViewer) {
        orbitViewer.resize();
        orbitViewer.resetView();
        orbitViewer.draw();
      }
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
    const panel = document.getElementById('cme-results-panel');
    if (panel) panel.classList.remove('hidden');
    setTimeout(() => {
      if (cmeSimulator) {
        cmeSimulator.resize();
        cmeSimulator.draw();
      }
      if (solarDiskViewer) solarDiskViewer.resize();
      calculateCMEKinematics();
    }, 50);
  } else if (tabId === 'comparator') {
    loadFleetMatrix();
  } else if (tabId === 'forecast') {
    loadMLForecast();
  } else if (tabId === 'hazards') {
    loadHazardsAndCycle();
  } else if (tabId === 'turbulence') {
    loadSpectralAnalysis();
  } else if (tabId === 'events') {
    loadEvents();
  } else if (tabId === 'missions') {
    loadMissions();
  } else if (tabId === 'import') {
    loadCustomPresets();
    loadCustomLatest();
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
          { label: 'Model Dst [nT]', data: [], borderColor: '#f43f5e', backgroundColor: 'rgba(244, 63, 94, 0.1)', fill: true, borderWidth: 1.5, pointRadius: 0, tension: 0.1 },
          { label: 'Observed Dst, Kyoto [nT]', data: [], borderColor: '#38bdf8', backgroundColor: '#38bdf8', showLine: true, spanGaps: true, borderWidth: 1.5, pointRadius: 2.5 }
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
  if (span === 'archive') return loadArchiveTelemetry();

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

function onTelemetrySpanChange() {
  const span = document.getElementById('telemetry-span-select')?.value;
  const panel = document.getElementById('archive-controls');
  if (panel) panel.classList.toggle('hidden', span !== 'archive');
  const satSelect = document.getElementById('telemetry-satellite-select');
  if (satSelect) satSelect.disabled = span === 'archive';
  if (span !== 'archive') loadTelemetry();
}

// Query string for the archive endpoint from the archive controls (times are UTC).
function archiveQuery() {
  const mission = document.getElementById('archive-mission-select')?.value || 'OMNI';
  const start = document.getElementById('archive-start')?.value || '';
  const end = document.getElementById('archive-end')?.value || '';
  const cadence = document.getElementById('archive-cadence-select')?.value || '1';
  return { mission, qs: `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&cadence_minutes=${cadence}` };
}

// One group of a data coverage report (helios/core/coverage.py): the covered fraction, never
// rounded up to 100.0 % while there are gaps, and the number and the longest of the gaps.
function coverageText(name, v) {
  const pct = 100 * v.covered_fraction;
  const lg = v.longest_gap;
  const len = !lg ? '' : lg.minutes >= 1440 ? `${(lg.minutes / 1440).toFixed(1)} days`
    : lg.minutes >= 60 ? `${(lg.minutes / 60).toFixed(1)} h` : `${lg.minutes} min`;
  return `${name} ${v.gaps && pct > 99.95 ? '> 99.9' : pct.toFixed(1)} %` +
    (lg ? ` (${v.gaps} gap${v.gaps > 1 ? 's' : ''}, longest ${len} from ${lg.start})` : '');
}

// Years of hourly OMNI that an answer of the statistics endpoints could not use or refresh
// (provenance.years_without_data, years_not_refreshed), as a note for its status line.
function omniYearsNote(prov) {
  const missing = (prov && prov.years_without_data) || [];
  const offline = (prov && prov.years_not_refreshed) || [];
  const unreached = missing.filter(y => offline.includes(y)), empty = missing.filter(y => !offline.includes(y));
  const stale = offline.filter(y => !missing.includes(y));
  return (unreached.length ? `; CDAWeb could not be reached for ${unreached.join(', ')} and nothing is cached: left out` : '') +
    (empty.length ? `; no OMNI data for ${empty.join(', ')}` : '') +
    (stale.length ? `; CDAWeb not reached, cached data used for ${stale.join(', ')}` : '');
}

async function loadArchiveTelemetry() {
  const statusEl = document.getElementById('archive-status');
  const { mission, qs } = archiveQuery();
  if (statusEl) statusEl.innerText = `Retrieving ${mission} from NASA CDAWeb...`;
  const t0 = performance.now();
  try {
    const res = await fetch(`/api/archive/${mission}?${qs}`);
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));
    const prov = data.provenance || {};
    const groups = (prov.coverage && prov.coverage.groups) || {};
    const cov = Object.entries(groups).map(([k, v]) => coverageText(k, v)).join('; ');
    if (statusEl) statusEl.innerText = (prov.description || '') + (cov ? `\nCoverage: ${cov}.` : '');
    updateFeedStatus(data, Math.round(performance.now() - t0));
    if (!(data.records || []).length) return;
    // Archive intervals are historical: the live NOAA scale badges do not apply.
    data.mission = {
      full_name: `${(data.mission && data.mission.name) || mission} archive (${prov.time_coverage_start} to ${prov.time_coverage_end} UTC)`,
      agency: (prov.datasets || []).map(d => d.id).join(' + ') || 'NASA CDAWeb',
      location: 'NASA CDAWeb HAPI'
    };
    data.classification = { g_scale: 'Archive: n/a', s_scale: 'n/a', r_scale: 'n/a', r_level: 0 };
    currentTelemetryData = data;
    updateTelemetryUI(data);
  } catch (err) {
    console.error('Error fetching archive interval:', err);
    if (statusEl) statusEl.innerText = `Archive request failed: ${err.message}`;
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
  const prov = data.provenance || {};
  const kind = prov.kind || 'synthetic';
  const badge = document.getElementById('feed-status-badge');
  if (badge) badge.title = prov.description || 'Telemetry Feed Diagnostic & Latency';

  if (kind === 'observed') {
    const src = (prov.source_spacecraft || []).join(', ');
    const datasets = (prov.datasets || []).map(d => d.id);
    let origin = 'NOAA RTSW';
    if (datasets.length) {
      origin = 'CDAWeb ' + datasets.join('+') + ((prov.description || '').includes('RTSW') ? ' + RTSW' : '');
    }
    badgeText.innerText = `Observed: ${origin}${src ? ' ' + src : ''} (${recCount} pts • ${latency}ms)`;
    badgeText.className = 'text-emerald-300 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-emerald-400 pulse-beacon';
  } else if (kind === 'unavailable') {
    badgeText.innerText = 'No archive data for this interval';
    badgeText.className = 'text-amber-300 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-amber-400';
  } else if (kind === 'simulated') {
    badgeText.innerText = `SIMULATED from L1 stream (${recCount} pts • ${latency}ms)`;
    badgeText.className = 'text-amber-300 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-amber-400';
  } else {
    badgeText.innerText = `SYNTHETIC model, archive offline (${recCount} pts • ${latency}ms)`;
    badgeText.className = 'text-rose-300 font-mono text-[11px]';
    badgeDot.className = 'w-2 h-2 rounded-full bg-rose-400';
  }
}

function sonifyCurrentTelemetry() {
  const latest = (currentTelemetryData && currentTelemetryData.latest) || {};
  const speed = typeof latest.speed === 'number' ? latest.speed : 450;
  const bz = typeof latest.bz_gsm === 'number' ? latest.bz_gsm : -2.5;
  const density = typeof latest.density === 'number' ? latest.density : 6.0;
  if (window.soundEngine) {
    window.soundEngine.sonifySolarWind(speed, bz, density);
  }
}

function updateTelemetryUI(data) {
  const mission = data.mission;
  const latest = data.latest || {};
  const cls = data.classification || {};
  const allRecords = data.records || [];

  // Filter records if a physical regime filter is active
  // Thresholds match the button labels (they were 480 km/s and 8 cm^-3). With a filter
  // the MIN/AVG/MAX rows describe the matching samples only, while the large numbers stay
  // the latest measurement; the note under the buttons says which.
  let records = allRecords;
  const filters = {
    bz_south: [r => typeof r.bz_gsm === 'number' && r.bz_gsm < 0, 'Bz < 0'],
    fast_wind: [r => typeof r.speed === 'number' && r.speed > 500, 'V > 500 km/s'],
    dense_plasma: [r => typeof r.density === 'number' && r.density > 10, 'N > 10 cm⁻³'],
  };
  const noteEl = document.getElementById('telemetry-filter-note');
  if (filters[currentTelemetryFilter]) {
    const [test, label] = filters[currentTelemetryFilter];
    const filtered = allRecords.filter(test);
    if (filtered.length > 0) records = filtered;
    if (noteEl) noteEl.innerText = filtered.length > 0
      ? `Filter ${label}: ${filtered.length} of ${allRecords.length} samples. MIN/AVG/MAX and charts use these; large values are the latest sample.`
      : `Filter ${label}: no sample in this window matches; showing all ${allRecords.length} samples.`;
  } else if (noteEl) {
    noteEl.innerText = '';
  }

  document.getElementById('sat-name-full').innerText = mission.full_name;
  document.getElementById('sat-agency-orbit').innerText = `${mission.agency} • ${mission.location}`;

  // Update Top Alert Badges
  const gBadge = document.getElementById('noaa-g-badge');
  const gText = document.getElementById('g-scale-text');
  if (gBadge && gText) {
    gText.innerText = cls.g_scale || 'G scale n/a';
    gBadge.style.color = cls.g_color || '#10b981';
    gBadge.style.borderColor = (cls.g_color || '#10b981') + '66';
    gBadge.style.backgroundColor = (cls.g_color || '#10b981') + '1a';
  }

  const bzBadge = document.getElementById('bz-alert-badge');
  const bzText = document.getElementById('bz-alert-text');
  if (bzBadge && bzText) {
    bzText.innerText = (latest.bz_gsm != null ? `Bz: ${latest.bz_gsm} nT` : 'Bz n/a');
    bzBadge.style.color = cls.bz_color || '#10b981';
    bzBadge.style.borderColor = (cls.bz_color || '#10b981') + '66';
    bzBadge.style.backgroundColor = (cls.bz_color || '#10b981') + '1a';
  }

  // Update Top Space Weather Condition Ticker
  const tickG = document.getElementById('ticker-g-scale');
  if (tickG) {
    tickG.innerText = cls.g_scale ? cls.g_scale.toUpperCase() : 'G N/A';
    tickG.style.color = cls.g_color || '#10b981';
  }
  const tickS = document.getElementById('ticker-s-scale');
  if (tickS) {
    tickS.innerText = cls.s_scale ? cls.s_scale.toUpperCase() : 'S N/A';
    tickS.style.color = cls.s_color || '#10b981';
  }
  const tickR = document.getElementById('ticker-r-scale');
  if (tickR) {
    tickR.innerText = cls.r_scale ? cls.r_scale.toUpperCase() : 'R N/A';
    tickR.style.color = cls.r_level > 0 ? '#f59e0b' : '#10b981';
  }
  const tickRmp = document.getElementById('ticker-rmp');
  if (tickRmp && latest.magnetopause_re != null) tickRmp.innerText = `${latest.magnetopause_re} RE`;
  const tickEps = document.getElementById('ticker-epsilon');
  if (tickEps && latest.akasofu_gw != null) tickEps.innerText = `${latest.akasofu_gw} GW`;

  // Update KPI Gauge Numbers
  document.getElementById('metric-speed').innerText = latest.speed != null ? latest.speed : '---';
  // Same 500 km/s fast-wind threshold as the regime filter and the exported chart
  document.getElementById('metric-speed-status').innerText = latest.speed == null ? 'No speed in the latest record' : (latest.speed > 600 ? 'Severe High-Speed Stream!' : (latest.speed > 500 ? 'Fast solar wind' : 'Slow wind'));

  document.getElementById('metric-bz').innerText = latest.bz_gsm != null ? latest.bz_gsm : '---';
  document.getElementById('metric-bz-status').innerText = latest.bz_gsm == null ? 'No Bz in the latest record' : (latest.bz_gsm < -10 ? 'Intense Southward (Storm Trigger)!' : (latest.bz_gsm < 0 ? 'Weak Southward' : 'Northward (Shielded)'));

  document.getElementById('metric-bt').innerText = latest.bt != null ? latest.bt : '---';
  document.getElementById('metric-density').innerText = latest.density != null ? latest.density : '---';
  document.getElementById('metric-pdyn').innerText = latest.dynamic_pressure != null ? latest.dynamic_pressure : '---';
  document.getElementById('metric-delay').innerText = latest.l1_travel_time_min != null ? latest.l1_travel_time_min : '---';

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
    const mb = solarWindMachBeta(latest);
    orbitViewer.setSolarWindConditions(latest.speed, latest.dynamic_pressure, latest.bz_gsm, mb.mms, mb.beta);
    const hudFlux = document.getElementById('hud-flux-speed');
    if (hudFlux && latest.speed) hudFlux.innerText = `${latest.speed} km/s`;
    if (orbitViewer.lastComputedBoundaries) {
      updateBoundaryCards(orbitViewer.lastComputedBoundaries);
    }
  }

  // Evaluate operational alerts and threshold excursions
  if (missionIncidentLogger && latest) {
    missionIncidentLogger.checkTelemetry(latest, mission);
  }

  const times = records.map(r => formatTimestampToTimezone(r.time_tag));
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

// Statistics between a measurement and a simulated / synthetic series describe the model,
// not two instruments: say so above the numbers.
function comparisonProvenanceWarning(comp, satA, satB) {
  const sides = [['A', satA, comp.provenance_a], ['B', satB, comp.provenance_b]];
  const notes = sides
    .filter(([, , prov]) => prov && prov.kind && !['observed', 'imported'].includes(prov.kind))
    .map(([side, sat, prov]) => `Spacecraft ${side} (${sat}) is ${prov.kind.toUpperCase()}${prov.kind === 'simulated'
      ? ': derived from the operational L1 stream with fixed offsets and noise'
      : ': offline model output'}.`);
  if (!notes.length) return '';
  return notes.join(' ') + ' The correlation, RMSE, bias and lag below describe that model, not a comparison of two instruments.';
}

function showComparisonProvenanceWarning(comp, satA, satB) {
  const box = document.getElementById('comp-provenance-warning');
  const textEl = document.getElementById('comp-provenance-warning-text');
  if (!box || !textEl) return;
  const msg = comparisonProvenanceWarning(comp, satA, satB);
  textEl.innerText = msg;
  box.classList.toggle('hidden', !msg);
}

async function runComparison() {
  const satA = document.getElementById('comp-sat-a').value;
  const satB = document.getElementById('comp-sat-b').value;
  const param = document.getElementById('comp-param').value;

  try {
    const res = await fetch(`/api/compare?mission_a=${satA}&mission_b=${satB}&parameter=${param}&span_days=1`);
    if (!res.ok) {
      let body = null;
      try { body = await res.json(); } catch (e) { body = null; }
      alert(`Comparison failed: ${apiErrorText(body, res)}`);
      return;
    }
    const comp = await res.json();

    showComparisonProvenanceWarning(comp, satA, satB);
    if (comp.status !== 'success') {
      alert(`Insufficient overlapping telemetry data between the selected spacecraft. ${comp.message || ''}`);
      return;
    }

    const m = comp.metrics;
    document.getElementById('stat-r').innerText = m.correlation_r;
    document.getElementById('stat-r').title = m.correlation_ci95
      ? `95 % interval ${m.correlation_ci95[0]} to ${m.correlation_ci95[1]} (Fisher z, ~${m.n_eff} independent samples)`
      : `Too few independent samples for an interval (~${m.n_eff ?? '?'})`;
    document.getElementById('stat-r2').innerText = m.r_squared;
    document.getElementById('stat-rmse').innerText = m.rmse;
    document.getElementById('stat-bias').innerText = (m.bias > 0 ? `+${m.bias}` : `${m.bias}`);
    const lagCi = comp.lag_analysis?.lag_ci95_minutes;
    document.getElementById('stat-lag').innerText = `${comp.lag_analysis?.optimal_lag_minutes || 0} min`;
    document.getElementById('stat-lag').title = lagCi ? `95 % interval ${lagCi[0]} to ${lagCi[1]} min (${comp.lag_analysis.lag_uncertainty_method})` : '';
    const lagCiEl = document.getElementById('stat-lag-ci');
    if (lagCiEl) lagCiEl.innerText = lagCi ? `95 %: ${lagCi[0]} to ${lagCi[1]} min` : '';
    const rCiEl = document.getElementById('stat-r-ci');
    if (rCiEl) rCiEl.innerText = m.correlation_ci95 ? `95 %: ${m.correlation_ci95[0]} to ${m.correlation_ci95[1]}` : (m.n_eff !== undefined ? 'too few independent samples' : '');
    document.getElementById('stat-fit').innerText = `A = ${m.slope}*B ${m.intercept >= 0 ? '+' : ''}${m.intercept}`;

    // Update Spatial Baseline & Phase Delay HUD
    const base = comp.spatial_baseline || {};
    const distKmEl = document.getElementById('baseline-dist-km');
    const distReEl = document.getElementById('baseline-dist-re');
    const vecGseEl = document.getElementById('baseline-vec-gse');
    const theoryDelayEl = document.getElementById('baseline-theory-delay');
    const empLagEl = document.getElementById('baseline-empirical-lag');
    const fidelityEl = document.getElementById('baseline-fidelity-score');

    if (distKmEl) distKmEl.innerText = `${base.distance_km != null ? base.distance_km.toLocaleString() : '---'} km`;
    if (distReEl) distReEl.innerText = `${base.distance_re != null ? base.distance_re : '--'} R_E`;
    if (vecGseEl) vecGseEl.innerText = base.position_unknown ? `unknown: ${base.position_unknown}`
      : `ΔX: ${base.dx_km || 0}, ΔY: ${base.dy_km || 0}, ΔZ: ${base.dz_km || 0}`;
    if (vecGseEl) vecGseEl.title = base.position_unknown ? '' : `Positions: A from ${base.position_source_a || 'model orbit'}; B from ${base.position_source_b || 'model orbit'}`;
    if (theoryDelayEl) theoryDelayEl.innerText = `${base.theoretical_delay_min != null ? (base.theoretical_delay_min > 0 ? `+${base.theoretical_delay_min}` : base.theoretical_delay_min) : '--'} min`;
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
        // The fit and identity lines are 'line' datasets, which would make x a category axis
        // and stack every point at the left edge: force a numeric axis.
        x: { ...darkChartOptions.scales.x, type: 'linear', position: 'bottom', title: { display: true, text: `${comp.mission_b} [${comp.parameter}]`, color: '#64748b' } },
        y: { ...darkChartOptions.scales.y, type: 'linear', title: { display: true, text: `${comp.mission_a} [${comp.parameter}]`, color: '#64748b' } }
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
    const modelSel = document.getElementById('dst-model-select');
    const params = new URLSearchParams({ dst_model: modelSel ? modelSel.value : 'obrien' });
    const timeEl = document.getElementById('aurora-time');
    const alEl = document.getElementById('aurora-al');
    if (timeEl && timeEl.value) params.set('time', timeEl.value + 'Z');
    if (alEl && alEl.value !== '') params.set('al', alEl.value);
    const res = await fetch(`/api/aurora?${params}`);
    const data = await res.json();
    const noteEl = document.getElementById('aurora-oval-note');
    if (!res.ok) {
      if (noteEl) noteEl.innerText = apiErrorText(data, res);
      return;
    }
    const b = data.boundaries;
    if (noteEl) noteEl.innerText = `Oval for ${data.oval_time_utc} UTC` + (b.al_capped ? ' (|AL| capped to 18-750 nT, the range where the Starkov fits are valid)' : '');
    const alSrc = document.getElementById('aurora-al-source');
    if (alSrc) alSrc.innerText = `|AL| = ${b.al_used_nt} nT: ${b.al_source}`;
    const flankDetail = document.getElementById('aurora-flank-detail');
    if (flankDetail && b.equatorward_dawn_lat !== undefined) flankDetail.innerText = `Equatorward boundary, dawn (06 MLT) ${b.equatorward_dawn_lat}°, dusk (18 MLT) ${b.equatorward_dusk_lat}°`;

    document.getElementById('aurora-midnight-lat').innerText = `${b.equatorward_midnight_lat}° N/S`;  // CGM latitude
    document.getElementById('aurora-power-gw').innerText = b.hemispheric_power_gw !== null && b.hemispheric_power_gw !== undefined ? `${b.hemispheric_power_gw} GW` : '--- GW';
    document.getElementById('aurora-flank-lat').innerText = `${b.equatorward_flanks_lat}°`;

    const regList = document.getElementById('aurora-regions-list');
    const regNote = document.getElementById('aurora-regions-note');
    if (regNote && b.equatorward_midnight_lat !== undefined) {
      regNote.innerText = `Regions near the oval, chosen from its equatorward boundary at magnetic midnight, now ${b.equatorward_midnight_lat}° corrected geomagnetic latitude (bands at 42°, 50° and 58°). A rough guide, not a probability of seeing the aurora.`;
    }
    if (regList && b.visible_regions) {
      regList.innerHTML = b.visible_regions.map(r => `
        <li class="p-2.5 rounded-lg bg-space-900/80 border border-slate-700/60 flex items-center space-x-2">
          <i class="fa-solid fa-location-dot text-emerald-400"></i>
          <span>${r}</span>
        </li>
      `).join('');
    }

    if (chartDst && data.dst_evolution) {
      const times = data.dst_evolution.map(d => d.time_tag.slice(11, 16));
      const dstVals = data.dst_evolution.map(d => d.dst_predicted_nt);
      chartDst.data.labels = times;
      chartDst.data.datasets[0].data = dstVals;
      chartDst.data.datasets[0].label = `${data.dst_model || 'Model'} Dst [nT]`;
      chartDst.data.datasets[1].data = alignHourlyToSeries(data.dst_evolution.map(d => d.time_tag), data.dst_observed || []);
      chartDst.update();

      const latestDst = dstVals[dstVals.length - 1];
      const obsList = data.dst_observed || [];
      const latestObs = obsList.length ? obsList[obsList.length - 1].dst : null;
      const curDstEl = document.getElementById('dst-current-val');
      if (curDstEl) curDstEl.innerText = latestObs !== null ? `Kyoto: ${latestObs} nT • model: ${latestDst} nT` : `Model: ${latestDst} nT`;
      const skillEl = document.getElementById('dst-skill-text');
      if (skillEl) skillEl.innerText = describeDstSkill(data.dst_skill, 'Kyoto Dst (hourly)') +
        ' Drivers: L1 solar wind shifted to Earth by its travel time' + (data.dst_initial_observed_nt !== null && data.dst_initial_observed_nt !== undefined ? `; model started from observed ${data.dst_initial_observed_nt} nT.` : '; no observed start value, model starts quiet.');
    }

    // Feed real-time geomagnetic parameters to high-resolution Auroral Renderer
    if (auroralRenderer) {
      auroralRenderer.resize();
      const kpUsed = !(data.kp_source || '').startsWith('not used');
      const kpVal = kpUsed ? (data.kp !== undefined ? data.kp : b.kp_used) : null;
      const bzVal = data.bz_gsm !== undefined ? data.bz_gsm : (b.bz_used !== undefined ? b.bz_used : -3.2);
      const pastTime = timeEl && timeEl.value ? data.oval_time_utc : null;
      auroralRenderer.setConditions(kpVal, bzVal, b.hemispheric_power_gw, b.equatorward_midnight_lat, data.oval_polygon,
                                    b.al_used_nt, pastTime);
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
      body: JSON.stringify({
        r1_rsun: r1, r2_rsun: r2, dt_minutes: dt,
        ambient_wind_kms: parseFloat(document.getElementById('cme-w')?.value) || 420,
        gamma_drag: (parseFloat(document.getElementById('cme-gamma')?.value) || 1.0) * 1e-7
      })
    });
    const cme = await res.json();
    if (!res.ok || cme.error) {
      alert(res.ok ? cme.error : `${apiErrorText(cme, res)} (enter numbers for both heights and the time step)`);
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
    const notes = document.getElementById('cme-model-notes');
    if (notes) {
      const g = cme.gopalswamy_2001_transit_hours !== null && cme.gopalswamy_2001_transit_hours !== undefined
        ? `Gopalswamy et al. (2001) empirical arrival at 1 AU: ${cme.gopalswamy_2001_transit_hours} h (${cme.gopalswamy_2001_earth_arrival}), ${cme.gopalswamy_2001_arrival_speed_kms} km/s, effective acceleration ${cme.gopalswamy_2001_acceleration_ms2} m/s² until 0.76 AU.`
        : 'Gopalswamy et al. (2001): outside the model for this speed.';
      notes.innerHTML = `<div>DBM (w = ${cme.ambient_solar_wind_kms} km/s, Γ = ${(cme.drag_parameter_gamma * 1e7).toFixed(2)}×10⁻⁷ km⁻¹): Earth arrival speed ${cme.v_arrival_earth_kms} km/s.</div><div>${g}</div>` +
        (cme.assumptions || []).map(a => `<div class="text-slate-500">• ${a}</div>`).join('');
    }

    // Initialize 2D Interplanetary Propagation Radar Simulation
    if (cmeSimulator) {
      setTimeout(() => {
        cmeSimulator.resize();
        cmeSimulator.updateFromBackendResult(cme);
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

function togglePSPAnimation() {
  if (!parkerRenderer) return;
  const isRunning = parkerRenderer.togglePSPPlay();
  const icon = document.getElementById('icon-psp-play');
  const text = document.getElementById('text-psp-play');
  if (icon && text) {
    if (isRunning) {
      icon.className = 'fa-solid fa-pause text-[10px]';
      text.innerText = 'Pause';
    } else {
      icon.className = 'fa-solid fa-play text-[10px]';
      text.innerText = 'Play';
    }
  }
}

function onPSPAnomalyScrub(val) {
  if (!parkerRenderer) return;
  parkerRenderer.setPSPAnomaly(val);
  const readout = document.getElementById('psp-anomaly-val');
  if (readout) readout.innerText = `${val}°`;
  const icon = document.getElementById('icon-psp-play');
  const text = document.getElementById('text-psp-play');
  if (icon && text) {
    icon.className = 'fa-solid fa-play text-[10px]';
    text.innerText = 'Play';
  }
}

function setPSPLocationPreset(preset) {
  if (!parkerRenderer) return;
  parkerRenderer.setPSPPreset(preset);
  const icon = document.getElementById('icon-psp-play');
  const text = document.getElementById('text-psp-play');
  if (icon && text) {
    if (preset === 'auto') {
      icon.className = 'fa-solid fa-pause text-[10px]';
      text.innerText = 'Pause';
    } else {
      icon.className = 'fa-solid fa-play text-[10px]';
      text.innerText = 'Play';
    }
  }
}

// Attach PSP functions to window
window.togglePSPAnimation = togglePSPAnimation;
window.onPSPAnomalyScrub = onPSPAnomalyScrub;
window.setPSPLocationPreset = setPSPLocationPreset;

// =========================================================================
// CUSTOM INGESTION & OMNI STUDIO
// =========================================================================
let customIngestChart = null;
let currentCustomDataset = null;

async function loadCustomPresets() {
  try {
    const res = await fetch('/api/custom/presets');
    if (!res.ok) return;
    const data = await res.json();
    const presets = data.presets || [];
    const grid = document.getElementById('import-presets-grid');
    if (grid && presets.length > 0) {
      grid.innerHTML = presets.map(p => `
        <button onclick="loadCustomPreset('${p.id}')" title="${p.note || ''}" class="p-2.5 rounded-lg bg-slate-900/90 hover:bg-slate-850 border border-slate-700/60 hover:border-sky-500/60 text-left transition group">
          <div class="flex items-center justify-between text-[10px] font-mono mb-1">
            <span class="font-bold text-sky-400">${p.tag || 'DATASET'}</span>
            <span class="text-slate-500">${p.records_count || ''} pts</span>
          </div>
          <div class="font-bold text-xs text-slate-200 group-hover:text-sky-300 transition truncate">${p.name}</div>
          <div class="text-[10px] text-slate-400 line-clamp-1 mt-0.5">${p.description || ''}</div>
        </button>
      `).join('');
    }
  } catch (err) {
    console.warn('Error fetching custom presets:', err);
  }
}

async function loadCustomLatest() {
  try {
    const res = await fetch('/api/custom/latest');
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.status === 'success' && data.total_records > 0) {
      currentCustomDataset = data;
      const dash = document.getElementById('import-result-dashboard');
      if (dash) dash.classList.remove('hidden');
      renderCustomIngestUI(data);
    }
  } catch (err) {
    // Nominal if no custom dataset has been ingested yet
  }
}

async function loadCustomPreset(presetId) {
  window.playBlip?.();
  try {
    const res = await fetch(`/api/custom/presets/${presetId}`);
    if (!res.ok) throw new Error('Preset not found');
    const data = await res.json();
    const preset = data.preset;
    if (preset) {
      document.getElementById('import-mission-name').value = `${preset.name} (illustrative profile)`;
      document.getElementById('import-content').value = preset.csv_content;
      await submitCustomImport();
    }
  } catch (e) {
    console.error('Failed to load preset:', e);
  }
}

function clearCustomImportEditor() {
  window.playBlip?.();
  document.getElementById('import-mission-name').value = "Custom Research Spacecraft";
  document.getElementById('import-content').value = "";
  const dash = document.getElementById('import-result-dashboard');
  if (dash) dash.classList.add('hidden');
  currentCustomDataset = null;
}

function loadSampleCSV() {
  loadCustomPreset('may2024_g5');
}

function handleFileUpload(event) {
  const file = event.target.files[0];
  if (!file) return;
  if (/\.(cdf|nc|nc4|h5|hdf|hdf5|fits|fts|zip|gz)$/i.test(file.name)) {
    alert(`${file.name} is a binary file. The importer reads CSV, delimited text and JSON: list the variables as text first (for CDAWeb data, choose the CSV or ASCII listing).`);
    event.target.value = '';
    return;
  }
  // The server accepts imports of up to 64 MB (MAX_IMPORT_BYTES); say so before reading the file.
  if (file.size > 60 * 1024 * 1024) {
    alert(`${file.name} is ${(file.size / 1048576).toFixed(0)} MB. Imports are limited to about 60 MB: split the file or average it to a coarser cadence first.`);
    event.target.value = '';
    return;
  }
  const reader = new FileReader();
  reader.onload = (e) => {
    document.getElementById('import-content').value = e.target.result;
    document.getElementById('import-mission-name').value = file.name.replace(/\.[^/.]+$/, "");
    submitCustomImport();
  };
  reader.readAsText(file);
}

async function submitCustomImport() {
  const missionNameInput = document.getElementById('import-mission-name');
  const contentInput = document.getElementById('import-content');
  const btn = document.getElementById('btn-submit-import');
  const btnText = document.getElementById('btn-submit-import-text');

  const missionName = (missionNameInput ? missionNameInput.value : '').trim() || "Custom Spacecraft";
  const content = contentInput ? contentInput.value : '';

  if (!content.trim()) {
    alert("Please enter or upload telemetry data first, or select one of the historical presets.");
    return;
  }

  if (btnText) btnText.innerText = "Processing Telemetry...";
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/custom/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: content, mission_name: missionName })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(apiErrorText(data, res));

    currentCustomDataset = data;
    window.playBlip?.();

    // Show dashboard
    const dash = document.getElementById('import-result-dashboard');
    if (dash) dash.classList.remove('hidden');

    renderCustomIngestUI(data);
    const warnEl = document.getElementById('import-warnings');
    if (warnEl) {
      const w = data.warnings || [];
      warnEl.innerHTML = w.map(x => `<li>${escapeHtmlReport(x)}</li>`).join('');
      warnEl.classList.toggle('hidden', w.length === 0);
    }
    loadMissions(); // Refresh fleet list so CUSTOM shows up if active
  } catch (err) {
    alert("Ingestion error: " + err.message);
  } finally {
    if (btnText) btnText.innerText = "Ingest & Process Telemetry";
    if (btn) btn.disabled = false;
  }
}

function renderCustomIngestUI(data) {
  const summary = data.summary || {};
  const records = data.records || [];
  const shocks = data.detected_shocks || [];

  // Update HUD KPIs
  const elRecords = document.getElementById('import-kpi-records');
  const elTimeSpan = document.getElementById('import-kpi-time-span');
  const elSpdMax = document.getElementById('import-kpi-speed-max');
  const elSpdMean = document.getElementById('import-kpi-speed-mean');
  const elBzMin = document.getElementById('import-kpi-bz-min');
  const elBzMax = document.getElementById('import-kpi-bz-max');
  const elPdynMax = document.getElementById('import-kpi-pdyn-max');
  const elStandoff = document.getElementById('import-kpi-standoff-min');
  const elGeoAlert = document.getElementById('import-kpi-geo-alert');
  const elShocks = document.getElementById('import-kpi-shocks-count');
  const elChartMission = document.getElementById('import-chart-mission-label');

  if (elRecords) elRecords.innerText = data.total_records.toLocaleString();
  if (elTimeSpan) elTimeSpan.innerText = summary.start_time && summary.end_time ? `${summary.start_time.slice(0, 10)} → ${summary.end_time.slice(0, 10)}` : 'Single epoch';
  const orDash = (v) => (v === null || v === undefined ? '---' : v);
  if (elSpdMax) elSpdMax.innerText = orDash(summary.speed_max);
  if (elSpdMean) elSpdMean.innerText = orDash(summary.speed_mean);
  if (elBzMin) elBzMin.innerText = orDash(summary.bz_min);
  if (elBzMax) elBzMax.innerText = orDash(summary.bz_max);
  if (elPdynMax) elPdynMax.innerText = orDash(summary.pdyn_max);
  if (elStandoff) {
    elStandoff.innerText = orDash(summary.standoff_min);
    if (typeof summary.standoff_min === 'number' && summary.standoff_min < 6.6) {
      elStandoff.className = "text-lg font-bold text-rose-500 font-mono mt-0.5";
      if (elGeoAlert) {
        elGeoAlert.innerText = "CRITICAL: Inward GEO (< 6.6 R_E)";
        elGeoAlert.className = "text-[10px] text-rose-400 font-mono font-bold";
      }
    } else {
      elStandoff.className = "text-lg font-bold text-emerald-400 font-mono mt-0.5";
      if (elGeoAlert) {
        elGeoAlert.innerText = "Nominal cavity (> 6.6 R_E)";
        elGeoAlert.className = "text-[10px] text-slate-500 font-mono";
      }
    }
  }
  if (elShocks) elShocks.innerText = shocks.length;
  if (elChartMission) elChartMission.innerText = (data.mission_name || 'CUSTOM').toUpperCase();

  // Render Timeseries Chart
  renderCustomTimeseriesChart(records);

  // Render Shocks Table
  const tbody = document.getElementById('import-shocks-tbody');
  if (tbody) {
    if (shocks.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="py-3 text-center text-slate-500 font-mono">No shock-like jump found (ΔV ≥ 45 km/s with N2/N1 ≥ 1.5 and B2/B1 ≥ 1.35 over three samples).</td></tr>`;
    } else {
      tbody.innerHTML = shocks.map(s => `
        <tr class="hover:bg-slate-800/40 transition">
          <td class="py-2 px-2 text-slate-300 font-bold">${s.time || '--'}</td>
          <td class="py-2 px-2">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold ${s.classification && s.classification.includes('CME') ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'}">
              ${s.classification || 'Fast Forward Shock'}
            </span>
          </td>
          <td class="py-2 px-2 text-slate-300">${s.upstream_speed} → ${s.downstream_speed} km/s</td>
          <td class="py-2 px-2 text-cyan-400 font-bold">+${s.delta_speed_kms} km/s</td>
          <td class="py-2 px-2 text-amber-300">${s.density_ratio}x</td>
          <td class="py-2 px-2 text-purple-300 font-bold">M_A ~ ${s.mach_proxy || '1.8'}</td>
        </tr>
      `).join('');
    }
  }
}

function renderCustomTimeseriesChart(records) {
  const canvas = document.getElementById('custom-ingest-chart');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');

  const labels = records.map(r => formatTimestampToTimezone(r.time_tag));
  const speeds = records.map(r => r.speed);
  const bzs = records.map(r => r.bz_gsm);
  const pdyns = records.map(r => r.dynamic_pressure);

  if (customIngestChart) {
    customIngestChart.destroy();
  }

  customIngestChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Speed (km/s)',
          data: speeds,
          borderColor: '#38bdf8',
          backgroundColor: 'rgba(56, 189, 248, 0.08)',
          borderWidth: 2,
          pointRadius: records.length > 50 ? 0 : 3,
          pointHoverRadius: 5,
          tension: 0.2,
          yAxisID: 'y'
        },
        {
          label: 'IMF Bz (nT)',
          data: bzs,
          borderColor: '#fb7185',
          backgroundColor: 'transparent',
          borderWidth: 1.8,
          pointRadius: records.length > 50 ? 0 : 2,
          pointHoverRadius: 4,
          tension: 0.2,
          yAxisID: 'y1'
        },
        {
          label: 'Pdyn (nPa)',
          data: pdyns,
          borderColor: '#fbbf24',
          backgroundColor: 'transparent',
          borderWidth: 1.8,
          borderDash: [3, 3],
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.2,
          yAxisID: 'y2'
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: 'rgba(15, 23, 42, 0.95)',
          titleColor: '#e2e8f0',
          bodyColor: '#cbd5e1',
          borderColor: 'rgba(56, 189, 248, 0.3)',
          borderWidth: 1,
          padding: 8,
          titleFont: { family: '"JetBrains Mono", monospace', size: 10 },
          bodyFont: { family: '"JetBrains Mono", monospace', size: 10 }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(51, 65, 85, 0.25)' },
          ticks: { color: '#64748b', font: { family: '"JetBrains Mono", monospace', size: 9 }, maxTicksLimit: 12 }
        },
        y: {
          type: 'linear',
          display: true,
          position: 'left',
          title: { display: true, text: 'Speed (km/s)', color: '#38bdf8', font: { size: 9 } },
          grid: { color: 'rgba(51, 65, 85, 0.25)' },
          ticks: { color: '#38bdf8', font: { family: '"JetBrains Mono", monospace', size: 9 } }
        },
        y1: {
          type: 'linear',
          display: true,
          position: 'right',
          title: { display: true, text: 'Bz (nT)', color: '#fb7185', font: { size: 9 } },
          grid: { drawOnChartArea: false },
          ticks: { color: '#fb7185', font: { family: '"JetBrains Mono", monospace', size: 9 } }
        },
        y2: {
          type: 'linear',
          display: false,
          position: 'right',
          grid: { drawOnChartArea: false }
        }
      }
    }
  });
}

function exportCustomData(format) {
  window.open(`/api/custom/export/${format}`, '_blank');
}

function injectCustomToComparator() {
  if (!currentCustomDataset) {
    alert("Please ingest a telemetry dataset first.");
    return;
  }
  const customName = currentCustomDataset.mission_name || "Custom Spacecraft";

  // Ensure CUSTOM option exists in comp-sat-a and comp-sat-b
  ['comp-sat-a', 'comp-sat-b'].forEach(id => {
    const select = document.getElementById(id);
    if (select) {
      let opt = select.querySelector('option[value="CUSTOM"]');
      if (!opt) {
        opt = document.createElement('option');
        opt.value = 'CUSTOM';
        select.appendChild(opt);
      }
      opt.innerText = `Custom: ${customName}`;
    }
  });

  const satBSelect = document.getElementById('comp-sat-b');
  if (satBSelect) satBSelect.value = 'CUSTOM';

  switchTab('comparator');
  runComparison();
}

async function loadMissions() {
  try {
    const res = await fetch('/api/missions');
    const missions = await res.json();
    const container = document.getElementById('fleet-cards-container');
    if (!container) return;

    // The custom mission's name comes from the imported file's name or the import form;
    // escape every text field before it goes into HTML.
    container.innerHTML = missions.map(escapeHtmlDeep).map(m => `
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

// Each selection gets a number; a slower answer for an earlier selection is dropped, so a
// quick second click cannot end with the first event's data under the second's highlight.
let eventSelectSeq = 0;
async function selectEvent(eventId) {
  const seq = ++eventSelectSeq;
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
    if (seq !== eventSelectSeq) return;
    const meta = ev.metadata;

    document.getElementById('event-title').innerText = meta.title;
    const evProv = ev.provenance || {};
    const obs = meta.observed_5min;
    document.getElementById('event-desc').innerText = meta.summary +
      `\n\nData: ${evProv.kind === 'observed' ? 'OBSERVED' : 'SYNTHETIC'}. ${evProv.description || ''}` +
      (obs ? ` The cards show the OMNI 5-min extremes of these 48 h${obs.min_sym_h !== null && obs.min_sym_h !== undefined ? ` (minimum SYM-H ${obs.min_sym_h} nT)` : ''} and the published peak Kp.`
           : ' The cards show the values the illustrative profile was built from and the published peak Kp.');
    // Observed OMNI extremes when the event is covered, otherwise the profile's input values
    const ext = obs || meta;
    const fmt = (v, unit) => (v === null || v === undefined ? `--- ${unit}` : `${v} ${unit}`);
    document.getElementById('event-peak-kp').innerText = meta.peak_kp;
    document.getElementById('event-min-bz').innerText = fmt(ext.min_bz, 'nT');
    document.getElementById('event-peak-v').innerText = fmt(ext.peak_speed, 'km/s');
    document.getElementById('event-peak-pdyn').innerText = fmt(ext.peak_dyn_pressure, 'nPa');

    const sevBadge = document.getElementById('event-severity-badge');
    if (sevBadge) {
      // NOAA levels: G5 from Kp 9o, G4 from Kp 8- (7.67)
      const isExtreme = meta.peak_kp >= 8.83;
      sevBadge.innerText = isExtreme ? `Extreme G5 (Kp=${meta.peak_kp})` : (meta.peak_kp >= 7.5 ? `Severe G4 (Kp=${meta.peak_kp})` : `Nominal (Kp=${meta.peak_kp})`);
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

    renderEventDst(ev);
  } catch (err) {
    console.error('Error selecting event:', err);
  }
}

// Hourly observations (time stamp = start of the hour) placed on a finer series' time axis.
function alignHourlyToSeries(timeTags, hourly) {
  const byHour = {};
  hourly.forEach(o => { byHour[String(o.time_tag).slice(0, 13)] = o.dst; });
  const seen = {};
  return timeTags.map(t => {
    const h = String(t).slice(0, 13);
    if (h in byHour && !seen[h]) { seen[h] = true; return byHour[h]; }
    return null;
  });
}

function describeDstSkill(sk, against) {
  if (!sk || sk.n === undefined) return '';
  if (sk.r === null || sk.r === undefined) return `Not enough overlap with ${against} to score the model (n = ${sk.n}).`;
  const iv = (ci) => (ci ? ` [${ci[0]}, ${ci[1]}]` : '');
  let note = '';
  if (sk.n_eff !== undefined) {
    note = sk.few_independent_samples
      ? ` Only ~${sk.n_eff} independent samples (autocorrelated series): intervals are missing or too narrow; score several storms.`
      : ` 95 % intervals in brackets (~${sk.n_eff} independent samples).`;
  }
  return `vs ${against}: n = ${sk.n}, r = ${sk.r}${iv(sk.r_ci95)}, RMSE = ${sk.rmse_nt}${iv(sk.rmse_ci95_nt)} nT, bias = ${sk.bias_nt}${iv(sk.bias_ci95_nt)} nT, min model ${sk.min_predicted_nt} / observed ${sk.min_observed_nt} nT.${note}`;
}

function renderEventDst(ev) {
  const block = document.getElementById('event-dst-block');
  const cmp = ev.dst_comparison;
  if (!block) return;
  if (!cmp) { block.classList.add('hidden'); return; }
  block.classList.remove('hidden');
  const ctx = document.getElementById('chart-event-dst')?.getContext('2d');
  if (!ctx) return;
  if (chartEventDst) chartEventDst.destroy();
  chartEventDst = new Chart(ctx, {
    type: 'line',
    data: {
      labels: cmp.time_tags.map(t => String(t).slice(5, 16)),
      datasets: [
        { label: 'SYM-H observed [nT]', data: cmp.observed, borderColor: '#38bdf8', borderWidth: 1.5, pointRadius: 0 },
        { label: cmp.models.obrien.name, data: cmp.models.obrien.series, borderColor: '#f43f5e', borderWidth: 1.2, pointRadius: 0 },
        { label: cmp.models.burton.name, data: cmp.models.burton.series, borderColor: '#eab308', borderWidth: 1.2, pointRadius: 0, borderDash: [4, 3] }
      ]
    },
    options: darkChartOptions
  });
  const sk = document.getElementById('event-dst-skill');
  if (sk) sk.innerText = `${cmp.models.obrien.name}: ${describeDstSkill(cmp.models.obrien.skill, 'SYM-H')}  ${cmp.models.burton.name}: ${describeDstSkill(cmp.models.burton.skill, 'SYM-H')}`;
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

    if (alphaEl) alphaEl.innerText = psd.spectral_slope_alpha != null ? psd.spectral_slope_alpha.toFixed(2) : '---';
    if (regimeEl) {
      regimeEl.innerText = psd.cascade_regime || 'Inertial Cascade';
      const a = psd.spectral_slope_alpha;
      regimeEl.className = `text-[11px] font-semibold mt-1 truncate ${a == null ? 'text-slate-400' : (a >= 1.55 && a <= 1.80 ? 'text-cyan-400' : (a >= 1.4 && a < 1.55 ? 'text-emerald-400' : 'text-amber-400'))}`;
    }
    if (r2El) r2El.innerText = psd.r_squared != null ? psd.r_squared.toFixed(2) : '---';
    if (rmsEl) rmsEl.innerText = psd.fluctuation_rms !== undefined ? psd.fluctuation_rms.toFixed(2) : '---';
    if (rmsUnitEl) {
      rmsUnitEl.innerText = param === 'speed' ? 'km/s' : (param === 'density' ? 'cm⁻³' : 'nT');
    }
    if (taylorKmEl) taylorKmEl.innerText = psd.taylor_scale_km_1mhz ? psd.taylor_scale_km_1mhz.toLocaleString() : '---';
    if (taylorReEl) taylorReEl.innerText = psd.taylor_scale_re_1mhz !== undefined ? psd.taylor_scale_re_1mhz : '--';

    if (chartSpectrum) chartSpectrum.destroy();

    const unit = param === 'speed' ? '(km/s)²/Hz' : (param === 'density' ? '(cm⁻³)²/Hz' : 'nT²/Hz');
    // (frequency in mHz, value) points so the frequency axis can be logarithmic: on a
    // category axis the power laws were not straight lines and the slope looked wrong.
    const fm = psd.frequencies_hz.map(f => f * 1000);
    const xy = arr => arr.map((v, i) => ({ x: fm[i], y: v }));

    const datasets = [
      {
        label: `Observed PSD [${sat} • ${param}] (${unit})`,
        data: xy(psd.power_density),
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
        data: xy(psd.kolmogorov_psd),
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
        data: xy(psd.iroshnikov_psd),
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
        datasets: datasets
      },
      options: {
        ...darkChartOptions,
        scales: {
          x: {
            ...darkChartOptions.scales.x,
            type: 'logarithmic',
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
                return `${context.dataset.label}: ${context.parsed.y.toExponential(3)} at ${context.parsed.x.toFixed(3)} mHz`;
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
  if (orbitViewer && orbitViewer.canvas && orbitViewer.canvas.offsetParent !== null) {
    if (orbitViewer.canvas.width === 0 || orbitViewer.canvas.height === 0 || orbitViewer.offsetX === 0) {
      orbitViewer.resize();
    }
    orbitViewer.draw();
    if (orbitViewer.lastComputedBoundaries) {
      updateBoundaryCards(orbitViewer.lastComputedBoundaries);
    }
  }
  requestAnimationFrame(animateOrbits);
}

function resetOrbitView() {
  if (orbitViewer) orbitViewer.resetView();
}

function toggleOrbitGrid(show) {
  if (orbitViewer) orbitViewer.setGseGrid(show);
}

function toggleOrbitDipole(show) {
  if (orbitViewer) orbitViewer.setDipoleField(show);
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

function setOrbitBoundaryModel(model) {
  if (orbitViewer) {
    orbitViewer.setBoundaryModel(model);
    orbitViewer.draw();
    if (orbitViewer.lastComputedBoundaries) {
      updateBoundaryCards(orbitViewer.lastComputedBoundaries);
    }
  }
}

function setOrbitSolarWindPreset(presetKey) {
  if (!orbitViewer) return;
  if (presetKey === 'quiet') {
    orbitViewer.setSolarWindConditions(380, 1.8, 2.5, 8.5, 2.0);
  } else if (presetKey === 'storm') {
    orbitViewer.setSolarWindConditions(580, 8.0, -6.5, 6.0, 1.0);
  } else if (presetKey === 'severe') {
    orbitViewer.setSolarWindConditions(920, 32.0, -28.0, 4.2, 0.3);
  }
  orbitViewer.draw();
  if (orbitViewer.lastComputedBoundaries) {
    updateBoundaryCards(orbitViewer.lastComputedBoundaries);
  }
  const btnSync = document.getElementById('btn-orbit-sync');
  if (btnSync) {
    btnSync.classList.add('animate-pulse', 'bg-amber-950/80', 'text-amber-300');
    btnSync.classList.remove('bg-sky-950/60', 'text-sky-300');
  }
}

function syncOrbitLiveTelemetry() {
  if (!orbitViewer || !currentTelemetryData || !currentTelemetryData.latest) return;
  const latest = currentTelemetryData.latest;
  const mb = solarWindMachBeta(latest);
  orbitViewer.setSolarWindConditions(latest.speed, latest.dynamic_pressure, latest.bz_gsm, mb.mms, mb.beta);
  orbitViewer.draw();
  if (orbitViewer.lastComputedBoundaries) {
    updateBoundaryCards(orbitViewer.lastComputedBoundaries);
  }
  const btnSync = document.getElementById('btn-orbit-sync');
  if (btnSync) {
    btnSync.classList.remove('animate-pulse', 'bg-amber-950/80', 'text-amber-300');
    btnSync.classList.add('bg-sky-950/60', 'text-sky-300');
  }
}

function updateBoundaryCards(b) {
  if (!b) return;
  const cardBow = document.getElementById('card-bow-standoff');
  const cardBowKm = document.getElementById('card-bow-km');
  if (cardBow) cardBow.innerText = `${b.r0_bs.toFixed(1)} RE`;
  if (cardBowKm) cardBowKm.innerText = `~${Math.round(b.r0_bs * 6371).toLocaleString()} km`;

  const cardMp = document.getElementById('card-mp-standoff');
  const cardMpKm = document.getElementById('card-mp-km');
  const cardMpStatus = document.getElementById('card-mp-geo-status');
  if (cardMp) {
    cardMp.innerText = `${b.r0_mp.toFixed(1)} RE`;
    cardMp.className = b.insideGeo ? 'text-2xl font-hud font-bold text-rose-400 animate-pulse' : 'text-2xl font-hud font-bold text-amber-300';
  }
  if (cardMpKm) cardMpKm.innerText = `~${Math.round(b.r0_mp * 6371).toLocaleString()} km`;
  if (cardMpStatus) {
    const margin = b.r0_mp - 6.6;
    if (b.insideGeo) {
      cardMpStatus.innerHTML = `<span class="text-rose-400 font-bold"><i class="fa-solid fa-triangle-exclamation mr-1"></i>SUB-GEO COMPRESSION (${margin.toFixed(1)} RE inside GEO)</span>`;
    } else {
      cardMpStatus.innerHTML = `<span class="text-emerald-400 font-medium">GEO Standoff Clear (+${margin.toFixed(1)} RE outside geostationary orbit)</span>`;
    }
  }

  const cardSheath = document.getElementById('card-sheath-thick');
  const cardSheathKm = document.getElementById('card-sheath-km');
  if (cardSheath) cardSheath.innerText = `${b.sheathRe.toFixed(1)} RE`;
  if (cardSheathKm) cardSheathKm.innerText = `~${Math.round(b.sheathRe * 6371).toLocaleString()} km`;

  const cardAlpha = document.getElementById('card-flaring-alpha');
  if (cardAlpha) cardAlpha.innerText = `${b.alpha_mp.toFixed(2)} / ${b.alpha_bs.toFixed(2)}`;
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

  if (span === 'archive') {
    const { mission, qs } = archiveQuery();
    if (format === 'csv') window.location.href = `/api/archive/${mission}?${qs}&format=csv`;
    else alert('PNG export covers the live views. Use CSV for archive intervals.');
    return;
  }
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
    if (container) container.innerHTML = `<div class="text-rose-400 p-4">Failed to generate bulletin: ${escapeHtml(err.message)}</div>`;
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

function escapeHtml(text) {
  return String(text ?? '')
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

// Copy of a JSON value with every string HTML-escaped (for template literals rendered as HTML).
function escapeHtmlDeep(value) {
  if (typeof value === 'string') return escapeHtml(value);
  if (Array.isArray(value)) return value.map(escapeHtmlDeep);
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([k, v]) => [k, escapeHtmlDeep(v)]));
  }
  return value;
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
        body.innerHTML = `<div class="p-6 text-center text-rose-400">Failed to load scientific references: ${escapeHtml(err.message)}</div>`;
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

function openUserGuideModal() {
  openReferencesModal('userguide');
}

function updateRefTabButtons() {
  const tabs = ['equations', 'providers', 'licenses', 'handbook', 'userguide', 'sandbox'];
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
  } else if (currentRefTab === 'userguide') {
    renderUserGuideTab(body);
  } else if (currentRefTab === 'sandbox') {
    renderSandboxTab(body);
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
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No scientific papers matched "${escapeHtml(refSearchQuery)}".</div>`;
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
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No data observatories matched "${escapeHtml(refSearchQuery)}".</div>`;
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
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No physical parameters matched "${escapeHtml(refSearchQuery)}".</div>`;
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

function renderUserGuideTab(container) {
  const q = (refSearchQuery || '').toLowerCase().trim();

  const sections = [
    {
      id: 'guide-arch',
      title: '1. Mission Control Architecture & Two-Tier Navigation',
      icon: 'fa-layer-group',
      color: 'text-sky-400',
      summary: 'Hierarchical four-domain layout, real-time command bar, and keyboard shortcuts for rapid scientific operations.',
      content: `
        <div class="space-y-3">
          <p class="text-xs text-slate-300 leading-relaxed">
            HELIOS-L1 operates on a two-tier mission architecture designed for mission-control efficiency and low cognitive overhead. The primary header gives global awareness through active status badges (NOAA G-scale, IMF Bz magnetic reconnection state, Subsolar Standoff distance, and Akasofu coupling flux ε).
          </p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
              <div class="text-[11px] font-bold text-sky-300 flex items-center space-x-1.5">
                <i class="fa-solid fa-compass"></i>
                <span>Tier 1: Scientific Mission Domains</span>
              </div>
              <ul class="text-[11px] text-slate-400 space-y-1 list-disc list-inside">
                <li><strong class="text-slate-200">1: L1 Fleet &amp; Telemetry</strong> (NOAA real-time solar wind and CDAWeb archive intervals, spacecraft comparator, orbits, fleet catalogue; Aditya-L1 and SOHO are simulated)</li>
                <li><strong class="text-slate-200">2: Solar &amp; Heliosphere</strong> (SOHO LASCO and GOES SUVI images, NOAA active regions, CME arrival models, Parker spiral, turbulence spectra)</li>
                <li><strong class="text-slate-200">3: Geospace &amp; Hazards</strong> (Starkov auroral oval and Dst models, storm forecast, D-RAP and GIC, solar cycle, storms archive)</li>
                <li><strong class="text-slate-200">4: Data Studio &amp; Science</strong> (file import, event analysis on archive data, OMNI statistics, references)</li>
              </ul>
            </div>

            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
              <div class="text-[11px] font-bold text-emerald-300 flex items-center space-x-1.5">
                <i class="fa-regular fa-keyboard"></i>
                <span>Primary Keyboard Hotkeys</span>
              </div>
              <div class="grid grid-cols-2 gap-1 text-[11px] text-slate-300 font-mono">
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-sky-300">1-4</kbd> Switch Domain</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">R</kbd> Live Data Fetch</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-cyan-300">A</kbd> Sonification Mute</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-indigo-300">B</kbd> Advisory Bulletin</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-emerald-300">P</kbd> DOI References</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-indigo-300">U</kbd> Operator Guide</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-amber-300">T</kbd> Time Zone</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">S</kbd> Settings</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">L</kbd> Incident Log</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">O</kbd> About</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-300">?</kbd> All Shortcuts</div>
                <div><kbd class="px-1.5 py-0.5 rounded bg-slate-900 border border-slate-700 text-rose-300">ESC</kbd> Close Active Modal</div>
              </div>
            </div>
          </div>
        </div>
      `
    },
    {
      id: 'guide-boundaries',
      title: '2. Sun-Earth L1 Orbital Geometry & Magnetopause / Bow Shock Modeling',
      icon: 'fa-shield-halved',
      color: 'text-amber-400',
      summary: 'Shue et al. (1998) magnetopause with the Chao et al. (2002) or Farris & Russell (1994) bow shock, GSE coordinates, and sub-GEO compression warnings.',
      content: `
        <div class="space-y-3">
          <p class="text-xs text-slate-300 leading-relaxed">
            The Orbital Geometry Simulator projects the Sun-Earth L1 and L2 Lagrangian saddle points in both 2D Ecliptic GSE (Geocentric Solar Ecliptic) and 3D oblique axonometric projections. Active spacecraft ephemerides (DSCOVR Lissajous, ACE Halo, ISRO Aditya-L1 Halo, WIND, SOHO, and GOES-16 GEO ring) are rendered with continuous physics-based streamflow particles.
          </p>

          <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-2">
            <div class="text-[11px] font-bold text-amber-400 uppercase tracking-wider flex items-center space-x-1.5">
              <i class="fa-solid fa-calculator"></i>
              <span>Governing Equations</span>
            </div>
            <div class="font-mono text-xs text-amber-300 space-y-1 pl-2 border-l-2 border-amber-500/50">
              <div>Magnetopause, Shue et al. (1998): r = r₀ (2 / (1 + cos θ))^α</div>
              <div>r₀ = (10.22 + 1.29 tanh(0.184 (Bz + 8.14))) · P_dyn^(-1/6.6),&nbsp;&nbsp;α = (0.58 − 0.007 Bz)(1 + 0.024 ln P_dyn)</div>
              <div>Bow shock, Chao et al. (2002): r = r₀ ((1 + ε) / (1 + ε cos θ))^α,&nbsp;&nbsp;ε = 1.029</div>
              <div>r₀ = a₁(1 + a₂Bz)(1 + a₉β)(1 + a₄((a₈ − 1)M_ms² + 2) / ((a₈ + 1)M_ms²)) · P_dyn^(-1/a₁₁)</div>
              <div>α = a₅(1 + a₁₃Bz)(1 + a₇P_dyn)(1 + a₁₀ ln(1 + β))(1 + a₁₄M_ms)&nbsp;&nbsp;[a₃, a₆ replace a₂, a₁₃ for Bz &lt; 0]</div>
              <div>Bow shock, Farris &amp; Russell (1994): R_bs = r₀,mp [1 + 1.1 ((γ − 1)M_ms² + 2) / ((γ + 1)(M_ms² − 1))],&nbsp;&nbsp;γ = 5/3</div>
              <div>M_ms = magnetosonic Mach number, β = plasma beta (OMNI definitions)</div>
            </div>
          </div>

          <div class="p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs space-y-1">
            <div class="font-bold text-rose-300 flex items-center space-x-1.5">
              <i class="fa-solid fa-triangle-exclamation text-rose-400"></i>
              <span>Critical Operational Alert: Sub-GEO Compression (r₀,mp &lt; 6.6 R_E)</span>
            </div>
            <p class="text-slate-300 leading-relaxed text-[11px]">
              Under severe coronal mass ejection impacts (dynamic pressure P_dyn &gt; 25 nPa coupled with southward Bz &lt; -20 nT), the dayside magnetopause can be compressed inside Geostationary Orbit (GEO radius = 6.6 R_E ≈ 42,164 km). Geostationary telecommunication and weather satellites (e.g. GOES-16) are abruptly exposed to unshielded magnetosheath plasma and direct solar wind, inducing severe electrostatic spacecraft surface charging, attitude control torque disturbances, and single-event upsets (SEUs).
            </p>
          </div>
        </div>
      `
    },
    {
      id: 'guide-telemetry',
      title: '3. Interplanetary Magnetic Field & Solar Wind Plasma Telemetry',
      icon: 'fa-satellite-dish',
      color: 'text-cyan-400',
      summary: 'Interpretation of IMF Bt, Bz, solar wind velocity, proton density, dynamic pressure, and real-time acoustic sonification.',
      content: `
        <div class="space-y-3">
          <p class="text-xs text-slate-300 leading-relaxed">
            The primary dashboard ingests 1-minute real-time interplanetary telemetry transmitted from L1 spacecraft (~1.5 million km upstream). Key observational parameters include:
          </p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-sky-300">Total Field (Bt) &amp; Bz Component</span>
              <p class="text-slate-400 text-[11px]">
                Bz is the critical gatekeeper. When Bz turns strongly negative (Southward), interplanetary magnetic field lines reconnect with Earth's northward dipole field on the dayside, initiating the Dungey convection cycle and driving major geomagnetic storms.
              </p>
            </div>
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-amber-300">Bulk Velocity (V_sw) &amp; Density (Np)</span>
              <p class="text-slate-400 text-[11px]">
                Slow solar wind (~300-400 km/s) originates from streamer belts, while fast streams (&gt; 600-800 km/s) emanate from open coronal holes. High proton density spikes (&gt; 20 cm⁻³) signify coronal mass ejection sheath plasma or co-rotating interaction regions (CIRs).
              </p>
            </div>
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-emerald-300">Dynamic Ram Pressure (P_dyn)</span>
              <p class="text-slate-400 text-[11px]">
                P_dyn = 1.6726 × 10⁻⁶ · Np · V_sw² (nPa). Governs the physical compression of Earth's dayside magnetopause cavity. Nominal background is 1.5 - 2.5 nPa; CME shock fronts frequently exceed 20 - 60 nPa.
              </p>
            </div>
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-purple-300">Real-Time Acoustic Sonification</span>
              <p class="text-slate-400 text-[11px]">
                The <em>Sonify Plasma</em> button plays the latest solar wind as sound (sound on or off with key 'A'): the pitch follows the speed (300-1000 km/s to 180-540 Hz), the second tone is a fifth above for northward and a tritone for southward Bz, and the tremolo rate follows the density (2-25 cm⁻³ to 3-12 Hz).
              </p>
            </div>
          </div>
        </div>
      `
    },
    {
      id: 'guide-omni',
      title: '4. File Import & Shock Screening',
      icon: 'fa-file-import',
      color: 'text-purple-400',
      summary: 'Your own CSV, text or JSON files, illustrative storm profiles, a simple screening for shock-like jumps, and comparison with the fleet.',
      content: `
        <div class="space-y-3">
          <p class="text-xs text-slate-300 leading-relaxed">
            The Custom Ingestion tab reads your own CSV, tab- or space-delimited text and JSON files (OMNI listings, CDAWeb text output, HELIOS exports) and computes the derived quantities. Measured OMNI data for any interval come from the dashboard's Archive Interval loader instead.
          </p>
          <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-2">
            <div class="text-[11px] font-bold text-purple-300 uppercase tracking-wider">Illustrative profiles (hand-written, not measured data):</div>
            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2 text-[11px]">
              <div class="p-2 rounded bg-space-900 border border-slate-800"><strong class="text-rose-400">May 2024 G5 Superstorm:</strong> Strongest geomagnetic storm in about 20 years.</div>
              <div class="p-2 rounded bg-space-900 border border-slate-800"><strong class="text-amber-400">Bastille Day 2000:</strong> X5.7 solar flare with extreme CME shock wave, V &gt; 1,000 km/s.</div>
              <div class="p-2 rounded bg-space-900 border border-slate-800"><strong class="text-red-400">Carrington 1859 Event:</strong> The historic benchmark superstorm (no in-situ data exist).</div>
              <div class="p-2 rounded bg-space-900 border border-slate-800"><strong class="text-orange-400">Halloween 2003 Storms:</strong> Series of intense X-class flares and satellite failures.</div>
              <div class="p-2 rounded bg-space-900 border border-slate-800"><strong class="text-emerald-400">Quiet Interplanetary Wind:</strong> Baseline quiet heliosphere background conditions.</div>
            </div>
          </div>
          <div class="p-3 rounded-lg bg-space-950 border border-slate-800 text-xs space-y-1">
            <span class="font-bold text-sky-300">Shock screening</span>
            <p class="text-slate-300 text-[11px] leading-relaxed">
              Each sample is compared with the one three samples earlier; a jump with ΔV ≥ 45 km/s, N₂/N₁ ≥ 1.5 and B₂/B₁ ≥ 1.35 is listed with a rough Mach proxy (1 + ΔV / 70 km/s). These are screening thresholds, not a Rankine-Hugoniot solution: shock normals, speeds and Mach numbers with uncertainties are in Data Studio, Event Analysis.
            </p>
          </div>
        </div>
      `
    },
    {
      id: 'guide-corona',
      title: '5. Solar EUV Corona, CME Kinematics & Parker Spiral Dynamics',
      icon: 'fa-sun',
      color: 'text-yellow-400',
      summary: 'GOES SUVI and SOHO LASCO images, NOAA active regions, CME drag-based and empirical arrival models, and Parker spiral magnetic field connectivity.',
      content: `
        <div class="space-y-3">
          <p class="text-xs text-slate-300 leading-relaxed">
            The tab shows the latest SOHO LASCO C2/C3 and GOES SUVI 195 Å images, the NOAA SWPC active regions on a schematic disk, and CME arrival models. The colour buttons of the disk are drawing styles named after these passbands:
          </p>
          <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
              <span class="font-bold text-amber-300">EUV passbands (drawing styles of the schematic disk)</span>
              <ul class="text-[11px] text-slate-400 space-y-1 list-disc list-inside">
                <li><strong class="text-amber-200">193 Å (Fe XII, 1.2 MK):</strong> Coronal holes, high-speed wind source regions.</li>
                <li><strong class="text-red-300">304 Å (He II, 50,000 K):</strong> Chromosphere, prominences, eruptive filaments.</li>
                <li><strong class="text-yellow-200">171 Å (Fe IX, 0.6 MK):</strong> Quiet corona, quiescent coronal magnetic loops.</li>
                <li><strong class="text-teal-200">131 Å (Fe VIII 0.4 MK and Fe XXI 10 MK):</strong> Extremely hot flaring plasma, flare arcades.</li>
                <li><strong class="text-sky-300">LASCO C2:</strong> White-light occulted coronagraph (2.0 to 6.0 R_Sun).</li>
              </ul>
            </div>
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1.5">
              <span class="font-bold text-sky-300">Parker Spiral &amp; SEP Magnetic Connectivity</span>
              <p class="text-[11px] text-slate-400 leading-relaxed">
                Solar rotation (Ω = 2.865 × 10⁻⁶ rad/s) twists interplanetary magnetic field lines into an Archimedean spiral:
                tan Ψ = (Ω · r) / V_sw.
                Near 1 AU at nominal solar wind speed (~450 km/s), the spiral angle is ~45°. This determines whether Solar Energetic Particles (SEPs) from an active region will be magnetically guided directly toward Earth and L1 spacecraft.
              </p>
            </div>
          </div>
        </div>
      `
    },
    {
      id: 'guide-hazards',
      title: '6. Geospace Hazards, GIC Modeling & HF Ionospheric Absorption',
      icon: 'fa-bolt',
      color: 'text-rose-400',
      summary: 'Auroral oval boundaries (Starkov 1994), Boteler GIC geoelectric fields on power grids, and NOAA D-RAP radio absorption.',
      content: `
        <div class="space-y-3">
          <p class="text-xs text-slate-300 leading-relaxed">
            The Geospace Hazards domain assesses operational space weather risks to terrestrial electrical power grids, trans-polar aviation routes, and satellite constellations:
          </p>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-emerald-300">Auroral Oval Visibility</span>
              <p class="text-slate-400 text-[11px]">
                Computes the poleward and equatorward oval boundaries and the equatorward edge of the diffuse aurora with the Starkov (1994) model, driven by OMNI AL when available (otherwise Kp converted to AL), for any UTC time. Projects luminescence curtains and ground observatory visibility on an interactive world map with day/night terminator.
              </p>
            </div>
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-amber-300">Geomagnetically Induced Currents</span>
              <p class="text-slate-400 text-[11px]">
                Plane-wave surface impedance model (Boteler &amp; Pirjola 2017): E = Z · H. Computes surface geoelectric field (V/km) and neutral transformer saturation currents based on underlying geology (Precambrian resistive shield vs sedimentary basin).
              </p>
            </div>
            <div class="bg-space-950 p-3 rounded-lg border border-slate-800 space-y-1">
              <span class="font-bold text-rose-300">D-RAP HF Radio Blackout</span>
              <p class="text-slate-400 text-[11px]">
                NOAA SWPC D-Region Absorption Prediction flare relation: Highest Affected Frequency HAF = 10 log₁₀(Fx) + 65 MHz (reduced by cos^0.75 χ) and absorption (HAF/f)^1.5 dB on the sunlit side. The proton (polar cap) part of D-RAP (Sauer &amp; Wilkinson 2008) is not modelled.
              </p>
            </div>
          </div>
        </div>
      `
    },
    {
      id: 'guide-analysis',
      title: '7. Event Analysis & OMNI Statistics',
      icon: 'fa-microscope',
      color: 'text-indigo-400',
      summary: 'Shock normals, minimum variance, deHoffmann-Teller, flux rope fits, magnetic cloud search, the Richardson & Cane ICME list, the IPShocks shock database, sudden commencements in SYM-H, superposed epochs, storm selection and Dst model skill on NASA CDAWeb data.',
      content: `
        <div class="space-y-2 text-[11px] text-slate-300 leading-relaxed">
          <p>Data Studio, Event Analysis works on WIND, ACE and DSCOVR data at the instruments' cadence and on OMNI: interplanetary shock normals (coplanarity and mixed-mode methods) with Monte Carlo uncertainties and multi-spacecraft timing; minimum variance analysis with Sonnerup &amp; Scheible (1998) errors; the deHoffmann-Teller frame and Walén test; Lundquist flux rope fits with the Lepping et al. (2003) error estimates; the time shift of WIND, ACE or DSCOVR data to the bow shock nose by NASA's High Resolution OMNI method, with OMNI's own shifts for comparison; the Lepping et al. (2005) magnetic cloud search; sudden commencements in OMNI SYM-H, compared with the lists of the Observatori de l'Ebre for ISGI and paired with the interplanetary shock at L1 that drove them; coupling functions, proton beta and Alfvén Mach number with uncertainties; superposed epoch analysis with bootstrap intervals, also of the GFZ indices Kp and Hp30; storm selection by Dst; ring current model skill over many storms; and hourly OMNI statistics since 1963 with intervals that allow for autocorrelation.</p>
          <p>The Richardson &amp; Cane list of near-Earth ICMEs since 1996 (read live, or the bundled snapshot) is shown as a table and marks the storms, shocks and cloud candidates found here. The IPShocks database of the University of Helsinki lists the shocks at WIND, ACE and DSCOVR with their normals, speeds and Mach numbers; the shock analysis shows the listed values next to its own and can use the database's averaging windows. Under each field and plasma result, the data coverage gives the fraction of the interval covered, the number of gaps and the longest one.</p>
          <p>Every result can be saved as JSON with the CDAWeb datasets, requests and parameters behind it.</p>
        </div>
      `
    }
  ];

  const filtered = sections.filter(s => {
    if (!q) return true;
    return (
      s.title.toLowerCase().includes(q) ||
      s.summary.toLowerCase().includes(q) ||
      s.content.toLowerCase().includes(q)
    );
  });

  if (filtered.length === 0) {
    container.innerHTML = `<div class="text-center py-12 text-slate-400">No user guide chapters matched "${escapeHtml(refSearchQuery)}".</div>`;
    return;
  }

  container.innerHTML = `
    <div class="mb-4 flex flex-wrap items-center justify-between gap-2 text-xs text-slate-400 border-b border-slate-800 pb-3">
      <div>
        <h3 class="font-tech font-bold text-slate-100 text-sm flex items-center space-x-2">
          <i class="fa-solid fa-graduation-cap text-indigo-400"></i>
          <span>HELIOS-L1 Science Suite Operator Manual &amp; Scientific Guide</span>
        </h3>
        <p class="text-[11px] text-slate-400 mt-0.5">Comprehensive operating manual, physical formulations, operational hazard scales, and mission control workflows.</p>
      </div>
      <span class="px-2.5 py-1 rounded bg-indigo-950/80 text-indigo-300 border border-indigo-800/60 font-mono text-[11px]">Full guide: docs/USER_GUIDE.md</span>
    </div>

    <div class="space-y-4">
      ${filtered.map(sec => `
        <div class="bg-space-800/80 p-5 rounded-xl border border-slate-800 hover:border-slate-700 transition shadow-lg space-y-3">
          <div class="flex items-center space-x-2.5 border-b border-slate-800 pb-2">
            <i class="fa-solid ${sec.icon} ${sec.color} text-sm"></i>
            <h4 class="font-bold text-slate-100 text-sm tracking-wide">${sec.title}</h4>
          </div>
          <p class="text-xs text-slate-400 italic">${sec.summary}</p>
          <div class="pt-1">${sec.content}</div>
        </div>
      `).join('')}
    </div>
  `;
}

// =============================================================================
// INTERACTIVE PHYSICS EQUATION SOLVER & SANDBOX
// =============================================================================
let sandboxParams = {
  vsw: 450,
  density: 5.0,
  bt: 6.0,
  bz: -4.0,
  by: 2.0,
  temp: 100000
};

function computeSandboxPhysics(p) {
  const vsw = Math.max(50, Number(p.vsw) || 450);
  const n = Math.max(0.01, Number(p.density) || 5.0);
  const bt = Math.max(0.01, Number(p.bt) || 6.0);
  const bz = p.bz !== undefined ? Number(p.bz) : -4.0;
  const by = p.by !== undefined ? Number(p.by) : 2.0;
  const temp = Math.max(1000, Number(p.temp) || 100000);

  // 1. Dynamic pressure (nPa)
  const pdyn = 1.6726e-6 * n * Math.pow(vsw, 2);
  const pFactor = Math.pow(Math.max(0.05, pdyn), -1.0 / 6.6);

  // 2. Wave speeds (km/s)
  const va = 21.812 * (bt / Math.sqrt(n));
  const cs = 0.1174 * Math.sqrt(temp);
  const vms = Math.sqrt(va * va + cs * cs);

  // 3. Mach numbers (proton wave speeds above, as /api/physics)
  const ma = vsw / Math.max(1.0, va);
  const mms = vsw / Math.max(1.0, vms);

  // 4. Plasma beta and the magnetosonic Mach number with the OMNI definitions (alphas and
  // electrons included), which the bow shock models and the orbit view use. The proton-only
  // M_ms above is about 10-15% higher and was fed to the bow shocks before.
  const omni = solarWindMachBeta({ speed: vsw, density: n, temperature: temp, bt: bt });
  const beta = omni.beta;
  const mms_omni = omni.mms;

  // 5. Shue et al. (1998) magnetopause and Chao et al. (2002) bow shock (orbits.js)
  const mp = shue1998Magnetopause(pdyn, bz);
  const mp_r0 = mp.r0;
  const mp_alpha = mp.alpha;
  const bs = chaoBowShock(pdyn, bz, mms_omni, beta);
  const bs_r0 = bs.r0;
  const bs_alpha = bs.alpha;

  // Shue et al. (1997) standoff (the one OMNI uses) and Farris & Russell (1994) bow shock for comparison
  const shue97_r0 = shue1997Standoff(pdyn, bz);
  const fr_bs_r0 = mms_omni > 1.0 ? farrisRussellBowShock(mp_r0, mms_omni).r0 : null;

  // Sheath thickness
  const sheath_re = bs_r0 - mp_r0;

  // 6. Clock angle & couplings
  const bt_trans = Math.sqrt(by * by + bz * bz);
  const theta = bt_trans > 0 ? Math.atan2(Math.abs(by), bz) : 0.0;
  const clock_deg = (theta * 180.0 / Math.PI);

  // Akasofu Poynting Flux (GW)
  const v_ms = vsw * 1000.0;
  const b_tesla = bt * 1e-9;
  const mu_0 = 1.25663706e-6;
  const l0 = 7.0 * 6371000.0;
  const sin4 = Math.pow(Math.sin(theta / 2.0), 4);
  const akasofu_gw = ((4.0 * Math.PI / mu_0) * v_ms * b_tesla * b_tesla * sin4 * l0 * l0) / 1e9;

  // Newell universal coupling (Wb/s)
  const dphi = Math.pow(vsw, 4.0 / 3.0) * Math.pow(Math.max(0.01, bt_trans), 2.0 / 3.0) * Math.pow(Math.sin(theta / 2.0), 8.0 / 3.0);

  // Boyle (1997) Polar Cap Potential Drop (kV)
  // Boyle et al. (1997) use the IMF magnitude |B|, not the transverse component.
  let phi_pc = (1e-4 * Math.pow(vsw, 2)) + (11.7 * bt * Math.pow(Math.sin(theta / 2.0), 3));
  phi_pc = Math.max(15.0, Math.min(280.0, phi_pc));

  // AE proxy (nT): rough HELIOS-L1 scaling of the Newell coupling, not a published fit
  const ae = Math.max(20.0, Math.min(2500.0, 0.048 * Math.pow(dphi, 0.85) + 25.0));

  // Convective electric field Ey (mV/m)
  const ey = -vsw * bz * 1e-3;

  return {
    vsw, n, bt, bz, by, temp,
    pdyn,
    va, cs, vms,
    ma, mms, mms_omni,
    beta,
    mp_r0, mp_alpha,
    bs_r0, bs_alpha,
    shue97_r0, fr_bs_r0,
    sheath_re,
    clock_deg,
    akasofu_gw,
    dphi,
    phi_pc,
    ae,
    ey,
    inside_geo: mp_r0 < 6.6,
    inside_geo_shue97: shue97_r0 < 6.6
  };
}

function renderSandboxTab(container) {
  const p = sandboxParams;
  const res = computeSandboxPhysics(p);

  container.innerHTML = `
    <div class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
        <div>
          <h3 class="font-tech font-bold text-slate-100 text-sm flex items-center space-x-2">
            <i class="fa-solid fa-calculator text-sky-400"></i>
            <span>Interactive Space Weather Physics Calculator &amp; Equation Solver</span>
          </h3>
          <p class="text-[11px] text-slate-400 mt-0.5">Real-time simulation of solar wind-magnetosphere coupling, wave speeds, Mach numbers, and boundary standoffs.</p>
        </div>
        <div class="flex items-center space-x-2">
          <button onclick="loadSandboxFromLive()" class="px-2.5 py-1 rounded-lg bg-sky-950/70 hover:bg-sky-900 text-sky-300 border border-sky-800/50 text-[11px] font-semibold transition flex items-center space-x-1">
            <i class="fa-solid fa-arrows-rotate text-[10px]"></i>
            <span>Sync Live L1</span>
          </button>
          <button onclick="injectSandboxToOrbit()" class="px-2.5 py-1 rounded-lg bg-amber-950/70 hover:bg-amber-900 text-amber-300 border border-amber-800/50 text-[11px] font-semibold transition flex items-center space-x-1">
            <i class="fa-solid fa-satellite text-[10px]"></i>
            <span>Send to Orbit Sim</span>
          </button>
        </div>
      </div>

      <!-- Scenarios Presets -->
      <div class="flex flex-wrap items-center gap-2 text-xs bg-space-950/80 p-2.5 rounded-xl border border-slate-800">
        <span class="text-[10px] uppercase font-bold text-slate-400 font-mono">Scenario Benchmarks:</span>
        <button onclick="setSandboxPreset('quiet')" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[11px] transition">Quiet Background</button>
        <button onclick="setSandboxPreset('cir')" class="px-2 py-0.5 rounded bg-amber-950/70 hover:bg-amber-900 text-amber-300 border border-amber-800/40 text-[11px] transition">Corotating Interaction Region (CIR)</button>
        <button onclick="setSandboxPreset('cme_g5')" class="px-2 py-0.5 rounded bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/40 text-[11px] transition font-bold">Extreme CME Shock (G5)</button>
        <button onclick="setSandboxPreset('high_mach')" class="px-2 py-0.5 rounded bg-sky-950/70 hover:bg-sky-900 text-sky-300 border border-sky-800/40 text-[11px] transition">High-Mach Flow</button>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <!-- Controls Column (5 cols) -->
        <div class="lg:col-span-5 bg-space-950/90 p-4 rounded-xl border border-slate-800 space-y-4">
          <div class="text-xs font-bold text-slate-200 uppercase tracking-wider flex items-center space-x-1.5 border-b border-slate-800 pb-2">
            <i class="fa-solid fa-sliders text-sky-400"></i>
            <span>Upstream Solar Wind Parameters</span>
          </div>

          <!-- Speed -->
          <div class="space-y-1">
            <div class="flex justify-between text-xs">
              <label class="text-slate-300 font-medium">Bulk Speed (V_sw):</label>
              <span id="sbx-val-vsw" class="font-mono text-amber-400 font-bold">${p.vsw} km/s</span>
            </div>
            <input type="range" min="200" max="1500" step="10" value="${p.vsw}" oninput="onSandboxParamChange('vsw', this.value)" class="w-full accent-amber-500 cursor-pointer">
          </div>

          <!-- Density -->
          <div class="space-y-1">
            <div class="flex justify-between text-xs">
              <label class="text-slate-300 font-medium">Proton Density (N_p):</label>
              <span id="sbx-val-density" class="font-mono text-emerald-400 font-bold">${p.density} cm⁻³</span>
            </div>
            <input type="range" min="0.5" max="80" step="0.5" value="${p.density}" oninput="onSandboxParamChange('density', this.value)" class="w-full accent-emerald-500 cursor-pointer">
          </div>

          <!-- Total B -->
          <div class="space-y-1">
            <div class="flex justify-between text-xs">
              <label class="text-slate-300 font-medium">Total IMF Magnitude (|B|):</label>
              <span id="sbx-val-bt" class="font-mono text-slate-200 font-bold">${p.bt} nT</span>
            </div>
            <input type="range" min="1.0" max="60" step="0.5" value="${p.bt}" oninput="onSandboxParamChange('bt', this.value)" class="w-full accent-slate-300 cursor-pointer">
          </div>

          <!-- Bz -->
          <div class="space-y-1">
            <div class="flex justify-between text-xs">
              <label class="text-slate-300 font-medium">IMF Bz (GSM):</label>
              <span id="sbx-val-bz" class="font-mono font-bold ${p.bz < 0 ? 'text-rose-400' : 'text-emerald-400'}">${p.bz > 0 ? '+' : ''}${p.bz} nT</span>
            </div>
            <input type="range" min="-45" max="45" step="0.5" value="${p.bz}" oninput="onSandboxParamChange('bz', this.value)" class="w-full accent-rose-500 cursor-pointer">
          </div>

          <!-- By -->
          <div class="space-y-1">
            <div class="flex justify-between text-xs">
              <label class="text-slate-300 font-medium">IMF By (GSM):</label>
              <span id="sbx-val-by" class="font-mono text-sky-400 font-bold">${p.by > 0 ? '+' : ''}${p.by} nT</span>
            </div>
            <input type="range" min="-35" max="35" step="0.5" value="${p.by}" oninput="onSandboxParamChange('by', this.value)" class="w-full accent-sky-500 cursor-pointer">
          </div>

          <!-- Temp -->
          <div class="space-y-1">
            <div class="flex justify-between text-xs">
              <label class="text-slate-300 font-medium">Proton Temperature (T_p):</label>
              <span id="sbx-val-temp" class="font-mono text-purple-400 font-bold">${(p.temp / 1000).toFixed(0)}k K</span>
            </div>
            <input type="range" min="20000" max="1000000" step="10000" value="${p.temp}" oninput="onSandboxParamChange('temp', this.value)" class="w-full accent-purple-500 cursor-pointer">
          </div>
        </div>

        <!-- Real-Time Metrics Display Grid (7 cols) -->
        <div class="lg:col-span-7 space-y-3">
          <!-- Top Standoff Dual Banner -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div class="bg-space-950 p-3.5 rounded-xl border border-sky-500/30 space-y-1">
              <div class="text-[10px] uppercase font-bold text-sky-400 flex items-center justify-between">
                <span>Shue et al. (1998) Magnetopause</span>
                <span id="sbx-chao-mp-geo" class="text-[9px] px-1.5 py-0.2 rounded font-mono ${res.inside_geo ? 'bg-rose-950 text-rose-300' : 'bg-emerald-950 text-emerald-300'}">${res.inside_geo ? 'SUB-GEO' : 'CLEAR'}</span>
              </div>
              <div class="flex items-baseline space-x-2">
                <span id="sbx-chao-mp-re" class="text-xl font-bold font-hud ${res.inside_geo ? 'text-rose-400' : 'text-sky-300'}">${res.mp_r0.toFixed(2)} R_E</span>
                <span id="sbx-chao-mp-km" class="text-xs text-slate-400 font-mono">~${Math.round(res.mp_r0 * 6371).toLocaleString()} km</span>
              </div>
              <div class="text-[11px] text-slate-400 font-mono">Flaring: α = <span id="sbx-chao-alpha">${res.mp_alpha.toFixed(3)}</span></div>
            </div>

            <div class="bg-space-950 p-3.5 rounded-xl border border-sky-500/30 space-y-1">
              <div class="text-[10px] uppercase font-bold text-cyan-400 flex items-center justify-between">
                <span>Chao et al. (2002) Bow Shock</span>
                <span class="text-[9px] text-slate-400 font-mono">M_ms (OMNI): <strong id="sbx-mach-badge" class="text-cyan-300">${res.mms_omni.toFixed(1)}</strong> β: <strong id="sbx-beta-badge" class="text-cyan-300">${res.beta.toFixed(2)}</strong></span>
              </div>
              <div class="flex items-baseline space-x-2">
                <span id="sbx-chao-bs-re" class="text-xl font-bold font-hud text-cyan-300">${res.bs_r0.toFixed(2)} R_E</span>
                <span id="sbx-chao-bs-km" class="text-xs text-slate-400 font-mono">~${Math.round(res.bs_r0 * 6371).toLocaleString()} km</span>
              </div>
              <div class="text-[11px] text-slate-400 font-mono">Sheath: ΔR = <span id="sbx-sheath-re" class="text-emerald-400 font-bold">${res.sheath_re.toFixed(1)} R_E</span></div>
            </div>
          </div>

          <!-- Secondary Metrics Cards (4 items) -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
            <!-- Dynamic Pressure -->
            <div class="bg-space-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
              <div class="text-[10px] font-bold text-slate-400 uppercase font-mono">Solar Wind Dynamic Pressure (P_dyn)</div>
              <div class="flex items-baseline space-x-2">
                <span id="sbx-pdyn" class="text-lg font-bold font-hud text-amber-300">${res.pdyn.toFixed(2)} nPa</span>
              </div>
              <p class="text-[10px] text-slate-500 font-mono">1.6726e-6 * N_p * V_sw²</p>
            </div>

            <!-- Shue comparison -->
            <div class="bg-space-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
              <div class="text-[10px] font-bold text-slate-400 uppercase font-mono">Shue (1997) Model Standoff</div>
              <div class="flex items-baseline space-x-2">
                <span id="sbx-shue-re" class="text-lg font-bold font-hud text-slate-200">${res.shue97_r0.toFixed(2)} R_E</span>
                <span id="sbx-shue-delta" class="text-[11px] text-slate-400 font-mono">Δ: ${(res.mp_r0 - res.shue97_r0).toFixed(2)} R_E</span>
              </div>
              <p class="text-[10px] text-slate-500 font-mono">(11.4 + K·Bz)·P^(-1/6.6), as in OMNI; Δ = Shue 1998 − Shue 1997</p>
            </div>

            <!-- Wave Speeds -->
            <div class="bg-space-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
              <div class="text-[10px] font-bold text-slate-400 uppercase font-mono">MHD Wave Speeds &amp; Mach</div>
              <div class="space-y-0.5 text-[11px] font-mono text-slate-300">
                <div>Alfvén V_A: <strong id="sbx-va" class="text-sky-300">${res.va.toFixed(1)} km/s</strong> (M_A: <span id="sbx-ma">${res.ma.toFixed(2)}</span>)</div>
                <div>Magnetosonic V_ms: <strong id="sbx-vms" class="text-purple-300">${res.vms.toFixed(1)} km/s</strong> (M_ms: <span id="sbx-mms">${res.mms.toFixed(2)}</span>)</div>
              </div>
            </div>

            <!-- Energy Coupling -->
            <div class="bg-space-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
              <div class="text-[10px] font-bold text-slate-400 uppercase font-mono">Akasofu Poynting Flux (ε)</div>
              <div class="flex items-baseline space-x-2">
                <span id="sbx-eps" class="text-lg font-bold font-hud ${res.akasofu_gw >= 100 ? 'text-amber-400' : 'text-slate-300'}">${res.akasofu_gw.toFixed(1)} GW</span>
                <span id="sbx-dphi" class="text-[10px] text-slate-400 font-mono">Newell: ${Math.round(res.dphi).toLocaleString()}</span>
              </div>
              <p class="text-[10px] text-slate-500 font-mono">Clock Angle: <span id="sbx-clock">${res.clock_deg.toFixed(1)}°</span></p>
            </div>

            <!-- Polar Cap Potential -->
            <div class="bg-space-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
              <div class="text-[10px] font-bold text-slate-400 uppercase font-mono">Polar Cap Potential (Φ_PC)</div>
              <div class="flex items-baseline space-x-2">
                <span id="sbx-phi" class="text-lg font-bold font-hud ${res.phi_pc >= 90 ? 'text-rose-400' : 'text-indigo-300'}">${res.phi_pc.toFixed(1)} kV</span>
              </div>
              <p class="text-[10px] text-slate-500 font-mono">Boyle et al. (1997) transpolar drop</p>
            </div>

            <!-- AE & Convective Electric Field -->
            <div class="bg-space-950/80 p-3 rounded-lg border border-slate-800 space-y-1">
              <div class="text-[10px] font-bold text-slate-400 uppercase font-mono">Auroral Electrojet &amp; E_y Field</div>
              <div class="space-y-0.5 text-[11px] font-mono text-slate-300">
                <div title="Rough HELIOS-L1 scaling of the Newell coupling, not a published fit; observed AE is in the OMNI archive data">AE Proxy (rough): <strong id="sbx-ae" class="${res.ae >= 500 ? 'text-amber-400 font-bold' : 'text-slate-200'}">${res.ae.toFixed(0)} nT</strong></div>
                <div>E_y Convective: <strong id="sbx-ey" class="${res.ey > 0 ? 'text-rose-400' : 'text-emerald-400'}">${res.ey > 0 ? '+' : ''}${res.ey.toFixed(2)} mV/m</strong></div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;
}

function onSandboxParamChange(param, val) {
  sandboxParams[param] = parseFloat(val);
  const p = sandboxParams;
  const res = computeSandboxPhysics(p);

  // Update slider label
  const lbl = document.getElementById(`sbx-val-${param}`);
  if (lbl) {
    if (param === 'vsw') lbl.innerText = `${p.vsw} km/s`;
    else if (param === 'density') lbl.innerText = `${p.density} cm⁻³`;
    else if (param === 'bt') lbl.innerText = `${p.bt} nT`;
    else if (param === 'bz') {
      lbl.innerText = `${p.bz > 0 ? '+' : ''}${p.bz} nT`;
      lbl.className = `font-mono font-bold ${p.bz < 0 ? 'text-rose-400' : 'text-emerald-400'}`;
    }
    else if (param === 'by') lbl.innerText = `${p.by > 0 ? '+' : ''}${p.by} nT`;
    else if (param === 'temp') lbl.innerText = `${(p.temp / 1000).toFixed(0)}k K`;
  }

  // Update output elements
  const elChaoMpRe = document.getElementById('sbx-chao-mp-re');
  if (elChaoMpRe) {
    elChaoMpRe.innerText = `${res.mp_r0.toFixed(2)} R_E`;
    elChaoMpRe.className = `text-xl font-bold font-hud ${res.inside_geo ? 'text-rose-400 animate-pulse' : 'text-sky-300'}`;
  }
  const elChaoMpKm = document.getElementById('sbx-chao-mp-km');
  if (elChaoMpKm) elChaoMpKm.innerText = `~${Math.round(res.mp_r0 * 6371).toLocaleString()} km`;

  const elChaoGeo = document.getElementById('sbx-chao-mp-geo');
  if (elChaoGeo) {
    elChaoGeo.innerText = res.inside_geo ? 'SUB-GEO' : 'CLEAR';
    elChaoGeo.className = `text-[9px] px-1.5 py-0.2 rounded font-mono ${res.inside_geo ? 'bg-rose-950 text-rose-300' : 'bg-emerald-950 text-emerald-300'}`;
  }

  const elChaoAlpha = document.getElementById('sbx-chao-alpha');
  if (elChaoAlpha) elChaoAlpha.innerText = res.mp_alpha.toFixed(3);

  const elChaoBsRe = document.getElementById('sbx-chao-bs-re');
  if (elChaoBsRe) elChaoBsRe.innerText = `${res.bs_r0.toFixed(2)} R_E`;

  const elChaoBsKm = document.getElementById('sbx-chao-bs-km');
  if (elChaoBsKm) elChaoBsKm.innerText = `~${Math.round(res.bs_r0 * 6371).toLocaleString()} km`;

  const elSheath = document.getElementById('sbx-sheath-re');
  if (elSheath) elSheath.innerText = `${res.sheath_re.toFixed(1)} R_E`;

  const elMach = document.getElementById('sbx-mach-badge');
  if (elMach) elMach.innerText = res.mms_omni.toFixed(1);
  const elBeta = document.getElementById('sbx-beta-badge');
  if (elBeta) elBeta.innerText = res.beta.toFixed(2);

  const elPdyn = document.getElementById('sbx-pdyn');
  if (elPdyn) elPdyn.innerText = `${res.pdyn.toFixed(2)} nPa`;

  const elShueRe = document.getElementById('sbx-shue-re');
  if (elShueRe) elShueRe.innerText = `${res.shue97_r0.toFixed(2)} R_E`;

  const elShueDelta = document.getElementById('sbx-shue-delta');
  if (elShueDelta) elShueDelta.innerText = `Δ: ${(res.mp_r0 - res.shue97_r0).toFixed(2)} R_E`;

  const elVa = document.getElementById('sbx-va');
  if (elVa) elVa.innerText = `${res.va.toFixed(1)} km/s`;

  const elMa = document.getElementById('sbx-ma');
  if (elMa) elMa.innerText = res.ma.toFixed(2);

  const elVms = document.getElementById('sbx-vms');
  if (elVms) elVms.innerText = `${res.vms.toFixed(1)} km/s`;

  const elMms = document.getElementById('sbx-mms');
  if (elMms) elMms.innerText = res.mms.toFixed(2);

  const elEps = document.getElementById('sbx-eps');
  if (elEps) {
    elEps.innerText = `${res.akasofu_gw.toFixed(1)} GW`;
    elEps.className = `text-lg font-bold font-hud ${res.akasofu_gw >= 100 ? 'text-amber-400' : 'text-slate-300'}`;
  }

  const elDphi = document.getElementById('sbx-dphi');
  if (elDphi) elDphi.innerText = `Newell: ${Math.round(res.dphi).toLocaleString()}`;

  const elClock = document.getElementById('sbx-clock');
  if (elClock) elClock.innerText = `${res.clock_deg.toFixed(1)}°`;

  const elPhi = document.getElementById('sbx-phi');
  if (elPhi) {
    elPhi.innerText = `${res.phi_pc.toFixed(1)} kV`;
    elPhi.className = `text-lg font-bold font-hud ${res.phi_pc >= 90 ? 'text-rose-400' : 'text-indigo-300'}`;
  }

  const elAe = document.getElementById('sbx-ae');
  if (elAe) {
    elAe.innerText = `${res.ae.toFixed(0)} nT`;
    elAe.className = res.ae >= 500 ? 'text-amber-400 font-bold' : 'text-slate-200';
  }

  const elEy = document.getElementById('sbx-ey');
  if (elEy) {
    elEy.innerText = `${res.ey > 0 ? '+' : ''}${res.ey.toFixed(2)} mV/m`;
    elEy.className = res.ey > 0 ? 'text-rose-400 font-bold' : 'text-emerald-400';
  }
}

function setSandboxPreset(presetKey) {
  if (presetKey === 'quiet') {
    sandboxParams = { vsw: 380, density: 4.5, bt: 5.0, bz: 2.5, by: 1.0, temp: 80000 };
  } else if (presetKey === 'cir') {
    sandboxParams = { vsw: 580, density: 15.0, bt: 12.0, bz: -6.5, by: -4.0, temp: 180000 };
  } else if (presetKey === 'cme_g5') {
    sandboxParams = { vsw: 980, density: 45.0, bt: 42.0, bz: -28.0, by: 16.0, temp: 450000 };
  } else if (presetKey === 'high_mach') {
    sandboxParams = { vsw: 750, density: 2.0, bt: 3.0, bz: -2.0, by: 1.0, temp: 40000 };
  }
  const body = document.getElementById('modal-references-body');
  if (body) renderSandboxTab(body);
  window.playBlip?.();
}

function loadSandboxFromLive() {
  if (!currentTelemetryData || !currentTelemetryData.latest) {
    alert("No active live telemetry available to sync.");
    return;
  }
  const lat = currentTelemetryData.latest;
  // Missing (null) live values keep the sandbox's current value and are named, instead of
  // being replaced by nominal numbers that then look like the live state.
  const fields = { vsw: 'speed', density: 'density', bt: 'bt', bz: 'bz_gsm', by: 'by_gsm', temp: 'temperature' };
  const missing = [];
  const next = { ...sandboxParams };
  for (const [key, src] of Object.entries(fields)) {
    const v = lat[src];
    if (v === null || v === undefined || !Number.isFinite(Number(v))) missing.push(src);
    else next[key] = Number(v);
  }
  sandboxParams = next;
  if (missing.length) alert(`Live record has no ${missing.join(', ')}; kept the sandbox value${missing.length > 1 ? 's' : ''} for ${missing.length > 1 ? 'them' : 'it'}.`);
  const body = document.getElementById('modal-references-body');
  if (body) renderSandboxTab(body);
  window.playBlip?.();
}

function injectSandboxToOrbit() {
  if (orbitViewer) {
    const res = computeSandboxPhysics(sandboxParams);
    orbitViewer.setSolarWindConditions(res.vsw, res.pdyn, res.bz, res.mms_omni, res.beta);
    orbitViewer.draw();
    if (orbitViewer.lastComputedBoundaries) {
      updateBoundaryCards(orbitViewer.lastComputedBoundaries);
    }
  }
  closeReferencesModal();
  switchTab('orbits');
  window.playBlip?.();
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
    const observedCycle = sc.data_kind === 'observed';
    const ssnEl = document.getElementById('sc25-ssn');
    if (ssnEl) ssnEl.innerText = sc.smoothed_sunspot_number ?? '---';
    const ssnNote = document.getElementById('sc25-ssn-note');
    if (ssnNote) ssnNote.innerText = observedCycle
      ? `13-month smoothed, ${sc.smoothed_month}; monthly ${sc.monthly_sunspot_number} (${sc.month})`
      : 'MODEL (NOAA data unavailable)';

    const f107El = document.getElementById('sc25-f107');
    if (f107El) f107El.innerText = sc.f107_radio_flux_sfu ?? '---';
    const f107Note = document.getElementById('sc25-f107-note');
    if (f107Note) f107Note.innerText = observedCycle
      ? `Smoothed, ${sc.smoothed_month}; monthly ${sc.monthly_f107_sfu} (${sc.month})`
      : 'MODEL: 63.7 + 0.728 SSN + 0.00089 SSN²';

    const progEl = document.getElementById('sc25-progress');
    if (progEl) progEl.innerText = `${sc.cycle_progress_percent}%`;

    const progBar = document.getElementById('sc25-progress-bar');
    if (progBar) progBar.style.width = `${sc.cycle_progress_percent}%`;

    const revEl = document.getElementById('sc25-reversal');
    if (revEl) revEl.innerText = observedCycle && sc.peak_month ? `SSN ${sc.peak_sunspot_number} in ${sc.peak_month}` : `Model peak ${sc.peak_sunspot_number}`;
    const srcEl = document.getElementById('sc25-source');
    if (srcEl) srcEl.innerText = sc.source || '';

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
  // Fraction of power lost for A dB of absorption: 1 - 10^(-A/10) (was a fixed "79.1%" text)
  const lossEl = document.getElementById('drap-att10-loss');
  if (lossEl) lossEl.innerText = `${(100 * (1 - Math.pow(10, -drap.attenuation_at_10mhz_db / 10))).toFixed(1)}% signal power lost`;

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
  const ssnVals = timeline.map(t => t.ssn_smoothed ?? null);
  const c24Vals = timeline.map(t => t.cycle_24_comparison_ssn ?? null);
  const monthlyVals = timeline.map(t => t.ssn_monthly ?? null);
  const predVals = timeline.map(t => t.ssn_predicted ?? null);
  const observed = timeline.some(t => t.ssn_monthly !== undefined);

  chartSolarCycle = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: observed ? 'Cycle 25, 13-month smoothed SSN (observed)' : 'Cycle 25 SSN (MODEL, NOAA data unavailable)',
          data: ssnVals,
          borderColor: '#f59e0b',
          backgroundColor: 'rgba(245, 158, 11, 0.15)',
          fill: true,
          borderWidth: 2,
          pointRadius: 0,
          tension: 0.3
        },
        {
          label: observed ? 'Cycle 24, smoothed SSN (months since its Dec 2008 minimum)' : 'Cycle 24 (MODEL: 0.68 x cycle 25)',
          data: c24Vals,
          borderColor: '#64748b',
          borderDash: [4, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3
        },
        ...(observed ? [{
          label: 'Monthly mean SSN',
          data: monthlyVals,
          borderColor: 'rgba(251, 191, 36, 0.45)',
          borderWidth: 1,
          pointRadius: 0,
          tension: 0
        }, {
          label: 'NOAA SWPC predicted SSN',
          data: predVals,
          borderColor: '#a78bfa',
          borderDash: [6, 3],
          borderWidth: 1.5,
          pointRadius: 0,
          tension: 0.3
        }] : [])
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
  closeIncidentLogModal();
  closeSettingsModal();
  closeAboutModal();
  closeTimezoneModal();
  const paramModal = document.getElementById('modal-parameter');
  if (paramModal) paramModal.classList.add('hidden');
}

/* ========================================================================= */
/* MISSION INCIDENT & ALERT LOGGING ENGINE                                  */
/* ========================================================================= */

let missionIncidentLogger = null;

class MissionIncidentLogger {
  constructor() {
    this.storageKey = 'helios_mission_incidents_v1';
    this.incidents = this.loadFromStorage();
    this.lastTriggerTimes = {};
    this.activeFilter = 'ALL';
    this.updateBadge();
  }

  loadFromStorage() {
    try {
      const raw = localStorage.getItem(this.storageKey);
      return raw ? JSON.parse(raw) : [];
    } catch (e) {
      return [];
    }
  }

  saveToStorage() {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this.incidents.slice(0, 100)));
    } catch (e) {
      console.warn('Incident log storage error:', e);
    }
  }

  addIncident(level, category, title, detail, paramName, paramValue, threshold) {
    const key = `${category}_${level}`;
    const now = Date.now();
    // Throttle repeated triggers of same condition to once every 12 minutes
    if (this.lastTriggerTimes[key] && (now - this.lastTriggerTimes[key]) < 720000) {
      return;
    }
    this.lastTriggerTimes[key] = now;

    const incident = {
      id: `inc_${now}_${Math.random().toString(36).substr(2, 5)}`,
      timestamp: new Date().toISOString(),
      level, // 'CRITICAL', 'WARNING', 'ADVISORY'
      category,
      title,
      detail,
      paramName,
      paramValue,
      threshold,
      acknowledged: false
    };

    this.incidents.unshift(incident);
    if (this.incidents.length > 100) this.incidents.pop();
    this.saveToStorage();
    this.updateBadge();
    this.renderLogBody();

    if (level === 'CRITICAL') {
      window.playSubGeoWarning?.();
    } else if (level === 'WARNING') {
      window.playShockAlert?.();
    }
  }

  checkTelemetry(latest, mission) {
    if (!latest) return;
    const vsw = latest.speed || 0;
    const bz = latest.bz_gsm !== undefined ? latest.bz_gsm : 0;
    const pdyn = latest.dynamic_pressure || 0;
    const rmp = latest.magnetopause_re || 10.0;

    // 1. Critical: Sub-GEO Magnetopause Crossing
    if (rmp < 6.6) {
      this.addIncident(
        'CRITICAL',
        'SUB_GEO_CROSSING',
        'Subsolar Magnetopause Compressed Inside GEO Orbit',
        `Standoff compressed to ${rmp.toFixed(1)} R_E (< 6.6 R_E GEO). Geostationary spacecraft directly exposed to unshielded solar wind / magnetosheath plasma.`,
        'R_mp',
        `${rmp.toFixed(1)} R_E`,
        '< 6.6 R_E'
      );
    }

    // 2. Critical: Severe Southward IMF Reconnection
    if (bz <= -15.0) {
      this.addIncident(
        'CRITICAL',
        'SEVERE_IMF_SOUTH',
        'Extreme Southward IMF Reconnection Driver',
        `Interplanetary magnetic field Bz southward at ${bz.toFixed(1)} nT. Major dayside reconnection driving ring current intensification (G4/G5 risk).`,
        'Bz (GSM)',
        `${bz.toFixed(1)} nT`,
        '<= -15.0 nT'
      );
    } else if (bz <= -8.0) {
      this.addIncident(
        'WARNING',
        'MODERATE_IMF_SOUTH',
        'Elevated Southward IMF Injection',
        `IMF Bz southward at ${bz.toFixed(1)} nT. Active dayside reconnection driving polar cap convection and magnetospheric substorms.`,
        'Bz (GSM)',
        `${bz.toFixed(1)} nT`,
        '<= -8.0 nT'
      );
    }

    // 3. Warning: Severe Dynamic Pressure Compression
    if (pdyn >= 12.0) {
      this.addIncident(
        'WARNING',
        'HIGH_DYNAMIC_PRESSURE',
        'Severe Solar Wind Momentum Flux Surge',
        `Solar wind dynamic pressure spiked to ${pdyn.toFixed(1)} nPa. Intense compression of Earth's dayside magnetopause cavity.`,
        'P_dyn',
        `${pdyn.toFixed(1)} nPa`,
        '>= 12.0 nPa'
      );
    }

    // 4. Warning: High-Speed Solar Wind Stream
    if (vsw >= 650.0) {
      this.addIncident(
        'WARNING',
        'HIGH_SPEED_STREAM',
        'High-Speed Solar Wind Stream (HSS / CME Front)',
        `Solar wind bulk speed reached ${vsw.toFixed(0)} km/s. Enhanced relativistic electron precipitation in outer Van Allen radiation belt.`,
        'V_sw',
        `${vsw.toFixed(0)} km/s`,
        '>= 650 km/s'
      );
    }
  }

  acknowledgeAll() {
    this.incidents.forEach(inc => inc.acknowledged = true);
    this.saveToStorage();
    this.updateBadge();
    this.renderLogBody();
  }

  acknowledge(id) {
    const inc = this.incidents.find(i => i.id === id);
    if (inc) {
      inc.acknowledged = true;
      this.saveToStorage();
      this.updateBadge();
      this.renderLogBody();
    }
  }

  clear() {
    this.incidents = [];
    this.saveToStorage();
    this.updateBadge();
    this.renderLogBody();
  }

  updateBadge() {
    const unack = this.incidents.filter(i => !i.acknowledged).length;
    const badge = document.getElementById('incident-badge-count');
    if (badge) {
      if (unack > 0) {
        badge.innerText = unack > 99 ? '99+' : unack;
        badge.classList.remove('hidden');
      } else {
        badge.classList.add('hidden');
      }
    }

    const cCrit = this.incidents.filter(i => i.level === 'CRITICAL').length;
    const cWarn = this.incidents.filter(i => i.level === 'WARNING').length;
    const cAdv = this.incidents.filter(i => i.level === 'ADVISORY').length;

    const elCrit = document.getElementById('cnt-flt-crit');
    const elWarn = document.getElementById('cnt-flt-warn');
    const elAdv = document.getElementById('cnt-flt-adv');
    if (elCrit) elCrit.innerText = cCrit;
    if (elWarn) elWarn.innerText = cWarn;
    if (elAdv) elAdv.innerText = cAdv;

    const stat = document.getElementById('incident-summary-status');
    if (stat) {
      stat.innerText = `${this.incidents.length} events logged (${unack} unacknowledged)`;
    }
  }

  renderLogBody() {
    const body = document.getElementById('incident-log-body');
    if (!body) return;

    let filtered = this.incidents;
    if (this.activeFilter !== 'ALL') {
      filtered = this.incidents.filter(i => i.level === this.activeFilter);
    }

    if (filtered.length === 0) {
      body.innerHTML = `<div class="text-center py-12 text-slate-500 italic">No ${this.activeFilter === 'ALL' ? '' : this.activeFilter.toLowerCase() + ' '}operational incidents recorded.</div>`;
      return;
    }

    body.innerHTML = filtered.map(inc => {
      const isCrit = inc.level === 'CRITICAL';
      const isWarn = inc.level === 'WARNING';
      const borderClr = isCrit ? 'border-rose-500/50' : (isWarn ? 'border-amber-500/40' : 'border-sky-500/30');
      const badgeBg = isCrit ? 'bg-rose-950/80 text-rose-300 border-rose-800/60' : (isWarn ? 'bg-amber-950/80 text-amber-300 border-amber-800/60' : 'bg-sky-950/80 text-sky-300 border-sky-800/60');
      const icon = isCrit ? 'fa-triangle-exclamation text-rose-400' : (isWarn ? 'fa-circle-exclamation text-amber-400' : 'fa-info-circle text-sky-400');
      const timeStr = new Date(inc.timestamp).toLocaleString();

      return `
        <div class="bg-space-950/80 p-3.5 rounded-xl border ${borderClr} shadow-md space-y-2 ${inc.acknowledged ? 'opacity-70' : ''}">
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
            <div class="flex items-center space-x-2">
              <i class="fa-solid ${icon} text-sm"></i>
              <span class="text-[10px] font-bold px-2 py-0.5 rounded border uppercase ${badgeBg}">${inc.level}</span>
              <span class="text-xs font-bold text-slate-200">${inc.title}</span>
            </div>
            <div class="flex items-center space-x-2">
              <span class="text-[11px] text-slate-400 font-mono">${timeStr}</span>
              ${!inc.acknowledged ? `
                <button onclick="acknowledgeIncident('${inc.id}')" class="px-2 py-0.5 rounded bg-space-800 hover:bg-emerald-900/60 text-emerald-400 border border-slate-700 hover:border-emerald-700/50 text-[10px] font-semibold transition">
                  <i class="fa-solid fa-check text-[9px] mr-1"></i>Acknowledge
                </button>
              ` : '<span class="text-[10px] text-slate-500 font-mono"><i class="fa-solid fa-check-double mr-1 text-emerald-500"></i>Acked</span>'}
            </div>
          </div>
          <p class="text-xs text-slate-300 leading-relaxed font-sans">${inc.detail}</p>
          <div class="flex flex-wrap items-center justify-between text-[11px] font-mono text-slate-400 pt-1">
            <div>
              <span class="text-slate-500 font-semibold">Trigger Parameter:</span>
              <strong class="text-slate-200 ml-1">${inc.paramName} = ${inc.paramValue}</strong>
              <span class="text-slate-500 ml-2">(Threshold: ${inc.threshold})</span>
            </div>
            <span class="text-slate-600 text-[10px]">ID: ${inc.id}</span>
          </div>
        </div>
      `;
    }).join('');
  }
}

function openIncidentLogModal() {
  const m = document.getElementById('modal-incidents');
  if (m) {
    m.classList.remove('hidden');
    if (missionIncidentLogger) {
      missionIncidentLogger.updateBadge();
      missionIncidentLogger.renderLogBody();
    }
  }
}

function closeIncidentLogModal() {
  const m = document.getElementById('modal-incidents');
  if (m) m.classList.add('hidden');
}

function filterIncidentLog(lvl) {
  if (missionIncidentLogger) {
    missionIncidentLogger.activeFilter = lvl;
    ['ALL', 'CRITICAL', 'WARNING', 'ADVISORY'].forEach(l => {
      const btn = document.getElementById(`incident-flt-${l}`);
      if (btn) {
        if (l === lvl) {
          btn.className = 'px-2.5 py-1 rounded-lg font-semibold bg-sky-600 text-white text-[11px] transition';
        } else {
          btn.className = 'px-2.5 py-1 rounded-lg font-semibold text-slate-400 hover:text-slate-200 text-[11px] transition';
        }
      }
    });
    missionIncidentLogger.renderLogBody();
  }
}

function acknowledgeAllIncidents() {
  if (missionIncidentLogger) missionIncidentLogger.acknowledgeAll();
}

function acknowledgeIncident(id) {
  if (missionIncidentLogger) missionIncidentLogger.acknowledge(id);
}

function clearIncidentLog() {
  if (confirm('Clear all recorded incident logs?')) {
    if (missionIncidentLogger) missionIncidentLogger.clear();
  }
}

function exportIncidentLogJSON() {
  if (!missionIncidentLogger) return;
  const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(missionIncidentLogger.incidents, null, 2));
  const a = document.createElement('a');
  a.setAttribute("href", dataStr);
  a.setAttribute("download", `helios_incident_log_${new Date().toISOString().slice(0, 10)}.json`);
  document.body.appendChild(a);
  a.click();
  a.remove();
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
  } else if (e.key === 'u' || e.key === 'U') {
    openUserGuideModal();
  } else if (e.key === 'l' || e.key === 'L') {
    openIncidentLogModal();
  } else if (e.key === 't' || e.key === 'T') {
    openTimezoneModal();
  } else if (e.key === 's' || e.key === 'S') {
    openSettingsModal();
  } else if (e.key === 'o' || e.key === 'O') {
    openAboutModal();
  }
});
