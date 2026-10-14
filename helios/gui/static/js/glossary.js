// One plain-language line per term the screens use without explaining it. Elements marked
// data-term="key" get the line as a tooltip (dotted underline), and the user guide (key U)
// lists them all.
const GLOSSARY = {
  'solar wind': 'The stream of charged particles (mostly protons and electrons) that flows out from the Sun at 300-800 km/s, carrying the Sun\'s magnetic field with it.',
  L1: 'The first Lagrange point, 1.5 million km from Earth towards the Sun, where spacecraft measure the solar wind about an hour before it reaches us.',
  IMF: 'Interplanetary magnetic field: the Sun\'s magnetic field carried out by the solar wind, a few nanotesla (nT) near Earth.',
  Bz: 'The north-south part of the interplanetary field. When it points south (negative), it links up with Earth\'s field and lets energy in: the main driver of storms and aurora.',
  GSM: 'Geocentric solar magnetospheric coordinates: x towards the Sun, z along the projection of Earth\'s magnetic axis, the natural frame for Bz.',
  density: 'How many solar wind protons there are per cubic centimetre: usually 2-10, much more in the dense material ahead of a CME.',
  'dynamic pressure': 'The push of the solar wind on Earth\'s magnetic field (density times speed squared), in nanopascal; about 2 nPa normally, above 10 nPa in strong storms.',
  'lead time': 'How long the solar wind measured at L1 takes to reach Earth: the warning time, usually 30-60 minutes.',
  magnetopause: 'The boundary of Earth\'s magnetic bubble (magnetosphere), normally about 10 Earth radii towards the Sun; a strong push can drive it inside the orbit of geostationary satellites (6.6 Earth radii).',
  'bow shock': 'The standing shock wave in front of Earth\'s magnetic bubble, where the supersonic solar wind slows down suddenly.',
  magnetosheath: 'The layer of slowed, heated solar wind between the bow shock and the magnetopause.',
  flaring: 'How quickly a boundary opens out away from the Sun-Earth line (the alpha of the boundary\'s shape).',
  'Akasofu epsilon': 'An estimate of the power the solar wind feeds into Earth\'s magnetosphere, in gigawatts, from speed, field strength and field direction.',
  'coupling function': 'A formula that turns solar wind speed and field into a measure of how strongly the solar wind drives Earth\'s magnetosphere; Newell\'s dPhi/dt is the one that best predicts geomagnetic activity.',
  Kp: 'The planetary K index, 0 (quiet) to 9 (extreme), from magnetometers around the world every 3 hours. Kp 5 is a minor storm (G1), Kp 9 an extreme one (G5).',
  'G scale': 'NOAA\'s geomagnetic storm scale G1 (minor) to G5 (extreme), set by Kp 5 to 9.',
  Dst: 'Disturbance storm time index, in nanotesla: how much the magnetic field at the equator is weakened by the ring of current around Earth in a storm. Below -50 nT is a storm, below -100 nT an intense one.',
  'auroral oval': 'The ring around each magnetic pole where aurora is seen. It widens towards the equator as activity rises.',
  'equatorward boundary': 'The edge of the auroral oval nearest the equator. Aurora can be seen overhead up to it and low on the horizon some way beyond.',
  CGM: 'Corrected geomagnetic coordinates: latitude and longitude measured from Earth\'s actual magnetic field rather than the geographic poles.',
  MLT: 'Magnetic local time: the time of day measured around Earth\'s magnetic axis. Aurora is strongest near magnetic midnight.',
  'hemispheric power': 'The power carried into one hemisphere\'s upper atmosphere by auroral particles, in gigawatts: about 5-20 GW quiet, over 100 GW in strong storms.',
  CME: 'Coronal mass ejection: a billion-tonne cloud of plasma and magnetic field thrown off the Sun. Aimed at Earth, it can arrive in 1-4 days and cause a storm.',
  coronagraph: 'A telescope that blocks the bright disk of the Sun to see the faint corona around it, where CMEs are first seen.',
  'Parker spiral': 'The spiral shape of the Sun\'s magnetic field in space, wound up by the Sun\'s rotation like water from a spinning garden sprinkler.',
  PFSS: 'Potential field source surface model: a calculation of the Sun\'s magnetic field from a map of the field on its surface, up to about 2.5 solar radii where it becomes radial.',
  'current sheet': 'The surface in the solar wind where the Sun\'s magnetic field changes direction (from outward to inward). Earth crossing it can bring a change in conditions.',
  'radio occultation': 'Measuring how a spacecraft\'s radio signal changes as it passes close to the Sun: the signal is delayed by the corona\'s electrons and its polarization is turned by their magnetic field.',
  'Faraday rotation': 'The turning of a radio wave\'s polarization by electrons in a magnetic field; it measures the field along the ray.',
  TEC: 'Total electron content: the number of free electrons along a ray, in TEC units (10^16 per square metre).',
  GIC: 'Geomagnetically induced currents: currents that a magnetic storm drives through power lines, pipelines and the ground; they can overheat transformers.',
  'D-RAP': 'NOAA\'s D-region absorption prediction: how strongly the lowest layer of the ionosphere, charged up by solar X-rays, absorbs shortwave (HF) radio on the day side.',
  'sunspot number': 'The count of sunspots, the standard measure of the Sun\'s 11-year activity cycle.',
  'F10.7': 'The Sun\'s radio brightness at 10.7 cm wavelength, measured daily since 1947: another measure of solar activity, in solar flux units.',
  'theta Bn': 'The angle between a shock\'s normal and the upstream magnetic field: below 45 deg the shock is quasi-parallel, above it quasi-perpendicular, which changes how it accelerates particles.',
  'Mach number': 'How many times faster than the relevant wave speed the flow (or the shock) moves; a shock needs a Mach number above 1.',
  'minimum variance': 'A way to find the orientation of a boundary or a twisted field from the field measured across it: the direction along which the field changes least.',
  'de Hoffmann-Teller': 'The frame moving with a structure in which the electric field vanishes; if it exists, the structure is carried by the flow and its speed is that frame\'s velocity.',
  'Alfven Mach number': 'The solar wind speed divided by the Alfven speed (the speed of magnetic waves); usually 5-15 near Earth, and low values mean a weaker bow shock.',
  'proton beta': 'The ratio of the plasma\'s thermal pressure to its magnetic pressure: below 1 the magnetic field dominates (as inside magnetic clouds).',
  'magnetic cloud': 'The core of many CMEs: a large twisted tube of strong, smoothly rotating magnetic field and cool plasma, often a strong storm driver.',
  'flux rope': 'A bundle of twisted magnetic field lines; magnetic clouds are flux ropes, fitted here with the Lundquist force-free model.',
  'sudden commencement': 'A sharp rise of the ground magnetic field within minutes, when a shock or pressure jump compresses the magnetosphere; it often marks a storm\'s start.',
  'SYM-H': 'A 1-minute version of Dst (the ring current index), from mid-latitude magnetometers; negative values mean a storm.',
  'superposed epoch': 'Lining up many events at the same moment (e.g. storm onset) and averaging them, so that the typical behaviour stands out from the noise.',
  ICME: 'Interplanetary CME: a CME as measured near Earth, often with a shock ahead and a magnetic cloud inside.',
  nT: 'Nanotesla, the unit of the magnetic field here: Earth\'s field at the ground is about 50 000 nT, the solar wind\'s about 5 nT.',
  nPa: 'Nanopascal, the unit of the solar wind\'s pressure: about a hundred-trillionth of the air pressure at sea level.',
  R_E: 'Earth radius, 6371 km: distances around Earth are counted in it. Geostationary satellites orbit at 6.6 R_E.',
  shock: 'A sudden jump in solar wind speed, density and field, usually driven by a fast CME or stream; it often starts a geomagnetic storm when it hits.',
  'power spectrum': 'How the strength of fluctuations is spread over time scales; turbulence in the solar wind follows a power law close to Kolmogorov\'s -5/3.',
};

/** Tooltips from GLOSSARY on [data-term] elements. */
function explainTerms(root = document) {
  root.querySelectorAll('[data-term]').forEach((n) => {
    const text = GLOSSARY[n.dataset.term];
    if (text) { n.title = text; n.classList.add('term'); }
  });
}

/** The whole glossary as a definition list (for the user guide). */
function glossaryHtml() {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
  return '<dl class="glossary text-xs">' + Object.entries(GLOSSARY)
    .map(([t, d]) => `<dt class="text-slate-200 font-semibold mt-2">${esc(t)}</dt><dd class="text-slate-400">${esc(d)}</dd>`)
    .join('') + '</dl>';
}
