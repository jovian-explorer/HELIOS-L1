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
  img.src = f.image_url;
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

document.addEventListener('DOMContentLoaded', initImageArchive);
