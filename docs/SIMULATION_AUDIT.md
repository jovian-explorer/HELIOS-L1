# Audit of simulations, models and positions

Phase 1 of the review asked for by the owner (October 2026): every simulated, modelled, animated or schematic item in HELIOS-L1, what it does now, the basis it should have, what is wrong, how serious it is, the test against real data that would prove a fix, and the smallest fix. Phase 2 fixes them in this order; each fix is ticked off here with its commit and the accuracy measured after it.

**How it was done.** The items were found with the code graph (graphify queries for CME, orbit, ephemeris, synthetic, simulated, magnetosphere, solar cycle and visualizer nodes) and every file they point to was read. Numbers were checked against real data: JPL Horizons vectors (5 epochs, 2024-05-10 to 2027-06-01, same frame), the NOAA real-time solar wind ephemeris, 46 Earth-directed CMEs of NASA DONKI (2023 to mid-2025) with their observed shocks at L1, GOES-19 magnetometer data, GFZ Kp, NOAA OVATION, NOAA solar region summaries (NCEI), OMNI files in the test data, and the published coefficients of each model. NASA CDAWeb/SPDF was down during the audit, so tests that need it are marked for Phase 2.

**Severity.** WRONG = wrong numbers shown as real. MISLEADING = schematic or invented content presented as real, or a correct model used outside its range. COSMETIC = drawing or label issues that do not change a number a user would rely on.

**Citations.** Every reference below with a DOI was checked against its Crossref record with Argus (27 checked, 0 wrong; two flagged only because the record carries a subtitle). References marked *unverified* have no DOI record checked and must be verified before they go into the code.

---

## Ranked list

