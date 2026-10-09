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

2. **Magnetopause & Bow Shock Boundaries (Shue et al., 1998 / Chao et al., 2002 / Farris & Russell, 1994):**
   * **Magnetopause, Shue et al. (1998):** $r = r_0 (2/(1+\cos\theta))^{\alpha}$ with $r_0 = (10.22 + 1.29\tanh(0.184(B_z + 8.14)))P_{dyn}^{-1/6.6}$ and $\alpha = (0.58 - 0.007B_z)(1 + 0.024\ln P_{dyn})$.
   * **Bow shock, Chao et al. (2002):** $r = r_0((1+\epsilon)/(1+\epsilon\cos\theta))^{\alpha}$, $\epsilon = 1.029$, with $r_0$ and $\alpha$ depending on $P_{dyn}$, $B_z$, plasma $\beta$ and the magnetosonic Mach number $M_{ms}$ (14 published coefficients, as reproduced in Mo et al. 2025, JGR, doi:10.1029/2025JA033966). Alternative: **Farris & Russell (1994)**, $R_{bs} = r_{0,mp}[1 + 1.1((\gamma-1)M_{ms}^2 + 2)/((\gamma+1)(M_{ms}^2 - 1))]$, the relation OMNI uses for its bow shock nose.
   * $M_{ms}$ and $\beta$ come from the measured speed, density, temperature and $|B|$ with the OMNI definitions.
   * **Magnetosheath Thickness ($\Delta R$):** Subsolar separation between Bow Shock and Magnetopause ($\Delta R = R_0,bs - r_0,mp$).
   * **Sub-GEO Compression Alert:** Alerts if $r_0 < 6.6 R_E$, signifying that geostationary spacecraft (GOES, telecommunications) are exposed directly to unshielded magnetosheath plasma.

3. **Akasofu Epsilon Energy Coupling ($\epsilon$):**
   $$\epsilon = \frac{4\pi}{\mu_0} v_{sw} B_t^2 \sin^4\left(\frac{\theta}{2}\right) l_0^2 \quad [\text{GW}]$$
   Measures power transfer into the magnetosphere driving substorms and auroral displays.

