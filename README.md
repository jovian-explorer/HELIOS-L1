# HELIOS-L1

**Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite**

> A unified scientific software suite for acquiring, analyzing, comparing, and visualizing space weather telemetry from satellites stationed at the Sun-Earth L1 Lagrange point and complementary heliospheric missions.

---

## 🌟 Name & Full Form

* **Short & Catchy Name:** **HELIOS-L1** (or **HELIOS**)
* **Full Form:** **H**eliophysical **E**xploration, **L**agrange-1 **I**nterplanetary **O**bservation & **S**pace-weather Suite

---

## 🛰️ Supported Spacecraft & Missions

HELIOS-L1 is engineered to ingest, cross-calibrate, and analyze data from the spacecraft fleet observing solar-terrestrial dynamics:

### 1. Sun-Earth L1 Fleet (~1.5 Million km Sunward)
* **DSCOVR** (*NOAA / NASA / USAF*): Primary operational space weather monitor in Lissajous orbit at L1. Features the **PlasMag** Faraday Cup (proton density, bulk speed) and Fluxgate Magnetometer ($B_x, B_y, B_z, B_t$).
* **ACE** (*NASA / Caltech*): Advanced Composition Explorer in L1 Halo orbit. Instruments include **MAG**, **SWEPAM**, and **EPAM** for solar energetic particle events and shock tracking.
* **Aditya-L1** (*ISRO*): India's pioneering solar observatory in L1 Halo orbit. Features **ASPEX** (SWIS/STEPS particle spectrometer), **PAPA** (plasma analyzer), **MAG** (tri-axial fluxgate magnetometer), and **VELC** (coronagraph).
* **WIND** (*NASA / GSFC*): Long-baseline solar wind reference observatory at L1 with **MFI** (magnetic field) and **SWE** (solar wind plasma).
* **SOHO** (*ESA / NASA*): Landmark solar observatory at L1. White-light coronagraphs (**LASCO C2/C3**) and **CELIAS/MTOF** solar wind composition.

### 2. Complementary Space Weather Missions
* **GOES-16 / GOES-18** (*NOAA / NASA*): Geostationary orbit (~35,786 km). Measures magnetospheric magnetic compression (**Hp**), solar X-ray irradiance (**EXIS XRS** for solar flare classification A/B/C/M/X), and radiation belt proton fluxes (**SEISS**).
* **SDO** (*NASA*): Solar Dynamics Observatory in geosynchronous orbit. Ultra-HD extreme ultraviolet coronal dynamics (**AIA**) and photospheric magnetic fields (**HMI**).
* **STEREO-A** (*NASA*): Heliocentric orbit (~0.96 AU ahead of Earth). Provides off-axis 3D triangulation of Earth-directed CMEs.

---

## 🔬 Scientific Analysis Capabilities

HELIOS-L1 implements rigorous magnetohydrodynamic (MHD) and space physics formulations:

1. **Solar Wind Dynamic Pressure ($P_{dyn}$):**
   $$P_{dyn} = 1.6726 \times 10^{-6} \cdot n_p \cdot v_{sw}^2 \quad [\text{nPa}]$$
   Quantifies solar wind momentum flux compressing Earth's magnetosphere.

2. **Magnetopause & Bow Shock Boundaries (Chao et al., 2002 / Shue et al., 1998):**
   * **Chao et al. (2002) Bilinear Model:** Computes dayside magnetopause standoff $r_0$ with distinct slope breaks across $B_z \ge 0$ ($+0.057 B_z$) and $B_z < 0$ ($+0.541 B_z$) erosion regimes, coupled with upstream Alfvén Mach-dependent Bow Shock standoff $R_0,bs$ and flaring parameters ($\alpha_{mp}, \alpha_{bs}$).
   * **Magnetosheath Thickness ($\Delta R$):** Subsolar separation between Bow Shock and Magnetopause ($\Delta R = R_0,bs - r_0,mp$).
   * **Sub-GEO Compression Alert:** Alerts if $r_0 < 6.6 R_E$, signifying that geostationary spacecraft (GOES, telecommunications) are exposed directly to unshielded magnetosheath plasma.