| # | ID | Severity | Item | Measured problem |
|---|---|---|---|---|
| 1 | P1 | WRONG | L1 spacecraft positions (DSCOVR, ACE, WIND, SOHO, Aditya-L1) | invented halo states, 235 000-875 000 km (6-33°) from Horizons, served as "SPICE verified" |
| 2 | C1 | WRONG | CME drag-based model default drag Γ = 1e-7 km⁻¹ | fast CMEs arrive 20-45 h late (presets 69-74 h for 18-31 h events) |
| 3 | C2 | WRONG | CME shock Mach number and compression | always 1.0 at the default Γ (no shock even for Halloween 2003); 4-6.5 otherwise |
| 4 | S1 | WRONG | Offline storm profiles | overshoot their own stated peaks (May 2024: 1469 vs 1023 km/s, 153 vs 48 nPa); no shock in any profile |
| 5 | P5 | WRONG | Solar Orbiter position | one osculating orbit: 56° off in May 2024, 23° in mid-2027; feeds the CME projection correction |
| 6 | P6 | WRONG | Parker Solar Probe position | elements valid only after Nov 2024: 4° (May 2024) to 110° (2020) off |
| 7 | P4 | WRONG | GOES-16 position and labels | at 75.2° W, but GOES-East is GOES-19 since April 2025; GOES-16 is 21 500 km / 29.5° away |
| 8 | S2 | WRONG | GOES "Hp" magnetometer view | invented formula; against GOES-19 r = 0.33, RMSE 26 nT |
| 9 | S3 | WRONG | AE estimate and its levels | median 307 vs observed 635 nT on 17 Mar 2015; "extreme" unreachable |
| 10 | P2 | WRONG | Halo/Lissajous orbit shapes and amplitudes | X at twice the frequency; amplitudes 2-3× too small |
| 11 | P3 | WRONG | Drawn L1 tracks vs server markers | up to 133 000 km apart for the same spacecraft |
| 12 | D1 | WRONG | Parker Solar Probe "Venus leg" preset | places the probe at 0.10 AU instead of 0.72 AU |
| 13 | D2 | WRONG | Example active regions on the solar disk | AR 3842 and AR 3848 in the wrong hemisphere |
| 14 | D4 | WRONG | Auroral oval in strong storms | Starkov oval never below 59.7° (CGM) at Kp 9; regions lists for ≤50° unreachable |
| 15 | D5 | WRONG | L1/magnetosphere view scales | two scales 3.4× apart in one plot; grid readings wrong |
| 16 | D6 | WRONG | Earth disk in the magnetosphere view | 2.9 R_E radius; GEO drawn 2.3 R_E above the surface |
| 17 | D3 | WRONG | Heliosphere "Model field \|B\|" tooltip | 5/r² nT, 1.46× too high at 0.1 AU, ignores speed |
| 18 | D7 | WRONG | Aurora map subsolar point | up to 0.44° off (Spencer series), disagrees with the server |
| 19 | S4 | WRONG | Halloween 2003 event window and "extremes" | 1114 km/s from scattered samples (59 h of no speed); window ends before Dst −383 nT |
| 20 | P8 | WRONG | Venus, Earth conic positions | Venus 0.32° (610 000 km) off; Earth 40-60 000 km |
| 21 | P11 | WRONG | Derived orbital elements for Earth-orbiting / L1 craft | heliocentric elements computed for geocentric objects ("true anomaly" etc.) |
| 22 | C3 | MISLEADING | Drag-based model start height | started at 6-11.5 R☉; the model applies beyond ~20 R☉ (+3-4 h) |
| 23 | C4 | MISLEADING | Gopalswamy et al. (2001) arrival | an ejecta-arrival model compared with shock times; started at r2 instead of near the Sun |
| 24 | C5 | MISLEADING | "Shock front", "sheath" and flux rope in the CME animation | the model tracks the CME front; the shock/sheath lead it by ~10 h at 1 AU |
| 25 | S5 | MISLEADING | 12-hour Kp trajectory | invented 5 %/h relaxation; 1-minute input; G5 "now" when GFZ Kp was G4 |
| 26 | S7 | MISLEADING | Shock screening on the dashboard | missed the 17 Mar 2015 shock; "CME shock if ΔV > 100" invented |
| 27 | P9 | MISLEADING | "SPICE verified" labels | shown for positions not from SPICE |
| 28 | P10 | MISLEADING | Unknown spacecraft IDs | answered with a fabricated position |
| 29 | P17 | MISLEADING | Active L1 spacecraft list | DSCOVR shown as operational; RTSW uses SOLAR1 (SWFO-L1), ACE and IMAP |
| 30 | P7 | MISLEADING | STEREO-A position before 2024 | 0.9-3.1° off; feeds CME tracking |
| 31 | P14 | MISLEADING | Positions fetched once | no refresh, no epoch for archive intervals |
| 32 | P12 | MISLEADING | PSP/Solar Orbiter drawn in the L1 view | as Earth-centred ellipses |
| 33 | C6 | MISLEADING | CME threat level and Kp | from the uncorrected speed alone |
| 34 | C8 | MISLEADING | CME projection correction | v_pos / sin ψ ignores the width; ×2.0 at 30° vs ~×1.3 |
| 35 | S6 | MISLEADING | Polar cap potential | no saturation; clipped at an invented 280 kV for 172 min in the 2015 storm |
| 36 | S8 | MISLEADING | Solar cycle offline fallback | peak 172 at 2024.75 vs observed 160.9 (Oct 2024); F10.7 relation on the old scale |
| 37 | S11 | MISLEADING | Carrington 1859 values | Bz −90 vs −64.5 nT in two places; 2300 km/s is the transit average, not the speed at Earth |
| 38 | S12 | MISLEADING | March 1989 solar wind | Bz −50 nT, 950 km/s, 42 nPa invented (no L1 data) |
| 39 | S13 | MISLEADING | Import presets | contradict the app's own peaks; quiet preset carries a real-looking 2026 date |
| 40 | S9 | MISLEADING | Simulation offsets | invented; STEREO-A as L1 data minus 12 km/s |
| 41 | S10 | MISLEADING | Synthetic temperature | 92 000 K at 338 km/s vs ~25 000 K |
| 42 | D8 | MISLEADING | Heliosphere particles | mixed frames; winding 30 % off the drawn spiral |
| 43 | D9 | MISLEADING | "CIR forward shock" | invented, from 0.4 AU; CIR shocks form beyond 2-3 AU |
| 44 | D10 | MISLEADING | Magnetic sectors | radial wedges with no data |
| 45 | D11 | MISLEADING | Heliosphere view speed | never uses the live L1 speed |
| 46 | D13 | MISLEADING | PSP "Alfvén surface crossing" | any distance ≤ 12 R☉ |
| 47 | D14 | MISLEADING | "NAIF SPICE Verified" badge | static |
| 48 | D15 | MISLEADING | L1 "early warning 45-60 min" | fixed; 21-100 min over 250-1200 km/s |
| 49 | D16 | MISLEADING | Radiation belts, dipole lines, tail | X-Z features drawn in X-Y; one ellipse for both belts |
| 50 | D17 | MISLEADING | 3D halo view | unequal axis scales; figure-8 track |
| 51 | D18 | MISLEADING | "Hill sphere / Roche lobe" curves | invented ellipses |
| 52 | D19 | MISLEADING | Solar disk geometry | B₀ = 0 for regions but 8.6° for the grid; no rotation |
| 53 | D20 | MISLEADING | "True solar limb darkening" | EUV images show limb brightening |
| 54 | D21 | MISLEADING | Fleet matrix | zero-lag correlation of spacecraft minutes apart |
| 55 | D12 | MISLEADING | "(Solar Limb)" after the footpoint | the limb is 90° W |
| 56 | C7 | COSMETIC | CME cone drawing | 25.8° half-width (comment says ~50°); flank does not meet the arc |
| 57 | C9 | COSMETIC | Silent clamps of w and Γ | values changed without a word |
| 58 | P13 | COSMETIC | L1 view axis stretch, Sun label, GEO ring plane | (overlaps D5, D17) |
| 59 | P15 | COSMETIC | Heliosphere view radii/labels | STEREO-A fixed 0.96 AU; "L1 (DSCOVR/Aditya)" |
| 60 | P16 | COSMETIC | L2 distance, L4/L5 sign convention | L2 at 1.496 instead of 1.508 million km |
| 61 | D22 | COSMETIC | Aurora fallback oval | half the ring clamped at 89.9°; fake shimmer |
| 62 | D23 | COSMETIC | Aurora wavelength strokes | 630/557.7/427.8 nm drawn side by side |
| 63 | D24 | COSMETIC | Small labels and decorations | Sun size, prominence spin, tooltips, legend colour, Pdyn 1.8 vs 2.0 nPa |
| 64 | S14 | COSMETIC | D-RAP "usability" thresholds, `polar_aviation_impact` name | invented thresholds; field describes the sunlit side |
| 65 | S15 | COSMETIC | Sonification | arbitrary mapping (labelled as sound, not data) |

