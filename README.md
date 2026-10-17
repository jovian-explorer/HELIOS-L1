# HELIOS-L1

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23322367.svg)](https://doi.org/10.5281/zenodo.23322367)

**Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite**

HELIOS-L1 is a free desktop app for space weather: the stream of particles and magnetic field from the Sun (the *solar wind*), the storms it causes around Earth, and the aurora. It reads live measurements from spacecraft parked 1.5 million km sunward of Earth at the *L1 point* (about an hour of warning before the wind reaches us) and decades of archived data, and runs the standard published models on them. Everything runs on your own computer; the data come from public NOAA, NASA and GFZ services.

> **HELIOS-L1 is public** (version 0.1.0). It is ready for use and for testing; results can still change between versions. Please report problems, wrong results and suggestions through **Feedback** in the app or on the [issue tracker](https://github.com/jovian-explorer/HELIOS-L1/issues/new/choose). To cite HELIOS-L1, use the DOI [10.5281/zenodo.23322367](https://doi.org/10.5281/zenodo.23322367) (all versions; see [CITATION.cff](CITATION.cff)).

## What can I do with it?

* **See the solar wind right now** and what it means: speed, density and magnetic field at L1, the NOAA storm scales (G, S, R), and how hard Earth's magnetic shield is being pushed.
* **Check whether the aurora may be visible from where you are**: the map shows the auroral oval for the current solar wind, the day-night line, and the darkness of the sky at aurora observatories.
* **Follow a solar eruption (CME) to Earth**: coronagraph images of the Sun, the eruption's speed, and its predicted arrival time.
* **Replay famous storms** (Bastille Day 2000, Halloween 2003, May 2024) with the real data.
* **Do research**: shock normals, flux-rope fits, minimum variance and de Hoffmann-Teller analysis, superposed epochs, OMNI statistics from 1963, PFSS coronal fields, radio occultation geometry. Every result lists its data sources and can be saved as CSV or JSON.

New to the subject? Press `U` for the user guide, `P` for the formulas and the papers they come from, and `?` for the keyboard shortcuts.

## Quick start

1. Download the archive for your system from the [Releases](https://github.com/jovian-explorer/HELIOS-L1/releases) page (details in [How to Install and Run](#-how-to-install-and-run)).
2. Unzip it and run `HELIOS-L1` (Windows: `HELIOS-L1.exe`). No Python or other software is needed.
3. The dashboard opens on the live solar wind. The four sections at the top lead to the rest: *L1 Fleet & Telemetry* (spacecraft data), *Solar & Heliosphere* (solar images, CMEs, the Sun's magnetic field), *Geospace & Hazards* (aurora, storm forecast, effects on power grids and radio) and *Data Studio & Science* (archive data, your own files, research analyses).

---

## 🛰️ Spacecraft and what HELIOS-L1 uses from each

### At the Sun-Earth L1 point (~1.5 million km sunward)
* **DSCOVR / NOAA operational stream** (*NOAA*): live 1-minute solar wind and field from NOAA's Real-Time Solar Wind feed; the spacecraft actually supplying it (e.g. SOLAR1) is named. Archive: DSCOVR magnetometer and Faraday cup data from NASA CDAWeb (plasma 2016-2019 only).
* **ACE** (*NASA*): live RTSW rows tagged ACE; archive MAG and SWEPAM (Level 2 and key parameters) from CDAWeb.
* **WIND** (*NASA*): archive MFI and SWE from CDAWeb, at the instruments' own cadence for the event analyses.
* **SOHO** (*ESA/NASA*): live solar wind speed and density from the CELIAS/MTOF Proton Monitor (University of Maryland, the last two days; SOHO has no magnetometer), the archive from CDAWeb (`SOHO_CELIAS-PM_5MIN`), and LASCO C2/C3 coronagraph images (NOAA, Helioviewer).
* **Aditya-L1** (*ISRO*): no public in-situ data (ISSDC PRADAN needs a registered login), so its view shows no values and says so.
* **OMNI** (*NASA*): solar wind time-shifted to Earth's bow shock and geomagnetic indices, 1963 to the present, for history, statistics and model checks.

### Elsewhere
* **STEREO-A** (*NASA*): live solar wind speed, density and field magnitude from its space weather beacon (STEREO Science Center), and the archive from CDAWeb (`STA_L2_MAGPLASMA_1M`); about 70° ahead of Earth on its orbit, so no GSM components or travel time to Earth.
* **GOES** (*NOAA*): X-ray flux (flare class, R scale, D-RAP) and ≥10 MeV protons (S scale), live from NOAA. GOES measures no solar wind, so it has no solar wind view.
* **SDO, SOHO, STEREO-A, Solar Orbiter** (*NASA/ESA*): solar and coronagraph images for any date (Helioviewer Project) and their science FITS files (SunPy). STEREO-A's position is used to correct CME speeds seen from off the Sun-Earth line.
* **Positions:** every spacecraft (the L1 fleet, GOES-19, Parker Solar Probe, Solar Orbiter, STEREO-A) and the planets from JPL Horizons ephemerides read with SPICE (within 1 km of Horizons), for now or for the end of a loaded archive interval; a spacecraft without an ephemeris for the time is shown without a position. Any spacecraft with a SPICE kernel for the radio occultation tool.

---

## 🔬 Scientific Analysis Capabilities

HELIOS-L1 implements rigorous magnetohydrodynamic (MHD) and space physics formulations:

1. **Solar Wind Dynamic Pressure ($P_{dyn}$):**
   $$P_{dyn} = 2.0 \times 10^{-6} \cdot n_p \cdot v_{sw}^2 \quad [\text{nPa}]$$ (OMNI flow pressure, 5 % alphas assumed)
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
   * **Live aurora: NOAA's OVATION Prime nowcast** (`GET /api/aurora/ovation`): the probability of visible aurora on a 1° grid, drawn on the map for the present; "your place" gives NOAA's probability there.
   * **Starkov (1994) auroral oval:** poleward and equatorward boundaries of the oval and the equatorward edge of the diffuse aurora in corrected geomagnetic colatitude, $\theta = A_0 + A_1\cos[15(t + \alpha_1)] + A_2\cos[15(2t + \alpha_2)] + A_3\cos[15(3t + \alpha_3)]$, with every $A_i$, $\alpha_i$ cubic in $\log_{10}|AL|$ (coefficients from Sigernes et al. 2011, Table 2). The driver is OMNI 1-min AL averaged over the hour before the oval time when OMNI covers it, otherwise Kp converted with Starkov's $|AL| = 18 - 12.3Kp + 27.2Kp^2 - 2Kp^3$ nT, or an AL you enter; $|AL|$ is limited to 18-750 nT (Kp 0 to a little above Kp 9; above about 780 nT the fitted equatorward boundary crosses the poleward one, so stronger activity is drawn at the 750 nT oval and the response says the value was capped). The map draws the boundaries for any UTC time, placed with the IGRF centred dipole and the magnetic local time of the subsolar point. `GET /api/aurora?time=&al=&kp=`.
   * **Hemispheric power** (when Kp is known): the TIE-GCM/WACCM relation attributed to Zhang & Paxton (2008), $HP = 16.82\,e^{0.32Kp} - 4.86$ GW for $Kp \le 7$, then linear to 300 GW at Kp 9 (the TIE-GCM extension). It is an estimate from Kp, not a measurement.
   * **Ring current Dst:** $dDst^*/dt = Q(VB_s) - Dst^*/\tau$, $Dst = Dst^* + b\sqrt{P_{dyn}} - c$, with either O'Brien & McPherron (2000) ($Q = -4.4(VB_s - 0.49)$ nT/h, $\tau = 2.4\,e^{9.74/(4.69 + VB_s)}$ h, $b = 7.26$, $c = 11$ nT) or Burton et al. (1975) ($Q = -5.4(VB_s - 0.5)$ nT/h, $\tau = 7.7$ h, $b = 15.8$, $c = 20$ nT).
   * **Observed indices next to the model:** the live view plots WDC Kyoto real-time Dst (hourly, via NOAA SWPC) with the model, driven by L1 solar wind shifted to Earth and started from the observed value, and gives r, RMSE and bias with 95 % intervals that allow for the autocorrelation of the series (one storm is only a few independent samples, which the answer says). Historical events and `GET /api/storm/indices?start=&end=` use OMNI 1-min SYM-H, ASY-H, AE, AL and AU and compare both models with SYM-H.

5. **Coronagraph Imagery & CME Kinematic Solver:**
   * Direct integration with real-time feeds from **SOHO LASCO C2**, **LASCO C3**, and **GOES SUVI 195/304 Å**. If an image cannot be loaded, the panel shows a placeholder drawing and says so.
   * Active region map: the numbered regions of the latest NOAA SWPC solar region summary (location, Mount Wilson and McIntosh class, area, flares of the day, SWPC 24 h C/M/X flare probabilities; `GET /api/solar/regions`), drawn on a schematic solar disk. The disk is a drawing in EUV or white-light colours, not an image.
   * Plane-of-sky expansion velocity calculator ($V_{cme} = \Delta r / \Delta t$) and the **Vršnak et al. (2013)** drag-based model (ambient wind and drag parameter adjustable) for arrival times and speeds at L1 and Earth, with the published defaults $\Gamma = 0.2	imes10^{-7}$ km⁻¹ and $w = 450$ km/s (Dumbović et al. 2021) and the model started at 20 R☉; checked on 44 DONKI CMEs of 2023-2025 (mean absolute error 14.4 h, as published for the model). Compared with the **Gopalswamy et al. (2001)** empirical arrival of the ejecta ($a = 2.193 - 0.0054u$ m/s² from the Sun until 0.76 AU, then constant speed). The response lists its assumptions (no projection correction unless the source and width are given; one drag parameter for all CMEs).

6. **Heliospheric Parker Spiral Field Modeling:**
   * Evaluates Archimedean magnetic spiral geometry ($r - r_0 = -\frac{V_{sw}}{\Omega_\odot} (\phi - \phi_0)$) and pitch angles ($\psi$).
   * Identifies the "well-connected" solar disk footpoint longitude for solar energetic particle (SEP) events.

7. **NASA OMNI Ingestion Studio & Shock Screen:**
   * Ingests custom CSV and NASA OMNI high-resolution telemetry.
   * Four example intervals of OMNI 5-minute data, bundled for offline use: 10-11 May 2024, 15 July 2000, 17 March 2015 and the quiet day of 7 December 2019.
   * Screens the series for shock-like jumps with the criteria of the IPShocks database (Kilpua et al. 2015); shock normals, speeds and Mach numbers with uncertainties are in the event analysis (item 10).

8. **Geomagnetically Induced Currents (GIC) & D-RAP Ionospheric Absorption:**
   * **Plane-wave induction (Boteler & Pirjola 2017):** the geoelectric field of a uniform ground for one period (180 s), $E = \sqrt{\rho/(\mu_0\omega)}\,|dB/dt|$, and the quasi-DC current it drives through a line and a transformer neutral: a first estimate (no layered or coastal ground).
   * **NOAA D-RAP Model:** Highest Affected Frequency $HAF = 10\log_{10}F_x + 65$ MHz (reduced by $\cos^{0.75}\chi$) and absorption $A(f) = (HAF/f)^{1.5}$ dB from solar X-ray flares.

9. **Sensor Cross-Calibration & Turbulence Power Spectral Density:**
   * Cross-correlation time lag ($\tau \sim 30\text{--}60$ min early warning between L1 and Earth).
     A positive lag means spacecraft B observes the same structure later than spacecraft A.
     The lag comes with a 95 % interval (moving-block bootstrap) and r with a 95 % interval that allows for the autocorrelation of the series.
     For observed RTSW data the baseline uses the NOAA ephemeris of the spacecraft that supplied the data (e.g. SOLAR1); other missions use their JPL Horizons ephemerides. The fleet matrix gives each pair's correlation at its best lag within ±60 min.
   * Pearson correlation ($r$, with its 95 % interval), $R^2$, RMSE, MAE, and linear calibration between any two spacecraft.
   * Fast Fourier Transform (FFT) analysis of IMF magnetic fluctuations to identify Alfvénic turbulence and Kolmogorov $f^{-5/3}$ inertial subrange slopes.

10. **Event analysis on archive data (WIND, ACE, DSCOVR at native cadence; STEREO-A, Solar Orbiter and Parker Solar Probe 1-min, RTN, for shocks, timing with ephemeris positions, minimum variance, deHoffmann-Teller and flux ropes):**
    * **Interplanetary shocks:** normals from magnetic coplanarity, velocity coplanarity and the mixed-mode methods MX1-3 (Schwartz 1998), shock speed $V_{sh} = \hat n \cdot (N_2\mathbf V_2 - N_1\mathbf V_1)/(N_2 - N_1)$, $\theta_{Bn}$, jumps, Alfvén and fast Mach numbers with Monte Carlo uncertainties. The normal points into the upstream plasma, as in the Harvard-Smithsonian CfA shock database, against which it was checked (17 March 2015 and 27 February 2014: MX3 normal within 1°, speed within 1%). `GET /api/analysis/shock?mission=WIND&time=2015-03-17T04:00`.
    * **Multi-spacecraft timing:** the normal and speed from one spacecraft predict the shock arrival at the others from their measured positions ($t = t_{ref} + \hat n\cdot\Delta\mathbf r/V_{sh}$); the observed arrival, residual and implied speed show how planar the shock is (27 February 2014 WIND to ACE: 1016 s predicted, 1103 s observed over 900,000 km). `GET /api/analysis/timing?reference=WIND&time=2014-02-27T15:50&targets=ACE,DSCOVR`.
    * **Magnetic cloud flux rope fit:** Lundquist force-free model, $\mathbf B = B_0[J_0(\alpha r)\hat e_{axis} + H J_1(\alpha r)\hat e_\phi]$ with $\alpha R_0 = 2.405$, fitted as in Lepping et al. (1990): axis longitude and latitude, $B_0$, handedness, closest approach, diameter, axial flux and $\chi_R$, checked against the WIND MFI magnetic cloud table (axis within 9-18°, $B_0$ within 6 % for three clouds), with 1σ errors of $B_0$, $R_0$, closest approach and axis direction from the error study of Lepping et al. (2003), interpolated as in the WIND MFI team's program (reproduces Table 5 of Lepping et al. 2006). `GET /api/analysis/fluxrope?mission=WIND&start=1995-10-18T19:48&end=1995-10-20T01:18`.
    * **deHoffmann-Teller frame** for any interval, with analytical and bootstrap error ellipsoids, the normal velocity along the minimum variance normal and the Walén test: `GET /api/analysis/ht?mission=WIND&start=2015-03-17T04:02&end=2015-03-17T04:25`.
    * **Coupling functions, proton beta and Alfvén Mach number with uncertainties** (Newell dΦ/dt, Akasofu ε, V·Bs, dynamic pressure, β_p = 2μ0nkT/B², M_A = V/V_A) on every plasma sample of an interval of up to 72 h, with the measurement error of each mean propagated from the 1-σ speed and density uncertainties that WIND SWE gives per spectrum, and the 95 % sampling interval of the mean: `GET /api/analysis/coupling?mission=WIND&start=2015-03-17T04:00&end=2015-03-18T04:00`.
    * **Time shift to the bow shock nose** as NASA's High Resolution OMNI does it (phase front normals from cross products or MVAB-0 for every 15-16 s field vector, Farris & Russell bow shock with the Shue et al. magnetopause, 29.8 km/s aberration) for WIND, ACE and DSCOVR over up to 48 h of arrival times, with the shifted 1-minute field and plasma, the flat ΔX/Vx delay and, for WIND and ACE, the agreement with OMNI's own shifts: `GET /api/analysis/timeshift?mission=WIND&start=2018-09-01T00:00&end=2018-09-02T00:00` (`format=csv` for the shifted data).
    * **Magnetic cloud search** in up to 31 days of 1-minute WIND, ACE, DSCOVR or OMNI data with the Lepping et al. (2005) identification scheme (loose or strict criteria): candidate regions with their mean field, proton beta, thermal speed, field latitude range and large-scale smoothness, each one-click fitted with the flux rope model: `GET /api/analysis/mcdetect?mission=WIND&start=1997-11-01&end=1997-11-30&criteria=loose`.
    * **Sudden commencements** in OMNI 1-minute SYM-H over up to a year (a step of at least 10 nT within 4 minutes after a quiet hour, persistent and with a solar wind pressure jump), each with its match in the sudden commencement lists of the Observatori de l'Ebre for ISGI (read from the observatory, CC BY-NC 4.0) and the listed ones not found; against those lists for 1995-2024 the search finds 74 % of the 566 listed SCs (90 % of those above 15 nT) and 37 % of its detections are not listed: `GET /api/analysis/sudden_commencements?start=2015-03-01&end=2015-07-01` (`format=csv`). Each onset is paired with the fast forward shock at L1 (IPShocks database) whose planar front, t + |n·r|/V_sh, reaches the Earth within 15 minutes; at 382 SCs of 1995-2023 the onset came 0.0 min after that arrival on median (IQR -1.7 to +1.6 min). The panel copies the onsets into the superposed epoch analysis.
    * **Superposed epoch analysis** of OMNI SYM-H, AE and the solar wind drivers, and of the GFZ indices Kp and Hp30 (`parameters=kp,hp30`, each held over its interval; CC BY 4.0), keyed on your onset times (mean, median, quartiles, events per bin, per-event extremes): `GET /api/analysis/superposed?onsets=2015-03-17T04:45,2024-05-10T17:05&parameters=sym_h,bz_gsm,speed`.
    * **OMNI statistics (1963 to the present, hourly):** distributions, joint histograms, conditional averages (e.g. Dst in bins of the Newell coupling function), correlations and yearly or monthly statistics against the sunspot number, with 95 % intervals that allow for autocorrelation, after filters on any quantity (`where=speed>500; beta<1; dst<=-50`), southward or northward IMF lasting at least N hours, the Xu & Borovsky (2015) solar wind type (ejecta, coronal hole, sector reversal, streamer belt) and the number of fine-scale points per hour. Every filter and the hours it kept are in the answer and the CSV: `GET /api/statistics/omni?start_year=1995&end_year=2024&analysis=conditional&x=newell&y=dst&log_x=true`. The same analyses are a panel of the Event Analysis tab.
    * **Storm selection by strength:** storms in hourly Dst (runs at or below a threshold, joined across recoveries shorter than 6 h, optional floor and plasma type before the minimum) with the solar wind before each minimum: `GET /api/statistics/storms?start_year=1996&end_year=2006&threshold_nt=-100` (90 storms, as counted by Echer et al. 2008). The superposed epoch analysis takes the same selection (`storm_threshold_nt=-150&storm_start_year=2015&storm_end_year=2024`, epoch at the Dst minimum or the first hour below the threshold) and records it in the provenance and the CSV; in the tab, *Find storms* fills the onset list.
    * **Ring current model skill over many storms:** both models driven by hourly OMNI over the years, scored storm by storm against Dst (r, RMSE, bias, error of the minimum) with means and 95 % intervals over the storms: `GET /api/statistics/dst_models?start_year=1998&end_year=2006&threshold_nt=-100` (O'Brien-McPherron r 0.88, RMSE 26 nT over 84 storms, as in Ji et al. 2012). One storm is too few for an interval; this is the place to judge the models.
    * **Interplanetary shocks at L1 (IPShocks database, University of Helsinki):** the 1064 fast forward and reverse shocks found at WIND, ACE and DSCOVR with the database's normal, θBn, speed, Mach numbers and errors (bundled, CC BY 4.0, doi:10.5281/zenodo.19730292): `GET /api/catalogs/shocks?start=2015-06-22&end=2015-06-23`. The shock analysis shows the listed values next to its own, and takes the database's windows (8 min, 1 min left out before and 2 min after: `exclude_after_minutes=2`). With those windows its MX3 normals are 1.2° from the listed ones on median for 288 ACE shocks (0.4° with ACE time tags moved to mid-interval as the database does), 2.4° for 188 WIND and 0.2° for 21 DSCOVR shocks.
    * **ICMEs (Richardson & Cane list, 1996 to the present):** the near-Earth ICMEs with their disturbance, start and end, magnetic cloud flag, shock and Dst, live or from the bundled snapshot (CC0, doi:10.7910/DVN/C2MHTH); storms, shocks and magnetic cloud candidates are marked with the ICME (or its sheath) they fall in: `GET /api/catalogs/icme?start=2003-10-20&end=2003-11-25`.
    * **Minimum variance analysis** with eigenvalue ratios and Sonnerup & Scheible (1998) angular errors: `GET /api/analysis/mva?mission=WIND&start=...&end=...`.
    * **In the app:** Data Studio & Science, Event Analysis: one form per analysis, tables and charts of the results, example buttons for the checked events, and Save JSON / CSV links.
    * Every result lists the CDAWeb datasets and HAPI requests behind it, the parameters and the software version; add `&download=true` for a JSON file.

11. **Operator User Guide & Scientific Literature Handbook (Hotkeys 'U' & 'P'):**
    * Full 6-chapter interactive operator manual embedded with real-time keyword search.
    * Complete directory of peer-reviewed formulas with direct DOI cross-references, data provider provenance (NOAA, NASA, ISRO, ESA, GFZ, WDC), and open science licenses.
    * Published results reproduced with HELIOS-L1's own tools on the same data (user guide, section 7, "Reproductions of published results"; `tests/test_reproductions.py`): the DBM tools paper's CME of 3 April 2010, the WIND magnetic cloud table's flux-rope fits, the Richardson & Cane ICME means and Dst minima, the limits of Shue et al. (1998), the drag-based model evaluation of Čalogović et al. (2021) and the ICME averages of Kilpua et al. (2017).

---

## 📡 Data Sources & Provenance

Every telemetry record carries a `data_source` field and every API response a `provenance` block, so measured and modelled values are never mixed up in plots, exports or reports:

| `data_source` | Meaning |
|---|---|
| `observed` | Measured values: the NOAA SWPC Real-Time Solar Wind (RTSW) 1-minute feeds (`json/rtsw/rtsw_mag_1m.json`, `rtsw_wind_1m.json`) or the NASA CDAWeb archive (HAPI). |
| `unavailable` | No data for the mission and window (Aditya-L1 always: its Level-2 data are on ISSDC PRADAN, https://pradan.issdc.gov.in/al1/, for registered users only, with no public API; SOHO and STEREO-A when their feeds cannot be reached; WIND before the archive reaches the window). No values are shown; nothing is simulated in their place. |
| `imported` | Rows from a user file in the Custom Ingestion tab. |

* **Solar cycle:** the hazards tab shows the observed monthly and 13-month smoothed international sunspot number (SILSO) and F10.7 with NOAA SWPC's predicted cycle and range (`json/solar-cycle/observed-solar-cycle-indices.json`, `predicted-solar-cycle.json`), the observed cycle 25 maximum, and cycle 24 aligned on its minimum. Without network access the NOAA SWPC solar-cycle products bundled with HELIOS-L1 are shown (monthly since December 2008 and the predicted cycle).

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
* **Historical events:** OMNI 5-minute data from NASA CDAWeb, or the same data bundled with HELIOS-L1 when CDAWeb cannot be reached (the quiet baseline is 6-8 December 2019); March 1989 has only SYM-H (no spacecraft measured the solar wind), Carrington 1859 has no time series (no measurements exist).
* **Gaps:** missing or fill values stay empty (null); derived quantities are empty when an input is missing. Rows with a non-zero RTSW quality flag are discarded.
* **Indices:** NOAA G/R/S scales use the latest observed planetary Kp, GOES 0.1–0.8 nm X-ray flux and ≥10 MeV proton flux. When Kp cannot be fetched, the Newell et al. (2008) estimate from the solar wind is used and labelled as such (`kp_source`).
* **Storm forecast tab:** a 12-hour Kp trajectory from the Newell et al. (2008) fit and a Dst trajectory from O'Brien & McPherron (2000), both from the last 3 hours of L1 solar wind held constant (persistence: an assumption, shown under the chart); storm probabilities and the NOAA Kp line in the chart (the product's "estimated" values for the current UTC day and "predicted" values after it) are NOAA SWPC's own 3-day forecast (`text/3-day-geomag-forecast.txt`, `products/noaa-planetary-k-index-forecast.json`).
* **Time:** all time stamps are UTC, `YYYY-MM-DD HH:MM:SS`.
* **CSV export** (`/api/export/csv`) starts with `# key: value` lines (data kind, provenance, coverage, cadence, units). Read it with `pandas.read_csv(path, comment="#")`, or pass `metadata=false` for a bare table.
* **Importing files:** CSV, tab- or space-delimited text, JSON (record lists, NOAA SWPC header-row products, NOAA real-time solar wind files `rtsw_*_1m.json`, of which only the active spacecraft's unflagged rows are used), HAPI CSV with its header (e.g. from CDAWeb, fill values become gaps) and HELIOS-L1's own CSV/JSON exports are read; header names are matched without regard to case, spaces or units in brackets (`Bz GSM (nT)`), unused columns and other warnings are listed in the import tab. The examples in the import tab are measured OMNI 5-minute data (NASA CDAWeb) of four intervals, bundled with the app. OMNI/CDF fill values (99999.9 km/s, 999.99 cm⁻³, 9999.99 nT, 9999999 K, ±1e31) are treated as missing, time stamps with offsets are converted to UTC, and OMNI `YEAR DOY HR MN` columns are recognised. Field components named `bx/by/bz` are taken as GSM. Files with only GSE components (`BX_GSE` ...) are rotated to GSM for each row's time (Hapgood 1992 with the IGRF-14 dipole axis, `helios/core/coordinates.py`); the result matches the GSM values published in OMNI to 0.01 nT.

### Third-party data and code bundled with HELIOS-L1

| What | Where | Licence | Credit |
|---|---|---|---|
| Chart.js 4.4.1 | `helios/gui/static/js/chart.min.js` | MIT | (c) 2023 Chart.js Contributors |
| Font Awesome Free 6.5.1 | `helios/gui/static/css/font-awesome.min.css`, `webfonts/` | Icons CC BY 4.0, fonts SIL OFL 1.1, code MIT | Fonticons, Inc., https://fontawesome.com |
| Tailwind CSS 3.4.17 (the generated utilities) | `helios/gui/static/css/tailwind.css` | MIT | Tailwind Labs, Inc. |
| NAIF generic kernels `naif0012.tls`, `pck00010.tpc`, `gm_de431.tpc`, unmodified | `helios/data/spice_kernels/` | NAIF permits redistribution of unmodified kernels (https://naif.jpl.nasa.gov/naif/rules.html) | NASA NAIF, Jet Propulsion Laboratory |
| Richardson & Cane list of near-Earth ICMEs since 1996, snapshot of the July 23, 2026 revision | `helios/data/icme_richardson_cane.json` | CC0 1.0 (Harvard Dataverse) | I. G. Richardson and H. V. Cane, doi:10.7910/DVN/C2MHTH; Cane & Richardson (2003, JGR 108, 1156); Richardson & Cane (2010, Sol. Phys. 264, 189) |
| IPShocks database, the shocks at WIND, ACE and DSCOVR of the version of 2026-04-24 (rows at other spacecraft and some columns left out, field names changed; `scripts/update_shock_catalog.py`) | `helios/data/ipshocks_l1.json` | CC BY 4.0 (Zenodo) | Kilpua, E., Good, S., Soljento, J., Price, D. J., Isavnin, A., Lumme, E., Mäkelä, T. V., Isavnina, K. & Andréeová, K., The IPShocks Database, doi:10.5281/zenodo.19730292; Kilpua et al. (2015, JGR 120, 4112, doi:10.1002/2015JA021138) |
| IGRF-14 degree-1 coefficients | `helios/core/coordinates.py` | | IAGA Working Group V-MOD; coefficients file from NOAA NCEI |

Read at run time and cached, never bundled: the SOHO CELIAS/MTOF Proton Monitor near-real-time solar wind of the University of Maryland (space.umd.edu/pm), the STEREO-A space weather beacon of the STEREO Science Center, the sudden commencement lists of the Observatori de l'Ebre (CC BY-NC 4.0, no commercial use), the Kp and Hp30 indices of GFZ (CC BY 4.0), the NOAA SWPC products and the NASA CDAWeb data; their terms are in section 10 of the [user guide](docs/USER_GUIDE.md). The test fixtures under `tests/data` are short excerpts of these sources (NASA CDAWeb, GFZ Kp and Hp30, Ebre list lines), credited in the tests that use them.

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

New builds are published about once a month (only the two newest stay on the releases page; each is archived on Zenodo), and installed builds check for them once a week and update themselves (Settings, *Updates*; see the user guide). The builds are unsigned. On Windows, click **More info → Run anyway** if SmartScreen warns. On macOS, the first time, right-click the executable and choose **Open** (or run `xattr -dr com.apple.quarantine HELIOS-L1`).

### Option 2: Install with pip (Python 3.10+)
```bash
pip install "helios-l1[solar] @ git+https://github.com/jovian-explorer/HELIOS-L1.git"
helios            # or: python -m helios
```
`[solar]` adds SunPy and sunkit-magex for science FITS files, the coronal field (PFSS) and the PFSS field of the radio occultation; leave it out for a smaller install without them. The standalone app includes them.
The repository is private, so pip needs GitHub access (e.g. `gh auth login` with git credentials set up).

### Using HELIOS-L1 from Python (no window)
The models are plain functions in `helios.core` and can be used in scripts and notebooks without starting the app. [`examples/headless_basics.py`](examples/headless_basics.py) runs offline and shows the magnetopause stand-off, Newell coupling, NOAA scales, the auroral oval, a Dst run, the Parker spiral and a minimum variance analysis:
```python
from helios.core.science import SpaceWeatherPhysics as swp
from helios.core.aurora_model import AuroralModel

p = swp.dynamic_pressure(15.0, 650.0)            # nPa, from density (cm^-3) and speed (km/s)
r0, alpha = swp.shue1998_magnetopause(p, -20.0)  # stand-off (Earth radii) and flaring, Shue et al. 1998
edge = AuroralModel.starkov_latitude(AuroralModel.kp_to_al(8.0), 0.0)  # oval edge at midnight, deg
```
Data come through `helios.core.downloader.DataDownloader` (async; e.g. `await DataDownloader().get_telemetry_bundle("DSCOVR", 1)`), and with the app running every result is also a JSON API at `http://127.0.0.1:8765/api/...` (listed at `/docs`). The CI runs the example on Windows, macOS and Linux.

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
  data/            bundled NAIF generic kernels (spice_kernels/) and catalogue snapshots
                   (Richardson & Cane ICME list, IPShocks shocks at L1)
tests/             pytest suite
packaging/         PyInstaller spec, build script, Tailwind config
scripts/           icon set (make_icons.py), CSS build (build_css.py), catalogue snapshot
                   updates (update_icme_catalog.py, update_shock_catalog.py)
assets/            application icon used for the Windows build
```

---

## Licence

HELIOS-L1 is free software under the MIT licence (`LICENSE`). The third-party code, fonts and data it bundles (Chart.js, Tailwind CSS, Font Awesome, NAIF kernels, the Richardson & Cane ICME list, the IPShocks database) keep their own licences, listed in `THIRD_PARTY_LICENSES.md`; both files are included in the standalone app.

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
The suite covers the physics models, telemetry pipeline, SPICE ephemeris engine and the REST API. The workflow `.github/workflows/ci.yml` runs it on Windows, macOS and Linux for every push to `main` and every pull request, on a copy of the tests against the installed package.