3. **Akasofu Epsilon Energy Coupling ($\epsilon$):**
   $$\epsilon = \frac{v_{sw} B_t^2}{\mu_0} \sin^4\left(\frac{\theta}{2}\right) l_0^2 \quad [\text{GW}]$$
   Measures power transfer into the magnetosphere driving substorms and auroral displays.

4. **Auroral Oval Boundaries & Dst Ring Current (Burton Model):**
   * **Starkov/Feldstein Model:** Evaluates midnight, flank, and noon equatorward auroral oval boundaries ($\Lambda_{eq}$) as a function of $Kp$ and $B_z$, determining geographic visibility regions worldwide.
   * **Burton et al. (1975) Dst Simulation:** Differential ring current injection and decay model predicting geomagnetic storm intensity ($Dst^*$).

5. **Coronagraph Imagery & CME Kinematic Solver:**
   * Direct integration with real-time feeds from **SOHO LASCO C2**, **LASCO C3**, and **SDO AIA 195/304 Å**.
   * Plane-of-sky expansion velocity calculator ($V_{cme} = \Delta r / \Delta t$) with **Gopalswamy et al. (2001)** aerodynamic drag deceleration, predicting arrival timestamps at L1 and Earth.

6. **Heliospheric Parker Spiral Field Modeling:**
   * Evaluates Archimedean magnetic spiral geometry ($r - r_0 = -\frac{V_{sw}}{\Omega_\odot} (\phi - \phi_0)$) and pitch angles ($\psi$).
   * Identifies the "well-connected" solar disk footpoint longitude for solar energetic particle (SEP) events.

7. **NASA OMNI Ingestion Studio & Rankine-Hugoniot Shock Solver:**
   * Ingests custom CSV and NASA OMNI high-resolution telemetry.
   * Features 5 one-click historical benchmarks: May 2024 G5 Superstorm, Bastille Day 2000, Carrington Event 1859, Halloween 2003, and Quiet Interplanetary Background.
   * Scans for Rankine-Hugoniot MHD jump conditions: compression ratio $r_c = N_2/N_1$, shock velocity $V_{sh}$, and fast magnetosonic Mach number $M_{ms}$.

8. **Geomagnetically Induced Currents (GIC) & D-RAP Ionospheric Absorption:**
   * **Boteler (2012) 1D Induction Model:** Computes surface geoelectric field ($E = Z \cdot H$) and neutral transformer currents on resistive geological shields.
   * **NOAA D-RAP Model:** Computes Highest Affected Frequency (HAF) and multi-MHz radio absorption on trans-polar airline corridors caused by solar X-ray flares and SPEs.

9. **Sensor Cross-Calibration & Turbulence Power Spectral Density:**
   * Cross-correlation time lag ($\tau \sim 30\text{--}60$ min early warning between L1 and Earth).
   * Pearson correlation ($r$), $R^2$, RMSE, MAE, and linear calibration between any two spacecraft.
   * Fast Fourier Transform (FFT) analysis of IMF magnetic fluctuations to identify Alfvénic turbulence and Kolmogorov $f^{-5/3}$ inertial subrange slopes.

10. **Operator User Guide & Scientific Literature Handbook (Hotkeys 'U' & 'P'):**
    * Full 6-chapter interactive operator manual embedded with real-time keyword search.
    * Complete directory of peer-reviewed formulas with direct DOI cross-references, data provider provenance (NOAA, NASA, ISRO, ESA, GFZ, WDC), and open science licenses.

---

## 🚀 How to Install and Run

HELIOS-L1 runs on Windows, macOS and Linux. It starts a local science server and opens the dashboard in a desktop window, or in your web browser if no native window backend is available.

