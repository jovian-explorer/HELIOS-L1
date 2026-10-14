/**
 * HELIOS-L1: FLEET-WIDE CROSS-CALIBRATION CORRELATION MATRIX ENGINE
 * Renders an interactive NxN heatmap of mutual Pearson correlation coefficients (r)
 * across DSCOVR, ACE, ADITYA-L1, WIND, and SOHO.
 */

async function loadFleetMatrix() {
  const current = latestRequest('loadFleetMatrix');
  const paramSelect = document.getElementById('comp-param');
  const param = paramSelect ? paramSelect.value : 'bz_gsm';

  const container = document.getElementById('fleet-matrix-container');
  if (!container) return;

  container.innerHTML = `
    <div class="p-6 text-center text-slate-400 font-mono text-xs flex items-center justify-center space-x-2">
      <i class="fa-solid fa-spinner fa-spin text-sky-400"></i>
      <span>Computing mutual fleet-wide cross-correlations...</span>
    </div>
  `;

  try {
    const res = await fetch(`/api/compare/matrix?parameter=${param}`);
    const data = await res.json().catch(() => ({}));
    if (!current()) return;
    if (!res.ok) throw new Error(apiErrorText(data, res));

    const missions = data.missions;
    const matrix = data.matrix_r;
    // Missions without measured data in the window are the operational stream with offsets and
    // noise; their high r with DSCOVR says nothing about the instruments, so mark them.
    const prov = data.provenance || {};
    const notMeasured = m => prov[m] && prov[m] !== 'observed';
    const kindTag = m => notMeasured(m)
      ? `<span class="ml-1 text-[9px] px-1 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30" title="${escapeHtml(prov[m])}: not a measurement">${escapeHtml(String(prov[m]).toUpperCase())}</span>`
      : '';

    let html = `
      <div class="overflow-x-auto">
        <table class="w-full text-xs font-mono border-collapse">
          <thead>
            <tr>
              <th class="p-2.5 text-left text-slate-400 border-b border-slate-800 font-tech">SPACECRAFT</th>
              ${missions.map(m => `
                <th class="p-2.5 text-center text-sky-400 border-b border-slate-800 font-bold">${m}${kindTag(m)}</th>
              `).join('')}
            </tr>
          </thead>
          <tbody>
    `;

    missions.forEach((mRow, i) => {
      html += `
        <tr class="hover:bg-space-900/50 transition">
          <td class="p-2.5 font-bold text-slate-300 border-b border-slate-800/60 flex items-center space-x-1.5">
            <span class="w-1.5 h-1.5 rounded-full bg-sky-400"></span>
            <span>${mRow}</span>${kindTag(mRow)}
          </td>
      `;

      missions.forEach((mCol, j) => {
        const r = matrix[i][j];
        const isDiag = i === j;
        const sim = !isDiag && (notMeasured(mRow) || notMeasured(mCol));

        let bgStyle = '';
        let textColor = '';

        if (isDiag || r === null || r === undefined) {  // no common data: n/a, not r = 0
          bgStyle = 'background: rgba(15, 23, 42, 0.6);';
          textColor = 'text-slate-500';
        } else if (r >= 0.85) {
          bgStyle = 'background: rgba(0, 240, 255, 0.18); border: 1px solid rgba(0, 240, 255, 0.3);';
          textColor = 'text-cyan-300 font-bold';
        } else if (r >= 0.70) {
          bgStyle = 'background: rgba(16, 185, 129, 0.16); border: 1px solid rgba(16, 185, 129, 0.25);';
          textColor = 'text-emerald-300 font-bold';
        } else if (r >= 0.40) {
          bgStyle = 'background: rgba(251, 191, 36, 0.14); border: 1px solid rgba(251, 191, 36, 0.2);';
          textColor = 'text-amber-300 font-semibold';
        } else {
          bgStyle = 'background: rgba(244, 63, 94, 0.12); border: 1px solid rgba(244, 63, 94, 0.2);';
          textColor = 'text-rose-300 font-semibold';
        }

        html += `
          <td class="p-2 text-center border-b border-slate-800/60">
            <div 
              onclick="selectMatrixPair('${mRow}', '${mCol}')" 
              style="${bgStyle}" 
              class="rounded-lg py-1.5 px-2.5 cursor-pointer hover:scale-105 transition shadow-sm ${textColor} ${sim ? 'opacity-50 italic' : ''}"
              title="${isDiag ? 'Self-correlation' : `${sim ? 'One side is not measured (simulated or synthetic), so r says nothing about the instruments. ' : ''}Click to cross-correlate ${mRow} vs ${mCol}`}"
            >
              ${r === null || r === undefined ? 'n/a' : r.toFixed(3)}
            </div>
          </td>
        `;
      });

      html += `</tr>`;
    });

    html += `
          </tbody>
        </table>
      </div>
    `;
    const simulated = missions.filter(notMeasured);
    if (simulated.length) {
      html += `<p class="text-[11px] text-amber-300/90 mt-2 px-2">${simulated.map(escapeHtml).join(', ')}: no measured data in this window. Their values are the operational L1 stream with fixed offsets and noise (or the offline model), so their correlations (faded) are not instrument comparisons.</p>`;
    }

    container.innerHTML = html;

  } catch (err) {
    if (!current()) return;
    container.innerHTML = `<div class="text-rose-400 text-xs p-4">Error loading fleet matrix: ${escapeHtml(err.message)}</div>`;
  }
}

function selectMatrixPair(satA, satB) {
  if (satA === satB) return;
  const selA = document.getElementById('comp-sat-a');
  const selB = document.getElementById('comp-sat-b');
  if (selA) selA.value = satA;
  if (selB) selB.value = satB;

  window.playRadarPing?.();
  if (typeof runComparison === 'function') {
    runComparison();
  }
}

window.loadFleetMatrix = loadFleetMatrix;
window.selectMatrixPair = selectMatrixPair;
