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

### Method 1: Windows Setup Installer Executable (`.exe`) — Recommended
Double-click the generated setup wizard executable:
```
dist\HELIOS-L1-Setup.exe
```
This standalone setup wizard:
* Prompts for installation directory (defaults to `%LOCALAPPDATA%\Programs\HELIOS-L1`).
* Extracts all binaries, libraries, and scientific assets.
* Creates high-resolution Windows Desktop and Start Menu shortcuts.
* Registers the application in Windows Settings (Apps & Features) with clean uninstaller.
* Can also run silently via command line: `dist\HELIOS-L1-Setup.exe /S`.

### Method 2: One-Click Desktop Batch Launcher
Double-click `Launch-HELIOS.bat` in the project root folder. It automatically detects and launches `HELIOS-L1.exe` or falls back to Python.

### Method 3: Direct Standalone Executable
Run the pre-compiled binary directly:
```powershell
.\dist\HELIOS-L1\HELIOS-L1.exe
```

### Method 4: Portable Distribution ZIP Archive
Unpack `dist/HELIOS-L1-v1.0-Windows-x64.zip` on any Windows PC and launch `HELIOS-L1.exe` (100% offline-ready, no Python required).

### Method 5: PowerShell Shortcut Creator
```powershell
powershell -ExecutionPolicy Bypass -File .\Create-Installer.ps1
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

Run the full pytest suite:
```powershell
python -m pytest tests/test_helios.py -v
```
All **26 unit, scientific verification, SPICE ephemeris, and API integration tests** pass with 100% success.