4. **Auroral Oval Boundaries & Dst Ring Current (Burton / O'Brien-McPherron):**
   * **Starkov (1994) auroral oval:** poleward and equatorward boundaries of the oval and the equatorward edge of the diffuse aurora in corrected geomagnetic colatitude, $\theta = A_0 + A_1\cos[15(t + \alpha_1)] + A_2\cos[15(2t + \alpha_2)] + A_3\cos[15(3t + \alpha_3)]$, with every $A_i$, $\alpha_i$ cubic in $\log_{10}|AL|$ (coefficients from Sigernes et al. 2011, Table 2). The driver is OMNI 1-min AL averaged over the hour before the oval time when OMNI covers it, otherwise Kp converted with Starkov's $|AL| = 18 - 12.3Kp + 27.2Kp^2 - 2Kp^3$ nT, or an AL you enter; $|AL|$ is limited to 18-750 nT (Kp 0 to a little above Kp 9; above about 780 nT the fitted equatorward boundary crosses the poleward one, so stronger activity is drawn at the 750 nT oval and the response says the value was capped). The map draws the boundaries for any UTC time, placed with the IGRF centred dipole and the magnetic local time of the subsolar point. `GET /api/aurora?time=&al=&kp=`.
   * **Hemispheric power** (when Kp is known): Zhang & Paxton (2008) $HP = 16.82\,e^{0.32Kp} - 4.86$ GW for $Kp \le 7$, then linear to 300 GW at Kp 9 (the TIE-GCM extension). It is an estimate from Kp, not a measurement.
   * **Ring current Dst:** $dDst^*/dt = Q(VB_s) - Dst^*/\tau$, $Dst = Dst^* + b\sqrt{P_{dyn}} - c$, with either O'Brien & McPherron (2000) ($Q = -4.4(VB_s - 0.49)$ nT/h, $\tau = 2.4\,e^{9.74/(4.69 + VB_s)}$ h, $b = 7.26$, $c = 11$ nT) or Burton et al. (1975) ($Q = -5.4(VB_s - 0.5)$ nT/h, $\tau = 7.7$ h, $b = 15.8$, $c = 20$ nT).
   * **Observed indices next to the model:** the live view plots WDC Kyoto real-time Dst (hourly, via NOAA SWPC) with the model, driven by L1 solar wind shifted to Earth and started from the observed value, and gives r, RMSE and bias with 95 % intervals that allow for the autocorrelation of the series (one storm is only a few independent samples, which the answer says). Historical events and `GET /api/storm/indices?start=&end=` use OMNI 1-min SYM-H, ASY-H, AE, AL and AU and compare both models with SYM-H.

5. **Coronagraph Imagery & CME Kinematic Solver:**
   * Direct integration with real-time feeds from **SOHO LASCO C2**, **LASCO C3**, and **GOES SUVI 195/304 Å**. If an image cannot be loaded, the panel shows a placeholder drawing and says so.
   * Active region map: the numbered regions of the latest NOAA SWPC solar region summary (location, Mount Wilson and McIntosh class, area, flares of the day, SWPC 24 h C/M/X flare probabilities; `GET /api/solar/regions`), drawn on a schematic solar disk. The disk is a drawing in EUV or white-light colours, not an image.
   * Plane-of-sky expansion velocity calculator ($V_{cme} = \Delta r / \Delta t$) and the **Vršnak et al. (2013)** drag-based model (ambient wind and drag parameter adjustable) for arrival times and speeds at L1 and Earth, compared with the **Gopalswamy et al. (2001)** empirical arrival model ($a = 2.193 - 0.0054u$ m/s² until 0.76 AU, then constant speed). The response lists its assumptions (no projection correction; rough shock Mach number; Kp category from speed only).

6. **Heliospheric Parker Spiral Field Modeling:**
   * Evaluates Archimedean magnetic spiral geometry ($r - r_0 = -\frac{V_{sw}}{\Omega_\odot} (\phi - \phi_0)$) and pitch angles ($\psi$).
   * Identifies the "well-connected" solar disk footpoint longitude for solar energetic particle (SEP) events.

7. **NASA OMNI Ingestion Studio & Rankine-Hugoniot Shock Solver:**
   * Ingests custom CSV and NASA OMNI high-resolution telemetry.
   * Features 5 one-click historical benchmarks: May 2024 G5 Superstorm, Bastille Day 2000, Carrington Event 1859, Halloween 2003, and Quiet Interplanetary Background.
   * Scans for Rankine-Hugoniot MHD jump conditions: compression ratio $r_c = N_2/N_1$, shock velocity $V_{sh}$, and fast magnetosonic Mach number $M_{ms}$.

8. **Geomagnetically Induced Currents (GIC) & D-RAP Ionospheric Absorption:**
   * **Boteler (2012) 1D Induction Model:** Computes surface geoelectric field ($E = Z \cdot H$) and neutral transformer currents on resistive geological shields.
   * **NOAA D-RAP Model:** Highest Affected Frequency $HAF = 10\log_{10}F_x + 65$ MHz (reduced by $\cos^{0.75}\chi$) and absorption $A(f) = (HAF/f)^{1.5}$ dB from solar X-ray flares.

9. **Sensor Cross-Calibration & Turbulence Power Spectral Density:**
   * Cross-correlation time lag ($\tau \sim 30\text{--}60$ min early warning between L1 and Earth).
     A positive lag means spacecraft B observes the same structure later than spacecraft A.
     The lag comes with a 95 % interval (moving-block bootstrap) and r with a 95 % interval that allows for the autocorrelation of the series.
     For observed RTSW data the baseline uses the NOAA ephemeris of the spacecraft that supplied the data (e.g. SOLAR1); other missions use model orbits.
   * Pearson correlation ($r$, with its 95 % interval), $R^2$, RMSE, MAE, and linear calibration between any two spacecraft.
   * Fast Fourier Transform (FFT) analysis of IMF magnetic fluctuations to identify Alfvénic turbulence and Kolmogorov $f^{-5/3}$ inertial subrange slopes.

10. **Event analysis on archive data (WIND, ACE, DSCOVR at native cadence):**
    * **Interplanetary shocks:** normals from magnetic coplanarity, velocity coplanarity and the mixed-mode methods MX1-3 (Schwartz 1998), shock speed $V_{sh} = \hat n \cdot (N_2\mathbf V_2 - N_1\mathbf V_1)/(N_2 - N_1)$, $\theta_{Bn}$, jumps, Alfvén and fast Mach numbers with Monte Carlo uncertainties. The normal points into the upstream plasma, as in the Harvard-Smithsonian CfA shock database, against which it was checked (17 March 2015 and 27 February 2014: MX3 normal within 1°, speed within 1%). `GET /api/analysis/shock?mission=WIND&time=2015-03-17T04:00`.
    * **Multi-spacecraft timing:** the normal and speed from one spacecraft predict the shock arrival at the others from their measured positions ($t = t_{ref} + \hat n\cdot\Delta\mathbf r/V_{sh}$); the observed arrival, residual and implied speed show how planar the shock is (27 February 2014 WIND to ACE: 1016 s predicted, 1103 s observed over 900,000 km). `GET /api/analysis/timing?reference=WIND&time=2014-02-27T15:50&targets=ACE,DSCOVR`.
    * **Magnetic cloud flux rope fit:** Lundquist force-free model, $\mathbf B = B_0[J_0(\alpha r)\hat e_{axis} + H J_1(\alpha r)\hat e_\phi]$ with $\alpha R_0 = 2.405$, fitted as in Lepping et al. (1990): axis longitude and latitude, $B_0$, handedness, closest approach, diameter, axial flux and $\chi_R$, checked against the WIND MFI magnetic cloud table (axis within 9-18°, $B_0$ within 6 % for three clouds), with 1σ errors of $B_0$, $R_0$, closest approach and axis direction from the error study of Lepping et al. (2003), interpolated as in the WIND MFI team's program (reproduces Table 5 of Lepping et al. 2006). `GET /api/analysis/fluxrope?mission=WIND&start=1995-10-18T19:48&end=1995-10-20T01:18`.
    * **deHoffmann-Teller frame** for any interval, with analytical and bootstrap error ellipsoids, the normal velocity along the minimum variance normal and the Walén test: `GET /api/analysis/ht?mission=WIND&start=2015-03-17T04:02&end=2015-03-17T04:25`.
    * **Coupling functions, proton beta and Alfvén Mach number with uncertainties** (Newell dΦ/dt, Akasofu ε, V·Bs, dynamic pressure, β_p = 2μ0nkT/B², M_A = V/V_A) on every plasma sample of an interval of up to 72 h, with the measurement error of each mean propagated from the 1-σ speed and density uncertainties that WIND SWE gives per spectrum, and the 95 % sampling interval of the mean: `GET /api/analysis/coupling?mission=WIND&start=2015-03-17T04:00&end=2015-03-18T04:00`.
    * **Time shift to the bow shock nose** as NASA's High Resolution OMNI does it (phase front normals from cross products or MVAB-0 for every 15-16 s field vector, Farris & Russell bow shock with the Shue et al. magnetopause, 29.8 km/s aberration) for WIND, ACE and DSCOVR over up to 48 h of arrival times, with the shifted 1-minute field and plasma, the flat ΔX/Vx delay and, for WIND and ACE, the agreement with OMNI's own shifts: `GET /api/analysis/timeshift?mission=WIND&start=2018-09-01T00:00&end=2018-09-02T00:00` (`format=csv` for the shifted data).
    * **Magnetic cloud search** in up to 31 days of 1-minute WIND, ACE, DSCOVR or OMNI data with the Lepping et al. (2005) identification scheme (loose or strict criteria): candidate regions with their mean field, proton beta, thermal speed, field latitude range and large-scale smoothness, each one-click fitted with the flux rope model: `GET /api/analysis/mcdetect?mission=WIND&start=1997-11-01&end=1997-11-30&criteria=loose`.
    * **Superposed epoch analysis** of OMNI SYM-H, AE and the solar wind drivers keyed on your onset times (mean, median, quartiles, events per bin, per-event extremes): `GET /api/analysis/superposed?onsets=2015-03-17T04:45,2024-05-10T17:05&parameters=sym_h,bz_gsm,speed`.
    * **OMNI statistics (1963 to the present, hourly):** distributions, joint histograms, conditional averages (e.g. Dst in bins of the Newell coupling function), correlations and yearly or monthly statistics against the sunspot number, with 95 % intervals that allow for autocorrelation, after filters on any quantity (`where=speed>500; beta<1; dst<=-50`), southward or northward IMF lasting at least N hours, the Xu & Borovsky (2015) solar wind type (ejecta, coronal hole, sector reversal, streamer belt) and the number of fine-scale points per hour. Every filter and the hours it kept are in the answer and the CSV: `GET /api/statistics/omni?start_year=1995&end_year=2024&analysis=conditional&x=newell&y=dst&log_x=true`. The same analyses are a panel of the Event Analysis tab.
    * **Storm selection by strength:** storms in hourly Dst (runs at or below a threshold, joined across recoveries shorter than 6 h, optional floor and plasma type before the minimum) with the solar wind before each minimum: `GET /api/statistics/storms?start_year=1996&end_year=2006&threshold_nt=-100` (90 storms, as counted by Echer et al. 2008). The superposed epoch analysis takes the same selection (`storm_threshold_nt=-150&storm_start_year=2015&storm_end_year=2024`, epoch at the Dst minimum or the first hour below the threshold) and records it in the provenance and the CSV; in the tab, *Find storms* fills the onset list.
    * **Ring current model skill over many storms:** both models driven by hourly OMNI over the years, scored storm by storm against Dst (r, RMSE, bias, error of the minimum) with means and 95 % intervals over the storms: `GET /api/statistics/dst_models?start_year=1998&end_year=2006&threshold_nt=-100` (O'Brien-McPherron r 0.88, RMSE 26 nT over 84 storms, as in Ji et al. 2012). One storm is too few for an interval; this is the place to judge the models.
    * **ICMEs (Richardson & Cane list, 1996 to the present):** the near-Earth ICMEs with their disturbance, start and end, magnetic cloud flag, shock and Dst, live or from the bundled snapshot (CC0, doi:10.7910/DVN/C2MHTH); storms, shocks and magnetic cloud candidates are marked with the ICME (or its sheath) they fall in: `GET /api/catalogs/icme?start=2003-10-20&end=2003-11-25`.
    * **Minimum variance analysis** with eigenvalue ratios and Sonnerup & Scheible (1998) angular errors: `GET /api/analysis/mva?mission=WIND&start=...&end=...`.
    * **In the app:** Data Studio & Science, Event Analysis: one form per analysis, tables and charts of the results, example buttons for the checked events, and Save JSON / CSV links.
    * Every result lists the CDAWeb datasets and HAPI requests behind it, the parameters and the software version; add `&download=true` for a JSON file.

11. **Operator User Guide & Scientific Literature Handbook (Hotkeys 'U' & 'P'):**
    * Full 6-chapter interactive operator manual embedded with real-time keyword search.
    * Complete directory of peer-reviewed formulas with direct DOI cross-references, data provider provenance (NOAA, NASA, ISRO, ESA, GFZ, WDC), and open science licenses.

---

## 📡 Data Sources & Provenance

Every telemetry record carries a `data_source` field and every API response a `provenance` block, so measured and modelled values are never mixed up in plots, exports or reports:

| `data_source` | Meaning |
|---|---|
| `observed` | Measured values: the NOAA SWPC Real-Time Solar Wind (RTSW) 1-minute feeds (`json/rtsw/rtsw_mag_1m.json`, `rtsw_wind_1m.json`) or the NASA CDAWeb archive (HAPI). |
| `simulated` | No data for the mission and window (Aditya-L1, SOHO, GOES-16 Hp, STEREO-A; WIND when the archive has not reached the window yet); values are the operational L1 stream with fixed calibration offsets and noise. Not a measurement. Aditya-L1 ASPEX/SWIS and MAG Level-2 data are on ISSDC PRADAN (https://pradan.issdc.gov.in/al1/) for registered users only; there is no public API, so they cannot be fetched without the user's own login. |
| `synthetic` | The archive could not be reached and nothing was cached; values come from the offline solar wind model. Historical storm profiles are also synthetic (built from published peak values). |
| `imported` | Rows from a user file in the Custom Ingestion tab. |

* **Solar cycle:** the hazards tab shows the observed monthly and 13-month smoothed international sunspot number (SILSO) and F10.7 with NOAA SWPC's predicted cycle and range (`json/solar-cycle/observed-solar-cycle-indices.json`, `predicted-solar-cycle.json`), the observed cycle 25 maximum, and cycle 24 aligned on its minimum. Without network access an analytic approximation is shown and labelled MODEL.

* **DSCOVR view:** the RTSW operational stream (rows flagged active). The spacecraft actually supplying it (e.g. SOLAR1) is stored per record in `source_spacecraft`.
* **ACE view:** the RTSW rows tagged `source = ACE` (real ACE data), so ACE vs. operational-monitor comparisons are genuine inter-spacecraft comparisons.
* **Coverage:** the RTSW feeds hold about the last 24 h. The 7-day span uses the CDAWeb archive where it has data and RTSW after the archive's last sample, as 5-minute block averages.
* **Archive (NASA CDAWeb HAPI, `https://cdaweb.gsfc.nasa.gov/hapi`):**

  | Mission | Magnetic field | Plasma |
  |---|---|---|
  | WIND | `WI_H0_MFI@0` (1-min), then `WI_K0_MFI` | `WI_H1_SWE` (non-linear fits), then `WI_K0_SWE` |
  | ACE | `AC_H0_MFI` (Level 2), then `AC_K1_MFI` | `AC_H0_SWE` (Level 2, ends 2024-07), then `AC_K0_SWE` |
  | DSCOVR | `DSCOVR_H0_MAG` (1-s, GSE; rotated to GSM) | `DSCOVR_H1_FC` (2016-2019 only) |
  | OMNI | `OMNI_HRO_1MIN` (time-shifted to the bow shock nose) | same |

  Preliminary key-parameter datasets only extend the definitive ones past their last sample, and the provenance lists every dataset used with its level and coverage. Any interval of up to 31 days, from the dashboard (Observation Horizon, Archive Interval) or `GET /api/archive/WIND?start=2024-05-10T00:00&end=2024-05-12T00:00` (add `&format=csv` for a file, `&cadence_minutes=5` for block averages). Data are cached per day as 1-minute means; a DSCOVR magnetometer day is about 7 MB to download the first time.
* **Historical events:** events since 1995 load real OMNI data; March 1989 (no OMNI 1-min coverage), Carrington 1859 and the quiet baseline are synthetic profiles and labelled so.
* **Gaps:** missing or fill values stay empty (null); derived quantities are empty when an input is missing. Rows with a non-zero RTSW quality flag are discarded.
* **Indices:** NOAA G/R/S scales use the latest observed planetary Kp, GOES 0.1–0.8 nm X-ray flux and ≥10 MeV proton flux. When Kp cannot be fetched, a Bz-based estimate is used and labelled as such (`kp_source`).
* **Storm forecast tab:** a 12-hour Kp trajectory from the Newell et al. (2008) fit and a Dst trajectory from O'Brien & McPherron (2000), both from the latest L1 solar wind held and relaxed towards quiet values (an assumption, shown under the chart); storm probabilities and the NOAA Kp line in the chart (the product's "estimated" values for the current UTC day and "predicted" values after it) are NOAA SWPC's own 3-day forecast (`text/3-day-geomag-forecast.txt`, `products/noaa-planetary-k-index-forecast.json`).
* **Time:** all time stamps are UTC, `YYYY-MM-DD HH:MM:SS`.
* **CSV export** (`/api/export/csv`) starts with `# key: value` lines (data kind, provenance, coverage, cadence, units). Read it with `pandas.read_csv(path, comment="#")`, or pass `metadata=false` for a bare table.
* **Importing files:** CSV, tab- or space-delimited text, JSON (record lists, NOAA SWPC header-row products) and HELIOS-L1's own CSV/JSON exports are read; header names are matched without regard to case, spaces or units in brackets (`Bz GSM (nT)`), unused columns and other warnings are listed in the import tab. The storm presets in the import tab are illustrative profiles for trying the pipeline, not measured data (measured OMNI data come from the Archive Interval loader). OMNI/CDF fill values (99999.9 km/s, 999.99 cm⁻³, 9999.99 nT, 9999999 K, ±1e31) are treated as missing, time stamps with offsets are converted to UTC, and OMNI `YEAR DOY HR MN` columns are recognised. Field components named `bx/by/bz` are taken as GSM. Files with only GSE components (`BX_GSE` ...) are rotated to GSM for each row's time (Hapgood 1992 with the IGRF-14 dipole axis, `helios/core/coordinates.py`); the result matches the GSM values published in OMNI to 0.01 nT.

---

## 🚀 How to Install and Run

The [user guide](docs/USER_GUIDE.md) describes every tab, the methods and how they were checked, the uncertainties, the data sources and their terms of use, and troubleshooting.

HELIOS-L1 runs on Windows, macOS and Linux. It starts a local science server and opens the dashboard in a desktop window, or in your web browser if no native window backend is available.

### Option 1: Download the standalone app (no Python needed)
From the [Releases](https://github.com/jovian-explorer/HELIOS-L1/releases) page, download the archive for your system:

| System | File | Run |
|---|---|---|
| Windows (x64) | `HELIOS-L1-<version>-windows-x86_64.zip` | Unzip, then double-click `HELIOS-L1\HELIOS-L1.exe` |
| macOS (Apple Silicon) | `HELIOS-L1-<version>-macos-arm64.tar.gz` | Extract, then run `HELIOS-L1/HELIOS-L1` |
| Linux (x86_64) | `HELIOS-L1-<version>-linux-x86_64.tar.gz` | Extract, then run `HELIOS-L1/HELIOS-L1` |

Builds update themselves once a week from the releases page (Settings, *Updates*; see the user guide). The builds are unsigned. On Windows, click **More info → Run anyway** if SmartScreen warns. On macOS, the first time, right-click the executable and choose **Open** (or run `xattr -dr com.apple.quarantine HELIOS-L1`).

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
* `--host` accepts only local addresses (`127.0.0.1`, `localhost`, `::1`); HELIOS is not meant to be reachable from the network.
* If the port is busy, HELIOS picks the next free one automatically; if it still cannot listen, it stops with a message naming the port and suggests `--port`.
* The API answers only requests addressed to `127.0.0.1`/`localhost` and refuses requests that a browser sends on behalf of another web site; scripts and `curl` can use it (POST bodies must be JSON with `Content-Type: application/json`).
* Limits: imported files up to 64 MB, archive and index intervals up to 31 days, event analyses up to 72 h, superposed epoch analyses up to 60 onsets and 180 days of data in total.

### Where HELIOS keeps its files
Downloaded telemetry cache and logs go in the per-user app folders, and your settings (`settings.json`) and the desktop window's browser storage in the config folder:

| System | Cache | Logs | Settings |
|---|---|---|---|
| Windows | `%LOCALAPPDATA%\HELIOS-L1\Cache` | `%LOCALAPPDATA%\HELIOS-L1\Logs` | `%LOCALAPPDATA%\HELIOS-L1` |
| macOS | `~/Library/Caches/HELIOS-L1` | `~/Library/Logs/HELIOS-L1` | `~/Library/Application Support/HELIOS-L1` |
| Linux | `~/.cache/HELIOS-L1` | `~/.local/state/HELIOS-L1/log` | `~/.config/HELIOS-L1` |

Set `HELIOS_HOME=/some/folder` to keep everything in one place instead (`cache/`, `logs/`, `config/`; portable installs, tests).

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

### Styles
The dashboard's Tailwind CSS utilities are built at development time into `helios/gui/static/css/tailwind.css` (committed, so the app needs neither Node.js nor a network connection). After any change to `index.html`, a script or `packaging/tailwind.config.js`, run `python scripts/build_css.py` (needs Node.js; it runs Tailwind CSS 3.4.17, MIT licence, with that config). The CSS records a digest of these files, and the test suite fails while it does not match.

### Building the standalone app
```bash
pip install -e ".[build]"
python packaging/build.py
```
This produces `dist/HELIOS-L1/` and an archive for the current OS (`--dist`/`--work` choose other folders); the archive name is the one the updater looks for (`helios/release_names.py`). PyInstaller can't cross-compile, so every OS builds its own. Pushing a tag like `v0.0.1` runs `.github/workflows/release.yml`, which builds Windows, macOS and Linux and attaches them to a GitHub Release.

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

