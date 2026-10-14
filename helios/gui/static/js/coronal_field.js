/**
 * HELIOS-L1: coronal magnetic field (PFSS) panel of the Parker Spiral tab (/api/pfss).
 */

function describeFieldLine(t) {
  if (!t || !t.traced) return 'not traced (outside the model grid)';
  const pol = t.open ? (t.polarity > 0 ? ', outward polarity' : ', inward polarity') : '';
  const hcs = t.hcs_distance_deg !== undefined ? `; ${t.hcs_distance_deg}° from the current sheet at r_ss` : '';
  return `${t.class}${pol}: footpoint ${t.footpoint_lon}° Carrington, ${t.footpoint_lat}° latitude, ` +
    `B_r ${t.footpoint_br_gauss} G${hcs}`;
}

// The JSOC e-mail address (needed for HMI maps) is remembered in this browser.
function jsocEmail() {
  const el = document.getElementById('pfss-email');
  const v = el ? el.value.trim() : '';
  try { if (v) localStorage.setItem('helios-jsoc-email', v); } catch (e) { /* not kept */ }
  return v || null;
}

document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('pfss-email');
  try { if (el && !el.value) el.value = localStorage.getItem('helios-jsoc-email') || ''; } catch (e) { /* none */ }
});

async function runPfss() {
  const current = latestRequest('runPfss');
  const out = document.getElementById('pfss-result');
  const v = id => document.getElementById(id).value;
  out.innerText = 'Computing (download, PFSS solution, tracing)...';
  const pt = v('pfss-point').split(',').map(x => parseFloat(x));
  const points = pt.length === 3 && pt.every(x => !isNaN(x)) ? [{ r_rsun: pt[0], lon: pt[1], lat: pt[2] }] : [];
  try {
    const res = await fetch('/api/pfss', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: v('pfss-source'), time: v('pfss-time'), speed_kms: parseFloat(v('pfss-speed')),
        rss: parseFloat(v('pfss-rss')), points, jsoc_email: jsocEmail() })
    });
    const data = await res.json();
    if (!current()) return;
    if (!res.ok) throw new Error(apiErrorText(data, res));
    const img = document.getElementById('pfss-plot');
    img.src = data.plot;
    img.classList.remove('hidden');
    document.getElementById('pfss-placeholder').classList.add('hidden');
    const e = data.earth;
    out.innerHTML =
      `<div class="font-semibold text-slate-100">${escapeHtml(data.map_instrument)} map ${escapeHtml(data.map_date)} UTC</div>` +
      `<div>Sub-Earth point: ${e.sub_earth_lon}° Carrington, ${e.sub_earth_lat}°. The wind now at Earth left the source surface ` +
      `${e.longitude_shift_deg}° further west (${e.speed_kms} km/s), at ${e.lon}°, ${e.lat}°: ${e.hcs_distance_deg}° from the current sheet.</div>` +
      `<div class="text-sky-300">Solar source: ${describeFieldLine(data.earth_source)}</div>` +
      data.traced.map(t => `<div>From (${t.seed.r_rsun} R☉, ${t.seed.lon}°, ${t.seed.lat}°): ${describeFieldLine(t)}</div>`).join('') +
      `<div class="text-slate-500">${escapeHtml(data.method)}; ${escapeHtml(data.classes)}. Red: B_r = 0 on the source surface; ` +
      `cyan/pink: open field out/in; yellow: closed.</div>`;
  } catch (err) {
    out.innerText = `PFSS unavailable: ${err.message}`;
  }
}