### Option 1: Download the standalone app (no Python needed)
From the [Releases](https://github.com/jovian-explorer/HELIOS-L1/releases) page, download the archive for your system:

| System | File | Run |
|---|---|---|
| Windows (x64) | `HELIOS-L1-<version>-windows-x86_64.zip` | Unzip, then double-click `HELIOS-L1\HELIOS-L1.exe` |
| macOS (Apple Silicon) | `HELIOS-L1-<version>-macos-arm64.tar.gz` | Extract, then run `HELIOS-L1/HELIOS-L1` |
| Linux (x86_64) | `HELIOS-L1-<version>-linux-x86_64.tar.gz` | Extract, then run `HELIOS-L1/HELIOS-L1` |

The builds are unsigned. On Windows, click **More info → Run anyway** if SmartScreen warns. On macOS, the first time, right-click the executable and choose **Open** (or run `xattr -dr com.apple.quarantine HELIOS-L1`).

### Option 2: Install with pip (Python 3.10+)
```bash
pip install "git+https://github.com/jovian-explorer/HELIOS-L1.git"
helios            # or: python -m helios
```
The repository is private, so pip needs GitHub access (e.g. `gh auth login` with git credentials set up).

### Command-line options
```
helios [--host 127.0.0.1] [--port 8765] [--headless] [--browser] [--version]
```
* `--headless` runs only the server (open `http://127.0.0.1:8765` yourself).
* `--browser` skips the desktop window and uses the default browser.
* If the port is busy, HELIOS picks the next free one automatically.

### Where HELIOS keeps its files
Downloaded telemetry cache and logs go in the per-user app folders:

| System | Cache | Logs |
|---|---|---|
| Windows | `%LOCALAPPDATA%\HELIOS-L1\Cache` | `%LOCALAPPDATA%\HELIOS-L1\Logs` |
| macOS | `~/Library/Caches/HELIOS-L1` | `~/Library/Logs/HELIOS-L1` |
| Linux | `~/.cache/HELIOS-L1` | `~/.local/state/HELIOS-L1/log` |

Set `HELIOS_HOME=/some/folder` to keep everything in one place instead (portable installs, tests).

### Platform notes
* **Windows:** the desktop window uses Microsoft Edge WebView2 (preinstalled on Windows 10/11).
* **macOS:** uses the built-in WebKit. Nothing extra is needed.
* **Linux:** the desktop window needs GTK or Qt bindings, e.g. `sudo apt install python3-gi gir1.2-webkit2-4.1` (or `pip install "pywebview[qt]"`). Without them HELIOS opens in your browser instead.

---

## 🛠️ Development

```bash
git clone https://github.com/jovian-explorer/HELIOS-L1.git
cd HELIOS-L1
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
python -m pytest            # full test suite
helios                      # run from source
```

### Building the standalone app
```bash
pip install -e ".[build]"
python packaging/build.py
```
This produces `dist/HELIOS-L1/` and an archive for the current OS. PyInstaller can't cross-compile, so every OS builds its own. Pushing a tag like `v0.0.1` runs `.github/workflows/release.yml`, which builds Windows, macOS and Linux and attaches them to a GitHub Release.

### Project layout
```
helios/            application package
  api/server.py    FastAPI REST API
  core/            physics, telemetry, SPICE ephemeris engines
  gui/app.py       launcher (server + desktop window / browser)
  gui/static/      dashboard frontend (offline: vendored JS, fonts, images)
  data/spice_kernels/  bundled NAIF generic kernels
tests/             pytest suite
packaging/         PyInstaller spec and build script
scripts/make_icons.py  regenerates the logo and icon set
assets/            application icon used for the Windows build
```

---

## 👨‍🔬 Creator & Lead Architect

* **Dr. Keshav Aggarwal**
  * **Current Affiliation:** Research Associate, Space Physics Laboratory (SPL), Vikram Sarabhai Space Centre (VSSC), Indian Space Research Organisation (ISRO), Thiruvananthapuram.
  * **Doctoral Education:** Ph.D. in Astronomy and Space Engineering, Department of Astronomy, Astrophysics and Space Engineering (DAASE), Indian Institute of Technology (IIT) Indore.
  * **Fellowship:** Prime Minister's Research Fellow (PMRF).
  * **Research Focus:** Planetary/exoplanetary atmospheres, ionospheres, planetary radio occultation, solar-planetary space weather interactions across MOM, Chandrayaan-2, Chandrayaan-3, Akatsuki, and Aditya-L1.

---

## 🧪 Automated Test Suite

```bash
python -m pytest
```
The suite covers the physics models, telemetry pipeline, SPICE ephemeris engine and the REST API. CI runs it on Windows, macOS and Linux for every push to `main`.