**Checked and correct** (no change needed): Shue et al. (1998) magnetopause, Chao et al. (2002) and Farris & Russell (1994) bow shocks (all coefficients; browser and server agree to 0.04 R_E); Parker spiral pitch and footpoint; the drag-based model equations (browser and server agree); Akasofu ε; Newell (2007) coupling and the Newell (2008) Kp coefficients; D-RAP formulas; the GIC plane-wave formula; peak Kp of the five historical events (GFZ); STEREO-A, Earth, Mars, Mercury now; the Moon (340-1100 km); GSE→GSM (0.01-0.06° against SunPy); geographic→GSE; the NOAA ephemeris of ACE (4500 km from Horizons); the observed solar cycle peak; GOES flare classes (49 of 49).

---

## Details

### Positions and orbits

**P1 — L1 spacecraft positions are invented.** `helios/core/spice_engine.py:120-128` (L1_HALO_SPECS), `:390-413` (`_l1_halo_state`), `:498-507`. Now: analytical halo states with invented amplitudes and phases, flagged `is_spice_verified: true`. Measured (Horizons, GSE): DSCOVR 311-567k km (12-21°), ACE 236-343k km (9-13°), WIND 235-532k km (6-20°), SOHO 285-874k km (9-33°), Aditya-L1 458-809k km (15-31°). Basis: the spacecraft trajectories (JPL Horizons / NAIF SPK). Fix: SPK files written from Horizons vectors with the existing `occultation.horizons_spk` (IDs −78, −92, −8, −21, −156; and SOLAR1/SWFO-L1 −231, IMAP −43), read with `spkezr` relative to Earth and rotated to GSE; else the NOAA RTSW ephemeris; else no position. Test: within 1000 km of Horizons at 5 epochs.

**P2 — Halo/Lissajous shapes.** `spice_engine.py:123-127, 398-400`; `orbital_mechanics.py:78-201`. X oscillates at twice the frequency; real ranges (Horizons, 2024-26, GSE, 1000 km): DSCOVR X 1369-1591, |Y| ≤ 293, |Z| ≤ 191; WIND |Y| ≤ 664 (HELIOS 190); Aditya |Y| ≤ 694 (HELIOS 240). ACE and DSCOVR are Lissajous, not halo, orbits (the menu says "ACE (Sun-Earth L1 Halo)"). Basis: Richardson (1980), Celest. Mech. 22, 241, doi:10.1007/BF01229511. Fix: draw the track from the SPK over ±180 days; delete the parametric formulas. Test: envelope within 10 % of Horizons.

**P3 — Drawn track ≠ server marker.** SOHO track Ay 200k / Az 110k km vs marker 650k / 200k (133 000 km apart); DSCOVR Z uses sin(2φ+0.5) vs cos(φ+0.5); ACE 36 000, WIND 50 000 km apart. Fix: one source (P1/P2).

**P4 — GOES.** `spice_engine.py:92-97`, `orbital_mechanics.py:203-226, 292`, `config.py:376-380`. GOES-16 drawn at 75.2° W; GOES-East has been GOES-19 since April 2025 (GOES-16 moved to 104.7° W; GOES-West is GOES-18 at 137.0° W). NOAA's "primary" products now come from satellite 18 (X-rays, protons) and 19 (magnetometer). Fix: name the satellite from the products' `satellite` field; place GOES-18/19 at their longitudes or from Horizons. Test: within 100 km.

