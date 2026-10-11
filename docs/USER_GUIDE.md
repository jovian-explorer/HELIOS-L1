# HELIOS-L1 user guide

This guide describes HELIOS-L1 as it is in this repository: how to install and start it, what each tab shows and where its numbers come from, how the analysis methods were checked, how far the results can be trusted, and what to do when something does not work. The README has the full formula list; the CHANGELOG records every check in detail.

Contents

1. [Install and start](#1-install-and-start)
2. [The window](#2-the-window)
3. [L1 Fleet & Telemetry](#3-l1-fleet--telemetry)
4. [Solar & Heliosphere](#4-solar--heliosphere)
5. [Geospace & Hazards](#5-geospace--hazards)
6. [Data Studio & Science](#6-data-studio--science)
7. [Event analysis methods and how they were checked](#7-event-analysis-methods-and-how-they-were-checked)
8. [Uncertainties and their limits](#8-uncertainties-and-their-limits)
9. [Measured, simulated and synthetic values](#9-measured-simulated-and-synthetic-values)
10. [Data sources, terms of use and citation](#10-data-sources-terms-of-use-and-citation)
11. [Exports and the API](#11-exports-and-the-api)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Install and start

### Standalone build

`python packaging/build.py` (after `pip install -e ".[build]"`) makes `dist/HELIOS-L1/` with the executable `HELIOS-L1` (`HELIOS-L1.exe` on Windows) and an archive of that folder. PyInstaller builds only for the system it runs on. Unzip the archive anywhere and run the executable; nothing else is needed. The builds are unsigned: on Windows choose *More info, Run anyway* if SmartScreen warns; on macOS right-click and *Open* the first time.

### Automatic updates

A standalone build checks once a week whether a newer build has been published on the project's GitHub releases page (Settings, *Updates*; on by default, *Check now* at any time). A newer build for your system is downloaded in the background, checked against the SHA-256 digest GitHub lists for it, and installed the next time you start HELIOS-L1: the program exits, a small script swaps the installation folder (the old one is kept as `<folder>.previous` until the new build runs, and put back if a step fails) and starts the new build with the same options. If the folder cannot be replaced (a program still has a file open in it) or the new build exits with an error within 20 s, the old build is put back and keeps running, Settings shows why, and the installation is tried again at a start an hour later (three times at most; *Check now* starts over). Your cache, logs and settings are in other folders and are not touched; after the update a dialog shows the release notes and any changes in the settings, and, if you skipped releases, how many and a link to everything that changed since your version (or to the CHANGELOG). Pre-releases are offered while you run a 0.x version. Copies run from source or installed with pip do not update themselves, nor does an installation that holds its own data folders (`HELIOS_HOME` inside it). While the repository is private, the check needs a GitHub token (`GITHUB_TOKEN`, `GH_TOKEN`, or a logged-in GitHub CLI); the token is sent only to api.github.com.

### From source (Python 3.10 or newer)

```bash
pip install -e .        # in a clone of the repository
helios                  # or: python -m helios
```

### Command line

```
helios [--host 127.0.0.1] [--port 8765] [--headless] [--browser] [--version]
```

* `--headless` starts only the local server; open `http://127.0.0.1:8765` in a browser yourself.
* `--browser` uses your default browser instead of the desktop window.
* `--host` accepts only `127.0.0.1`, `localhost` or `::1`. HELIOS-L1 is a local application and refuses to listen on the network.
* If port 8765 is taken, the next free port is used. If HELIOS-L1 is already running on the port, the new start reconnects to it.

The desktop window uses Edge WebView2 on Windows (part of Windows 10 and 11), WebKit on macOS, and GTK or Qt on Linux (`sudo apt install python3-gi gir1.2-webkit2-4.1`, or `pip install "pywebview[qt]"`). Without a window backend the dashboard opens in the browser.

### Where files go

| | Windows | macOS | Linux |
|---|---|---|---|
| Download cache | `%LOCALAPPDATA%\HELIOS-L1\Cache` | `~/Library/Caches/HELIOS-L1` | `~/.cache/HELIOS-L1` |
| Logs | `%LOCALAPPDATA%\HELIOS-L1\Logs` | `~/Library/Logs/HELIOS-L1` | `~/.local/state/HELIOS-L1/log` |
| Settings (`settings.json`) and window storage | `%LOCALAPPDATA%\HELIOS-L1` | `~/Library/Application Support/HELIOS-L1` | `~/.config/HELIOS-L1` |

Set the environment variable `HELIOS_HOME` to a folder to keep all three there instead (`cache/`, `logs/`, `config/`), for a portable copy or for tests.

---

## 2. The window

* **Status bar (top line):** the latest NOAA G, S and R scales, the magnetopause stand-off distance and the Akasofu coupling from the live solar wind, and the clock in the selected time zone.
* **Header:** the data source of the view on screen (for example *Observed: NOAA RTSW SOLAR1*, or the CDAWeb datasets of an archive interval), the G scale, the latest Bz, and the buttons *Live Fetch*, *Bulletin*, *References*, *Guide*, *Incidents*, *Settings* and *About*.
* **Domain bar:** four domains, each with its own row of tabs, plus sound on/off, bulletin, Markdown summary, CSV and PNG export.

Keyboard shortcuts (not while typing in a field):

| Key | Action | Key | Action |
|---|---|---|---|
| 1-4 | Switch domain | R | Refresh the current view |
| A | Sound on/off | B | Bulletin |
| P | References | U | In-app guide |
| L | Incident log | T | Time zone |
| S | Settings | O | About |
| ? or F1 | All shortcuts | Esc | Close the dialog |

**Settings** (key S): four dark colour themes (Mission Slate, Deep Space, Solar Amber, Terminal/high contrast; there is no light theme), three text sizes, the number of worker threads for heavy computations (archive decoding, spectra, comparisons), and the display time zone. *Apply & Save* writes `settings.json`; if the file cannot be written, the settings apply for the session and the dialog says why they were not saved. Times in data files, exports and the API are always UTC.

After you start a different version of HELIOS-L1 with the same settings, a dialog lists once what changed in the settings: new settings with their defaults, settings whose allowed values or default changed, stored values this version cannot use, and stored settings it does not have. Nothing stored is changed: values this version cannot use stay in `settings.json` for the version that uses them, and the dialog lets you keep the values or pick others.

**Incident log** (key L): entries made during the session when the live data cross fixed thresholds: magnetopause stand-off below 6.6 R_E, Bz at or below -8 nT (warning) or -15 nT (critical), dynamic pressure at or above 12 nPa, speed at or above 650 km/s. The same kind of event is not logged again within 12 minutes. The log is kept in the window's browser storage (up to 100 entries) and can be exported as JSON.

---

## 3. L1 Fleet & Telemetry

### L1 Telemetry (dashboard)

Cards and charts of the solar wind at L1: speed, IMF Bz (GSM) with the clock angle, |B|, proton density, dynamic pressure (P = 1.6726e-6 n V² nPa) and the travel time from the spacecraft to Earth, with the minimum, mean and maximum of the window. Charts: the field components, speed and density, the magnetopause stand-off (Shue et al. 1998) and the Akasofu ε. Below them a table of shock-like jumps (see 6.1 for the thresholds).

* **Active spacecraft:** DSCOVR and ACE show the NOAA Real-Time Solar Wind (RTSW) 1-minute feed. The "DSCOVR" view is NOAA's operational stream; the spacecraft that supplied it (for example SOLAR1) is named in the header and stored per record. The ACE view uses the RTSW rows tagged ACE. Aditya-L1, SOHO, GOES-16 and STEREO-A have no public real-time solar wind feed here, and WIND only through the archive: their views are **simulated** and labelled so (section 9).
* **Observation horizon:** the last 24 hours (RTSW keeps about one day), the last 7 days (archive where it has data, RTSW after its last sample, as 5-minute means), or **Archive Interval**.
* **Archive Interval (NASA CDAWeb):** any interval of up to 31 days from WIND, ACE, DSCOVR or OMNI, as 1-minute, 5-minute or 1-hour means. Datasets: WIND `WI_H0_MFI@0` and `WI_H1_SWE` (then the key-parameter files `WI_K0_*`), ACE `AC_H0_MFI` and `AC_H0_SWE` (Level 2; SWEPAM Level 2 ends in July 2024, then `AC_K0_SWE`), DSCOVR `DSCOVR_H0_MAG` (1 s, GSE, rotated to GSM) and `DSCOVR_H1_FC` (plasma 2016-2019 only), OMNI `OMNI_HRO_1MIN` (time-shifted to the bow shock nose, with SYM-H, ASY-H, AE, AL, AU). Archives lag real time by days (key parameters) to months (Level 2, OMNI). The status line and the CSV header give the coverage of the interval: for the field, the plasma and (OMNI) SYM-H, the fraction of the interval covered, the number of gaps and the longest one (gaps longer than 10 minutes, or than two samples at 1-hour means; "> 99.9 %" when only a short gap remains). The JSON lists the gaps, the first 20 of them. Days are cached as 1-minute means; a DSCOVR magnetometer day is about 7 MB the first time.
* **Physical regime filter:** shows only the minutes with Bz < 0, speed > 500 km/s or density > 10 cm⁻³.
* **Sonify Plasma:** plays the latest values as sound: pitch from the speed (300-1000 km/s to 180-540 Hz), a fifth above for northward and a tritone for southward Bz, tremolo rate from the density (2-25 cm⁻³ to 3-12 Hz).

### Multi-Satellite Comparator

Compares one quantity (Bz, |B|, speed, density, dynamic pressure) between two spacecraft over the last day: Pearson r with its 95 % interval, R², RMSE, bias, the linear calibration A = a·B + b, and the cross-correlation lag with a 95 % interval from a moving-block bootstrap. A positive lag means B sees the same structure later than A. The baseline panel gives the separation and the delay expected from the X separation and the mean speed, using the NOAA ephemeris of the spacecraft that supplied observed RTSW data and model orbits otherwise.

The **fleet matrix** at the top shows r for every pair. Missions without measured data in the window are tagged SIMULATED (or SYNTHETIC) and their cells are faded: their values are the operational stream with offsets and noise, so a high r with DSCOVR means nothing about instruments. A warning appears in the same way when one side of a pairwise comparison is not measured.

An imported file can be compared with the fleet (*Compare with L1 Fleet* in the import tab). If the file ends before the live window, WIND, ACE, DSCOVR and OMNI are taken from the archive for the file's interval. The file carries no spacecraft position, so no baseline is computed for it.

### Position of Probes & Orbits

A schematic of the Sun-Earth line in GSE with the L1 spacecraft (analytical halo, Lissajous and Keplerian orbit models, with time and planetary constants from the bundled NAIF kernels), Earth's magnetopause (Shue et al. 1998) and bow shock (Chao et al. 2002, or Farris & Russell 1994) for quiet, storm, extreme or live solar wind, in 2D or a 3D halo view. The drawing is not to scale between the L1 region and the magnetosphere; the numbers in the HUD and the cards are.

### Fleet Catalog

Mission cards: agency, orbit, instruments, cadence, data policy as stated by the agencies, a reference with DOI and the data portal. Imported datasets appear here as custom missions.

---

## 4. Solar & Heliosphere

### Coronagraph & CME

* The latest SOHO LASCO C2 and C3 and GOES SUVI 195 Å images from NOAA SWPC. If an image cannot be loaded, a placeholder drawing is shown and labelled.
* **Solar image archive:** images of SDO/AIA and HMI, SOHO/LASCO C2, C3 and EIT, STEREO-A/SECCHI EUVI, COR1 and COR2 and Solar Orbiter/EUI FSI for any interval, from the Helioviewer Project (api.helioviewer.org). For n frames the images closest to n evenly spaced times are taken, each once. Every picture is centred on the Sun at a fixed field of view per instrument, so its scale (arcsec per pixel) and the solar radius in pixels are given and hold for the whole sequence. They are display images; the science FITS files of the same interval are listed and downloaded through SunPy Fido (optional: `pip install "helios-l1[solar]"`). Images are cached; intervals more than a day old for good.
* **Running difference, J-map, CME front:** each archive frame minus the previous one; a height-time map of the difference brightness along a chosen position angle (Sheeley et al. 1999, doi:10.1029/1999JA900308); front points set by clicking the map or from the automatic track (outermost height above 3σ of the robust noise, only outward and slower than 4000 km/s); a linear or quadratic fit gives speed and acceleration with errors; with the source longitude and latitude the plane-of-sky speed is corrected to radial motion, v = v_pos / sin ψ (projection effects: Vršnak et al. 2007, doi:10.1051/0004-6361:20077175), except within 20° of the line of sight. The fitted front starts the CME arrival solver at its last height and time. On the 10 September 2017 CME (LASCO C3, PA 262) the automatic front gives 2480 ± 90 km/s against 2970 km/s from the CDAW leading-edge heights: it lies behind the leading edge, so set points by hand for leading-edge speeds.
* **Radio occultation:** for a spacecraft (Mars Express, Juno, BepiColombo, Solar Orbiter, Parker Solar Probe, STEREO-A, MAVEN, MRO, Akatsuki, or any NAIF ID) and a DSN station over an interval: the SPICE ray geometry (light-time corrected spacecraft position, closest approach to the Sun in R☉ and its heliographic position, solar elongation, range rate, geometric Doppler), and along the ray the electron column, the plasma Doppler shift +40.3/(c f) dTEC/dt and, with a field model, the rotation measure and Faraday rotation. Density: Leblanc, Dulk & Bougeret (1998, doi:10.1023/A:1005049730506) or Baumbach-Allen (Allen 1947, doi:10.1093/mnras/107.5-6.426); field: a Parker spiral of chosen polarity, or the PFSS source-surface field carried along Parker spirals. Kernels: the NAIF generic kernels (DE440s, station positions, Earth orientation; downloaded once, about 60 MB) and, for the spacecraft, an SPK from the NAIF or ESA SPICE server or one written from JPL Horizons vectors. Measured polarization angles can be freed of the 180° ambiguity (jumps removed, and shifted towards the model by a multiple of 180°). Compared with published Faraday rotation: Ingleby, Spangler & Whiting (2007, ApJ 668, 520, doi:10.1086/521140) measured with the VLA at 1.5-1.7 GHz the rotation measures of 18 extragalactic sources seen 5.6-9.7 R☉ from the Sun in March-April 2005 (-25 to +61 rad/m², rms 16.5 rad/m²). For the same lines of sight (their source positions and dates) the elongations computed here agree with theirs to 0.1°. At 6.2 R☉ the Leblanc density (1.3×10⁴ cm⁻³) is 0.54 times their LASCO-based value (2.4×10⁴ cm⁻³) and the Parker field (42 mG) lies inside their range of 30-78 mG. With a flat current sheet on the solar equator the rotation measures come out at an rms of 3.6 rad/m² with the wrong sign for 13 of the 18 sources: the size and sign of the rotation are set by where the line of sight crosses the warped current sheet, so the Parker-spiral model gives only the order of magnitude of n B; a model of the actual sheet, such as the PFSS option (GONG maps from 2006 on), is needed for a given date (it could not be tested on these 2005 data).
* **Event correlation:** for a disturbance at a time, height (R☉) and position angle (from solar north through east, seen from Earth), e.g. the closest point of an occultation ray (its position angle is given with the other results, checked against the celestial position angle minus the solar P angle to 0.1°) or a coronagraph front, the CMEs of the SOHO/LASCO CDAW catalogue (Yashiro et al. 2004, doi:10.1029/2003JA010282), CACTus (Robbrecht & Berghmans 2004, doi:10.1051/0004-6361:20041302) and DONKI (NASA CCMC) that reach that height within a window, at their catalogue speed from the catalogue's reference height (CDAW: first height of its height-time file; CACTus: onset taken at 2.2 R☉; DONKI: time at 21.5 R☉), marked by whether the position angle lies in their angular extent (halos, and DONKI cones containing the Sun-Earth line, cover all), and the GOES flares of the NOAA SWPC list (through HEK) and DONKI flares of the day before. For the CME of 10 September 2017 at 15.8 R☉, PA 262 at 16:42 UT (CDAW leading edge 15.77 R☉ at 16:42), CDAW predicts 16:47 and DONKI 16:53, with the X8.2 flare of AR 12673 (peak 16:06) in both flare lists; the CACTus detection starts later (16:48).
* **Corona to L1:** a CME from a measured height, time and speed (e.g. the J-map fit, with the drag-based model of the CME solver, Vršnak et al. 2013) or a solar wind stream leaving the source surface at a constant speed (the inverse of the PFSS ballistic mapping) is followed to L1; the predicted arrival and speed are compared with the nearest fast forward shock of the IPShocks database at the chosen spacecraft (WIND, ACE or DSCOVR; any of them if none) within 24 h, and drawn over the speed measured there (NASA CDAWeb, 5-minute means, two days either side). For the CME of 10 September 2017 (C3 front 22.9 R☉ at 17:30 UT, 2480 km/s) the default drag (Γ = 10⁻⁷ km⁻¹, w = 420 km/s) predicts 13 September 07:27 UT at 464 km/s, 12.1 h after the shock observed by WIND on 12 September 19:21 UT (downstream 547 km/s); with Γ = 0.2×10⁻⁷ km⁻¹ it predicts 19 h early at 791 km/s. The CME left from the west limb, so Earth met its flank. The IPShocks snapshot reaches March 2024.
* **Active region map:** the numbered regions of the latest NOAA SWPC solar region summary (position, Mount Wilson and McIntosh class, area, flares of the day, SWPC 24-hour C/M/X probabilities) on a **drawn** disk. The 193/304/171/131 Å and C2 buttons only change the drawing style; they are not images.
* **CME solver:** speed from two plane-of-sky heights and the time between them, then arrival at L1 and Earth with the drag-based model of Vršnak et al. (2013) (ambient wind w and drag parameter Γ adjustable) next to the empirical arrival model of Gopalswamy et al. (2001). The presets reproduce the SOHO/LASCO linear speeds of the CDAW catalogue for May 2024 (1280 km/s), Halloween 2003 (2459 km/s) and Bastille Day 2000 (1674 km/s); Carrington and Nominal are illustrative. No projection correction is applied (halo CMEs are faster along the Sun-Earth line than in the sky plane); the shock Mach number and the Kp category are rough estimates and say so.

### Parker Spiral & CIR

Archimedean spiral field lines for a chosen wind speed, the spiral angle at 1 AU and the longitude of the footpoint magnetically connected to Earth (important for solar energetic particles), with sector boundaries and stream interaction regions drawn schematically, and the orbit of Parker Solar Probe.

**Coronal magnetic field (PFSS).** A potential field source surface model (sunkit-magex, the successor of pfsspy; Stansby et al. 2020, doi:10.21105/joss.02732) of the latest GONG, ADAPT (realization 0) or HMI synoptic map before a chosen time (HMI needs an e-mail address registered with JSOC). The wind now at Earth is mapped back ballistically (Neugebauer et al. 1998, doi:10.1029/98JA00798): source-surface longitude = sub-Earth Carrington longitude + Ω(1 AU − r_ss)/V. The field line traced down from there gives the solar source (open field in a coronal hole or at the edge of an active region, |B_r| ≥ 50 G at the footpoint), its polarity and its angular distance from the heliospheric current sheet (B_r = 0 on the source surface). Field lines can be traced from any point between 1 R☉ and the source surface. Optional dependencies: `pip install "helios-l1[solar]"`.

### FFT Turbulence & PSD

Power spectrum of one field or plasma quantity from 1, 3 or 7 days of 1-minute data, the fitted spectral index compared with Kolmogorov (-5/3) and Iroshnikov-Kraichnan (-3/2), the RMS fluctuation and the length scale V/f at 1 mHz (Taylor's frozen-in flow). At 1-minute resolution the spectrum ends below 8.3 mHz (the Nyquist frequency), far below the ion scales, so it covers the energy-containing and inertial ranges only.

---

## 5. Geospace & Hazards

### Auroral Oval & Map

The Starkov (1994) oval (poleward and equatorward boundaries and the equatorward edge of the diffuse aurora, coefficients from Sigernes et al. 2011) for any UTC time, driven by OMNI AL when OMNI covers the time, otherwise by Kp converted to AL, or by an AL you enter (limited to 18-750 nT). Hemispheric power from Kp (Zhang & Paxton 2008) is an estimate, not a measurement. The region list picks one of four fixed lists from the equatorward boundary at magnetic midnight; it is a rough guide, not a probability of seeing the aurora.

The Dst panel runs the Burton et al. (1975) or O'Brien & McPherron (2000) model on the L1 solar wind shifted to Earth, starting from the observed Kyoto real-time Dst, and scores it against that Dst.

### Storm Forecast

A 12-hour Kp trajectory from the Newell et al. (2008) coupling fit and an O'Brien-McPherron Dst trajectory, both from the latest solar wind **held and relaxed towards quiet values** (an assumption, written under the chart; it is not a forecast of the solar wind). The storm probabilities and the yellow Kp line are NOAA SWPC's own forecast (3-day geomagnetic forecast; Kp forecast product, whose values are "estimated" for the current UTC day and "predicted" after it).

### Terrestrial Hazards & Solar Cycle

* **Solar cycle:** observed monthly and 13-month smoothed sunspot number (SILSO) and F10.7 with NOAA SWPC's predicted cycle; cycle 24 aligned on its minimum for comparison.
* **D-RAP:** the flare part of NOAA's D-Region Absorption Prediction: HAF = 10 log10(Fx) + 65 MHz, reduced by cos^0.75 of the solar zenith angle, and absorption (HAF/f)^1.5 dB. The proton (polar cap) part is not modelled.
* **GIC:** the geoelectric field of a uniform ground of one resistivity (Precambrian shield 5000 Ω·m, 500 or 50 Ω·m) with the plane-wave surface impedance (Boteler & Pirjola 2017) for a chosen dB/dt and geology, with the voltage along a 200 km line and an example transformer neutral current. These are order-of-magnitude illustrations: real fields depend on the local conductivity profile.

### Storms Archive

Historical storms. Events since 1995 load measured OMNI data (5-minute means) and compare SYM-H with both ring current models; March 1989, Carrington 1859 and the quiet baseline are synthetic profiles and labelled so.

---

## 6. Data Studio & Science

### 6.1 Custom Ingestion & OMNI

Paste or upload CSV, tab- or space-delimited text, JSON (record lists, NOAA SWPC header-row products) or HELIOS-L1's own CSV/JSON exports (files up to 64 MB). Column names are matched without regard to case, spaces or units in brackets; recognised names include `time`, `epoch`, `speed`, `Vp`, `proton_speed`, `density`, `Np`, `temperature`, `Tpr`, `bx/by/bz` (taken as GSM), `bx_gse ...` (rotated to GSM for each row's time, Hapgood 1992 with the IGRF-14 dipole) and OMNI's `YEAR DOY HR MN`. OMNI and CDF fill values are treated as missing; unused columns are listed. CDF and NetCDF files must first be listed as text (for example CDAWeb's ASCII output).

The five profile cards are hand-written illustrations for trying the pipeline, not measured data.

After import the tab shows the summary, the time series and a **shock screening**: each sample is compared with the one three samples earlier and a jump with ΔV ≥ 45 km/s, N2/N1 ≥ 1.5 and B2/B1 ≥ 1.35 is listed with a rough Mach proxy (1 + ΔV/70 km/s). This only finds candidates; use the shock analysis of Event Analysis for normals, speeds and Mach numbers.

### 6.2 Event Analysis

Forms for each method (section 7), with example buttons for the checked events. Times are UTC (`YYYY-MM-DDTHH:MM`). Limits: field and plasma analyses up to 72 hours, the time shift up to 48 hours of arrival times, magnetic cloud search up to 31 days, the sudden commencement search up to 366 days, superposed epoch analysis up to 60 onsets and 180 days of data in total. Every panel has *Save JSON* (and CSV where it fits) with the datasets, HAPI requests, parameters and software version. Under the shock, minimum variance, deHoffmann-Teller, coupling, magnetic cloud search and flux rope results, *Data coverage* gives for the field and for the plasma the fraction of the analysed interval covered, the number of gaps and the longest one (gaps longer than five sample intervals and a minute; "> 99.9 %" when only a short gap remains), so an analysis over a data gap is visible at once. The storm finder, the Dst model skill and the OMNI statistics name any year of hourly OMNI that could not be read.

### 6.3 ICMEs: the Richardson & Cane list

The Event Analysis tab lists the near-Earth interplanetary coronal mass ejections of the list kept by I. G. Richardson and H. V. Cane since 1996 (disturbance time, ICME start and end, magnetic cloud, reported fast shock, mean speed and |B|, the minimum Dst they attribute to the ICME and the quality of the boundary times), as a table or CSV; the legend above the table explains each column from the list's footnotes. The live list is read when the network is available (kept for a week); otherwise the bundled snapshot is used, and every answer says which. The same list marks:

* each storm of the storm finder: whether its Dst minimum (the middle of the hour) lies in an ICME, in its sheath (from the disturbance to the ICME start), or in the 3 h after the ICME end (the list attributes a storm to an ICME "or slightly thereafter");
* each magnetic cloud candidate: the listed ICMEs it overlaps and the fraction of it inside the ICME;
* a shock analysed at L1: the listed disturbance 1 h before to 3 h after it (typically the sudden commencement at Earth some 30-60 min later).

Checks: the parser reads all 644 events of the July 23, 2026 revision exactly as the authors' spreadsheet on Harvard Dataverse lists them; 89 of the 98 WIND magnetic clouds (Lepping et al.) since 1996 lie inside a listed ICME, all flagged as magnetic clouds; for the 514 ICMEs with final Dst, the minimum of OMNI hourly Dst from the disturbance to the ICME end (or the next disturbance) plus 1 h equals the listed value for 79 % and is within 2 nT for 90 % (the rest are the authors' attributions when ICMEs overlap or Dst was already depressed). Of the 90 storms of 1996-2006 at or below -100 nT, 75 have their Dst minimum in a listed ICME (57), its sheath (14) or the 3 h after it (4); all ten at or below -250 nT lie in an ICME (7) or its sheath (3). The list is the authors' judgement and "a work in progress": an unmatched storm may still have an ICME driver.

### 6.4 Interplanetary shocks: the IPShocks database

The *Interplanetary shocks at L1* panel lists the fast forward and fast reverse shocks of the IPShocks database (University of Helsinki) found at WIND, ACE and DSCOVR, 1064 shocks from December 1994 to March 2024 in the version of 24 April 2026, with the database's own values: 8-minute averages from 9 to 1 minutes before and 2 to 10 minutes after a fast forward shock (2-10 min before and 1-9 min after a reverse one), the mixed-mode normal MX3, θBn, the shock speed from mass flux, the Alfvén Mach number and the magnetosonic one (sound speed with a fixed electron temperature of 146,277 K), the jumps, and the database's errors (standard deviations of the window means, propagated). *Analyse* runs the shock analysis of section 6.2 with the same windows at the listed time (the time is not refined). The shock analysis shows the listed shock at the same spacecraft within 5 minutes next to its own values, with the angle between the two normals. The list is bundled (CC BY 4.0, doi:10.5281/zenodo.19730292); cite it with Kilpua et al. (2015, JGR 120, 4112).

How the shock analysis compares, with the database's windows and times: for the 288 fast forward shocks at ACE (1998-2021) the MX3 normal is 1.2° from the listed one on median (90 % within 3.8°), θBn 0.7° and the shock speed 4 km/s (90 %: 15 km/s), all within the listed errors. The rest comes from the time tags: the database moved ACE records from the start to the middle of their 16-s (MAG) and 64-s (SWEPAM) intervals, as the ACE Science Center describes its Level 2 time stamps; moved the same way, the normals agree to 0.4° on median (90 %: 1.3°), about the rounding of the listed normals. The tags are used as given here, because the data do not bear the move out: the 16-s field values equal means of the 1-s field (stamped without the ~5 s light-time error of the other Level 2 data) centred 1.5 s before to 3.5 s after their tags on 16 days of 1998-2024, not 8 s after; and at 273 of these shocks the 64-s density jump comes 4 ± 2 s before the field jump in tag time, where start-of-interval stamps on both would put it 24 s before. For 188 of 200 fast forward shocks at WIND drawn at random from 2004-2024 (11 had too few spectra in a window, 1 no data): normal 2.4° (90 %: 8.6°), θBn 0.8°, speed 9 km/s on median, 99 % of θBn and 94 % of speeds within the listed errors; the upstream densities from the SWE non-linear fits used here are 5 % below the database's. For 21 shocks at DSCOVR (2016-2019): 0.2°, 0.01° and 0.1 km/s. The Alfvén Mach numbers here are 2-3 % higher on median: the upstream |B| here is that of the mean vector (1-2 % below the mean magnitude the database uses) and the database averages the Alfvén speed over samples.

### 6.5 Sudden commencements

The *Sudden commencements in SYM-H* panel searches OMNI 1-minute SYM-H over up to 366 days for sudden commencements: a rise of at least 10 nT within 4 minutes holding a 1-minute step of at least 4 nT, after a quiet hour (median absolute 1-minute change at most 0.5 nT, or the largest step at least 20 times that median), that keeps at least half its amplitude over the next 15 minutes and comes with a jump of OMNI's solar wind flow pressure by at least half (medians of the hour after the onset against 60 to 10 minutes before; the hour-long windows absorb OMNI's time-shift errors, which reach tens of minutes). A step without pressure data is kept and marked "no data". The onset is the first minute of the rise; the table gives the amplitude, rise time, largest step, quiet-hour change and the pressures before and after.

The detections are compared with the lists of the International Service on Rapid Magnetic Variations (Observatori de l'Ebre, for ISGI) for the years of the interval, read from the observatory (definitive lists to 2022, preliminary ones since; definitive lists are cached for good, preliminary ones for a week) and not bundled, as they are licensed CC BY-NC 4.0. A listed SC (SSC or SI since 2006, SC before) counts as found when a detected onset lies within 3 minutes of it. The table shows each detection with its listed match and the listed SCs that were not detected; *Show* draws SYM-H and the flow pressure from 60 minutes before to 90 minutes after. *L1 shock* names the fast forward shock of the IPShocks database (section 6.4) whose front, taken as planar with the listed normal n and speed V_sh, reaches the Earth (t + |n·r|/V_sh from the spacecraft position r) within 15 minutes of the onset, and how far the onset is from that arrival. At the 617 detections of 1995-2023 (the database ends in March 2024) 382 have one, 83 % of those in the Ebre lists and 26 % of the others; the onsets came 0.0 min after the predicted arrival on median (half within -1.7 to +1.6 min), while the radial X/V_sh puts the arrival 4 min late on median; a random time lies this close to a predicted arrival 0.13 % of the time. *Hp30 max, 24 h* is the highest half-hourly GFZ Hp30 in the 24 hours from the onset, with the start of its half hour: the activity that followed. It does not relabel the list's SSC and SI: the threshold the lists state for an SSC (Dst at or below -50 nT or Kp at least 5o within 48 h) reproduces only 64 % of their labels of 2006-2026 with OMNI's hourly Dst and Kp (330 listed events; calling all of them SSC would give 81 %). *Use as epoch onsets below* copies the detected onsets (at most 60) into the superposed epoch analysis.

How it was checked: OMNI SYM-H and pressure of 1995-2024 against the Ebre lists of those years, the thresholds of the step, quiet-hour, persistence and pressure tests chosen on the odd years and the even years held out. Over the 30 years 420 of the 566 listed SCs are found (74 %; 75 % in the held-out years): 90 % of those above 15 nT (mean amplitude at the five low-latitude list observatories), 59 % of those of 10-15 nT and 25 % of those up to 10 nT; of the SCs listed since 2006, 78 % of the SSCs and 60 % of the SIs. 95 % of the found onsets are within a minute of the listed time. Of the 663 detections, 243 are not listed (37 %; 34 % in the held-out years); 62 of these follow a fast forward interplanetary shock at L1 (WIND, ACE or DSCOVR) in the IPShocks database (doi:10.5281/zenodo.19730292, CC BY 4.0) by the expected travel time, and most of the others are SYM-H steps under a jump of the solar wind pressure: the lists, made by eye from five low-latitude magnetograms, leave out many clear steps. The preliminary lists of 2025-2026 (SYM-H to September 2026): 23 of 29 found, 14 of 37 detections not listed. Limits: a commencement in a disturbed record whose step is under 20 times the background change is missed (25 March 2015, 13:20); OMNI pressure is missing for 10 % of the detections.

### 6.6 References & Portals (key P)

Equations with DOIs, data portals, licences, a parameter handbook, the in-app guide and an interactive solver for the boundary and coupling formulas.

---

## 7. Event analysis methods and how they were checked

| Method | What it gives | Checked against |
|---|---|---|
| Interplanetary shock (`/api/analysis/shock`) | Normals from magnetic and velocity coplanarity and the mixed-mode methods MX1-3 (Schwartz 1998), shock speed from mass flux, θBn, jumps, Alfvén and fast Mach numbers, Monte Carlo uncertainties; shock time refined to the |B| ramp | Harvard-Smithsonian CfA shock database: 17 Mar 2015 (MX3 normal within 1°, θBn 60.5° vs 60.1 ± 3.1°, 540 vs 536 ± 3 km/s), 27 Feb 2014 (normal within 1°, 439 vs 436 km/s), 22 Jun 2015 (2.5° from the CfA Rankine-Hugoniot normal). IPShocks database with its windows: MX3 normals 1.2° from the listed ones on median for 288 ACE shocks (0.4° with mid-interval ACE time tags), 2.4° for 188 WIND and 0.2° for 21 DSCOVR shocks; θBn and speeds within the listed errors for 94-100 % (section 6.4) |
| Multi-spacecraft timing (`/api/analysis/timing`) | Predicted arrival at the other spacecraft from the normal and speed, observed arrival, residual, and the arrival listed there in the IPShocks database | 27 Feb 2014 WIND to ACE: 1016 s predicted, 1103 s observed, within the CfA ACE arrival ± 80 s and 2 s before the IPShocks one. How good planar timing can be: with the IPShocks normals and speeds, the 219 shocks listed at both WIND and ACE (1998-2021) arrive 81 s from the prediction on median when the spacecraft are less than 50 R_E apart across the Sun-Earth line, 137 s at 50-100 R_E, 222 s at 100-200 R_E and 581 s further apart |
| Minimum variance (`/api/analysis/mva`) | Eigenvalues and vectors, ratios, angular errors (Sonnerup & Scheible 1998, eq. 8.23), bootstrap | AMPTE/IRM benchmark of ISSI SR-001 ch. 8 (Table 8.4): eigenvalues 1012.86 / 137.91 / 7.08 (published λ2 138.01), normal to 4 decimals, angular errors as published |
| deHoffmann-Teller (`/api/analysis/ht`) | V_HT, frame quality, error ellipsoid (eq. 9.16) and bootstrap, normal velocity, Walén slope | ISSI SR-001 ch. 9 benchmark: c = 0.994 and D ratio 0.012 as published, error semiaxes 7.54 / 4.54 / 3.90 km/s (published 7.62 / 4.59 / 3.94) |
| Lundquist flux rope (`/api/analysis/fluxrope`) | Axis, B0, handedness, closest approach, diameter, axial flux, χR, 1σ errors from Lepping et al. (2003) | WIND MFI magnetic cloud table: axis within 9-18°, B0 within 6 % for three clouds; error program reproduces Table 5 of Lepping et al. (2006) for 48 of 50 clouds |
| Magnetic cloud search (`/api/analysis/mcdetect`) | Candidate regions with the Lepping et al. (2005) tests (loose or strict) | Run on November 1997 WIND data (4 of 7 candidates pass, flux rope fitted); no published candidate list was reproduced. Short failing stretches are bridged, an addition of this application (the paper gives no rule) |
| Time shift to the bow shock nose (`/api/analysis/timeshift`) | Delay of every 15-16 s field vector to the bow shock nose by OMNI's phase front method, shifted 1-min field and plasma, flat ΔX/Vx delay, OMNI comparison | OMNI HRO `Timeshift`, minutes OMNI took from the same spacecraft (2 days each): ACE 15-16 Mar 2015 99 % within 1 min (flat delay 8 %), ACE 19-20 Nov 2003 86 % (33 %), WIND 11-12 Sep 2017 77 % (32 %) and 1-2 Sep 2018 73 % (11 %) with WIND near the Sun-Earth line; with the spacecraft far off it, WIND 15-16 Mar 2015 at Y = +58 R_E 43 % (3 %) and ACE 1-2 Jun 2002 at Y = +34 R_E 54 % (10 %). Phase front normals 1.5° (median) from those in OMNI's shifted WIND file for 15-16 Mar 2015, 71 % within 5° |
| Coupling functions (`/api/analysis/coupling`) | Newell dΦ/dt, Akasofu ε, V·Bs, dynamic pressure, proton beta and Alfvén Mach number per plasma sample, measurement and sampling uncertainty of the means | Independent recomputation and Monte Carlo draws from the WIND SWE speed, density and thermal speed errors (within 5 %). Beta and M_A in OMNI's conventions against OMNI HRO's own values in the minutes it took from WIND: median ratios 1.10 and 1.03 (11-12 Sep 2017), 1.04 and 1.02 (1-2 Sep 2018), the difference of OMNI's normalized key-parameter densities and temperatures from the non-linear fits used here (density ratio 1.05 and 1.035 on median) |
| Sudden commencements (`/api/analysis/sudden_commencements`) | Onsets of SYM-H steps after a quiet hour, persistent and with a solar wind pressure jump; amplitude, rise time, largest step; match in the Ebre lists | Ebre lists 1995-2024: 420 of 566 listed SCs found (74 %, 90 % above 15 nT), 243 of 663 detections not listed (37 %), 62 of these after an IPShocks shock at L1; thresholds chosen on odd years, even years held out (75 % found, 34 % not listed) |
| Superposed epoch (`/api/analysis/superposed`) | Mean, median, quartiles, counts per bin, bootstrap 95 % intervals; OMNI 1-min quantities and the GFZ indices Kp and Hp30, each held over its 3-hour or half-hour interval | Synthetic events: interval width 2·1.96·σ/√N within 15 %. GFZ Kp equals OMNI's hourly Kp (in tenths) in every compared hour of 2003, 2015 and 2024; 17 Mar 2015 and 10 May 2024: Kp 8- from 12 UT and 9o from 00 UT on 11 May, Hp30 9- at 13:30 and 11- at 22:30, as GFZ lists them |
| Storm selection (`/api/statistics/storms`) | Runs of Dst below a threshold, joined across short recoveries, with the solar wind before each minimum | Echer et al. (2008): 90 storms ≤ -100 nT in 1996-2006; minima of the ≤ -250 nT storms -263 to -422 nT |
| Dst model skill (`/api/statistics/dst_models`) | Burton and O'Brien-McPherron per storm and averaged, 95 % intervals over storms | Ji et al. (2012): O'Brien-McPherron r 0.90/0.84/0.87/0.89 by storm type (theirs 0.90/0.80/0.87/0.90) |
| OMNI statistics (`/api/statistics/omni`) | Distributions, joint histograms, conditional means, correlations, yearly/monthly means with filters | Daily means equal NASA's published daily averages within their rounding for all days of 1995-2024; Xu & Borovsky (2015) classes give 88.5 % ejecta inside the WIND magnetic clouds (87.5 % in Li et al. 2020) |

Known differences that remain: the time shift is built from OMNI's published description (and Weimer's published MVAB-0 routine), not from OMNI's processing code; WIND delays come out 0.3 min longer than OMNI's on median near the Sun-Earth line (0.7 min at Y = +58 R_E), ACE delays within 0.1 min. Planar phase fronts can misplace a shock: on 7 Sep 2017 the WIND shock reaches the bow shock nose at 23:11 in OMNI and 23:12 here while SYM-H jumps from 23:00. The Burton model's RMSE and minimum error differ from Ji et al. (2012), whose Burton constants are not given; the Rankine-Hugoniot shock normal of the CfA database (RH08-RH10) is not implemented.

---

## 8. Uncertainties and their limits

* **Autocorrelation.** Solar wind and index series are strongly autocorrelated, so consecutive minutes are not independent. Correlations, means and RMSEs carry 95 % intervals based on an effective sample size from the lag-1 autocorrelation (Bretherton et al. 1999 for r with the Fisher z interval; Wilks 2011 for means). When fewer than about 10 independent samples remain, the answer says so and the interval is missing or too narrow: one storm is roughly 1-3 independent samples, which is why model skill should be judged over many storms (Dst model skill panel).
* **Comparator lag.** The bootstrap interval is conservative: in simulations it covered the true lag in 99-100 % of cases with a spread 1.3-1.6 times the actual one.
* **Shock parameters.** Uncertainties come from Monte Carlo draws of the upstream and downstream window means. Compared with the CfA database, normal and θBn spreads come out smaller and speed spreads larger; the CfA error method is not documented, so the two are not directly comparable.
* **Flux rope errors** are those of the Lepping et al. (2003) simulation study, not of the fit; outside its range (χR, cone angle, closest approach) the panel warns that they are extrapolated.
* **Coupling functions, beta and Mach number.** Only WIND SWE gives per-spectrum speed, density and thermal speed errors; for ACE and DSCOVR only the sampling interval is given, and field errors are in none of the archives.
* **Models.** The auroral oval, the ring current models, the CME arrival times, D-RAP and GIC are empirical or idealised models with their own scatter; their outputs carry no error bars beyond what is stated next to them.

---

## 9. Measured, simulated and synthetic values

Every record has a `data_source` and every API answer a `provenance` block:

| Kind | Meaning |
|---|---|
| `observed` | Measured: NOAA RTSW or the NASA CDAWeb archive. |
| `simulated` | No data for this mission and window (Aditya-L1, SOHO, GOES-16 Hp, STEREO-A; WIND before the archive reaches the window): the operational L1 stream with fixed offsets and noise. Not a measurement. Aditya-L1 Level-2 data are on ISRO's PRADAN portal for registered users only and cannot be fetched without your own login. |
| `synthetic` | Nothing could be reached and nothing was cached: values from the offline solar wind model; also the historical storm profiles built from published peaks. |
| `imported` | Rows from your file. |

Missing values stay empty. Rows with a non-zero RTSW quality flag are dropped. When Kp cannot be fetched, a Bz-based estimate is used and labelled (`kp_source`).

---

## 10. Data sources, terms of use and citation

| Source | Used for | Terms and credit |
|---|---|---|
| NOAA SWPC (services.swpc.noaa.gov): RTSW, ephemerides, GOES X-rays and protons, Kp and forecasts, Kyoto Dst feed, solar regions, solar cycle, LASCO and SUVI images | Live views | U.S. Government work, public domain in the U.S. (17 U.S.C. § 105); credit NOAA SWPC. |
| NASA CDAWeb HAPI (cdaweb.gsfc.nasa.gov/hapi): WIND MFI/SWE, ACE MAG/SWEPAM, DSCOVR MAG/FC, OMNI | Archive, event analysis, statistics | NASA open data; acknowledge the instrument teams and CDAWeb. For OMNI cite King & Papitashvili (2005, JGR 110, A02104). |
| WDC for Geomagnetism, Kyoto: Dst, SYM-H, ASY-H, AE (via NOAA and OMNI) | Ring current, storms | Free for scientific use, **no commercial use**; acknowledge the data suppliers and WDC Kyoto and include the index DOIs in references. Real-time (quicklook) values: contact WDC Kyoto before using them in publications. |
| GFZ German Research Centre for Geosciences: Kp and Hp30 (kp.gfz.de web service, read for the years asked for and cached) | Superposed epoch analysis | CC BY 4.0; name GFZ as the data source; cite Matzka et al. (2021, Space Weather 19, e2020SW002641; data doi:10.5880/Kp.0001) for Kp and Yamazaki et al. (2022, GRL 49, e2022GL098860) for Hp30. |
| WDC-SILSO, Royal Observatory of Belgium (via NOAA and OMNI) | Sunspot number | CC BY-NC 4.0; "Source: WDC-SILSO, Royal Observatory of Belgium, Brussels", doi:10.24414/qnza-ac80. |
| SOHO LASCO (ESA/NASA), GOES SUVI (NOAA) | Images | Credit SOHO/LASCO (ESA & NASA) and NOAA GOES SUVI. |
| Richardson & Cane list of near-Earth ICMEs since 1996 (izw1.caltech.edu/ACE/ASC/DATA/level3/icmetable2.htm; a snapshot of the July 23, 2026 revision is bundled) | ICME list panel; storms, shocks and cloud candidates marked with it | CC0 1.0 (Harvard Dataverse); cite doi:10.7910/DVN/C2MHTH with Cane & Richardson (2003, JGR 108, 1156) and Richardson & Cane (2010, Sol. Phys. 264, 189). |
| Sudden commencement lists of the International Service on Rapid Magnetic Variations, Observatori de l'Ebre (obsebre.es/en/variations/rapid), read for the years asked for and cached | Sudden commencement panel | CC BY-NC 4.0, **no commercial use**; credit the International Service on Rapid Magnetic Variations, Observatori de l'Ebre, for ISGI, and INTERMAGNET for the observatory data. |
| IPShocks database of interplanetary shocks at WIND, ACE and DSCOVR (doi:10.5281/zenodo.19730292; bundled snapshot of the version of 24 April 2026) | Shock list panel; the listed values next to the shock analysis; validation of the sudden commencement search | CC BY 4.0; cite Kilpua, E., Good, S., Soljento, J., Price, D. J., Isavnin, A., Lumme, E., Mäkelä, T. V., Isavnina, K. & Andréeová, K., The IPShocks Database, doi:10.5281/zenodo.19730292, and Kilpua et al. (2015, JGR 120, 4112). |
| Harvard-Smithsonian CfA Interplanetary Shock Database; WIND MFI magnetic cloud table and error program (wind.nasa.gov/mfi) | Validation of shocks and flux ropes | Cited in the CHANGELOG where used. |
| NAIF generic kernels (`naif0012.tls`, `pck00010.tpc`, `gm_de431.tpc`), IGRF-14 coefficients (NOAA NCEI) | Ephemerides, GSE-GSM rotation | Public. |

The mission cards in the Fleet Catalog repeat the data policies as the agencies state them.

---

## 11. Exports and the API

* **CSV** (domain bar, archive panel, analysis panels): starts with `# key: value` lines (data kind, provenance, datasets, coverage, cadence, units). Read with `pandas.read_csv(path, comment="#")`, or add `metadata=false` to `/api/export/csv` for a bare table.
* **PNG** (*Plot*): the live dashboard charts; archive intervals are exported as CSV.
* **Summary** (Markdown) and **Bulletin** (HTML): the current alert levels and 24-hour extremes with their provenance.
* **JSON** from every analysis panel, or add `&download=true` to an analysis URL.
* **API:** the server answers on `http://127.0.0.1:<port>/api/...` (examples for each analysis are in the README). It accepts only requests addressed to 127.0.0.1/localhost and refuses requests a browser sends for another web site; scripts and `curl` work. POST bodies must be JSON with `Content-Type: application/json`. `GET /api/status` answers `{"status": "online", ...}` and serves as a health check.

---

## 12. Troubleshooting

| Problem | What to do |
|---|---|
| The window does not open, the dashboard opens in the browser | No window backend: install WebView2 (Windows), or GTK/Qt bindings on Linux (section 1). The browser works the same. |
| "could not listen on 127.0.0.1:<port>" | Another program holds the port. Start with `--port 8790` (any free port). |
| Values say SIMULATED or SYNTHETIC | The source has no data for that window or could not be reached (section 9). Check the network; cached data are used when available. |
| An archive interval is empty | The archive has not reached that date yet (key parameters lag days, Level 2 and OMNI months), or the instrument has no data then (DSCOVR plasma only 2016-2019). Try OMNI or another spacecraft. |
| The comparator finds no overlap | The two series cover different times; the message gives each side's coverage. For a file, the archive is used for its interval (section 3). |
| An analysis says too few samples or poorly determined | Lengthen the window, check the plasma coverage, or read the warning: for example λ2/λ3 < 10 means an MVA normal that should not be used. |
| Settings are not kept | The dialog says when `settings.json` could not be written (read-only or locked folder). Use `HELIOS_HOME` to point to a writable folder. |
| Old or wrong cached data | Close HELIOS-L1 and delete the cache folder (section 1); it is filled again on demand. |
| An update was not installed | Settings, *Updates* gives the reason (for example a download whose digest did not match, or a folder that is not writable). The install script writes `updates/install.log` in the settings folder. Deleting `<folder>.update` beside the installation discards a downloaded build. |
| Anything else | The log file in the logs folder records failed downloads and errors. |
