/**
 * Event replay: spacecraft positions in the Earth-fixed HEE frame (Sun at the centre, Earth to the
 * right) moving with a time slider, and each spacecraft's solar wind speed and |B| with a time cursor.
 * Data: /api/replay (CDAWeb archive and Event Analysis sources; SPICE positions).
 */
const REPLAY_COLORS = { 'WIND': '#7fa5cf', 'ACE': '#d7b46a', 'DSCOVR': '#9fc98f', 'SOHO': '#c9a0dc',
  'STEREO-A': '#d77e7e', 'Solar Orbiter': '#6cc5c0', 'Parker Solar Probe': '#e39b62' };
const REPLAY_PRESETS = { jan2026: ['2026-01-18T00:00', '2026-01-21T00:00'] };
let replayData = null, replayIndex = 0, replayTimer = null, replayCharts = [];

function replayHasData(c) {
  return c.speed_kms.some(v => v !== null) || c.bt_nt.some(v => v !== null);
}

// Position of a craft at grid time t (ms), linear between the ephemeris epochs; null without one.
function replayPosition(name, t) {
  const p = replayData.positions, ts = p.times.map(x => Date.parse(x)), xs = p.craft[name];
  let k = ts.findIndex(x => x > t);
  if (k < 0) k = ts.length - 1;
  if (k === 0) k = 1;
  const a = xs[k - 1], b = xs[k];
  if (!a || !b) return a || b;
  const f = Math.max(0, Math.min(1, (t - ts[k - 1]) / (ts[k] - ts[k - 1])));
  return a.map((v, i) => v + f * (b[i] - v));
}

const replayCursor = {
  id: 'replayCursor',
  afterDatasetsDraw(chart) {
    if (!replayData) return;
    const x = chart.scales.x.getPixelForValue(replayIndex), { top, bottom } = chart.chartArea;
    const ctx = chart.ctx;
    ctx.save(); ctx.strokeStyle = '#e4e6e9'; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
    ctx.beginPath(); ctx.moveTo(x, top); ctx.lineTo(x, bottom); ctx.stroke(); ctx.restore();
  }
};

function drawReplayMap() {
  const canvas = document.getElementById('replay-canvas');
  if (!canvas || !replayData) return;
  const rect = canvas.parentElement.getBoundingClientRect(), dpr = window.devicePixelRatio || 1;
  canvas.width = rect.width * dpr; canvas.height = rect.height * dpr;
  const ctx = canvas.getContext('2d'), w = rect.width, h = rect.height;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.fillStyle = '#16171a'; ctx.fillRect(0, 0, w, h);
  const t = Date.parse(replayData.times[replayIndex]);
  const pos = replayData.craft.map(c => ({ c, p: replayPosition(c.name, t) }));
  const rMax = Math.max(1.05, ...pos.filter(o => o.p).map(o => Math.hypot(o.p[0], o.p[1]) * 1.08));
  const s = Math.min(w, h) / 2 / rMax, cx = w / 2, cy = h / 2;
  // HEE: X (Sun to Earth) to the right, Y (Earth's motion) up.
  const px = p => [cx + p[0] * s, cy - p[1] * s];
  ctx.strokeStyle = 'rgba(154,158,165,0.25)'; ctx.fillStyle = '#83878f'; ctx.font = '10px sans-serif';
  for (let r = 0.25; r <= rMax; r += 0.25) {
    ctx.beginPath(); ctx.arc(cx, cy, r * s, 0, 2 * Math.PI); ctx.stroke();
    ctx.fillText(`${r} AU`, cx + r * s * 0.71 + 2, cy - r * s * 0.71);
  }
  ctx.fillStyle = '#f2c14e'; ctx.beginPath(); ctx.arc(cx, cy, 6, 0, 2 * Math.PI); ctx.fill();
  const earthAu = replayData.positions.earth_au[0];
  const [ex, ey] = px([earthAu, 0]);
  ctx.fillStyle = '#5b9bd5'; ctx.beginPath(); ctx.arc(ex, ey, 5, 0, 2 * Math.PI); ctx.fill();
  ctx.fillStyle = '#e4e6e9'; ctx.fillText('Earth', ex + 8, ey + 14);  // the L1 craft are listed below it
  const l1 = [];
  for (const { c, p } of pos) {
    const has = replayHasData(c), v = c.speed_kms[replayIndex], b = c.bt_nt[replayIndex];
    const val = !has ? 'no data' : [v !== null ? `${Math.round(v)} km/s` : null, b !== null ? `${b.toFixed(1)} nT` : null].filter(Boolean).join(', ') || 'gap';
    if (!p) continue;
    const [x, y] = px(p), near = Math.hypot(x - ex, y - ey) < 12;
    if (near) { l1.push([c.name, val, has]); continue; }
    ctx.fillStyle = has ? REPLAY_COLORS[c.name] : '#5f636b';
    ctx.beginPath(); ctx.arc(x, y, 4, 0, 2 * Math.PI); ctx.fill();
    const text = `${c.name}: ${val}`, tw = ctx.measureText(text).width;
    ctx.fillStyle = has ? '#e4e6e9' : '#83878f';
    ctx.fillText(text, x + 7 + tw > w - 4 ? x - 7 - tw : x + 7, y - 6);
  }
  // Craft near L1 are within a few pixels of Earth at this scale: list them beside it.
  l1.forEach(([n, val, has], i) => {
    ctx.fillStyle = has ? REPLAY_COLORS[n] : '#83878f';
    ctx.fillText(`${n} (L1): ${val}`, Math.min(ex - 60, w - 190), ey + 30 + 13 * i);
  });
  ctx.fillStyle = '#b9bcc1';
  ctx.fillText(`${replayData.times[replayIndex].replace('T', ' ').slice(0, 16)} UTC`, 10, 16);
  ctx.fillText('HEE: Sun at the centre, Earth to the right, Earth\'s motion up', 10, h - 8);
}