**P5 — Solar Orbiter.** `spice_engine.py:63-68`. One osculating orbit, valid 2025-02 to 2026-12 (Venus flybys; Müller et al. 2020, A&A 642, A1, doi:10.1051/0004-6361/202038467). Off by 56° (May 2024), 6.8° (Jan 2025), 23° (Jun 2027), 165-172° in 2020/2028. Feeds `cme_tracking.py:205-208` (observer for EUI). Fix: SPK −144; refuse epochs without one. Test: < 0.01° heliocentric.

**P6 — Parker Solar Probe.** `spice_engine.py:57-62`. Valid only after 2024-11-06: 4.1° (May 2024), 17.6° (Jun 2023), 56° (Mar 2022), 110° (Jun 2020). Fix: SPK −96.

**P7 — STEREO-A before 2024.** `spice_engine.py:69-73`. 0.9° (2023), 2.0° (2022), 3.1° (2020); feeds CME tracking (EUVI, COR). Fix: SPK −234.

**P8 — Planets.** `spice_engine.py:74-77, 446-454`. Venus 0.32° (610 000 km) off at all epochs; Earth conic 40-60 000 km. Fix: the DE440s kernel already downloaded for the occultation tool (`spkezr` 199/299/399/499/301).

**P9 — "SPICE verified" labels.** `spice_engine.py:626`, `server.py:1877-1882`, `orbits.js:412-413`, `orbital_mechanics.py:294`. Fix: a `source` field shown with every position; `is_spice_verified` only when `spkezr` produced it.

**P10 — Unknown IDs.** `spice_engine.py:509-517` returns a made-up position. Fix: 404 listing the valid IDs.

**P11 — Derived elements.** `spice_engine.py:550, 564-565`; `orbits.js:410`. Heliocentric elements computed for geocentric/L1 objects. Fix: geocentric elements for Earth orbiters; none for L1 craft.

**P12 — PSP/Solar Orbiter in the L1 view.** `orbital_mechanics.py:228-285`. Drawn as Earth-centred ellipses; STEREO-A as a fixed marker. Fix: remove from the L1 view or show a direction arrow.

**P13 — L1 view scales** (cosmetic, see D5/D17): Y/Z stretched 1.44-1.53×, inset 3.4×, Sun mislabelled, decorative Hill curves, GEO ring in the ecliptic.

**P14 — Positions fetched once.** `app.js:2897-2905`, `parker.js:57, 65-77`. Fix: refresh every ~10 min; pass the epoch for archive intervals.

**P15 — Heliosphere view.** STEREO-A radius fixed at 0.96 AU, "1.00 AU" for Earth, inclinations ignored in 2D (cosmetic); fallback animated planet orbits marked only `isSpice: false`.

**P16 — Lagrange points.** `orbital_mechanics.py:20-52`; `orbits.js:926-927`. L2 at 1.496 instead of 1.508 million km; L4/L5 sign convention undocumented.

**P17 — Active L1 list.** RTSW now carries SOLAR1 (SWFO-L1), ACE and IMAP; DSCOVR has been absent for 30 days. Labels `orbits.js:446`, `parker.js:952`. Fix: list from the RTSW `source`/`active` fields.

### CME propagation

Real-data test: 46 DONKI CMEs (2023 to mid-2025) with one associated interplanetary shock at L1 (most accurate analysis, |lon|, |lat| ≤ 30°, v ≥ 450 km/s), each run from 21.5 R☉ at time21_5 with w = 420 km/s. Mean error / mean absolute error of the predicted shock arrival: drag-based model Γ = 1e-7: +9.8 / 14.8 h (late, growing with speed: +7.8 h at 450-800, +10.4 h at 800-1300, +13.3 h above 1300 km/s); Γ = 0.2e-7: −5.9 / 13.4 h; Gopalswamy (2001): −2.9 / 16.8 h (about 25 h early above 1300 km/s).

**C1 — Default drag parameter.** `coronagraph.py:100`, `index.html:1394`, `app.js:1908`, `cme_sim.js:23`, `corona_link.py:31`. Γ = 1e-7 km⁻¹ decelerates every CME to the ambient wind: predicted arrival speed 451-463 km/s for every CME from 452 to 2112 km/s (observed shock speeds 440-629 km/s). Presets: Halloween 2003 68.9 h (observed ~18.5 h), Bastille 2000 72.2 h (~27.7 h), Carrington 68.2 h (17.6 h in its own tooltip), May 2024 73.5 h (~31 h) (observed values to be checked against the literature in Phase 2). Basis: Vršnak et al. (2013), Sol. Phys. 285, 295, doi:10.1007/s11207-012-0035-4 (Γ 0.2-2e-7 km⁻¹; 0.2e-7 the usual forecasting value). Fix: default 0.2e-7 everywhere. Test: DONKI set MAE and bias by speed class.

