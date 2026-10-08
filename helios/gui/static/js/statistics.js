/*
 * OMNI statistics panel (Event Analysis tab): builds /api/statistics/omni requests from the
 * form, draws the answer (histogram, joint histogram, conditional mean with its 95 % band,
 * solar-cycle series) and lists every filter with the hours it kept. All numbers come from
 * the server.
 */
(function () {
  let chart = null;
  let quantities = {};

  function el(id) { return document.getElementById(id); }

  function num(v, digits = 3) {
    if (v === null || v === undefined || Number.isNaN(v)) return '---';
    const a = Math.abs(v);
    return (a !== 0 && (a < 0.01 || a >= 1e5)) ? Number(v).toExponential(2) : Number(v).toPrecision(digits);
  }

  function setStatus(text, isError = false) {
    el('st-status').textContent = text;
    el('st-status').className = `text-xs ${isError ? 'text-rose-400' : 'text-slate-400'}`;
  }

  function table(headers, rows) {
    const esc = (t) => (typeof escapeHtml === 'function' ? escapeHtml(String(t)) : String(t));
    return `<table class="ea-table"><thead><tr>${headers.map(h => `<th class="ea-th">${esc(h)}</th>`).join('')}</tr></thead>` +
      `<tbody>${rows.map(r => `<tr>${r.map(c => `<td class="ea-td">${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  }

  function label(q) {
    const info = quantities[q];
    return info ? `${q}${info.units ? ` (${info.units})` : ''}` : q;
  }

  function axis(title, type = 'linear') {
    const ticks = { color: '#94a3b8' };
    if (type === 'logarithmic') {  // label the decades only
      ticks.callback = (v) => (Math.abs(Math.log10(v) - Math.round(Math.log10(v))) < 1e-6 ? String(Number(v)) : '');
    }
    return { type, title: { display: true, text: title, color: '#94a3b8' }, ticks, grid: { color: 'rgba(148,163,184,0.12)' } };
  }

  function resetCanvas(show = true) {
    if (chart) { chart.destroy(); chart = null; }
    const c = el('st-chart');
    c.parentElement.classList.toggle('hidden', !show);  // no empty chart area without a chart
    const ctx = c.getContext('2d');
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, c.width, c.height);
    return c;
  }

  function draw(config) {
    const c = resetCanvas();
    if (typeof Chart === 'undefined') return;
    config.options = Object.assign({ responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
      plugins: { legend: { labels: { color: '#cbd5e1', boxWidth: 12, font: { size: 10 },
        filter: (item) => !/ low$/.test(item.text) } } } }, config.options || {});  // lower band edges need no legend entry
    chart = new Chart(c.getContext('2d'), config);
  }

  // Joint histogram as a heat map drawn directly on the canvas (log colour scale of counts).
  function drawHeatmap(r, xq, yq, logX, logY) {
    const c = resetCanvas();
    // Chart.js leaves its own size on the canvas: take the size of the container instead.
    c.style.width = '100%'; c.style.height = '100%';
    const w = c.parentElement.clientWidth, h = c.parentElement.clientHeight;
    c.width = w; c.height = h;
    const ctx = c.getContext('2d');
    const m = { l: 80, r: 70, t: 10, b: 40 };
    const nx = r.x_edges.length - 1, ny = r.y_edges.length - 1;
    const maxC = Math.max(1, ...r.counts.flat());
    const pw = (w - m.l - m.r) / nx, ph = (h - m.t - m.b) / ny;
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < ny; j++) {
        const n = r.counts[i][j];
        if (!n) continue;
        const f = Math.log(1 + n) / Math.log(1 + maxC);
        ctx.fillStyle = `hsl(${240 - 200 * f}, 85%, ${25 + 35 * f}%)`;
        ctx.fillRect(m.l + i * pw, h - m.b - (j + 1) * ph, Math.ceil(pw), Math.ceil(ph));
      }
    }
    ctx.fillStyle = '#94a3b8';
    ctx.font = '10px JetBrains Mono, monospace';
    for (let i = 0; i <= nx; i += Math.max(1, Math.round(nx / 6))) {
      ctx.fillText(num(r.x_edges[i], 3), m.l + i * pw - 10, h - m.b + 14);
    }
    ctx.textAlign = 'right';
    for (let j = 0; j <= ny; j += Math.max(1, Math.round(ny / 6))) {
      ctx.fillText(num(r.y_edges[j], 3), m.l - 4, h - m.b - j * ph + 3);
    }
    ctx.textAlign = 'left';
    ctx.fillText(`${label(xq)}${logX ? ' (log bins)' : ''}`, m.l + (w - m.l - m.r) / 2 - 40, h - 6);
    ctx.save(); ctx.translate(12, m.t + (h - m.t - m.b) / 2 + 60); ctx.rotate(-Math.PI / 2);
    ctx.fillText(`${label(yq)}${logY ? ' (log bins)' : ''}`, 0, 0); ctx.restore();
    // colour bar
    for (let k = 0; k < 100; k++) {
      const f = k / 99;
      ctx.fillStyle = `hsl(${240 - 200 * f}, 85%, ${25 + 35 * f}%)`;
      ctx.fillRect(w - m.r + 15, h - m.b - (k + 1) * (h - m.t - m.b) / 100, 12, Math.ceil((h - m.t - m.b) / 100));
    }
    ctx.fillStyle = '#94a3b8';
    ctx.fillText(`${maxC}`, w - m.r + 30, m.t + 8);
    ctx.fillText('1', w - m.r + 30, h - m.b);
    ctx.fillText('hours', w - m.r + 12, h - m.b + 14);
  }

  async function loadQuantities() {
    try {
      const res = await fetch('/api/statistics/omni/quantities');
      if (!res.ok) return;
      quantities = (await res.json()).quantities || {};
      const opts = Object.keys(quantities).map(q => `<option value="${q}">${q}</option>`).join('');
      el('st-x').innerHTML = opts; el('st-y').innerHTML = opts;
      el('st-x').value = 'newell'; el('st-y').value = 'dst';
      Object.keys(quantities).forEach(q => {
        el('st-x').querySelector(`option[value="${q}"]`).title = quantities[q].label;
      });
    } catch (e) { /* the panel works once the server answers */ }
  }

  window.stAnalysisChanged = function () {
    const a = el('st-analysis').value;
    el('st-y-box').style.display = (a === 'distribution' || a === 'cycle') ? 'none' : '';
    el('st-res-box').style.display = a === 'cycle' ? '' : 'none';
  };

  window.stPreset = function (analysis, x, y, bins, logX, where, logY) {
    el('st-analysis').value = analysis; el('st-x').value = x;
    if (y) el('st-y').value = y;
    el('st-bins').value = bins; el('st-logx').checked = !!logX; el('st-logy').checked = logY === 'log';
    el('st-where').value = where || '';
    window.stAnalysisChanged();
    window.stRun();
  };

  function query() {
    const a = el('st-analysis').value;
    const q = new URLSearchParams({
      start_year: el('st-y0').value, end_year: el('st-y1').value, analysis: a, x: el('st-x').value,
      bins: el('st-bins').value, log_x: el('st-logx').checked, log_y: el('st-logy').checked,
      resolution: el('st-res').value, where: el('st-where').value.trim(),
      bz_south_hours: el('st-bzs').value || 0, bz_north_hours: el('st-bzn').value || 0,
      min_imf_points: el('st-imfpts').value || 0, min_plasma_points: el('st-plspts').value || 0,
      sw_type: [...document.querySelectorAll('.st-type:checked')].map(c => c.value).join(','),
    });
    if (a !== 'distribution' && a !== 'cycle') q.set('y', el('st-y').value);
    return q;
  }

  window.stRun = async function () {
    const q = query();
    const url = `/api/statistics/omni?${q}`;
    setStatus('Running (the first request for a span of years downloads about 1 MB per year from CDAWeb)...');
    el('st-summary').innerHTML = ''; el('st-filters').innerHTML = '';
    let body;
    try {
      const res = await fetch(url);
      body = await res.json().catch(() => null);
      if (!res.ok) throw new Error(typeof apiErrorText === 'function' ? apiErrorText(body, res) : `HTTP ${res.status}`);
    } catch (e) {
      setStatus(e.message, true);
      return;
    }
    const out = body.result, r = out.result, x = out.x, y = out.y;
    const prov = body.provenance;
    setStatus(`${out.hours_selected.toLocaleString()} of ${out.hours_in_interval.toLocaleString()} hours selected` +
      omniYearsNote(prov) + '.');
    el('st-filters').innerHTML = table(['Filter (applied in this order)', 'Hours remaining'],
      out.filters.map(f => [f.filter, f.hours_remaining.toLocaleString()]));
    const csv = el('st-csv'); csv.href = `${url}&format=csv`; csv.classList.remove('hidden');
    const dl = el('st-download'); dl.href = `${url}&download=true`; dl.classList.remove('hidden');
    const corrRow = (c) => (c && c.r !== null && c.r !== undefined)
      ? [['Pearson r', `${num(c.r)} (95 %: ${c.ci95 ? `${num(c.ci95[0])} to ${num(c.ci95[1])}` : 'too few independent samples'})`],
         ['Spearman rank correlation', num(c.spearman_rho)], ['Hours / independent samples', `${c.n.toLocaleString()} / ~${num(c.n_eff, 3)}`]]
      : [];
    const logX = el('st-logx').checked, logY = el('st-logy').checked;

    if (out.analysis === 'distribution') {
      const pts = r.counts.map((n, i) => ({ x: logX ? Math.sqrt(r.edges[i] * r.edges[i + 1]) : (r.edges[i] + r.edges[i + 1]) / 2, y: n }));
      draw({ type: 'bar', data: { datasets: [{ label: `Hours per bin of ${x}`, data: pts, backgroundColor: 'rgba(56,189,248,0.6)', barPercentage: 1.0, categoryPercentage: 1.0 }] },
        options: { scales: { x: axis(label(x), logX ? 'logarithmic' : 'linear'), y: axis('Hours') } } });
      const p = r.percentiles;
      el('st-summary').innerHTML = table(['Statistic', 'Value'], [
        ['Mean (95 % interval)', `${num(r.mean, 4)} (${r.mean_ci95 ? `${num(r.mean_ci95[0], 4)} to ${num(r.mean_ci95[1], 4)}` : '---'})`],
        ['Standard deviation', num(r.std)], ['Median (quartiles)', `${num(p.median)} (${num(p.p25)} to ${num(p.p75)})`],
        ['5th / 95th percentile', `${num(p.p05)} / ${num(p.p95)}`],
        ['Hours / independent samples', `${r.n.toLocaleString()} / ~${num(r.n_eff, 3)}`],
        ['Outside the plotted range', r.outside_range.toLocaleString()]]);
    } else if (out.analysis === 'joint') {
      drawHeatmap(r, x, y, logX, logY);
      el('st-summary').innerHTML = table(['Statistic', 'Value'], [...corrRow(r.correlation), ['Outside the plotted range', r.outside_range.toLocaleString()]]);
    } else if (out.analysis === 'conditional') {
      const pts = (k) => r.x_center.map((c, i) => ({ x: c, y: r[k][i] })).filter(p => p.y !== null);
      draw({ type: 'line', data: { datasets: [
        { label: 'Upper quartile', data: pts('q75'), borderColor: 'rgba(148,163,184,0.5)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(148,163,184,0.10)' },
        { label: 'Lower quartile', data: pts('q25'), borderColor: 'rgba(148,163,184,0.5)', borderWidth: 1, pointRadius: 0 },
        { label: 'Mean 95 % interval', data: pts('mean_ci95_high'), borderColor: 'rgba(245,158,11,0.5)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(245,158,11,0.18)' },
        { label: 'Mean 95 % low', data: pts('mean_ci95_low'), borderColor: 'rgba(245,158,11,0.5)', borderWidth: 1, pointRadius: 0 },
        { label: `Mean of ${y}`, data: pts('mean'), borderColor: '#f59e0b', borderWidth: 2, pointRadius: 2 },
        { label: `Median of ${y}`, data: pts('median'), borderColor: '#38bdf8', borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0 },
      ] }, options: { scales: { x: axis(label(x), logX ? 'logarithmic' : 'linear'), y: axis(label(y)) } } });
      el('st-summary').innerHTML = table([`${x} (bin centre)`, 'Hours', `Mean ${y}`, '95 % interval', 'Median', 'Quartiles'],
        r.x_center.map((c, i) => [num(c), r.n[i].toLocaleString(), num(r.mean[i]),
          r.mean_ci95_low[i] !== null ? `${num(r.mean_ci95_low[i])} to ${num(r.mean_ci95_high[i])}` : (r.n[i] < r.min_count ? 'too few hours' : '---'),
          num(r.median[i]), r.q25[i] !== null ? `${num(r.q25[i])} to ${num(r.q75[i])}` : '---'])) +
        table(['Correlation of the hourly values', 'Value'], corrRow(r.correlation));
    } else if (out.analysis === 'correlation') {
      resetCanvas(false);
      el('st-summary').innerHTML = table(['Statistic', 'Value'], corrRow(r));
    } else {
      const per = r.periods.filter(p => p.mean !== null);
      const t = (p) => (r.resolution === 'year' ? Number(p.period) + 0.5 : Number(p.period.slice(0, 4)) + (Number(p.period.slice(5, 7)) - 0.5) / 12);
      draw({ type: 'line', data: { datasets: [
        { label: '95 % interval', data: per.filter(p => p.mean_ci95).map(p => ({ x: t(p), y: p.mean_ci95[1] })), borderColor: 'rgba(245,158,11,0.4)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(245,158,11,0.18)', yAxisID: 'y' },
        { label: '95 % low', data: per.filter(p => p.mean_ci95).map(p => ({ x: t(p), y: p.mean_ci95[0] })), borderColor: 'rgba(245,158,11,0.4)', borderWidth: 1, pointRadius: 0, yAxisID: 'y' },
        { label: `Mean ${x}`, data: per.map(p => ({ x: t(p), y: p.mean })), borderColor: '#f59e0b', borderWidth: 2, pointRadius: 2, yAxisID: 'y' },
        { label: 'Sunspot number', data: r.periods.filter(p => p.sunspot_number !== null).map(p => ({ x: t(p), y: p.sunspot_number })), borderColor: '#94a3b8', borderWidth: 1, borderDash: [3, 3], pointRadius: 0, yAxisID: 'y2' },
      ] }, options: { scales: { x: Object.assign(axis('Year'), { ticks: { color: '#94a3b8', callback: (v) => String(v) } }), y: axis(label(x)), y2: Object.assign(axis('Sunspot number'), { position: 'right', grid: { drawOnChartArea: false } }) } } });
      const c = r.correlation;
      el('st-summary').innerHTML = table(['Statistic', 'Value'], c ? [
        [`r of ${r.resolution}ly means with the sunspot number`, `${num(c.r_with_sunspot_number)} (95 %: ${c.ci95 ? `${num(c.ci95[0])} to ${num(c.ci95[1])}` : 'too few independent periods'})`],
        ['Periods used / independent', `${c.n_periods} / ~${num(c.n_eff, 3)} (coverage at least ${Math.round(100 * r.min_coverage)} %)`]] : [['Correlation', 'too few periods']]);
    }
  };

  document.addEventListener('DOMContentLoaded', () => { loadQuantities(); window.stAnalysisChanged(); });
})();