function setReplayIndex(i) {
  if (!replayData) return;
  replayIndex = Math.max(0, Math.min(replayData.times.length - 1, i));
  const slider = document.getElementById('replay-slider');
  if (slider) slider.value = replayIndex;
  drawReplayMap();
  replayCharts.forEach(ch => ch.draw());
}

function toggleReplayPlay() {
  const btn = document.getElementById('replay-play');
  if (replayTimer) { clearInterval(replayTimer); replayTimer = null; if (btn) btn.innerText = 'Play'; return; }
  if (!replayData) return;
  if (replayIndex >= replayData.times.length - 1) setReplayIndex(0);
  if (btn) btn.innerText = 'Pause';
  replayTimer = setInterval(() => {
    if (replayIndex >= replayData.times.length - 1) return toggleReplayPlay();
    setReplayIndex(replayIndex + 1);
  }, 80);
}

function replayChart(id, key, title) {
  const ctx = document.getElementById(id)?.getContext('2d');
  if (!ctx) return null;
  const labels = replayData.times.map(t => formatTimestampToTimezone(t));
  const datasets = replayData.craft.filter(replayHasData).filter(c => c[key].some(v => v !== null)).map(c => ({
    label: c.name, data: c[key], borderColor: REPLAY_COLORS[c.name], backgroundColor: REPLAY_COLORS[c.name],
    borderWidth: 1.4, pointRadius: 0, spanGaps: false }));
  return new Chart(ctx, { type: 'line', data: { labels, datasets }, plugins: [replayCursor],
    options: withAxisTitles(`Time (${selectedTimezone})`, title) });
}

async function loadReplay(preset) {
  if (preset) {
    document.getElementById('replay-start').value = REPLAY_PRESETS[preset][0];
    document.getElementById('replay-end').value = REPLAY_PRESETS[preset][1];
  }
  const start = document.getElementById('replay-start').value, end = document.getElementById('replay-end').value;
  const note = document.getElementById('replay-note');
  if (!start || !end) { note.innerText = 'Choose a start and an end (UTC).'; return; }
  if (replayTimer) toggleReplayPlay();
  note.innerText = 'Loading the spacecraft data and positions (the first time for an interval can take a minute: Solar Orbiter sends plasma moments every 4 s)...';
  const res = await fetch(`/api/replay?start=${encodeURIComponent(start + 'Z')}&end=${encodeURIComponent(end + 'Z')}`);
  const data = await res.json();
  if (!res.ok) { note.innerText = apiErrorText(data, res); return; }
  replayData = data;
  replayCharts.forEach(ch => ch.destroy());
  replayCharts = [replayChart('chart-replay-speed', 'speed_kms', 'Solar wind speed [km/s]'),
                  replayChart('chart-replay-bt', 'bt_nt', '|B| [nT]')].filter(Boolean);
  const slider = document.getElementById('replay-slider');
  slider.max = data.times.length - 1;
  const jumps = data.craft.filter(c => c.first_speed_jump).map(c => `${c.name} ${c.first_speed_jump.slice(5, 16).replace('T', ' ')}`);
  const none = data.craft.filter(c => !replayHasData(c)).map(c => c.name);
  note.innerText = `${data.step_minutes}-min means. First lasting speed rise of 100 km/s or more (start of the ${data.step_minutes}-min step, UTC): ` +
    (jumps.length ? jumps.join('; ') : 'none') + '.' + (none.length ? ` No data in the interval: ${none.join(', ')}.` : '') +
    ' Positions: ' + data.frame + '.';
  setReplayIndex(0);
}

// PNG of the two plots on the page background (Chart.js canvases are transparent).
function saveReplayPng() {
  if (!replayCharts.length) return;
  const cs = replayCharts.map(ch => ch.canvas), out = document.createElement('canvas');
  out.width = Math.max(...cs.map(c => c.width)); out.height = cs.reduce((a, c) => a + c.height, 0);
  const ctx = out.getContext('2d');
  ctx.fillStyle = '#16171a'; ctx.fillRect(0, 0, out.width, out.height);
  let y = 0;
  cs.forEach(c => { ctx.drawImage(c, 0, y); y += c.height; });
  const a = document.createElement('a');
  a.href = out.toDataURL('image/png');
  a.download = `helios_replay_${replayData.times[0].slice(0, 10)}.png`;
  a.click();
}

window.addEventListener('resize', () => drawReplayMap());