**C2 — Shock Mach number and compression.** `coronagraph.py:204-209`. M = max(1, (v_arr − w)/50 km/s), compression 4M²/(M²+3): 1.0/1.0 for every event at the default Γ; 4-6.5 with Γ = 0.2e-7 (observed 1-3). Uses the CME front speed and the Alfvén instead of the fast magnetosonic speed and a gas-dynamic jump. Fix: compare with the IPShocks catalogue (in the repo) and keep only what it supports, e.g. M = (v − w)/c_ms with a stated c_ms ≈ 70 km/s, or remove both numbers.

**C3 — Start height.** `coronagraph.py:124`; presets `index.html:1353-1382` start at 6-11.5 R☉. The drag-based model applies beyond ~20 R☉ (Vršnak et al. 2013). Fix: carry the measured speed to 20-21.5 R☉, then start the model.

**C4 — Gopalswamy model.** `coronagraph.py:73-90, 185`. Coefficients match the cited paper (Gopalswamy et al. 2001, JGR 106, 29207, doi:10.1029/2001JA000177; to be read against the paper in Phase 2), but it predicts the ejecta arrival; the shock version is Gopalswamy et al. (2005), Adv. Space Res. 36, 2289, doi:10.1016/j.asr.2004.07.014. It is started at r2 instead of near the Sun (6 h on the test set). Fix: start where the paper does; label "ejecta"; add the 2005 shock model if kept.

**C5 — Shock/sheath/flux rope in the animation.** `cme_sim.js:347-364`; `corona_link.py:63-67`. The model tracks the CME front; the shock and sheath lead the ejecta by about 10 h at 1 AU (Kilpua et al. 2017, Space Sci. Rev. 212, 1271, doi:10.1007/s11214-017-0411-3). The flux rope at 0.78 of the front distance is illustrative. Fix: label the front "CME front (drag-based model)"; drop the sheath/shock labels or show them only as schematic.

**C6 — Threat level and Kp.** `coronagraph.py:212-227`. From the plane-of-sky speed alone (600/1000/1600 km/s); storm strength depends mainly on the southward field. Fix: remove, or show as "speed class" with no Kp.

**C7 — Cone drawing.** `cme_sim.js:336-341`. Fixed 0.45 rad (25.8°; comment says ~50°); the flank line does not meet the arc. Fix: use the measured half-angle when known (DONKI 15-53° in the test set) and draw the flank to (d cos θ, d sin θ).

**C8 — Projection correction.** `cme_tracking.py:184-195`. v = v_pos / sin ψ ignores the CME width: ×2.0 at ψ = 30° against about ×1.3 for a 40° cone. Fix: cone-model correction (reference to be chosen and verified in Phase 2) or a stated limit.

**C9 — Silent clamps.** `coronagraph.py:122-123` clamps w to 250-900 km/s and Γ to 0.1-3e-7 without saying so. Fix: refuse out-of-range values (422) or report the clamp.

### Drawings and animations

**D1 — PSP Venus preset.** `parker.js:94-96`; `index.html` "Venus Leg (0.72 AU)". ν = 100° gives r = a(1−e²)/(1+e cos ν) = 0.102 AU. Fix: cos ν = (a(1−e²)/r − 1)/e (≈ 177°). Test: 0.72 ± 0.01 AU.

**D2 — Example active regions.** `solar_viewer.js:38-56`. AR 3842 drawn at N14.5 (NOAA: S15), AR 3848 at S12 (NOAA: N12); AR 3842 class β-γ-δ, not β-γ. Fix: positions from the NOAA solar region summaries of the flare dates (3664 S19W87, 3697 S18E35, 3842 S15E06, 3848 N12W11).

**D3 — Field tooltip.** `parker.js:572`. 5/r² nT; Parker (1958, ApJ 128, 664, doi:10.1086/146579) gives |B| = B_r1 r⁻² √(1+(Ωr/V)²): the tooltip is 1.46× too high at 0.1 AU, 1.29× at 0.5 AU, 0.77× at 1.5 AU. Fix: Parker formula scaled to the measured L1 field.

**D4 — Oval in strong storms.** `aurora_model.py` (|AL| capped at 750 nT), drawn by `aurora.js`. Equatorward midnight boundary 67.5/63.8/61.4/59.9/59.7° CGM at Kp 1/3/5/7/9; checked earlier against DMSP in storms up to Dst −132 nT (agreement), but G5 storms are beyond the fit. Fix: above Kp ~7 use OVATION (NOAA) or Zhang & Paxton (2008, JASTP 70, 1231, doi:10.1016/j.jastp.2008.03.008), or state the limit on the map. Test: DMSP boundaries on 10-11 May 2024 (when CDAWeb is back).

