# Changelog

## Unreleased

### Data acquisition
- The NOAA `/products/solar-wind` plasma and magnetometer JSON products used for "live" data now return HTTP 404, so every live view had been showing synthetic model output without saying so. Live solar wind now comes from the NOAA SWPC RTSW 1-minute feeds. The DSCOVR view shows the operational L1 stream (the supplying spacecraft, e.g. SOLAR1, is recorded per record); the ACE view shows real ACE data.
- Every record has a `data_source` label (`observed`, `simulated`, `synthetic`, `imported`) and every API response a `provenance` block (description, source spacecraft, UTC coverage, cadence). The feed badge in the dashboard shows which kind of data is on screen.
- Missing values stay null. Previously missing field values became 0 nT and missing plasma values were replaced by 400 km/s and 4–5 cm⁻³ before computing derived quantities.
- 7-day views are 5-minute block averages instead of every fifth sample.
- HTTP error pages and non-JSON responses fall back to the cached copy; cache files are written atomically.
- NOAA G/R/S scales use observed planetary Kp, GOES X-ray and ≥10 MeV proton flux instead of a Kp guessed from Bz and fixed X-ray (1.5e-6 W/m²) and proton (1.2 pfu) values.

- Real archive data from NASA CDAWeb through its HAPI server for WIND (MFI 1-min, SWE), ACE (MAG and SWEPAM Level 2, then preliminary key parameters), the DSCOVR science archive (1-s magnetometer from 2015, Faraday cup 2016-2019) and OMNI 1-min HRO. Dataset IDs and parameter names were checked against the live HAPI catalog. Declared fill values and samples flagged bad by the instrument teams are dropped; data are reduced to 1-minute means and cached per day (days that ended more than two days ago are kept, recent days are re-checked every six hours).
- New `/api/archive/{mission}?start=&end=&cadence_minutes=` endpoint (JSON or `format=csv`) returns measured data for any interval of up to 31 days, with the datasets used, their level and coverage in the provenance. `/api/archive` lists the sources.
- WIND is no longer simulated when the archive has data for the window. The 7-day DSCOVR and ACE views use archive data where it exists and the RTSW feed only after the archive's last sample, instead of showing just the ~24 h RTSW window. When the archive has nothing yet (it lags real time by days to months), the view says so and keeps the labelled fallback.
- Historical events (May 2024, St. Patrick's Day 2015, Halloween 2003, Bastille Day 2000) show 48 h of real OMNI data as 5-minute means, with the observed extremes next to the published values. Events without OMNI coverage (March 1989, Carrington 1859) and the quiet baseline remain illustrative synthetic profiles, labelled as such.

### Scientific corrections
- Akasofu ε lacked the 4π/μ₀ factor of the SI form and was 12.6 times too small (500 km/s, 10 nT southward: 994 GW, previously 79 GW).
- Shue et al. (1998) flaring exponent used ln(P_dyn + 1) instead of ln(P_dyn) (API and in-browser calculator).
- Flare class is the real GOES class (e.g. X5.3); before, it was the R-scale threshold label ("X1" for an X5.3 flare, "B" for A-class). Without proton data the S-scale says so instead of using an invented 0.8 pfu.
- Spectrum tab: the sample interval is taken from the time stamps (it was fixed at 60 s, so 5-minute data had all frequencies 5× too high); gaps are interpolated instead of spliced out; the PSD is one-sided and window-normalised in (unit)²/Hz.
- Dst (Burton/O'Brien–McPherron) simulation used a fixed 5-minute step, so 1-minute data ran five times too fast. The step now comes from the time stamps and uses the exact solution over each step.
- Cross-correlation lag had the opposite sign to the theoretical propagation delay it is compared with. Positive now means spacecraft B observes later than A.
- Comparator no longer bridges long data gaps with interpolated values that were then counted as real samples; mixed time zone formats can be compared.
- A single interplanetary shock was reported up to three times; it is now one event.
- GSE Z axis in the ephemeris engine pointed to ecliptic south (left-handed frame), flipping the sign of every GSE z. Orbit trajectories returned the same point for every step.
- Boyle et al. (1997) polar cap potential uses the IMF magnitude |B| (it used √(By² + Bz²)).
- Newell coupling in the forecaster used |B| instead of the transverse field B_T = √(By² + Bz²).
- D-RAP absorption follows the SWPC relation HAF = 10 log₁₀(Fx) + 65 MHz (reduced by cos^0.75 χ) and A(f) = (HAF/f)^1.5 dB.

### Import and export
- Files with only GSE field components are no longer left without Bz-based quantities: By and Bz are rotated to GSM for the time of each row (Hapgood 1992, with the dipole axis from the IGRF-14 degree-1 coefficients), and Bx is shared by both systems. The rotation reproduces the GSM components published in OMNI to their 0.01 nT rounding. GSE columns are kept in the imported records; files with their own GSM columns are used as they are.
- File import: OMNI/CDF fill values are treated as missing, missing columns are no longer filled with nominal values, time stamps are converted to UTC and sorted, OMNI YEAR/DOY/HR/MN columns are read, and the import is vectorised.
- CSV export includes a metadata header (provenance, coverage, cadence, units) and handles records with differing fields; NetCDF-style schema units are correct.
- Reports state the actual provenance of the data they summarise and no longer fail on a trailing data gap.

### Interface and robustness
- Time labels convert UTC to the selected time zone correctly in WebKit-based windows (macOS, Linux).
- Export endpoints reject unknown missions and spans outside 1–7 days.
- The test suite runs offline against a temporary `HELIOS_HOME` and no longer touches the user's cache folder.
