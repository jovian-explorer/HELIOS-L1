"""
Checks of small pure functions in the dashboard JavaScript, run with Node.js when it
is installed (skipped otherwise).
"""
import json
import math
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import helios

# Resolve through the package so the test also works when CI runs it against the installed wheel.
APP_JS = Path(helios.__file__).resolve().parent / "gui" / "static" / "js" / "app.js"
NODE = shutil.which("node")


def _extract(name: str) -> str:
    src = APP_JS.read_text(encoding="utf-8")
    m = re.search(rf"^function {name}\(.*?^}}", src, re.S | re.M)
    assert m, f"{name} not found in app.js"
    return m.group(0)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_timestamp_labels_convert_utc_to_selected_zone():
    """Server stamps 'YYYY-MM-DD HH:MM:SS' are UTC; 18:40 UTC is 00:10 next day in IST (+05:30)."""
    script = _extract("formatTimestampToTimezone") + """
let selectedTimezone = 'Asia/Kolkata';
const out = [formatTimestampToTimezone('2026-10-02 18:40:00'),
             formatTimestampToTimezone('2026-10-02T18:40:00Z')];
selectedTimezone = 'UTC';
out.push(formatTimestampToTimezone('2026-10-02 18:40:00'));
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["10-03 00:10", "10-03 00:10", "10-02 18:40"]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_comparator_warns_when_a_side_is_not_measured():
    script = _extract("comparisonProvenanceWarning") + """
const obs = {kind: 'observed'}, sim = {kind: 'simulated'}, syn = {kind: 'synthetic'};
console.log(JSON.stringify([
  comparisonProvenanceWarning({provenance_a: obs, provenance_b: obs}, 'DSCOVR', 'ACE'),
  comparisonProvenanceWarning({provenance_a: obs, provenance_b: sim}, 'DSCOVR', 'WIND'),
  comparisonProvenanceWarning({provenance_a: syn, provenance_b: {kind: 'imported'}}, 'DSCOVR', 'File'),
]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    none, sim, syn = json.loads(res.stdout)
    assert none == ""
    assert "Spacecraft B (WIND) is SIMULATED" in sim and "not a comparison of two instruments" in sim
    assert "Spacecraft A (DSCOVR) is SYNTHETIC" in syn and "Spacecraft B" not in syn


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_orbit_boundary_models_match_python():
    """orbits.js boundary formulas give the same numbers as helios.core.science."""
    from helios.core.science import SpaceWeatherPhysics as S
    src = (APP_JS.parent / "orbits.js").read_text(encoding="utf-8")
    head = src[:src.index("class OrbitRenderer {")]
    script = head + """
const out = [];
for (const [p, bz, m, b] of [[2.42, -0.35, 5.77, 3.02], [2.0, 3.0, 8.0, 1.0], [30.0, -20.0, 3.0, 0.4]]) {
  const mp = shue1998Magnetopause(p, bz), bs = chaoBowShock(p, bz, m, b);
  out.push([mp.r0, mp.alpha, bs.r0, bs.alpha, farrisRussellBowShock(mp.r0, m).r0, shue1997Standoff(p, bz)]);
}
const mb = solarWindMachBeta({speed: 450, density: 5, temperature: 1e5, bt: 5});
out.push([mb.mms, mb.beta]);
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    rows = json.loads(res.stdout)
    for row, (p, bz, m, b) in zip(rows, [(2.42, -0.35, 5.77, 3.02), (2.0, 3.0, 8.0, 1.0), (30.0, -20.0, 3.0, 0.4)]):
        r0, alpha = S.shue1998_magnetopause(p, bz)
        bs = S.chao_bow_shock(p, bz, mach_number=m, plasma_beta=b)
        assert row[0] == pytest.approx(r0, abs=1e-9) and row[1] == pytest.approx(alpha, abs=1e-9)
        assert row[2] == pytest.approx(bs["standoff_r0_re"], abs=0.006)
        assert row[3] == pytest.approx(bs["flaring_alpha"], abs=6e-4)
        assert row[4] == pytest.approx(S.farris_russell_bow_shock(r0, m)["standoff_r0_re"], abs=0.006)
        assert row[5] == pytest.approx(S.shue1997_standoff(p, bz), abs=1e-9)
    mms, beta = rows[3]
    assert beta == pytest.approx(S.plasma_beta(5, 1e5, 5), abs=1e-9)
    # OMNI: V_A = 20 * 5 / sqrt(5) = 44.72, C_s = 0.12 sqrt(2.28e5) = 57.30 -> M_ms = 450 / 72.69
    assert mms == pytest.approx(450 / math.hypot(44.7214, 57.2992), abs=1e-3)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_aurora_map_label_uses_the_server_boundary():
    """The map overlay computed its own equatorward boundary (68 - 1.8 Kp), disagreeing with the card."""
    src = (APP_JS.parent / "aurora.js").read_text(encoding="utf-8")
    assert "68 - this.kpIndex * 1.8" not in src
    assert "this.eqMidnightLat" in src
    assert "b.equatorward_midnight_lat" in APP_JS.read_text(encoding="utf-8")


def test_drap_power_loss_text_is_computed():
    src = APP_JS.read_text(encoding="utf-8")
    html = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    assert "79.1% Signal Power Loss" not in html and 'id="drap-att10-loss"' in html
    assert "Math.pow(10, -drap.attenuation_at_10mhz_db / 10)" in src


def test_comparator_scatter_uses_numeric_axes():
    src = APP_JS.read_text(encoding="utf-8")
    body = src[src.index("function renderCompScatterChart") if "function renderCompScatterChart" in src else src.index("chart-comp-scatter"):]
    body = body[:body.index("function renderCompResidualChart")]
    assert "type: 'linear', position: 'bottom'" in body


def test_psd_plot_frequency_axis_is_logarithmic():
    src = APP_JS.read_text(encoding="utf-8")
    block = src[src.index("chartSpectrum = new Chart"):]
    block = block[:block.index("async function initOrbits")]
    assert block.count("type: 'logarithmic'") == 2 and "labels:" not in block
