/*
 * Event analysis tab: shock normals and timing, minimum variance, coupling functions, magnetic cloud search,
 * Lundquist flux rope fit and superposed epoch analysis (/api/analysis/*). All numbers come from the server; this
 * file only builds the requests, tables and charts. Times are entered and shown in UTC.
 */
(function () {
  const charts = {};
  let seaResult = null;

  function el(id) { return document.getElementById(id); }

  function fmt(v, digits = 2) {
    if (v === null || v === undefined || Number.isNaN(v)) return '---';
    return Number(v).toFixed(digits);
  }

  function vec(v, digits = 3) {
    return Array.isArray(v) ? `(${v.map(x => fmt(x, digits)).join(', ')})` : '---';
  }

  function setStatus(id, text, isError = false) {
    const s = el(id);
    if (!s) return;
    s.textContent = text;
    s.className = `text-xs ${isError ? 'text-rose-400' : 'text-slate-400'}`;
  }

  function table(headers, rows) {
    const head = headers.map(h => `<th class="ea-th">${h}</th>`).join('');
    const body = rows.map(r => `<tr>${r.map(c => `<td class="ea-td">${c}</td>`).join('')}</tr>`).join('');
    return `<table class="ea-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }

  function utc(id) { return (el(id)?.value || '').trim(); }

  // Gaps in the data behind an analysis (provenance.coverage; coverageText is in app.js).
  function coverageNote(prov) {
    const c = (prov && prov.coverage) || {};
    const parts = Object.entries(c).filter(([, v]) => v).map(([k, v]) => coverageText(k, v));
    return parts.length ? ` Data coverage: ${parts.join('; ')}.` : '';
  }

  // Where a time falls in the Richardson & Cane ICME list (helios/core/icme_catalog.py).
  function describeIcme(x) {
    if (!x) return 'none listed';
    const where = { ICME: 'in the ICME', sheath: 'in the sheath of the ICME', after: 'just after the ICME' }[x.region] || x.region;
    const mc = x.magnetic_cloud === 2 ? ', magnetic cloud' : '';
    const dst = x.dst_min_nt !== null && x.dst_min_nt !== undefined ? `, listed Dst ${x.dst_min_nt}${x.dst_kind !== 'final' ? ` (${x.dst_kind})` : ''}` : '';
    return `${where} ${x.icme_start} to ${x.icme_end}${mc}${dst}`;
  }

  async function getJSON(url) {
    const res = await fetch(url);
    let body = null;
    try { body = await res.json(); } catch (e) { body = null; }
    if (!res.ok) throw new Error(typeof apiErrorText === 'function' ? apiErrorText(body, res) : `HTTP ${res.status}`);
    return body;
  }

  function showDownload(id, url) {
    const a = el(id);
    if (!a) return;
    a.href = url + (url.includes('?') ? '&' : '?') + 'download=true';
    a.classList.remove('hidden');
  }

  function drawChart(id, config) {
    const ctx = el(id)?.getContext('2d');
    if (!ctx || typeof Chart === 'undefined') return;
    // The chart areas stay hidden until there is something to draw (they left 250-290 px
    // of empty space in every panel before the first result).
    el(id).parentElement.classList.remove('hidden');
    if (charts[id]) charts[id].destroy();
    config.options = Object.assign({
      responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
      plugins: { legend: { labels: { color: '#b9bcc1', boxWidth: 12, font: { size: 10 } } } },
    }, config.options || {});
    charts[id] = new Chart(ctx, config);
  }

  function axis(title, extra = {}) {
    return Object.assign({ type: 'linear', title: { display: true, text: title, color: '#9a9ea5' },
      ticks: { color: '#9a9ea5' }, grid: { color: 'rgba(154, 158, 165,0.12)' } }, extra);
  }

  function minutesFrom(tags, t0) {
    const ref = Date.parse(t0.replace(' ', 'T') + 'Z');
    return tags.map(t => (Date.parse(t.replace(' ', 'T') + 'Z') - ref) / 60000);
  }

  function hoursFrom(tags, t0) { return minutesFrom(tags, t0).map(m => m / 60); }

  // ---------------------------------------------------------------- shocks
  function shockQuery() {
    const q = new URLSearchParams({
      time: utc('ea-shock-time'), upstream_minutes: el('ea-shock-up').value,
      downstream_minutes: el('ea-shock-down').value, exclude_minutes: el('ea-shock-gap').value,
    });
    if (el('ea-shock-gap-after').value !== '') q.set('exclude_after_minutes', el('ea-shock-gap-after').value);
    if (!el('ea-shock-refine').checked) q.set('refine', 'false');
    return q;
  }

  window.eaShockPreset = function (mission, time, up, down, gap, gapAfter = '', refine = true) {
    el('ea-shock-mission').value = mission;
    el('ea-shock-time').value = time;
    el('ea-shock-up').value = up;
    el('ea-shock-down').value = down;
    el('ea-shock-gap').value = gap;
    el('ea-shock-gap-after').value = gapAfter;
    el('ea-shock-refine').checked = refine;
    window.eaRunShock();
  };

  // The windows of the IPShocks database at its listed time: 8 min on each side, leaving out
  // 1 min before and 2 min after a fast forward shock (2 before and 1 after a fast reverse one).
  window.eaIpshocksWindows = function (mission, time, type) {
    window.eaShockPreset(mission, time.replace(' ', 'T'), 8, 8, type === 'FR' ? 2 : 1, type === 'FR' ? 1 : 2, false);
  };

  window.eaRunShock = async function () {
    const current = latestRequest('eaRunShock');  // a second run of this form wins
    const q = shockQuery();
    q.set('mission', el('ea-shock-mission').value);
    const url = `/api/analysis/shock?${q}`;
    setStatus('ea-shock-status', 'Fetching native-cadence data from CDAWeb...');
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      const pm = r.preferred_method;
      const m = r.methods[pm] || {};
      setStatus('ea-shock-status',
        `${r.shock_type} shock at ${r.shock_time} UTC${r.shock_time_refined ? ' (refined from ' + r.shock_time_requested + ')' : ''}; ` +
        `${pm}: n = ${vec(m.normal_gse)}, θBn = ${fmt(m.theta_bn_deg, 1)}° ± ${fmt(m.theta_bn_sigma_deg, 1)}, ` +
        `V_sh = ${fmt(m.shock_speed_kms, 0)} ± ${fmt(m.shock_speed_sigma_kms, 0)} km/s, N2/N1 = ${fmt(r.density_ratio)}, ` +
        `B2/B1 = ${fmt(r.field_ratio)}.` + (r.warnings.length ? ' Warnings: ' + r.warnings.join(' ') : '') + ipshocksText(r) +
        (r.icme_list ? ` Richardson & Cane ICME list: disturbance ${r.icme_list.disturbance} (${r.icme_list.disturbance_source}), ` +
          `${r.icme_list.delay_minutes} min after this shock; ICME ${r.icme_list.icme_start} to ${r.icme_list.icme_end}` +
          `${r.icme_list.magnetic_cloud === 2 ? ', magnetic cloud' : ''}.` : ' No disturbance in the Richardson & Cane ICME list within 1 h before to 3 h after this shock.') +
        coverageNote(body.provenance));
      const rows = Object.entries(r.methods).map(([k, v]) => [
        k + (k === pm ? ' *' : ''), vec(v.normal_gse), `${fmt(v.theta_bn_deg, 1)} ± ${fmt(v.theta_bn_sigma_deg, 1)}`,
        `${fmt(v.shock_speed_kms, 0)} ± ${fmt(v.shock_speed_sigma_kms, 0)}`, fmt(v.alfven_mach), fmt(v.fast_mach)]);
      el('ea-shock-table').innerHTML = table(['Method', 'Normal (GSE)', 'θBn (°)', 'V_sh (km/s)', 'M_A', 'M_f'], rows) +
        `<p class="text-[10px] text-slate-500 mt-1">${r.conventions} Upstream: ${fmt(r.upstream.density_cm3)} cm⁻³, ` +
        `|B| ${fmt(r.upstream.B_magnitude_nT)} nT (${r.upstream.plasma_samples} spectra); downstream ${fmt(r.downstream.density_cm3)} cm⁻³, ` +
        `|B| ${fmt(r.downstream.B_magnitude_nT)} nT (${r.downstream.plasma_samples} spectra). Data: ` +
        body.provenance.datasets.map(d => d.id).join(', ') + '.</p>';
      const f = body.series.field_gse, p = body.series.plasma_gse;
      const fx = minutesFrom(f.time_tags, r.shock_time), px = minutesFrom(p.time_tags, r.shock_time);
      const w = r.windows_minutes;
      const bmax = Math.max(...f.bt.filter(v => v !== null)) * 1.1;
      drawChart('ea-shock-chart', {
        type: 'line',
        data: { datasets: [
          { label: '|B| (nT)', data: fx.map((x, i) => ({ x, y: f.bt[i] })), borderColor: '#7fa5cf', borderWidth: 1, pointRadius: 0, yAxisID: 'y' },
          { label: 'N (cm⁻³)', data: px.map((x, i) => ({ x, y: p.n[i] })), borderColor: '#b98f3f', borderWidth: 1.5, pointRadius: 2, yAxisID: 'y1' },
          { label: 'Averaging windows', data: [{ x: w.before[0], y: bmax }, { x: w.before[1], y: bmax }, { x: NaN, y: NaN },
            { x: w.after[0], y: bmax }, { x: w.after[1], y: bmax }], borderColor: '#529b6e', borderWidth: 4, pointRadius: 0, spanGaps: false, yAxisID: 'y' },
        ] },
        options: { scales: { x: axis(`Minutes from ${r.shock_time} UTC`), y: axis('|B| (nT)'),
          y1: axis('N (cm⁻³)', { position: 'right', grid: { drawOnChartArea: false } }) } },
      });
      showDownload('ea-shock-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-shock-status', e.message, true);
    }
  };

  // The IPShocks entry of the analysed shock (result.ipshocks) next to the values found here.
  function ipshocksText(r) {
    const ip = r.ipshocks, m = r.methods[r.preferred_method] || {};
    if (!ip) return ' Not in the IPShocks database within 5 min.';
    const w = r.windows_minutes, theirs = ip.type === 'FR' ? [-10, -2, 1, 9] : [-9, -1, 2, 10];
    const same = w.before[0] === theirs[0] && w.before[1] === theirs[1] && w.after[0] === theirs[2] && w.after[1] === theirs[3];
    return ` IPShocks (University of Helsinki, ${ip.catalog.licence}): ${ip.type} at ${ip.time} UTC (${ip.offset_seconds > 0 ? '+' : ''}${ip.offset_seconds} s), ` +
      `MX3 normal ${vec(ip.normal_gse, 2)}, ${fmt(ip.normal_angle_deg, 1)}° from the ${r.preferred_method} normal here; ` +
      `θBn ${fmt(ip.theta_bn_deg, 1)} ± ${fmt(ip.theta_bn_error_deg, 1)}° (here ${fmt(m.theta_bn_deg, 1)}), ` +
      `V_sh ${fmt(ip.shock_speed_kms, 0)} ± ${fmt(ip.shock_speed_error_kms, 0)} km/s (here ${fmt(m.shock_speed_kms, 0)}), ` +
      `M_A ${fmt(ip.alfven_mach)} ± ${fmt(ip.alfven_mach_error)} (here ${fmt(m.alfven_mach)})` +
      (same ? ', same windows.' : `; their windows are ${theirs[0]} to ${theirs[1]} and +${theirs[2]} to +${theirs[3]} min.`);
  }

  // ---------------------------------------------------------------- IPShocks database
  window.eaListShocks = async function () {
    const current = latestRequest('eaListShocks');  // a second run of this form wins
    const q = new URLSearchParams({ start: utc('ea-ips-start'), end: utc('ea-ips-end'), spacecraft: el('ea-ips-craft').value });
    setStatus('ea-ips-status', 'Reading the shock list...');
    try {
      const body = await getJSON(`/api/catalogs/shocks?${q}`);
      if (!current()) return;
      const c = body.catalog;
      setStatus('ea-ips-status', `${body.count} shock${body.count === 1 ? '' : 's'}. ${c.name}, version ${c.version}, licence ${c.licence}. Cite: ${c.citation}.`);
      el('ea-ips-table').innerHTML = body.count ? table(
        ['Time (UTC)', 'Spacecraft', 'Type', 'θBn (°)', 'V_sh (km/s)', 'M_A', 'M_ms', 'N2/N1', 'B2/B1', 'ΔV (km/s)', 'V up (km/s)', ''],
        body.events.map(e => [e.time, e.spacecraft, e.type, `${fmt(e.theta_bn_deg, 0)} ± ${fmt(e.theta_bn_error_deg, 0)}`,
          `${fmt(e.shock_speed_kms, 0)} ± ${fmt(e.shock_speed_error_kms, 0)}`, fmt(e.alfven_mach, 1), fmt(e.magnetosonic_mach, 1),
          fmt(e.density_ratio), fmt(e.field_ratio), fmt(e.speed_jump_kms, 0), fmt(e.upstream_speed_kms, 0),
          `<button class="ea-link" onclick="eaIpshocksWindows('${e.spacecraft}','${e.time}','${e.type}')">Analyse</button>`])) : '';
      const a = el('ea-ips-csv');
      a.href = `/api/catalogs/shocks?${q}&format=csv`;
      a.classList.remove('hidden');
    } catch (e) {
      if (!current()) return;
      setStatus('ea-ips-status', e.message, true);
    }
  };

  window.eaRunTiming = async function () {
    const current = latestRequest('eaRunTiming');  // a second run of this form wins
    const q = shockQuery();
    const ref = el('ea-shock-mission').value;
    q.set('reference', ref);
    q.set('targets', ['WIND', 'ACE', 'DSCOVR'].filter(s => s !== ref).join(','));
    const url = `/api/analysis/timing?${q}`;
    el('ea-timing-table').innerHTML = '<p class="text-slate-400">Fetching data for the other spacecraft...</p>';
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const ref0 = body.reference;
      const listedAt = x => !x ? 'none' : x.time.slice(11) + (x.minus_observed_s === null ? '' :
        ` (${x.minus_observed_s > 0 ? '+' : ''}${x.minus_observed_s} s)`);
      const rows = body.targets.map(t => t.status !== 'ok' ? [t.spacecraft, t.status, '', '', '', '', '', ''] : [
        t.spacecraft, t.predicted_time, t.observed_time || 'not found', listedAt(t.ipshocks), fmt(t.predicted_delay_s, 0),
        fmt(t.observed_delay_s, 0), fmt(t.residual_s, 0), fmt(t.implied_speed_kms, 0)]);
      el('ea-timing-table').innerHTML =
        `<p class="text-slate-300 mb-1">Reference ${ref0.spacecraft} at ${ref0.shock_time} UTC, ${ref0.method} normal ${vec(ref0.normal_gse)}, ` +
        `V_sh ${fmt(ref0.shock_speed_kms, 0)} km/s. <a class="ea-link" href="${url}&download=true">Save JSON</a></p>` +
        table(['Spacecraft', 'Predicted (UTC)', 'Observed (UTC)', 'IPShocks (vs observed)', 'Predicted delay (s)', 'Observed delay (s)', 'Residual (s)', 'Implied V along n (km/s)'], rows) +
        `<p class="text-[10px] text-slate-500 mt-1">${body.note}</p>`;
    } catch (e) {
      if (!current()) return;
      el('ea-timing-table').innerHTML = `<p class="text-rose-400">${escapeHtml(e.message)}</p>`;
    }
  };

  // ---------------------------------------------------------------- MVA
  window.eaRunMva = async function () {
    const current = latestRequest('eaRunMva');  // a second run of this form wins
    const q = new URLSearchParams({ mission: el('ea-mva-mission').value, start: utc('ea-mva-start'),
      end: utc('ea-mva-end'), average_seconds: el('ea-mva-avg').value });
    const url = `/api/analysis/mva?${q}`;
    setStatus('ea-mva-status', 'Running...');
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      const ev = r.eigenvectors, l = r.eigenvalues_nT2, er = r.angular_error_deg;
      setStatus('ea-mva-status', `${r.n_vectors} vectors; λ2/λ3 = ${fmt(r.ratio_intermediate_to_min, 1)}, λ1/λ2 = ${fmt(r.ratio_max_to_intermediate, 1)}` +
        (r.ratio_intermediate_to_min !== null && r.ratio_intermediate_to_min < 10 ? ' (λ2/λ3 < 10: normal poorly determined)' : '') +
        `; <B>·n = ${fmt(r.mean_normal_field_nT)} ± ${fmt(r.mean_normal_field_error_nT)} nT (eq. 8.24).` + coverageNote(body.provenance));
      el('ea-mva-table').innerHTML = table(['Direction', 'Eigenvalue (nT²)', 'Eigenvector (GSE)', 'Angular error (°)'], [
        ['Maximum', fmt(l[0], 3), vec(ev.max), `${fmt(er.max_toward_intermediate, 2)} (toward intermediate)`],
        ['Intermediate', fmt(l[1], 3), vec(ev.intermediate), ''],
        ['Minimum (normal)', fmt(l[2], 3), vec(ev.min), `${fmt(er.normal_toward_max, 2)} / ${fmt(er.normal_toward_intermediate, 2)} (toward maximum / intermediate)`],
      ]) + (r.bootstrap ? `<p class="text-slate-400 mt-1">Bootstrap (${r.bootstrap.n_samples} resamples): normal ±${fmt(r.bootstrap.normal_toward_max_std_deg, 2)}° toward maximum, ±${fmt(r.bootstrap.normal_toward_intermediate_std_deg, 2)}° toward intermediate; ⟨B⟩·n ${fmt(r.bootstrap.mean_normal_field_nT)} ± ${fmt(r.bootstrap.mean_normal_field_std_nT)} nT.</p>` : '');
      showDownload('ea-mva-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-mva-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- deHoffmann-Teller frame
  window.eaRunHt = async function () {
    const current = latestRequest('eaRunHt');  // a second run of this form wins
    const q = new URLSearchParams({ mission: el('ea-mva-mission').value, start: utc('ea-mva-start'), end: utc('ea-mva-end') });
    const url = `/api/analysis/ht?${q}`;
    setStatus('ea-ht-status', 'Running...');
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      setStatus('ea-ht-status', `${r.n_vectors} plasma samples; c(Ec, EHT) = ${fmt(r.correlation_ec_eht, 3)}, D(VHT)/D(0) = ${fmt(r.D.residual_ratio, 3)}` +
        (r.walen ? `; Walén slope ${fmt(r.walen.slope, 2)} (|slope| ≈ 1: rotational, ≈ 0: tangential discontinuity)` : '') + '.' + coverageNote(body.provenance));
      const row = (name, e) => [name, vec(e.v_ht_kms, 1), e.error_axes.map(a => fmt(a.sigma_kms, 1)).join(' / '),
        `${fmt(e.normal_velocity_kms, 1)} ± ${fmt(e.normal_velocity_error_kms, 1)}`];
      el('ea-ht-table').innerHTML = table(['Estimate', 'VHT (GSE, km/s)', 'Error semiaxes (km/s)', 'un along MVA normal (km/s)'], [
        row('Minimum D (eq. 9.10)', r.D), row('Minimum Q (eq. 9.14)', r.Q),
        ...(r.bootstrap ? [row(`Bootstrap, ${r.bootstrap.n_samples} resamples`, r.bootstrap)] : [])]);
      showDownload('ea-mva-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-ht-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- coupling functions
  window.eaRunCoupling = async function () {
    const current = latestRequest('eaRunCoupling');  // a second run of this form wins
    const q = new URLSearchParams({ mission: el('ea-cpl-mission').value, start: utc('ea-cpl-start'), end: utc('ea-cpl-end') });
    const url = `/api/analysis/coupling?${q}`;
    setStatus('ea-cpl-status', 'Running...');
    el('ea-cpl-table').innerHTML = '';
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      setStatus('ea-cpl-status', `${r.n_samples} plasma samples` +
        (r.uncertainties_available ? '; archive 1-σ speed and density errors propagated.' : '; this archive gives no per-sample uncertainties (measurement errors not shown).') + coverageNote(body.provenance));
      const names = { newell_dphi_dt: 'Newell dΦ/dt', akasofu_epsilon_gw: 'Akasofu ε (GW)', vbs_mv_m: 'V·Bs (mV/m)', dynamic_pressure_npa: 'P_dyn (nPa)',
        proton_beta: 'Proton β', alfven_mach: 'Alfvén Mach M_A' };
      const sig = v => (v === null || v === undefined ? '---' : Number(v).toPrecision(2));
      const rows = Object.entries(r.functions).map(([k, f]) => [names[k] || k, Number(f.mean).toPrecision(4),
        `± ${sig(f.measurement_sigma_of_mean)}`,
        f.sampling_ci95_of_mean ? `${Number(f.sampling_ci95_of_mean[0]).toPrecision(3)} to ${Number(f.sampling_ci95_of_mean[1]).toPrecision(3)}` : 'too few independent samples',
        fmt(f.n_eff, 1), f.median_relative_sigma === null ? '---' : `${fmt(100 * f.median_relative_sigma, 1)} %`]);
      el('ea-cpl-table').innerHTML = table(['Quantity', 'Mean', 'Measurement error', '95 % sampling interval', 'n_eff', 'Median per-sample error'], rows);
      showDownload('ea-cpl-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-cpl-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- time shift to the bow shock nose
  window.eaRunTimeshift = async function () {
    const current = latestRequest('eaRunTimeshift');  // a second run of this form wins
    const q = new URLSearchParams({ mission: el('ea-ts-mission').value, start: utc('ea-ts-start'), end: utc('ea-ts-end') });
    const url = `/api/analysis/timeshift?${q}`;
    setStatus('ea-ts-status', 'Fetching the field, plasma and positions (from 3 h before the first arrival) and shifting...');
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result, s = r.summary, c = r.omni_comparison, n = s.normals_percent, ser = body.series;
      const cmp = c && c.phase_front ? ` Against OMNI (${c.phase_front.minutes} minutes taken from this spacecraft): median difference ` +
        `${fmt(c.phase_front.median_difference_min, 2)} min, ${fmt(c.phase_front.within_1_min_percent, 0)} % within 1 min and ` +
        `${fmt(c.phase_front.within_2_min_percent, 0)} % within 2 min` +
        (c.flat ? `; flat delay ${fmt(c.flat.within_1_min_percent, 0)} % and ${fmt(c.flat.within_2_min_percent, 0)} %.` : '.') : (r.omni_note ? ` ${r.omni_note}` : '');
      setStatus('ea-ts-status', `${s.minutes} arrival minutes from ${s.vectors} field vectors (${fmt(s.cadence_s, 0)} s). Delay ${fmt(s.delay_median_min, 1)} min ` +
        `(10-90 %: ${fmt(s.delay_range_min[0], 1)} to ${fmt(s.delay_range_min[1], 1)}), flat ${fmt(s.flat_delay_median_min, 1)} min; bow shock nose at ` +
        `${fmt(s.bow_shock_nose_x_re, 1)} R_E. Normals: cross product ${fmt(n.cross_product, 0)} %, MVAB-0 ${fmt(n.mvab0, 0)} %, interpolated ${fmt(n.interpolated, 0)} %` +
        (s.vectors_not_shifted ? `; ${s.vectors_not_shifted} vectors not shifted (no normal within 3 h, or no velocity within 1 h).` : '.') + cmp + coverageNote(body.provenance));
      const t0 = Date.parse(ser.time_tags[0].replace(' ', 'T') + 'Z');
      const hx = ser.time_tags.map(t => (Date.parse(t.replace(' ', 'T') + 'Z') - t0) / 3.6e6);
      const pts = key => hx.map((x, i) => ({ x, y: ser[key][i] }));
      const datasets = [
        { label: 'Phase front delay (min)', data: pts('delay_min'), borderColor: '#7fa5cf', borderWidth: 1, pointRadius: 0 },
        { label: 'Flat delay ΔX/Vx (min)', data: pts('flat_delay_min'), borderColor: '#9a9ea5', borderDash: [4, 3], borderWidth: 1, pointRadius: 0 },
      ];
      if (ser.omni_delay_min) {
        datasets.push({ label: 'OMNI time shift (min)', data: pts('omni_delay_min'), borderColor: '#b98f3f', backgroundColor: '#b98f3f',
          showLine: false, pointRadius: 1 });
      }
      drawChart('ea-ts-chart', { type: 'line', data: { datasets },
        options: { scales: { x: axis(`Hours from ${ser.time_tags[0]} UTC (arrival at the bow shock nose)`), y: axis('Delay (min)') } } });
      const a = el('ea-ts-csv');
      a.href = `${url}&format=csv`;
      a.classList.remove('hidden');
      showDownload('ea-ts-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-ts-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- Richardson & Cane ICME list
  window.eaListIcmes = async function () {
    const current = latestRequest('eaListIcmes');  // a second run of this form wins
    const q = new URLSearchParams({ start: utc('ea-icme-start'), end: utc('ea-icme-end') });
    setStatus('ea-icme-status', 'Reading the ICME list...');
    try {
      const body = await getJSON(`/api/catalogs/icme?${q}`);
      if (!current()) return;
      const c = body.catalog;
      setStatus('ea-icme-status', `${body.count} ICMEs. Source: ${c.name}, revision ${c.revision}, ${c.origin}. ` +
        `Licence ${c.licence}. Cite: ${c.citation}.`);
      const cloud = { 2: 'cloud (2)', 1: 'rotation only (1)', 0: 'none (0)' };
      el('ea-icme-table').innerHTML = body.count ? table(
        ['Disturbance (UTC)', 'ICME start', 'ICME end', 'Magnetic cloud', 'Shock', 'V (km/s)', '|B| (nT)', 'Dst (nT)', 'Quality'],
        body.events.map(e => [e.disturbance + (e.disturbance_source === 'sudden commencement or disturbance arrival' ? '' :
          `<br><span class="text-slate-500">${e.disturbance_source}</span>`), e.icme_start, e.icme_end,
          cloud[e.magnetic_cloud] ?? '---', e.fast_forward_shock ? 'yes' : '', fmt(e.v_icme_kms, 0), fmt(e.b_mean_nt, 0),
          e.dst_min_nt === null ? '---' : `${e.dst_min_nt}${e.dst_kind !== 'final' ? ` (${e.dst_kind})` : ''}`,
          `${e.quality ?? '---'}${e.weak_signatures ? ' (weak)' : ''}`])) : '';
      const a = el('ea-icme-csv');
      a.href = `/api/catalogs/icme?${q}&format=csv`;
      a.classList.remove('hidden');
    } catch (e) {
      if (!current()) return;
      setStatus('ea-icme-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- sudden commencements
  let scResult = null;
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`;

  window.eaFindSc = async function () {
    const current = latestRequest('eaFindSc');  // a second run of this form wins
    const q = new URLSearchParams({ start: utc('ea-sc-start'), end: utc('ea-sc-end') });
    const url = `/api/analysis/sudden_commencements?${q}`;
    setStatus('ea-sc-status', 'Fetching OMNI 1-min SYM-H and pressure by month (up to a minute for a year) and the Ebre lists...');
    el('ea-sc-table').innerHTML = '';
    try {
      const body = await getJSON(url);
      if (!current()) return;
      scResult = body;
      const r = body.result, c = r.comparison, ser = body.series;
      const lists = Object.entries(c.years).map(([y, k]) => `${y} ${k || 'not readable'}`).join(', ');
      setStatus('ea-sc-status', `${plural(c.detections, 'sudden commencement')} detected. Ebre lists (${lists}): ${c.found} of ${plural(c.listed, 'listed SC')} found, ` +
        `${plural(c.not_listed, 'detection')} not listed (onsets within ${c.tolerance_minutes} min).` +
        (c.years_unread.length ? ` The list of ${c.years_unread.join(', ')} could not be read (offline, or not published yet).` : '') +
        ` ${c.with_l1_shock} of the detections follow a fast forward shock at L1 in the IPShocks database (planar arrival within ` +
        `${c.l1_shock_list.window_minutes} min; the database reaches ${c.l1_shock_list.last_shock.slice(0, 10)}).` +
        coverageNote(body.provenance), c.years_unread.length > 0);
      const listed = (x, onset) => !x ? 'not listed' : `${x.type} ${x.time.slice(0, 10) === onset.slice(0, 10) ? x.time.slice(11, 16) : x.time.slice(5, 16)} (${fmt(x.amplitude_nt, 1)} nT` +
        (x.offset_minutes === null ? ')' : `, ${x.offset_minutes > 0 ? '+' : ''}${fmt(x.offset_minutes, 1)} min)`);
      // e.g. "WIND 04:00, 562 km/s, +0.4 min": the onset 0.4 min after the shock's planar arrival.
      const l1 = (x, onset) => !x ? '' : `${x.spacecraft} ${x.time.slice(0, 10) === onset.slice(0, 10) ? x.time.slice(11, 16) : x.time.slice(5, 16)}, ` +
        `${fmt(x.shock_speed_kms, 0)} km/s, ${x.onset_minus_predicted_minutes > 0 ? '+' : ''}${fmt(x.onset_minus_predicted_minutes, 1)} min`;
      const hp30 = (x, onset) => !x ? '' : `${fmt(x.value, 1)} (${x.interval_start.slice(0, 10) === onset.slice(0, 10) ? x.interval_start.slice(11) : x.interval_start.slice(5)})`;
      el('ea-sc-table').innerHTML = r.events.length ? table(
        ['Onset (UTC)', 'Amplitude (nT)', 'Rise (min)', 'Step (nT/min)', 'Quiet (nT/min)', 'Pressure (nPa)', 'Ebre list', 'L1 shock (onset − arrival)', 'Hp30 max, 24 h', ''],
        r.events.map((e, i) => e.detected ? [e.time, fmt(e.amplitude_nt, 0), e.rise_minutes, fmt(e.max_step_nt, 0), fmt(e.quiet_nt, 1),
          e.pressure_jump === null ? 'no data' : `${fmt(e.pressure_before_npa, 1)} → ${fmt(e.pressure_after_npa, 1)} (×${fmt(e.pressure_ratio, 1)})`,
          listed(e.listed, e.time), l1(e.l1_shock, e.time), hp30(e.hp30_max_24h, e.time), `<button class="ea-link" onclick="eaShowSc(${i})">Show</button>`]
          : [e.time, '<span class="text-rose-400">not detected</span>', '', '', '', '', listed(e.listed, e.time), l1(e.l1_shock, e.time),
            hp30(e.hp30_max_24h, e.time), `<button class="ea-link" onclick="eaShowSc(${i})">Show</button>`])) : '';
      const t0 = Date.parse(ser.time_tags[0].replace(' ', 'T') + 'Z');
      const days = ser.time_tags.length * ser.cadence_minutes > 2 * 1440;
      const xOf = t => (Date.parse(t.replace(' ', 'T') + 'Z') - t0) / (days ? 864e5 : 36e5);
      const marks = (pick) => r.events.filter(pick).map(e => ({ x: xOf(e.time), y: e.window.sym_h[60] }));
      drawChart('ea-sc-chart', { type: 'line', data: { datasets: [
        { label: `SYM-H (nT, ${ser.cadence_minutes}-min)`, data: ser.time_tags.map((t, i) => ({ x: xOf(t), y: ser.sym_h[i] })),
          borderColor: '#7fa5cf', borderWidth: 1, pointRadius: 0, order: 1 },
        { label: 'Detected onset', data: marks(e => e.detected), showLine: false, pointRadius: 4, pointStyle: 'triangle',
          borderColor: '#b98f3f', backgroundColor: '#b98f3f' },
        { label: 'Listed, not detected', data: marks(e => !e.detected), showLine: false, pointRadius: 4, pointStyle: 'crossRot',
          borderColor: '#c26262', backgroundColor: '#c26262', borderWidth: 2 },
      ] }, options: { scales: { x: axis(`${days ? 'Days' : 'Hours'} from ${ser.time_tags[0]} UTC`, { min: 0, max: xOf(ser.time_tags[ser.time_tags.length - 1]) }),
        y: axis('SYM-H (nT)') } } });
      const a = el('ea-sc-csv');
      a.href = `${url}&format=csv`;
      a.classList.remove('hidden');
      showDownload('ea-sc-download', url);
      el('ea-sc-onsets').classList.toggle('hidden', !r.events.some(e => e.detected));
      if (r.events.length) window.eaShowSc(0);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-sc-status', e.message, true);
    }
  };

  window.eaShowSc = function (i) {
    const e = scResult && scResult.result.events[i];
    if (!e) return;
    const m = scResult.series.window_minutes;
    const ys = e.window.sym_h.filter(v => v !== null);
    drawChart('ea-sc-event-chart', { type: 'line', data: { datasets: [
      { label: 'SYM-H (nT)', data: m.map((x, k) => ({ x, y: e.window.sym_h[k] })), borderColor: '#7fa5cf', borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' },
      { label: 'Flow pressure (nPa, OMNI)', data: m.map((x, k) => ({ x, y: e.window.pressure[k] })), borderColor: '#b98f3f', borderWidth: 1, pointRadius: 0, yAxisID: 'y1' },
      { label: e.detected ? 'Onset' : 'Listed onset', data: ys.length ? [{ x: 0, y: Math.min(...ys) }, { x: 0, y: Math.max(...ys) }] : [],
        borderColor: '#9a9ea5', borderDash: [3, 3], borderWidth: 1, pointRadius: 0, yAxisID: 'y' },
    ] }, options: { scales: { x: axis(`Minutes from ${e.time} UTC`, { min: m[0], max: m[m.length - 1] }), y: axis('SYM-H (nT)'),
      y1: axis('Pressure (nPa)', { position: 'right', grid: { drawOnChartArea: false } }) } } });
  };

  window.eaScToSea = function () {
    const on = scResult ? scResult.result.events.filter(e => e.detected).map(e => e.time.replace(' ', 'T')) : [];
    el('ea-sea-onsets').value = on.slice(0, 60).join('\n');
    setStatus('ea-sc-status', `${plural(Math.min(on.length, 60), 'onset')} copied to the superposed epoch analysis below` +
      (on.length > 60 ? ` (the first 60 of ${on.length}: it takes at most 60).` : '.'), on.length > 60);
  };

  // ---------------------------------------------------------------- magnetic cloud search
  window.eaRunCloudSearch = async function () {
    const current = latestRequest('eaRunCloudSearch');  // a second run of this form wins
    const mission = el('ea-mcd-mission').value;
    const q = new URLSearchParams({ mission, start: utc('ea-mcd-start'), end: utc('ea-mcd-end'),
      criteria: el('ea-mcd-criteria').value });
    const url = `/api/analysis/mcdetect?${q}`;
    setStatus('ea-mcd-status', 'Fetching 1-min data and scanning (up to a minute for a month)...');
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      const yes = c => c ? 'pass' : '<span class="text-rose-400">fail</span>';
      setStatus('ea-mcd-status', `${r.accepted.length} of ${r.candidates.length} candidate regions pass all tests (${r.criteria} criteria). ${r.notes}` + coverageNote(body.provenance));
      el('ea-mcd-table').innerHTML = r.candidates.length ? table(
        ['Start (UTC)', 'End (UTC)', 'Hours', '&lt;B&gt; (nT)', '&lt;βp&gt;', '&lt;VTh&gt; (km/s)', 'ΔθB (°)', 'χM/&lt;B&gt;', 'Bz', 'Tests', 'ICME list (R&amp;C)', ''],
        r.candidates.map((c, i) => [c.start, c.end, fmt(c.duration_hours, 1), fmt(c.mean_b_nt, 1), fmt(c.mean_beta, 2),
          fmt(c.mean_thermal_speed_kms, 1), fmt(c.theta_b_range_deg, 0), fmt(c.chi_m_over_b, 2), c.bz_sense,
          Object.entries(c.tests).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${yes(v)}`).join('<br>'),
          (c.icme_list || []).length ? c.icme_list.map(x => `${x.icme_start} to ${x.icme_end}, ${Math.round(100 * x.fraction_inside_icme)} % inside` +
            `${x.magnetic_cloud === 2 ? ', magnetic cloud' : ''}`).join('<br>') : 'none listed',
          `<button class="ea-link" onclick="eaFitCandidate(${i})">Fit flux rope</button>`])) : '';
      window.eaCloudCandidates = { mission, list: r.candidates };
      showDownload('ea-mcd-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-mcd-status', e.message, true);
    }
  };

  window.eaFitCandidate = function (i) {
    const c = window.eaCloudCandidates?.list?.[i];
    if (!c) return;
    const m = el('ea-mc-mission');
    if ([...m.options].some(o => o.value === window.eaCloudCandidates.mission)) m.value = window.eaCloudCandidates.mission;
    el('ea-mc-start').value = c.start.replace(' ', 'T');
    el('ea-mc-end').value = c.end.replace(' ', 'T');
    el('ea-mc-start').scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.eaRunFluxRope();
  };

  // ---------------------------------------------------------------- flux rope
  window.eaRunFluxRope = async function () {
    const current = latestRequest('eaRunFluxRope');  // a second run of this form wins
    const q = new URLSearchParams({ mission: el('ea-mc-mission').value, start: utc('ea-mc-start'),
      end: utc('ea-mc-end'), average_minutes: el('ea-mc-avg').value });
    const url = `/api/analysis/fluxrope?${q}`;
    setStatus('ea-mc-status', 'Fitting (a few seconds)...');
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      setStatus('ea-mc-status', `${r.n_averages} averages of ${r.average_minutes} min, cloud speed ${fmt(r.speed_kms, 0)} km/s. ${r.conventions}` + coverageNote(body.provenance));
      const u = r.uncertainties || {};
      const pm = (v, d) => (v === undefined || v === null ? '' : ` ± ${fmt(v, d)}`);
      el('ea-mc-table').innerHTML = table(['Quantity', 'Value ± 1σ'], [
        ['Axis longitude φA / latitude θA (GSE)', `${fmt(r.axis_longitude_deg, 1)}° / ${fmt(r.axis_latitude_deg, 1)}°${pm(u.axis_latitude_deg, 0)}°`],
        ['Axis direction (error cone)', u.axis_cone_deg !== undefined ? `± ${fmt(u.axis_cone_deg, 0)}° (cone angle βCA ${fmt(u.cone_angle_beta_ca_deg, 0)}°)` : '---'],
        ['B0 (axial field)', `${fmt(r.b0_nT, 1)}${pm(u.b0_nT, 1)} nT`], ['Handedness', r.handedness],
        ['Closest approach', `${fmt(r.closest_approach_percent, 0)}${pm(u.closest_approach_percent, 0)} % of R0 at ${r.closest_approach_time} UTC`],
        ['Diameter 2R0', `${fmt(r.diameter_au, 3)}${pm(u.diameter_au, 3)} AU`], ['Axial flux', `${fmt(r.axial_flux_1e20_Mx, 1)} × 10²⁰ Mx`],
        ['χR (unit vectors)', `${fmt(r.chi_r, 3)} (noise level ${fmt(u.noise_level_nT, 1)} nT)`]]) +
        `<p class="text-[10px] text-slate-400 mt-1">Uncertainties from the error study of Lepping et al. (2003) as tabulated for the WIND clouds (Lepping et al. 2006).${(u.warnings || []).map(w => ' ' + escapeHtml(w)).join('')}</p>`;
      const hx = hoursFrom(r.model.time_tags, r.start.replace(' ', 'T'));
      const comp = ['Bx', 'By', 'Bz'], colors = ['#7fa5cf', '#529b6e', '#c26262'];
      const ds = [];
      comp.forEach((c, k) => {
        ds.push({ label: `${c} observed`, data: hx.map((x, i) => ({ x, y: r.model.observed_gse_nT[i][k] })), borderColor: colors[k],
          backgroundColor: colors[k], showLine: false, pointRadius: 2.5 });
        ds.push({ label: `${c} model`, data: hx.map((x, i) => ({ x, y: r.model.model_gse_nT[i][k] })), borderColor: colors[k],
          borderWidth: 1.5, pointRadius: 0 });
      });
      drawChart('ea-mc-chart', { type: 'line', data: { datasets: ds },
        options: { scales: { x: axis(`Hours from ${r.start} UTC`), y: axis('B (nT, GSE)') } } });
      showDownload('ea-mc-download', url);
    } catch (e) {
      if (!current()) return;
      setStatus('ea-mc-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- superposed epoch
  // Storm selection by Dst: the onsets come from /api/statistics/storms, and while the list
  // is unchanged the analysis is requested with the same selection, so that the server
  // records it in the provenance and the CSV.
  let stormSelection = null;

  function stormParams() {
    const p = { storm_threshold_nt: el('ea-storm-thr').value, storm_start_year: el('ea-storm-y0').value,
      storm_end_year: el('ea-storm-y1').value, storm_separation_hours: el('ea-storm-sep').value,
      storm_driver: el('ea-storm-driver').value, storm_epoch: el('ea-storm-epoch').value };
    if (el('ea-storm-floor').value !== '') p.storm_floor_nt = el('ea-storm-floor').value;
    return p;
  }

  window.eaFindStorms = async function () {
    const current = latestRequest('eaFindStorms');  // a second run of this form wins
    const p = stormParams();
    const q = new URLSearchParams({ start_year: p.storm_start_year, end_year: p.storm_end_year,
      threshold_nt: p.storm_threshold_nt, separation_hours: p.storm_separation_hours, driver: p.storm_driver });
    if (p.storm_floor_nt !== undefined) q.set('floor_nt', p.storm_floor_nt);
    setStatus('ea-storm-status', 'Selecting storms from hourly Dst...');
    try {
      const body = await getJSON(`/api/statistics/storms?${q}`);
      if (!current()) return;
      const r = body.result, years = omniYearsNote(body.provenance);
      const key = p.storm_epoch === 'minimum' ? 'minimum_time' : 'first_hour_below';
      const list = r.storms.map(st => st[key].replace(' ', 'T')).join('\n');
      el('ea-sea-onsets').value = list;
      stormSelection = r.storms.length ? { params: p, text: list } : null;
      const ic = r.icme_catalog || {};
      const n = ic.counts || {};
      setStatus('ea-storm-status', `${r.storms.length} storms (${r.log.map(l => `${l.filter}: ${l.storms_remaining}`).join('; ')}${years}).` +
        (r.storms.length > 60 ? ' The analysis takes at most 60: narrow the selection.' : '') +
        (ic.counts ? ` Dst minimum in a listed ICME ${n.ICME}, its sheath ${n.sheath}, the ${ic.after_hours} h after it ${n.after}, none ${n.none} ` +
          `(${ic.name}, revision ${ic.revision}, ${ic.origin}; doi:${ic.doi}, ${ic.licence}).` : ''), r.storms.length > 60 || years !== '');
      el('ea-storm-table').innerHTML = r.storms.length ? table(['Dst minimum (UTC)', 'Dst (nT)', 'Below threshold from', 'Bz 6 h before (nT)', 'V (km/s)', 'Plasma type', 'ICME list (Richardson & Cane)'],
        r.storms.map(st => [st.minimum_time, fmt(st.minimum_dst_nt, 0), st.first_hour_below, fmt(st.driver_bz_gsm_nt, 1),
          fmt(st.driver_speed_kms, 0), st.driver_type ? st.driver_type.replace('_', ' ') : '---', describeIcme(st.icme)])) : '';
    } catch (e) {
      if (!current()) return;
      setStatus('ea-storm-status', e.message, true);
    }
  };

  window.eaScoreDstModels = async function () {
    const current = latestRequest('eaScoreDstModels');  // a second run of this form wins
    const p = stormParams();
    const q = new URLSearchParams({ start_year: p.storm_start_year, end_year: p.storm_end_year,
      threshold_nt: p.storm_threshold_nt, separation_hours: p.storm_separation_hours, driver: p.storm_driver });
    if (p.storm_floor_nt !== undefined) q.set('floor_nt', p.storm_floor_nt);
    const url = `/api/statistics/dst_models?${q}`;
    setStatus('ea-skill-status', 'Running both models over every hour of the years...');
    el('ea-skill-table').innerHTML = '';
    try {
      const body = await getJSON(url);
      if (!current()) return;
      const r = body.result;
      const cell = (m, k, d) => (m[k].mean === null ? '---' : `${fmt(m[k].mean, d)}${m[k].ci95 ? ` (${fmt(m[k].ci95[0], d)} to ${fmt(m[k].ci95[1], d)})` : ''}`);
      el('ea-skill-table').innerHTML = table(['Model', 'Storms', 'Mean r (95 %)', 'Mean RMSE nT (95 %)', 'Mean bias nT (95 %)', 'Minimum error nT (95 %)'],
        Object.values(r.models).map(m => [m.name, m.n_storms, cell(m, 'r', 2), cell(m, 'rmse_nt', 1), cell(m, 'bias_nt', 1), cell(m, 'minimum_error_nt', 1)]));
      setStatus('ea-skill-status', `Scored against hourly Dst in each storm window (highest Dst in the 24 h before the minimum to recovery above -50 nT, after Ji et al. 2012); bias and minimum error are model minus observed. Intervals treat the storms as independent` +
        `${omniYearsNote(body.provenance)}.`, omniYearsNote(body.provenance) !== '');
    } catch (e) {
      if (!current()) return;
      setStatus('ea-skill-status', e.message, true);
    }
  };

  window.eaRunSea = async function () {
    const current = latestRequest('eaRunSea');  // a second run of this form wins
    const onsets = (el('ea-sea-onsets').value || '').split(/[\s,]+/).filter(Boolean).join(',');
    const q = new URLSearchParams({ parameters: el('ea-sea-params').value.replace(/\s+/g, ''),
      before_hours: el('ea-sea-before').value, after_hours: el('ea-sea-after').value, cadence_minutes: el('ea-sea-cad').value });
    if (stormSelection && el('ea-sea-onsets').value === stormSelection.text) {
      Object.entries(stormSelection.params).forEach(([k, v]) => q.set(k, v));
    } else {
      q.set('onsets', onsets);
    }
    const url = `/api/analysis/superposed?${q}`;
    setStatus('ea-sea-status', 'Fetching OMNI windows...');
    try {
      const seaBody = await getJSON(url);
      if (!current()) return;
      seaResult = seaBody.result;
      el('ea-sea-show-row').classList.remove('hidden');  // the quantity menu once there is a result
      const sel = el('ea-sea-show');
      sel.innerHTML = seaResult.parameters.map(p => `<option value="${p}">${p}</option>`).join('');
      setStatus('ea-sea-status', `${seaResult.n_events} events, ${seaResult.cadence_minutes}-min bins.`);
      const p0 = seaResult.parameters[0];
      // The extreme that marks activity: the minimum of SYM-H, AL and Bz, the maximum of the others (AE, Kp, Hp30, speed...).
      const ext = p => (['sym_h', 'al', 'bz_gsm'].includes(p) ? 'min' : 'max');
      el('ea-sea-table').innerHTML = table(['Onset (UTC)', 'Records'].concat(seaResult.parameters.map(p => `${p} ${ext(p)} (epoch h)`)),
        seaResult.events.map(e => [e.onset, e.n_records].concat(seaResult.parameters.map(p => e[p] ?
          `${fmt(e[p][ext(p)], 1)} (${fmt(e[p][`${ext(p)}_epoch_hours`], 2)})` : '---'))));
      const csv = el('ea-sea-csv');
      csv.href = url + '&format=csv';
      csv.classList.remove('hidden');
      showDownload('ea-sea-download', url);
      sel.value = p0;
      window.eaDrawSea();
    } catch (e) {
      if (!current()) return;
      setStatus('ea-sea-status', e.message, true);
    }
  };

  window.eaDrawSea = function () {
    if (!seaResult) return;
    const p = el('ea-sea-show').value;
    const st = seaResult.statistics[p], x = seaResult.epoch_hours;
    const pts = arr => x.map((v, i) => ({ x: v, y: arr[i] }));
    drawChart('ea-sea-chart', {
      type: 'line',
      data: { datasets: [
        { label: 'Upper quartile', data: pts(st.q75), borderColor: 'rgba(127, 165, 207,0.4)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(127, 165, 207,0.12)' },
        { label: 'Lower quartile', data: pts(st.q25), borderColor: 'rgba(127, 165, 207,0.4)', borderWidth: 1, pointRadius: 0 },
        { label: 'Median', data: pts(st.median), borderColor: '#7fa5cf', borderWidth: 2, pointRadius: 0 },
        { label: 'Mean', data: pts(st.mean), borderColor: '#b98f3f', borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0 },
        ...(st.mean_ci95_low ? [
          { label: 'Mean 95 % CI (bootstrap)', data: pts(st.mean_ci95_high), borderColor: 'rgba(185, 143, 63,0.5)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(185, 143, 63,0.10)' },
          { label: 'Mean 95 % CI low', data: pts(st.mean_ci95_low), borderColor: 'rgba(185, 143, 63,0.5)', borderWidth: 1, pointRadius: 0 },
        ] : []),
      ] },
      options: { scales: { x: axis('Epoch time (hours from onset)', { min: x[0], max: x[x.length - 1] }), y: axis(p) } },
    });
  };
})();
