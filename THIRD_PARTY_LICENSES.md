# Third-party licences

HELIOS-L1 itself is under the MIT licence (`LICENSE`). It bundles the following third-party
code, fonts and data, each under its own terms. The application icon, logo and the offline
placeholder pictures in `helios/gui/static/img/` are HELIOS-L1's own drawings (MIT).

## Chart.js 4.4.1

`helios/gui/static/js/chart.min.js` (https://www.chartjs.org), MIT licence:

```
Copyright (c) 2023 Chart.js Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Tailwind CSS 3.4.17

`helios/gui/static/css/tailwind.css` is generated with Tailwind CSS (https://tailwindcss.com), MIT licence:

```
Copyright (c) Tailwind Labs, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Font Awesome Free 6.5.1

`helios/gui/static/css/font-awesome.min.css` and `helios/gui/static/webfonts/` (https://fontawesome.com),
Copyright 2023 Fonticons, Inc. Licence: https://fontawesome.com/license/free

- Icons: Creative Commons Attribution 4.0 (CC BY 4.0), https://creativecommons.org/licenses/by/4.0/
- Fonts: SIL Open Font License 1.1, https://openfontlicense.org
- Code: MIT licence

## NAIF generic SPICE kernels

`helios/data/spice_kernels/` (`naif0012.tls`, `pck00010.tpc`, `gm_de431.tpc`), unmodified, from NASA's
Navigation and Ancillary Information Facility (NAIF), Jet Propulsion Laboratory. NAIF permits the
redistribution of unmodified kernels: https://naif.jpl.nasa.gov/naif/rules.html

## Richardson & Cane list of near-Earth ICMEs

`helios/data/icme_richardson_cane.json`, a snapshot of the 23 July 2026 revision. CC0 1.0 (Harvard
Dataverse, doi:10.7910/DVN/C2MHTH). I. G. Richardson and H. V. Cane; please cite Cane & Richardson
(2003, JGR 108, 1156) and Richardson & Cane (2010, Sol. Phys. 264, 189).

## IPShocks database

`helios/data/ipshocks_l1.json`: the shocks at WIND, ACE and DSCOVR of the version of 2026-04-24
(rows at other spacecraft and some columns left out, field names changed;
`scripts/update_shock_catalog.py`). Creative Commons Attribution 4.0 (CC BY 4.0). Kilpua, E., Good, S.,
Soljento, J., Price, D. J., Isavnin, A., Lumme, E., Mäkelä, T. V., Isavnina, K. & Andréeová, K.,
The IPShocks Database, doi:10.5281/zenodo.19730292; Kilpua et al. (2015, JGR 120, 4112,
doi:10.1002/2015JA021138).

## IGRF-14 coefficients

The degree-1 coefficients in `helios/core/coordinates.py` are from the International Geomagnetic
Reference Field, 14th generation (IAGA Working Group V-MOD), as distributed by NOAA NCEI.

## Optional libraries in the standalone build

The standalone app also contains the Python runtime and the libraries HELIOS-L1 depends on (see
`pyproject.toml`), among them NumPy, SciPy, pandas, Matplotlib, FastAPI, Uvicorn, SpiceyPy (CSPICE),
pywebview, Astropy, SunPy and sunkit-magex, each under its own open-source licence (BSD, MIT or
Apache 2.0; see each project).