**D5 — Two scales in the L1 view.** `orbits.js`. Magnetosphere at 3.79 px/R_E, grid and L1 tracks at 1.11 px/R_E; against the grid the bow shock reads ~44 R_E and the Sun 3.3 million km. Fix: a scale break or inset with its own scale, "not to scale" for the Sun.

**D6 — Earth disk.** `orbits.js:883-904`. 11 px = 2.9 R_E; GEO drawn 2.3 R_E above the surface. Fix: 1 R_E.

**D7 — Subsolar point.** `aurora.js:161-175`. Spencer series, up to 0.44° in latitude (0.19° in longitude) from astropy. Fix: take it from the server (`coordinates.sun_direction_geo`, 0.01° from astropy). Test: < 0.05° over a year.

**D8-D24** (misleading or cosmetic, see the ranked table): particles that slide along a non-rotating spiral with 30 % wrong winding (`parker.js:858-866`); an invented CIR shock from 0.4 AU (`parker.js:675-735`; CIR shocks form beyond 2-3 AU, Gosling & Pizzo 1999, Space Sci. Rev. 89, 21, doi:10.1023/A:1005291711900); data-free sector wedges (`parker.js:640-660`); a speed slider never set from the live L1 speed (`app.js:1998`, `parker.js:24`); "(Solar Limb)" after the footpoint (`parker.js:1255`); "Alfvén surface crossing" at ≤ 12 R☉ (`parker.js:221`, `spice_engine.py:44`; first crossing measured at 18.8 R☉, Kasper et al. 2021, PRL 127, 255101, doi:10.1103/PhysRevLett.127.255101); a static "NAIF SPICE verified" badge (`index.html`); a fixed "45-60 min" warning (`parker.js:455`); belts, dipole lines and tail drawn in the wrong plane (`orbits.js:845-852, 941-1080`; Van Allen & Frank 1959, Nature 183, 430, doi:10.1038/183430a0); unequal 3D axis scales and a figure-8 halo (`orbits.js:281-289`); invented Hill/Roche curves (`orbits.js:582-587`); B₀ = 0 for regions but 8.6° for the grid and no rotation (`solar_viewer.js:150-160, 401-404, 443-449`; Snodgrass & Ulrich 1990, ApJ 351, 309, doi:10.1086/168467); "limb darkening" on an EUV disk (`solar_viewer.js`; Neckel & Labs 1994, Sol. Phys. 153, 91, doi:10.1007/BF00712494); a zero-lag fleet matrix (`matrix.js`, `comparator.compute_fleet_matrix`); the aurora fallback ring with fake shimmer (`aurora.js:220-255`); wavelength strokes side by side (`aurora.js:540-575`); and small labels (Sun size, prominence spin 20× the rotation, STEREO-A "0.962 AU / 30.4 km/s", Solar Orbiter inclination "24-33°" (17° until Dec 2026), legend colour, Pdyn 1.8 vs 2.0 nPa in the browser).

### Synthetic data and empirical models

**S1 — Offline storm profiles.** `downloader.py:1105-1116`. All 48 h at a CME-shock baseline (850 km/s, 35 cm⁻³, Bz −22 nT) plus a decaying boost of (peak − 400) km/s: May 2024 1469 km/s / 153 nPa vs the stated 1023 / 48.3; Carrington 2746 / 534 vs 2300 / 96; others +450 km/s, pressure 3-5×; no shock detected in any profile. Fix: quiet baseline before the shock, step at the shock, ramp to the stated peaks. Test: profile maxima equal the stated peaks; the shock detector finds the shock.

**S2 — GOES "Hp".** `downloader.py:695-706`. hp = 100 + 4.5 Pdyn − 1.5|Bz| (no local time): against GOES-19 over 1168 min, mean 108 vs 88.9 nT, r = 0.33, RMSE 26 nT. Fix: NOAA's `json/goes/primary/magnetometers-*.json`, else none.

**S3 — AE estimate.** `science.py:424-452`, `app.js:4022`. 17 Mar 2015: estimate median 307 / max 449 nT, observed median 635 / max 2298 nT; "extreme" (≥ 1000 nT) unreachable. Not in Newell et al. (2007, JGR 112, doi:10.1029/2006JA012015). Fix: remove, or refit on multi-year OMNI.

**S4 — Halloween 2003.** `downloader.py:1031-1037`. "OMNI 5-min extremes" 1114 km/s / 12.5 nPa come from scattered samples (no speed for 59 h, 28 Oct 14 UT to 31 Oct 00 UT); literature peak ~1900-2000 km/s (Skoug et al. 2004, JGR 109, doi:10.1029/2004JA010494); the window ends before the second CME and before Dst −383 nT at 22 UT on 30 Oct. Fix: extend the window to 31 Oct 06 UT and state the gap fraction.

