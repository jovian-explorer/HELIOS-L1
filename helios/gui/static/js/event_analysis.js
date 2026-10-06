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
    if (charts[id]) charts[id].destroy();
    config.options = Object.assign({
      responsive: true, maintainAspectRatio: false, animation: false, parsing: false,
      plugins: { legend: { labels: { color: '#cbd5e1', boxWidth: 12, font: { size: 10 } } } },
    }, config.options || {});
    charts[id] = new Chart(ctx, config);
  }

  function axis(title, extra = {}) {
    return Object.assign({ type: 'linear', title: { display: true, text: title, color: '#94a3b8' },
      ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.12)' } }, extra);
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
    return q;
  }

  window.eaShockPreset = function (mission, time, up, down, gap) {
    el('ea-shock-mission').value = mission;
    el('ea-shock-time').value = time;
    el('ea-shock-up').value = up;
    el('ea-shock-down').value = down;
    el('ea-shock-gap').value = gap;
    window.eaRunShock();
  };

  window.eaRunShock = async function () {
    const q = shockQuery();
    q.set('mission', el('ea-shock-mission').value);
    const url = `/api/analysis/shock?${q}`;
    setStatus('ea-shock-status', 'Fetching native-cadence data from CDAWeb...');
    try {
      const body = await getJSON(url);
      const r = body.result;
      const pm = r.preferred_method;
      const m = r.methods[pm] || {};
      setStatus('ea-shock-status',
        `${r.shock_type} shock at ${r.shock_time} UTC${r.shock_time_refined ? ' (refined from ' + r.shock_time_requested + ')' : ''}; ` +
        `${pm}: n = ${vec(m.normal_gse)}, θBn = ${fmt(m.theta_bn_deg, 1)}° ± ${fmt(m.theta_bn_sigma_deg, 1)}, ` +
        `V_sh = ${fmt(m.shock_speed_kms, 0)} ± ${fmt(m.shock_speed_sigma_kms, 0)} km/s, N2/N1 = ${fmt(r.density_ratio)}, ` +
        `B2/B1 = ${fmt(r.field_ratio)}.` + (r.warnings.length ? ' Warnings: ' + r.warnings.join(' ') : ''));
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
          { label: '|B| (nT)', data: fx.map((x, i) => ({ x, y: f.bt[i] })), borderColor: '#38bdf8', borderWidth: 1, pointRadius: 0, yAxisID: 'y' },
          { label: 'N (cm⁻³)', data: px.map((x, i) => ({ x, y: p.n[i] })), borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 2, yAxisID: 'y1' },
          { label: 'Averaging windows', data: [{ x: w.before[0], y: bmax }, { x: w.before[1], y: bmax }, { x: NaN, y: NaN },
            { x: w.after[0], y: bmax }, { x: w.after[1], y: bmax }], borderColor: '#10b981', borderWidth: 4, pointRadius: 0, spanGaps: false, yAxisID: 'y' },
        ] },
        options: { scales: { x: axis(`Minutes from ${r.shock_time} UTC`), y: axis('|B| (nT)'),
          y1: axis('N (cm⁻³)', { position: 'right', grid: { drawOnChartArea: false } }) } },
      });
      showDownload('ea-shock-download', url);
    } catch (e) {
      setStatus('ea-shock-status', e.message, true);
    }
  };

  window.eaRunTiming = async function () {
    const q = shockQuery();
    const ref = el('ea-shock-mission').value;
    q.set('reference', ref);
    q.set('targets', ['WIND', 'ACE', 'DSCOVR'].filter(s => s !== ref).join(','));
    const url = `/api/analysis/timing?${q}`;
    el('ea-timing-table').innerHTML = '<p class="text-slate-400">Fetching data for the other spacecraft...</p>';
    try {
      const body = await getJSON(url);
      const ref0 = body.reference;
      const rows = body.targets.map(t => t.status !== 'ok' ? [t.spacecraft, t.status, '', '', '', '', ''] : [
        t.spacecraft, t.predicted_time, t.observed_time || 'not found', fmt(t.predicted_delay_s, 0), fmt(t.observed_delay_s, 0),
        fmt(t.residual_s, 0), fmt(t.implied_speed_kms, 0)]);
      el('ea-timing-table').innerHTML =
        `<p class="text-slate-300 mb-1">Reference ${ref0.spacecraft} at ${ref0.shock_time} UTC, ${ref0.method} normal ${vec(ref0.normal_gse)}, ` +
        `V_sh ${fmt(ref0.shock_speed_kms, 0)} km/s. <a class="ea-link" href="${url}&download=true">Save JSON</a></p>` +
        table(['Spacecraft', 'Predicted (UTC)', 'Observed (UTC)', 'Predicted delay (s)', 'Observed delay (s)', 'Residual (s)', 'Implied V along n (km/s)'], rows) +
        `<p class="text-[10px] text-slate-500 mt-1">${body.note}</p>`;
    } catch (e) {
      el('ea-timing-table').innerHTML = `<p class="text-rose-400">${escapeHtml(e.message)}</p>`;
    }
  };

  // ---------------------------------------------------------------- MVA
  window.eaRunMva = async function () {
    const q = new URLSearchParams({ mission: el('ea-mva-mission').value, start: utc('ea-mva-start'),
      end: utc('ea-mva-end'), average_seconds: el('ea-mva-avg').value });
    const url = `/api/analysis/mva?${q}`;
    setStatus('ea-mva-status', 'Running...');
    try {
      const r = (await getJSON(url)).result;
      const ev = r.eigenvectors, l = r.eigenvalues_nT2, er = r.angular_error_deg;
      setStatus('ea-mva-status', `${r.n_vectors} vectors; λ2/λ3 = ${fmt(r.ratio_intermediate_to_min, 1)}, λ1/λ2 = ${fmt(r.ratio_max_to_intermediate, 1)}` +
        (r.ratio_intermediate_to_min !== null && r.ratio_intermediate_to_min < 10 ? ' (λ2/λ3 < 10: normal poorly determined)' : '') +
        `; <B>·n = ${fmt(r.mean_normal_field_nT)} ± ${fmt(r.mean_normal_field_error_nT)} nT (eq. 8.24).`);
      el('ea-mva-table').innerHTML = table(['Direction', 'Eigenvalue (nT²)', 'Eigenvector (GSE)', 'Angular error (°)'], [
        ['Maximum', fmt(l[0], 3), vec(ev.max), `${fmt(er.max_toward_intermediate, 2)} (toward intermediate)`],
        ['Intermediate', fmt(l[1], 3), vec(ev.intermediate), ''],
        ['Minimum (normal)', fmt(l[2], 3), vec(ev.min), `${fmt(er.normal_toward_max, 2)} / ${fmt(er.normal_toward_intermediate, 2)} (toward maximum / intermediate)`],
      ]) + (r.bootstrap ? `<p class="text-slate-400 mt-1">Bootstrap (${r.bootstrap.n_samples} resamples): normal ±${fmt(r.bootstrap.normal_toward_max_std_deg, 2)}° toward maximum, ±${fmt(r.bootstrap.normal_toward_intermediate_std_deg, 2)}° toward intermediate; ⟨B⟩·n ${fmt(r.bootstrap.mean_normal_field_nT)} ± ${fmt(r.bootstrap.mean_normal_field_std_nT)} nT.</p>` : '');
      showDownload('ea-mva-download', url);
    } catch (e) {
      setStatus('ea-mva-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- deHoffmann-Teller frame
  window.eaRunHt = async function () {
    const q = new URLSearchParams({ mission: el('ea-mva-mission').value, start: utc('ea-mva-start'), end: utc('ea-mva-end') });
    const url = `/api/analysis/ht?${q}`;
    setStatus('ea-ht-status', 'Running...');
    try {
      const r = (await getJSON(url)).result;
      setStatus('ea-ht-status', `${r.n_vectors} plasma samples; c(Ec, EHT) = ${fmt(r.correlation_ec_eht, 3)}, D(VHT)/D(0) = ${fmt(r.D.residual_ratio, 3)}` +
        (r.walen ? `; Walén slope ${fmt(r.walen.slope, 2)} (|slope| ≈ 1: rotational, ≈ 0: tangential discontinuity)` : '') + '.');
      const row = (name, e) => [name, vec(e.v_ht_kms, 1), e.error_axes.map(a => fmt(a.sigma_kms, 1)).join(' / '),
        `${fmt(e.normal_velocity_kms, 1)} ± ${fmt(e.normal_velocity_error_kms, 1)}`];
      el('ea-ht-table').innerHTML = table(['Estimate', 'VHT (GSE, km/s)', 'Error semiaxes (km/s)', 'un along MVA normal (km/s)'], [
        row('Minimum D (eq. 9.10)', r.D), row('Minimum Q (eq. 9.14)', r.Q),
        ...(r.bootstrap ? [row(`Bootstrap, ${r.bootstrap.n_samples} resamples`, r.bootstrap)] : [])]);
      showDownload('ea-mva-download', url);
    } catch (e) {
      setStatus('ea-ht-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- coupling functions
  window.eaRunCoupling = async function () {
    const q = new URLSearchParams({ mission: el('ea-cpl-mission').value, start: utc('ea-cpl-start'), end: utc('ea-cpl-end') });
    const url = `/api/analysis/coupling?${q}`;
    setStatus('ea-cpl-status', 'Running...');
    el('ea-cpl-table').innerHTML = '';
    try {
      const r = (await getJSON(url)).result;
      setStatus('ea-cpl-status', `${r.n_samples} plasma samples` +
        (r.uncertainties_available ? '; archive 1-σ speed and density errors propagated.' : '; this archive gives no per-sample uncertainties (measurement errors not shown).'));
      const names = { newell_dphi_dt: 'Newell dΦ/dt', akasofu_epsilon_gw: 'Akasofu ε (GW)', vbs_mv_m: 'V·Bs (mV/m)', dynamic_pressure_npa: 'P_dyn (nPa)' };
      const sig = v => (v === null || v === undefined ? '---' : Number(v).toPrecision(2));
      const rows = Object.entries(r.functions).map(([k, f]) => [names[k] || k, Number(f.mean).toPrecision(4),
        `± ${sig(f.measurement_sigma_of_mean)}`,
        f.sampling_ci95_of_mean ? `${Number(f.sampling_ci95_of_mean[0]).toPrecision(3)} to ${Number(f.sampling_ci95_of_mean[1]).toPrecision(3)}` : 'too few independent samples',
        fmt(f.n_eff, 1), f.median_relative_sigma === null ? '---' : `${fmt(100 * f.median_relative_sigma, 1)} %`]);
      el('ea-cpl-table').innerHTML = table(['Quantity', 'Mean', 'Measurement error', '95 % sampling interval', 'n_eff', 'Median per-sample error'], rows);
      showDownload('ea-cpl-download', url);
    } catch (e) {
      setStatus('ea-cpl-status', e.message, true);
    }
  };

  // ---------------------------------------------------------------- magnetic cloud search
  window.eaRunCloudSearch = async function () {
    const mission = el('ea-mcd-mission').value;
    const q = new URLSearchParams({ mission, start: utc('ea-mcd-start'), end: utc('ea-mcd-end'),
      criteria: el('ea-mcd-criteria').value });
    const url = `/api/analysis/mcdetect?${q}`;
    setStatus('ea-mcd-status', 'Fetching 1-min data and scanning (up to a minute for a month)...');
    try {
      const r = (await getJSON(url)).result;
      const yes = c => c ? 'pass' : '<span class="text-rose-400">fail</span>';
      setStatus('ea-mcd-status', `${r.accepted.length} of ${r.candidates.length} candidate regions pass all tests (${r.criteria} criteria). ${r.notes}`);
      el('ea-mcd-table').innerHTML = r.candidates.length ? table(
        ['Start (UTC)', 'End (UTC)', 'Hours', '<B> (nT)', '<βp>', '<VTh> (km/s)', 'ΔθB (°)', 'χM/<B>', 'Bz', 'Tests', ''],
        r.candidates.map((c, i) => [c.start, c.end, fmt(c.duration_hours, 1), fmt(c.mean_b_nt, 1), fmt(c.mean_beta, 2),
          fmt(c.mean_thermal_speed_kms, 1), fmt(c.theta_b_range_deg, 0), fmt(c.chi_m_over_b, 2), c.bz_sense,
          Object.entries(c.tests).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${yes(v)}`).join('<br>'),
          `<button class="ea-link" onclick="eaFitCandidate(${i})">Fit flux rope</button>`])) : '';
      window.eaCloudCandidates = { mission, list: r.candidates };
      showDownload('ea-mcd-download', url);
    } catch (e) {
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
    const q = new URLSearchParams({ mission: el('ea-mc-mission').value, start: utc('ea-mc-start'),
      end: utc('ea-mc-end'), average_minutes: el('ea-mc-avg').value });
    const url = `/api/analysis/fluxrope?${q}`;
    setStatus('ea-mc-status', 'Fitting (a few seconds)...');
    try {
      const r = (await getJSON(url)).result;
      setStatus('ea-mc-status', `${r.n_averages} averages of ${r.average_minutes} min, cloud speed ${fmt(r.speed_kms, 0)} km/s. ${r.conventions}`);
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
      const comp = ['Bx', 'By', 'Bz'], colors = ['#38bdf8', '#10b981', '#f43f5e'];
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
    const p = stormParams();
    const q = new URLSearchParams({ start_year: p.storm_start_year, end_year: p.storm_end_year,
      threshold_nt: p.storm_threshold_nt, separation_hours: p.storm_separation_hours, driver: p.storm_driver });
    if (p.storm_floor_nt !== undefined) q.set('floor_nt', p.storm_floor_nt);
    setStatus('ea-storm-status', 'Selecting storms from hourly Dst...');
    try {
      const r = (await getJSON(`/api/statistics/storms?${q}`)).result;
      const key = p.storm_epoch === 'minimum' ? 'minimum_time' : 'first_hour_below';
      const list = r.storms.map(st => st[key].replace(' ', 'T')).join('\n');
      el('ea-sea-onsets').value = list;
      stormSelection = r.storms.length ? { params: p, text: list } : null;
      setStatus('ea-storm-status', `${r.storms.length} storms (${r.log.map(l => `${l.filter}: ${l.storms_remaining}`).join('; ')}).` +
        (r.storms.length > 60 ? ' The analysis takes at most 60: narrow the selection.' : ''), r.storms.length > 60);
      el('ea-storm-table').innerHTML = r.storms.length ? table(['Dst minimum (UTC)', 'Dst (nT)', 'Below threshold from', 'Bz 6 h before (nT)', 'V (km/s)', 'Plasma type'],
        r.storms.map(st => [st.minimum_time, fmt(st.minimum_dst_nt, 0), st.first_hour_below, fmt(st.driver_bz_gsm_nt, 1),
          fmt(st.driver_speed_kms, 0), st.driver_type ? st.driver_type.replace('_', ' ') : '---'])) : '';
    } catch (e) {
      setStatus('ea-storm-status', e.message, true);
    }
  };

  window.eaScoreDstModels = async function () {
    const p = stormParams();
    const q = new URLSearchParams({ start_year: p.storm_start_year, end_year: p.storm_end_year,
      threshold_nt: p.storm_threshold_nt, separation_hours: p.storm_separation_hours, driver: p.storm_driver });
    if (p.storm_floor_nt !== undefined) q.set('floor_nt', p.storm_floor_nt);
    const url = `/api/statistics/dst_models?${q}`;
    setStatus('ea-skill-status', 'Running both models over every hour of the years...');
    el('ea-skill-table').innerHTML = '';
    try {
      const r = (await getJSON(url)).result;
      const cell = (m, k, d) => (m[k].mean === null ? '---' : `${fmt(m[k].mean, d)}${m[k].ci95 ? ` (${fmt(m[k].ci95[0], d)} to ${fmt(m[k].ci95[1], d)})` : ''}`);
      el('ea-skill-table').innerHTML = table(['Model', 'Storms', 'Mean r (95 %)', 'Mean RMSE nT (95 %)', 'Mean bias nT (95 %)', 'Minimum error nT (95 %)'],
        Object.values(r.models).map(m => [m.name, m.n_storms, cell(m, 'r', 2), cell(m, 'rmse_nt', 1), cell(m, 'bias_nt', 1), cell(m, 'minimum_error_nt', 1)]));
      setStatus('ea-skill-status', `Scored against hourly Dst in each storm window (highest Dst in the 24 h before the minimum to recovery above -50 nT, after Ji et al. 2012); bias and minimum error are model minus observed. Intervals treat the storms as independent.`);
    } catch (e) {
      setStatus('ea-skill-status', e.message, true);
    }
  };

  window.eaRunSea = async function () {
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
      seaResult = (await getJSON(url)).result;
      const sel = el('ea-sea-show');
      sel.innerHTML = seaResult.parameters.map(p => `<option value="${p}">${p}</option>`).join('');
      setStatus('ea-sea-status', `${seaResult.n_events} events, ${seaResult.cadence_minutes}-min bins.`);
      const p0 = seaResult.parameters[0];
      el('ea-sea-table').innerHTML = table(['Onset (UTC)', 'Records'].concat(seaResult.parameters.map(p => `${p} min (epoch h)`)),
        seaResult.events.map(e => [e.onset, e.n_records].concat(seaResult.parameters.map(p => e[p] ? `${fmt(e[p].min, 1)} (${fmt(e[p].min_epoch_hours, 2)})` : '---'))));
      const csv = el('ea-sea-csv');
      csv.href = url + '&format=csv';
      csv.classList.remove('hidden');
      showDownload('ea-sea-download', url);
      sel.value = p0;
      window.eaDrawSea();
    } catch (e) {
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
        { label: 'Upper quartile', data: pts(st.q75), borderColor: 'rgba(56,189,248,0.4)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(56,189,248,0.12)' },
        { label: 'Lower quartile', data: pts(st.q25), borderColor: 'rgba(56,189,248,0.4)', borderWidth: 1, pointRadius: 0 },
        { label: 'Median', data: pts(st.median), borderColor: '#38bdf8', borderWidth: 2, pointRadius: 0 },
        { label: 'Mean', data: pts(st.mean), borderColor: '#f59e0b', borderWidth: 1.5, borderDash: [4, 3], pointRadius: 0 },
        ...(st.mean_ci95_low ? [
          { label: 'Mean 95 % CI (bootstrap)', data: pts(st.mean_ci95_high), borderColor: 'rgba(245,158,11,0.5)', borderWidth: 1, pointRadius: 0, fill: '+1', backgroundColor: 'rgba(245,158,11,0.10)' },
          { label: 'Mean 95 % CI low', data: pts(st.mean_ci95_low), borderColor: 'rgba(245,158,11,0.5)', borderWidth: 1, pointRadius: 0 },
        ] : []),
      ] },
      options: { scales: { x: axis('Epoch time (hours from onset)'), y: axis(p) } },
    });
  };
})();
