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


def test_regime_filter_thresholds_match_labels():
    src = APP_JS.read_text(encoding="utf-8")
    assert "r.speed > 500" in src and "r.density > 10" in src
    assert "r.speed >= 480" not in src and "r.density >= 8" not in src


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_api_error_text_reads_validation_errors():
    """FastAPI parameter errors are lists; they reached the user as '[object Object]'."""
    script = _extract("apiErrorText") + """
console.log(JSON.stringify([
  apiErrorText({detail: 'Unknown theme'}, {status: 422}),
  apiErrorText({detail: [{loc: ['query', 'kp'], msg: 'Input should be less than or equal to 9'}]}, {status: 422}),
  apiErrorText({}, {status: 500}),
]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["Unknown theme", "kp: Input should be less than or equal to 9", "Request failed (HTTP 500)"]


def _orbits_models() -> str:
    """Top-level boundary functions of orbits.js (everything before the renderer class)."""
    src = (APP_JS.parent / "orbits.js").read_text(encoding="utf-8")
    return src[:src.index("class OrbitRenderer")]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
@pytest.mark.parametrize("p", [
    {"vsw": 450.0, "density": 5.0, "bt": 6.0, "bz": -4.0, "by": 2.0, "temp": 100000.0},
    {"vsw": 380.0, "density": 4.5, "bt": 5.0, "bz": 2.5, "by": 1.0, "temp": 80000.0},
    {"vsw": 980.0, "density": 45.0, "bt": 42.0, "bz": -28.0, "by": 16.0, "temp": 450000.0},
    {"vsw": 750.0, "density": 2.0, "bt": 3.0, "bz": -2.0, "by": 1.0, "temp": 40000.0},
])
def test_sandbox_calculator_matches_python_physics(p):
    """
    The in-browser physics calculator (app.js computeSandboxPhysics with the orbits.js
    boundary models) and helios/core/science.py implement the same equations twice; the
    numbers must agree. Before, the sandbox fed the proton-only Mach number to the bow
    shock models while the orbit view (and the panel text) used the OMNI definition.
    """
    from helios.core.science import SpaceWeatherPhysics as S
    script = _orbits_models() + _extract("computeSandboxPhysics") + \
        f"\nconsole.log(JSON.stringify(computeSandboxPhysics({json.dumps(p)})));"
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    js = json.loads(res.stdout)

    v, n, b, bz, by, t = p["vsw"], p["density"], p["bt"], p["bz"], p["by"], p["temp"]
    pdyn = S.dynamic_pressure(n, v)
    mach = S.mach_numbers(v, b, n, t)
    beta = S.plasma_beta(n, t, b)
    mms_omni = S.omni_magnetosonic_mach(v, b, n, t)
    mp_r0, mp_alpha = S.shue1998_magnetopause(pdyn, bz)
    bs = S.chao_bow_shock(pdyn, bz, mach_number=mms_omni, plasma_beta=beta)
    fr = S.farris_russell_bow_shock(mp_r0, mms_omni)
    expected = {
        "pdyn": (pdyn, 1e-9), "va": (mach["alfven_speed_kms"], 0.06), "cs": (mach["sound_speed_kms"], 0.06),
        "ma": (mach["alfven_mach"], 0.006), "mms": (mach["magnetosonic_mach"], 0.006),
        "beta": (beta, 1e-9), "mms_omni": (mms_omni, 1e-9),
        "mp_r0": (mp_r0, 1e-9), "mp_alpha": (mp_alpha, 1e-9),
        "bs_r0": (bs["standoff_r0_re"], 0.006), "bs_alpha": (bs["flaring_alpha"], 0.0006),
        "shue97_r0": (S.shue1997_standoff(pdyn, bz), 1e-9), "fr_bs_r0": (fr["standoff_r0_re"], 0.006),
        "akasofu_gw": (S.akasofu_epsilon(v, b, by, bz), 1e-6),
        "dphi": (S.newell_coupling(v, by, bz), 1e-6),
        "phi_pc": (S.polar_cap_potential(v, by, bz, b_total_nt=b)["polar_cap_potential_kv"], 0.06),
        "ae": (S.auroral_electrojet_ae(v, by, bz)["ae_index_nt"], 0.06),
        "ey": (S.convective_electric_field(v, bz), 0.006),
    }
    for key, (want, tol) in expected.items():
        assert js[key] == pytest.approx(want, abs=tol, rel=1e-9), key


def test_js_constants_match_python_models():
    """Parker spiral rotation rate and the DBM L1 distance/drag default are the same in JS and Python."""
    from helios.core.parker_spiral import ParkerSpiralModel
    from helios.core.coronagraph import CoronagraphAnalyzer
    parker = (APP_JS.parent / "parker.js").read_text(encoding="utf-8")
    cme = (APP_JS.parent / "cme_sim.js").read_text(encoding="utf-8")
    omega = float(re.search(r"this\.omegaSun = ([\d.e+-]+);", parker).group(1))
    assert omega == ParkerSpiralModel.OMEGA_SUN_RAD_S
    l1 = re.search(r"this\.l1Km = ([\d.]+) - ([\d.]+);", cme)
    assert float(l1.group(1)) - float(l1.group(2)) == pytest.approx(CoronagraphAnalyzer.L1_DIST_KM)
    gamma = float(re.search(r"this\.gamma = ([\d.e+-]+);", cme).group(1))
    assert gamma == 1.0e-7  # calculate_cme_kinematics default


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_mission_cards_escape_the_imported_mission_name():
    """
    The custom mission's name (an imported file's name, or the import form) went into the
    mission directory's HTML unescaped: a file named '<img src=x onerror=...>.csv' (a valid
    name on macOS and Linux) ran script in the application's own origin.
    """
    src = APP_JS.read_text(encoding="utf-8")
    assert "missions.map(escapeHtmlDeep).map(m =>" in src
    script = _extract("escapeHtml") + _extract("escapeHtmlDeep") + """
