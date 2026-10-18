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
out.push(formatTimestampToTimezone('2026-10-02 18:40:00'), formatTimestampToTimezone('2026-10-02T18:40:00'));
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == ["10-03 00:10", "10-03 00:10", "10-02 18:40", "10-02 18:40"]
    # No chart slices UTC stamps itself: they all go through the zone formatter.
    assert not re.search(r"time(_tag)?\.slice\(11, ?16\)", APP_JS.read_text(encoding="utf-8"))


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
        "phi_pc": (S.polar_cap_potential(v, by, bz, n)["polar_cap_potential_kv"], 0.06),
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
    period_days = float(re.search(r"this\.omegaSun = 2 \* Math\.PI / \(([\d.]+) \* 86400\);", parker).group(1))
    assert 2 * math.pi / (period_days * 86400) == pytest.approx(ParkerSpiralModel.OMEGA_SUN_RAD_S, rel=1e-12)
    from helios.core.constants import R_SUN_KM
    for js in ("parker.js", "cme_sim.js"):
        r = float(re.search(r"this\.rSunKm = ([\d.]+);", (APP_JS.parent / js).read_text(encoding="utf-8")).group(1))
        assert r == R_SUN_KM  # one solar radius everywhere (IAU 2015 nominal)
    l1 = re.search(r"this\.l1Km = ([\d.]+) - ([\d.]+);", cme)
    assert float(l1.group(1)) - float(l1.group(2)) == pytest.approx(CoronagraphAnalyzer.L1_DIST_KM)
    gamma = float(re.search(r"this\.gamma = ([\d.e+-]+);", cme).group(1))
    from helios.core.coronagraph import DBM_GAMMA_PER_KM, DBM_W_KMS
    assert gamma == DBM_GAMMA_PER_KM  # calculate_cme_kinematics default
    assert float(re.search(r"this\.vAmbient = ([\d.]+);", cme).group(1)) == DBM_W_KMS


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
    html = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
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
    from conftest import source_root
    root = source_root()
    static = APP_JS.parent.parent
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


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_coverage_text_counts_gaps_and_never_shows_100_percent_with_a_gap():
    script = _extract("coverageText") + """
console.log(JSON.stringify([
  coverageText('field', {covered_fraction: 0.9998, gaps: 1, longest_gap: {minutes: 10, start: '1997-11-03 00:50:00'}}),
  coverageText('magnetic field', {covered_fraction: 0.566, gaps: 2, longest_gap: {minutes: 1874, start: '2019-06-27 16:46:00'}}),
  coverageText('plasma', {covered_fraction: 0.839, gaps: 236, longest_gap: {minutes: 283, start: '1997-11-06 21:48:00'}}),
  coverageText('plasma', {covered_fraction: 1.0, gaps: 0, longest_gap: null}),
]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [
        "field > 99.9 % (1 gap, longest 10 min from 1997-11-03 00:50:00)",
        "magnetic field 56.6 % (2 gaps, longest 1.3 days from 2019-06-27 16:46:00)",
        "plasma 83.9 % (236 gaps, longest 4.7 h from 1997-11-06 21:48:00)",
        "plasma 100.0 %",
    ]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_omni_years_note_names_years_left_out_or_not_refreshed():
    # The storm finder and the Dst model skill said nothing when a year could not be read:
    # with CDAWeb failing for 1996, 1996-2006 at -100 nT gave 89 storms instead of 90, unmarked.
    script = _extract("omniYearsNote") + """