**S5 — 12-hour Kp trajectory.** `ml_forecast.py:19-20, 176-183`. Newell et al. (2008, JGR 113, A04218, doi:10.1029/2007JA012825) coefficients correct, but applied to one 1-minute sample (the fit used averaged data) and relaxed at an invented 5 %/h to fixed quiet values. 17 Mar 2015: "now" Kp 9.0 (GFZ 5.3-7.7); 12-h values 3.8-5.6 while Kp stayed 6.0-7.7. Quiet day: RMSE 0.74 (persistence 1.04). Fix: 1-3 h mean inputs; persistence (or say "beyond 3 h: climatology").

**S6 — Polar cap potential.** `science.py:392-421`. Boyle et al. (1997, JGR 102, 111, doi:10.1029/96JA01742) formula and units correct, but unsaturated; the 15-280 kV clip and levels are invented (172 min at 280 kV in the 2015 storm). Fix: a saturating form (reference to verify in Phase 2) or a stated limit.

**S7 — Shock screening.** `science.py:602-659`. Missed the 17 Mar 2015 shock (~04:47 UT; ΔV ~100 km/s, B 9.5→27 nT, density ratio < 1.5 within 3 min). Fix: 8-min means before/after, skip gaps, IPShocks thresholds (Kilpua et al. 2015, JGR 120, 4112, doi:10.1002/2015JA021138; exact thresholds to verify). Test: the shocks of the IPShocks catalogue in the test data.

**S8 — Solar cycle fallback.** `solar_cycle.py:125, 189`. Peak 172 at 2024.75 vs 160.9 (Oct 2024); 13 SSN high on average (rms 15); F10.7 relation for the old sunspot scale (5.4 sfu high); 10.6 vs 11 years for progress. Fix: amplitude 161, one 11-year basis.

**S9-S13** (misleading): invented instrument offsets (`downloader.py:39-46`; STEREO-A as L1 minus 12 km/s; `time_skew_min` unused); synthetic temperature 92 000 K at 338 km/s vs ~25 000 K (Lopez & Freeman 1986, JGR 91, 1701, doi:10.1029/JA091iA02p01701) and a fixed Bz −4 nT for 24 h (`downloader.py:983`); Carrington Bz −90 vs −64.5 nT in two places and 2300 km/s used as the speed at Earth (Tsurutani et al. 2003, JGR 108, doi:10.1029/2002JA009504; Cliver & Dietrich 2013, JSWSC 3, A31, doi:10.1051/swsc/2013053); March 1989 Bz −50 nT, 950 km/s, 42 nPa invented (`downloader.py:1049-1055`); import presets contradicting the app's stated peaks and a quiet preset dated 2026-09-21 (`importer.py`).

**S14-S15** (cosmetic): D-RAP "usability" thresholds and the field name `polar_aviation_impact` (`ionosphere.py`); sonification mapping (`audio.js`), arbitrary but presented as sound, not data.

---

## Phase 2 order

1. One change for P1-P8 (and P9-P11, P17): real trajectories from SPICE kernels (DE440s for planets, Horizons-written SPKs for the spacecraft, cached and refreshed weekly) through `spkezr`; the conics remain only as a labelled fallback that refuses epochs outside their validity. Regression test: every body at 5 epochs against Horizons (< 1000 km for L1/Earth-orbiting craft, < 0.01° heliocentric).
2. C1-C5: CME defaults, start height, shock outputs and labels, tested on the DONKI set.
3. S1-S5, S2/S3: synthetic profiles, GOES Hp, AE, Halloween window, Kp trajectory.
4. D1-D7 and the remaining drawing items, each with its test or a "schematic" label.

## Progress