const m = escapeHtmlDeep({name: '<img src=x onerror="alert(1)">', status: "a'b", n: 3,
                          instruments: [{name: '<b>'}]});
console.log(JSON.stringify(m));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout)
    assert out["name"] == "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;"
    assert out["status"] == "a&#39;b" and out["n"] == 3 and out["instruments"][0]["name"] == "&lt;b&gt;"


def test_dialogs_are_not_nested_in_other_dialogs():
    """
    A missing </div> in the incident log dialog put the settings, about and time zone dialogs
    inside it: opening them showed nothing (zero size inside a hidden parent).
    Every top-level dialog must be a direct child of <body>.
    """
    from html.parser import HTMLParser
    from pathlib import Path
    html = (Path(__file__).parent.parent / "helios" / "gui" / "static" / "index.html").read_text(encoding="utf-8")
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    class P(HTMLParser):
        def __init__(self):
            super().__init__()
            self.stack, self.parents = [], {}

        def handle_starttag(self, tag, attrs):
            if tag in void:
                return
            el_id = dict(attrs).get("id")
            if el_id:
                self.parents[el_id] = [i for _, i in self.stack]
            self.stack.append((tag, el_id))

        def handle_endtag(self, tag):
            if tag in void:
                return
            while self.stack:
                t, _ = self.stack.pop()
                if t == tag:
                    break

    p = P()
    p.feed(html)
    for dialog in ("bulletin-modal", "modal-references", "modal-shortcuts", "modal-incidents",
                   "modal-settings", "modal-about", "modal-timezone", "modal-review"):
        ancestors = [i for i in p.parents[dialog] if i]
        assert ancestors == [], f"{dialog} is inside {ancestors}"


def test_tailwind_css_is_built_and_current():
    """
    The page used the in-browser Tailwind script (Play CDN), which warns that it is not for
    production on every load. The utilities are now built at development time into
    css/tailwind.css (scripts/build_css.py); it must match the page and scripts it was built from.
    """
    import importlib.util
    from pathlib import Path
    root = Path(__file__).parent.parent
    static = root / "helios" / "gui" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    assert "tailwind.min.js" not in html and "cdn.tailwindcss.com" not in html and "tailwind.config" not in html
    assert '<link rel="stylesheet" href="/static/css/tailwind.css">' in html
    assert html.index("/static/css/style.css") < html.index("/static/css/tailwind.css")
    spec = importlib.util.spec_from_file_location("build_css", root / "scripts" / "build_css.py")
    build_css = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build_css)
    scanned = {p.name for p in build_css.content_files()}
    ours = {p.name for p in (static / "js").glob("*.js") if p.name != "chart.min.js"}
    assert scanned == ours | {"index.html"}, "every script must be in packaging/tailwind.config.js"
    css = (static / "css" / "tailwind.css").read_text(encoding="utf-8")
    assert "tailwindcss v3.4.17 | MIT License" in css
    assert f"inputs-sha256: {build_css.inputs_digest()}" in css, \
        "css/tailwind.css is out of date: run python scripts/build_css.py"
    for cls in (".bg-space-950", ".border-amber-900\/40", ".gap-x-2", ".space-x-3\.5"):
        assert cls in css