console.log(JSON.stringify([
  omniYearsNote({years_without_data: [], years_not_refreshed: []}),
  omniYearsNote({years_without_data: [1996], years_not_refreshed: [1996]}),
  omniYearsNote({years_without_data: [2026], years_not_refreshed: [2003, 2004]}),
  omniYearsNote(undefined),
]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [
        "",
        "; CDAWeb could not be reached for 1996 and nothing is cached: left out",
        "; no OMNI data for 2026; CDAWeb not reached, cached data used for 2003, 2004",
        "",
    ]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_cme_animation_reaches_l1_at_the_server_transit_time():
    """The animation started at 1 R_sun while the server's transit times start at the second height."""
    from helios.core.coronagraph import CoronagraphAnalyzer
    cme = CoronagraphAnalyzer.calculate_cme_kinematics(5.0, 20.0, 180.0, launch_time_iso="2024-05-09T09:24")
    src = (APP_JS.parent / "cme_sim.js").read_text(encoding="utf-8")
    script = "const window = {}; const document = {getElementById: () => null};\n" + src + f"""
const s = Object.create(CMESimulator.prototype);
Object.assign(s, {{rSunKm: 695700, r0Km: 695700, l1Km: 149597870.7 - 1496000.0, earthKm: 149597870.7, v0: 1000,
                  vAmbient: 420, gamma: 1e-7}});
s.updateFromBackendResult({json.dumps(cme)});
console.log(JSON.stringify([s.getShockAtTime(s.transitL1Hrs).rKm, s.l1Km]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    r, l1 = json.loads(res.stdout)
    assert r == pytest.approx(l1, rel=0.002)  # transit hours are rounded to 0.1 h


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_parker_view_places_psp_and_solo_at_their_angle_from_earth():
    """PSP and SolO were drawn at true anomaly + a fixed made-up perihelion direction."""
    from helios.core.spice_engine import get_spice_engine
    eng = get_spice_engine()
    fleet = {k: eng.get_spacecraft_state(k, epoch_utc="2026-10-10T00:00:00")
             for k in ("PARKER_SOLAR_PROBE", "SOLAR_ORBITER", "EARTH")}
    src = (APP_JS.parent / "parker.js").read_text(encoding="utf-8")
    script = "const window = {}; const document = {getElementById: () => null};\n" + src + f"""
const p = Object.create(ParkerSpiralRenderer.prototype);
Object.assign(p, {{auKm: 149597870.7, rSunKm: 695700, manualAnomalyDeg: null, pspOrbitSpeedMultiplier: 0.00075,
                  time: 0, spiceFleetData: {json.dumps(fleet)}}});
console.log(JSON.stringify([p.getPSPState().theta, p.getSolOState().theta]));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)  # too long for -e
    assert res.returncode == 0, res.stderr
    earth = fleet["EARTH"]["heliocentric"]["ecliptic_longitude_deg"]
    for theta, key in zip(json.loads(res.stdout), ("PARKER_SOLAR_PROBE", "SOLAR_ORBITER")):
        want = fleet[key]["heliocentric"]["ecliptic_longitude_deg"] - earth
        assert (math.degrees(theta) - want + 180) % 360 - 180 == pytest.approx(0, abs=1e-6)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_orbit_view_marks_missing_inputs_as_assumed():
    """A missing Mach number kept the previous preset (e.g. 4.2) and was shown as measured."""
    src = (APP_JS.parent / "orbits.js").read_text(encoding="utf-8")
    script = "const window = {}; const document = {getElementById: () => null};\n" + src + """
const o = Object.create(OrbitRenderer.prototype);
o.setSolarWindConditions(920, 32.0, -28.0, 4.2, 0.3);
o.setSolarWindConditions(450, 2.0, -3.0, null, undefined);
console.log(JSON.stringify([o.machNumber, o.plasmaBeta, o.assumedMark('machNumber'), o.assumedMark('bz')]));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [8.0, 2.0, " (assumed)", ""]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_predicted_arrival_marker_position_on_a_time_series():
    script = _extract("arrivalTimeMs") + "\n" + _extract("arrivalIndex") + """
const tags = ['2017-09-13 07:00:00', '2017-09-13 07:05:00', '2017-09-13 07:10:00'];
console.log(JSON.stringify([arrivalIndex(tags, arrivalTimeMs('2017-09-13 07:07:30 UTC')),
                            arrivalIndex(tags, arrivalTimeMs('2017-09-14 00:00:00')), arrivalIndex(tags, arrivalTimeMs('2017-09-13 07:00:00'))]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [1.5, None, 0]


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_aurora_map_subsolar_point_has_the_equation_of_time():
    """3 November 12:00 UT: the Sun is over about 4.1 deg W (equation of time +16.4 min), declination about -15.05 deg (Spencer series good to about 0.2 deg)."""
    src = (APP_JS.parent / "aurora.js").read_text(encoding="utf-8")
    script = "const window = {}; const document = {getElementById: () => null};\n" + src + """
const a = Object.create(AuroralMapRenderer.prototype);
a.mapTime = new Date(Date.UTC(2026, 10, 3, 12, 0, 0));
a.magPoleNorth = { lat: 80.8, lon: -72.8 };
const s = a.getSubsolarPoint();
console.log(JSON.stringify([s.lon, s.lat, a.getDipoleLatitude(-72.8, 80.8)]));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    lon, lat, pole = json.loads(res.stdout)
    assert lon == pytest.approx(-4.1, abs=0.15) and lat == pytest.approx(-15.05, abs=0.3) and pole == pytest.approx(90.0)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_aurora_map_outlook_for_the_users_place():
    src = (APP_JS.parent / "aurora.js").read_text(encoding="utf-8")
    script = "const window = {}; const document = {getElementById: () => null};\n" + src + """
const a = Object.create(AuroralMapRenderer.prototype);
a.mapTime = new Date(Date.UTC(2026, 0, 15, 22, 0, 0));
a.magPoleNorth = { lat: 80.8, lon: -72.8 };
a.ovalBoundaries = { north: { equatorward: Array.from({length: 73}, (_, i) => ({ lon: -180 + 5 * i, lat: 60 })) } };
const out = [];
for (const [lat, lon] of [[70, 19], [55, 19], [35, 19], [-45, 170]]) { a.home = { lat, lon }; out.push(a.homeOutlook()); }
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    inside, near, far, south = json.loads(res.stdout)
    assert "overhead" in inside["oval"] and inside["sky"] == "dark night"
    assert "low on the northern horizon" in near["oval"]
    assert "unlikely" in far["oval"]
    assert south["oval"] == "the oval is not loaded yet" and south["sky"].startswith("daylight")


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_aurora_outlook_with_ovation_uses_the_distance_to_the_aurora():
    # Reproduction: below 10 % every place read "may still be seen low on the horizon" (London
    # with the aurora at 65-75 N included).
    src = (APP_JS.parent / "aurora.js").read_text(encoding="utf-8")
    script = "const window = {}; const document = {getElementById: () => null};\n" + src + """
const a = Object.create(AuroralMapRenderer.prototype);
a.mapTime = new Date();a.mapIsNow = true; a.showOvation = true;
a.magPoleNorth = { lat: 80.8, lon: -72.8 };
const cells = [];
for (let lo = 0; lo < 360; lo++) for (let la = 65; la <= 75; la++) cells.push([lo, la, 30]);
a.setOvation({ cells, forecast_time: new Date().toISOString() });
const out = [];
for (const [lat, lon] of [[69.6, 18.9], [60, 19], [51.5, -0.1], [-45, 170]]) { a.home = { lat, lon }; out.push(a.homeOutlook().oval); }
console.log(JSON.stringify(out));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    tromso, near, london, south = json.loads(res.stdout)
    assert "30 % probability" in tromso and "overhead" in tromso
    assert "5° of latitude poleward: aurora possible low on the northern horizon" in near
    assert "14° of latitude poleward: aurora unlikely" in london
    assert "no 10 % region poleward of you" in south


def test_every_data_term_on_the_page_is_in_the_glossary():
    import re
    js = (APP_JS.parent / "glossary.js").read_text(encoding="utf-8")
    block = js[js.index("const GLOSSARY = {"):js.index("};", js.index("const GLOSSARY = {"))]
    keys = set(re.findall(r"^\s*'?([\w\-. ]+?)'?\s*:", block, re.M))
    html = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    used = set(re.findall(r'data-term="([^"]+)"', html))
    assert len(used) > 20 and not used - keys, used - keys
    assert html.index("js/glossary.js") < html.index("js/app.js")


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_storm_story_steps_from_measured_data():
    script = _extract("stormStory") + """
const rows = [
  {time_tag: '2024-05-10 17:00:00', speed: 450, bz_gsm: 2},
  {time_tag: '2024-05-10 17:05:00', speed: 460, bz_gsm: 1},
  {time_tag: '2024-05-10 17:10:00', speed: 690, bz_gsm: -5},
  {time_tag: '2024-05-10 18:00:00', speed: 720, bz_gsm: -12},
  {time_tag: '2024-05-10 19:00:00', speed: 750, bz_gsm: -40},
];
const dst = {time_tags: ['2024-05-11 01:00:00', '2024-05-11 02:00:00'], observed: [-300, -518]};
console.log(JSON.stringify([stormStory(rows, dst), stormStory([{time_tag: '2024-01-01 00:00:00', speed: 400, bz_gsm: 3}], null)]));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    steps, quiet = json.loads(res.stdout)
    assert len(steps) == 3 and quiet == []
    assert "2024-05-10 17:10 UTC" in steps[0] and "460 to 690 km/s" in steps[0]
    assert "2024-05-10 18:00 UTC" in steps[1] and "-40 nT" in steps[1]
    assert "2024-05-11 02:00 UTC" in steps[2] and "518 nT" in steps[2]


def test_research_forms_explain_themselves_in_plain_words():
    import re
    html = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    start, end = html.index('id="tab-analysis"'), html.index('id="tab-missions"')
    heads = re.findall(r"<h4[^>]*>.*?</h4>\n\s*(<p[^>]*>In plain words:)?", html[start:end])
    assert heads and all(heads), "every Event Analysis form needs an 'In plain words' line"


def test_spacecraft_without_data_are_labelled_where_they_are_chosen():
    import re
    html = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    opts = re.findall(r'<option value="(ADITYA_L1)">([^<]*)</option>', html)
    assert opts and all(label.endswith("no public data") for _, label in opts)
    for sel in ("forecast-satellite-select", "turbulence-sat-select"):  # no spectrum or forecast of simulated data
        block = html[html.index(f'id="{sel}"'):html.index("</select>", html.index(f'id="{sel}"'))]
        assert "ADITYA_L1" not in block and "SOHO" not in block
    assert 'id="sim-banner"' in html


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_every_script_parses():
    """A syntax error in one file (e.g. an unescaped apostrophe) only showed in the browser."""
    for js in sorted(APP_JS.parent.glob("*.js")):
        res = subprocess.run([NODE, "--check", str(js)], capture_output=True, text=True, encoding="utf-8", timeout=60)
        assert res.returncode == 0, f"{js.name}: {res.stderr}"


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_latest_request_check_goes_stale_when_a_newer_request_starts():
    script = "const _latestRequests = {};\n" + _extract("latestRequest") + """
const a = latestRequest('x'); const b = latestRequest('x'); const c = latestRequest('y');
console.log(JSON.stringify([a(), b(), c()]));
"""
    res = subprocess.run([NODE], input=script, capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [False, True, True]


def test_positions_are_refreshed_while_the_views_are_open():
    """Positions were fetched once per session: a window left open drew where the craft were
    hours or days ago (PSP moves up to ~190 km/s near perihelion)."""
    parker = (APP_JS.parent / "parker.js").read_text(encoding="utf-8")
    assert re.search(r"setInterval\(\(\) => this\.fetchSpiceEphemeris\(\), 600000\)", parker)
    app = APP_JS.read_text(encoding="utf-8")
    assert "setInterval(refreshOrbits, 600000)" in app
    # An archive interval shows the positions at its end (P14 of docs/SIMULATION_AUDIT.md).
    assert re.search(r"setPositionEpoch\(headerTag === ' \(archive end\)'", app)
    assert "epoch=${encodeURIComponent(positionEpoch)}" in parker


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_psp_venus_preset_is_at_venus_distance():
    """The "Venus leg" preset used nu = 100 deg, which is 0.10 AU on PSP's orbit, not 0.72 AU."""
    src = (APP_JS.parent / "parker.js").read_text(encoding="utf-8")
    body = re.search(r"static anomalyAtRadius\((.*?)\) \{(.*?)\n  \}", src, re.S)
    script = (f"function f({body.group(1)}) {{{body.group(2)}}}\n"
              "const nu = f(0.723) * Math.PI / 180, a = 0.3879, e = 0.8819;\n"
              "console.log(JSON.stringify([nu * 180 / Math.PI, a * (1 - e * e) / (1 + e * Math.cos(nu))]));")
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    nu, r = json.loads(res.stdout)
    assert r == pytest.approx(0.723, abs=0.01) and 170 < nu < 180


def test_historical_active_regions_are_where_noaa_placed_them():
    """NOAA SRS of the flare dates (west positive): AR 3842 and AR 3848 were in the wrong hemisphere."""
    src = (APP_JS.parent / "solar_viewer.js").read_text(encoding="utf-8")
    got = {m[0]: (float(m[1]), float(m[2])) for m in re.findall(r"id: '(AR \d+)'.*?lat: (-?[\d.]+), lon: (-?[\d.]+)", src)}
    assert got == {"AR 3664": (-19, 87), "AR 3697": (-18, -35), "AR 3842": (-15, -6), "AR 3848": (12, 11)}


def test_heliosphere_field_tooltip_uses_parker_magnitude():
    """|B| = B_r1 r^-2 sqrt(1 + (Omega r / V)^2) scaled to the L1 field (was 5 / r^2 nT)."""
    src = (APP_JS.parent / "parker.js").read_text(encoding="utf-8")
    assert "5.0 / (mw.r_au * mw.r_au)" not in src
    assert "this.b1auNt / wind(1) * wind(mw.r_au) / (mw.r_au * mw.r_au)" in src
    assert "parkerRenderer.b1auNt = Number(latest.bt)" in APP_JS.read_text(encoding="utf-8")


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_aurora_subsolar_point_matches_the_server():
    """The map's subsolar point (Spencer series, up to 0.44 deg off) now follows the server's
    Hapgood (1992) ephemeris: within 0.05 deg over a year."""
    import numpy as np
    from datetime import datetime, timedelta, timezone
    from helios.core.coordinates import sun_direction_geo
    src = (APP_JS.parent / "aurora.js").read_text(encoding="utf-8")
    body = re.search(r"  getSubsolarPoint\(\) \{(.*?)\n  \}", src, re.S).group(1)
    times = [datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=37 * k) for k in range(237)]
    script = (f"function f() {{{body}}}\nconst out = {json.dumps([t.isoformat() for t in times])}"
              ".map(t => f.call({ mapTime: new Date(t) }));\nconsole.log(JSON.stringify(out));")
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=30)
    got = json.loads(res.stdout)
    ref = sun_direction_geo(times)
    lat = np.degrees(np.arcsin(ref[:, 2])); lon = np.degrees(np.arctan2(ref[:, 1], ref[:, 0]))
    dlon = (np.array([g["lon"] for g in got]) - lon + 180) % 360 - 180
    assert np.max(np.abs(np.array([g["lat"] for g in got]) - lat)) < 0.05 and np.max(np.abs(dlon)) < 0.05


def test_heliosphere_drawing_has_no_invented_structures():
    """Deleted: a CIR shock from 0.4 AU (CIR shocks form beyond 2-3 AU) and data-free sector
    wedges; parcels move radially with a step tied to the field lines' rotation (k = Omega AU / V)."""
    src = (APP_JS.parent / "parker.js").read_text(encoding="utf-8")
    page = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    assert "drawCIRShocks" not in src and "drawPolaritySectors" not in src
    assert "parker-toggle-cir" not in page and "parker-toggle-sectors" not in page
    assert "const step = 0.002 / k;" in src and "this.time * 0.002" in src
    assert "Alfvén Surface crossing" not in src and "(Solar Limb)" not in src


def test_heliosphere_speed_follows_the_measured_wind_until_set_by_hand():
    app = APP_JS.read_text(encoding="utf-8")
    assert "if (!parkerSpeedFromUser && latest.speed != null" in app
    assert "if (!fromData) parkerSpeedFromUser = true;" in app


def test_aurora_map_uses_the_storm_time_edge_from_kp_5():
    """D4: from Kp 5 (the server's model_limit) the diffuse boundary is the storm-time edge
    (DMSP: within 0.6 deg at Kp 7-9): drawn first, shown on the card and used for "your place"."""
    aurora = (APP_JS.parent / "aurora.js").read_text(encoding="utf-8")
    app = APP_JS.read_text(encoding="utf-8")
    assert "b.model_limit ? b.diffuse_equatorward_midnight_lat : null" in app
    assert "const edgePts = storm ? hemi.diffuse : hemi.equatorward;" in aurora
    assert "storm-time edge of the aurora" in aurora and "if (this.stormEdge) {" in aurora


def test_no_handler_is_called_with_an_empty_argument():
    """The restyle's class clean-up removed the word "shadow" from toggleAuroraLayer('shadow', ...),
    so the Night Shadow checkbox did nothing."""
    page = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    assert not re.findall(r'on(?:click|change|input)="[^"]*\(\'\'\s*,', page)


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_dashboard_status_text_follows_the_value():
    # Reproduction: the |B|, density and pressure cards kept a fixed "Nominal background",
    # "Nominal plasma", "Standard compression", also at 50 nT in a storm or without data.
    src = APP_JS.read_text(encoding="utf-8")
    const = re.search(r"^const OMNI_TYPICAL = .*?;$", src, re.M).group(0)
    script = const + "\n" + _extract("typicalText") + """
console.log(JSON.stringify([typicalText('bt', 50), typicalText('bt', 3.2), typicalText('density', 6),
                            typicalText('dynamic_pressure', null)]));
"""
    res = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert res.returncode == 0, res.stderr
    storm, quiet, dens, missing = json.loads(res.stdout)
    assert storm == "Above 95 % of hours" and quiet == "Below usual (median 5.1 nT)"
    assert dens.startswith("Above usual (median 4.9") and missing == "No value in the latest record"
    html = (APP_JS.parent.parent / "index.html").read_text(encoding="utf-8")
    assert "Nominal background" not in html and ">CLOSED<" not in html
