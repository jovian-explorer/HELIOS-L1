/**
 * HELIOS-L1: FLEET-WIDE CROSS-CALIBRATION CORRELATION MATRIX ENGINE
 * Renders an interactive NxN heatmap of mutual Pearson correlation coefficients (r)
 * across DSCOVR, ACE, ADITYA-L1, WIND, and SOHO.
 */

async function loadFleetMatrix() {
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
    if (!res.ok) throw new Error('Matrix API failed');
    const data = await res.json();

    const missions = data.missions;
    const matrix = data.matrix_r;

    let html = `
      <div class="overflow-x-auto">
        <table class="w-full text-xs font-mono border-collapse">
          <thead>
            <tr>
              <th class="p-2.5 text-left text-slate-400 border-b border-slate-800 font-tech">SPACECRAFT</th>
              ${missions.map(m => `
                <th class="p-2.5 text-center text-sky-400 border-b border-slate-800 font-bold">${m}</th>
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
            <span>${mRow}</span>
          </td>
      `;

      missions.forEach((mCol, j) => {
        const r = matrix[i][j];
        const isDiag = i === j;

        let bgStyle = '';
        let textColor = '';

        if (isDiag) {
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
              class="rounded-lg py-1.5 px-2.5 cursor-pointer hover:scale-105 transition shadow-sm ${textColor}"
              title="${isDiag ? 'Self-correlation' : `Click to cross-correlate ${mRow} vs ${mCol}`}"
            >
              ${isDiag ? '1.000' : r.toFixed(3)}
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

    container.innerHTML = html;

  } catch (err) {
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