| ID | Fixed in | Measured after the fix |
|---|---|---|
| P1, P2, P3 | 61144a3, 25d38b3 | L1 craft from Horizons SPKs via SPICE: < 1 km from independent Horizons vectors at 2024-05-10, 2024-11-06 and 2026-10-10 (network test `test_positions_match_horizons`); drawn track and marker are one ephemeris |
| P4 | 61144a3 | GOES-19 (GOES-East) and GOES-18 from their Horizons ephemerides; GOES-16 no longer shown |
| P5, P6, P7 | 61144a3 | Solar Orbiter, PSP, STEREO-A from SPKs −144, −96, −234: < 1 km; the conics are kept only inside their fitted dates and labelled "approximate" |
| P8 | 61144a3 | Planets, Earth and Moon from DE440s: < 1 km; GSE axes use the ecliptic pole of date, 0.0005° from SunPy |
| P9 | 61144a3 | Every position carries `position_source`; `is_spice_verified` only for an ephemeris state; none where no ephemeris exists ("no position is invented") |
| P10 | 61144a3 | Unknown IDs: 404 |
| P11 | 61144a3 | Orbital elements only for heliocentric bodies |
| P12 | 61144a3 | PSP, Solar Orbiter and STEREO-A removed from the L1 view; SWFO-L1 and IMAP added |
| P14 | f7f23c8, 7f8a9f8 | Positions refreshed every 10 min in both views; with an archive interval loaded both views show the positions at its end (checked in the browser: 10 May 2024 17:59, DSCOVR at the 2024 position) |
| P16 | 905306d | L1 1.498, L2 1.508 million km (restricted three-body solution, μ = 3.0404e-6) |
| P17 | f7f23c8 | Labels list the craft near L1 (SWFO-L1, ACE, IMAP, WIND, SOHO, Aditya-L1, DSCOVR), no "active" claim; DSCOVR's position ends with its Horizons coverage (2 Nov 2026) |
| — | a2389a9, baeb2ef | Found while checking: a new session repeated 48 refused Horizons requests (orbit view 62 s, now 1.4 s warm); two first requests at once aborted the server inside CSPICE (engine set up under its lock) |
| C1 | c69da22 | Defaults Γ = 0.2e-7 km⁻¹, w = 450 km/s (Dumbović et al. 2021, doi:10.3389/fspas.2021.639986, from Vršnak et al. 2013, 2014), not fitted here. 44 DONKI CMEs 2023-01..2025-06 with one shock at L1 (re-fetched 2026-10-15; 46 at the audit), run from 21.5 R☉: bias +9.4 → −6.9 h, MAE 15.5 → 14.4 h (450-800 km/s: −3.2/15.8; 800-1300: −9.5/11.6; >1300: −14.1/15.7). Published: ~14 h for the DBM (Vršnak et al. 2014), ~10 h for propagation models (Dumbović et al. 2021). Presets: Halloween 68.9 → 32.0 h (obs. ~18.5), Bastille 72.2 → 39.7 h (~27.7): extreme events stay late with one Γ. Test `test_drag_based_model_defaults_on_observed_cme_arrivals` |
| C2 | c69da22 | Mach number and compression removed |
| C3 | c69da22 | Model starts at 20 R☉, constant speed from the measured height (server and animation) |
| C4 | c69da22 | Gopalswamy (2001) started at the Sun as in the paper, labelled ejecta arrival; on the DONKI set against shocks: +4.9 / 17.4 h |
| C5 | 2007199 | Animation: "CME front, drag-based model"; flux rope, shock and "Earth impact" labels removed |
| C6 | c69da22 | Threat level, Kp and speed class removed |
| C7 | 2007199 | 30° half-angle schematic cone, flanks meet the arc |
| C8 | e45d1e0 | Optional half-width: v = v_pos / sin(min(ψ + w, 90°)) (Sun-centred cone front); 40° CME at ψ = 30°: ×1.06 instead of ×2.0; without a width the old formula is flagged |
| C9 | c69da22 | w and Γ used as given (API range checks only) |
| — | 964eeee | Found while checking P14: concurrent first downloads of one kernel collided (2 of 3 failed) and were remembered as failures for 10 min; now one download per kernel |
| S1 | 181b77f | No generated storm profiles: offline the events are the OMNI 5-min data bundled with the app (`helios/data/omni_events.json.gz`, 120 kB). May 2024 maxima 1469 → 1023 km/s, Bz −44.3 nT (the stated peaks, now measured); shocks found offline: 0 → May 2024 (10 May 17:05 UT) and Bastille 2000 (15 Jul 14:40 UT). Quiet baseline = OMNI 6-8 Dec 2019 (GFZ Kp ≤ 1−). Test `test_offline_events_are_the_bundled_omni_data` |
| S4 | 181b77f | Halloween window 28 Oct 12 UT to 31 Oct 06 UT: minimum SYM-H −427 nT (includes Dst −383 nT, 30 Oct 22 UT); every event states its plasma coverage (Halloween 35.0 %, longest gap 1.3 days), so the 1114 km/s maximum is shown as scattered samples |
| S11 | 181b77f, fd65593 | Carrington: no time series and no Bz/speed/pressure (−90 and −64.5 nT, 2300 km/s at Earth removed); summary keeps the 17.6 h transit (mean speed ≈ 2360 km/s); Carrington import table removed |
| S12 | 181b77f | March 1989: OMNI has no solar wind for 12-14 Mar; the event shows SYM-H only (minimum −714 nT); the invented −50 nT / 950 km/s / 42 nPa removed |
| S13 | fd65593 | Import examples are OMNI 5-min cuts of the bundled data (May 2024, Bastille 2000, March 2015, 7 Dec 2019); the hand-written tables and the 2026-09-21 quiet day are gone |
