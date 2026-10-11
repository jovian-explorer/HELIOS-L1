// Tailwind CSS 3.4.17 (MIT licence) configuration for helios/gui/static/css/tailwind.css.
// Rebuild with `python scripts/build_css.py` after changing classes in the page or scripts.
module.exports = {
  content: {
    relative: true,
    files: [
      '../helios/gui/static/index.html',
      '../helios/gui/static/js/app.js',
      '../helios/gui/static/js/audio.js',
      '../helios/gui/static/js/aurora.js',
      '../helios/gui/static/js/cme_sim.js',
      '../helios/gui/static/js/coronal_field.js',
      '../helios/gui/static/js/event_analysis.js',
      '../helios/gui/static/js/forecast.js',
      '../helios/gui/static/js/image_archive.js',
      '../helios/gui/static/js/matrix.js',
      '../helios/gui/static/js/occultation.js',
      '../helios/gui/static/js/orbits.js',
      '../helios/gui/static/js/parker.js',
      '../helios/gui/static/js/solar_viewer.js',
      '../helios/gui/static/js/statistics.js',
    ],
  },
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        space: {
          950: '#03060c',
          900: '#060a12',
          800: '#0b1329',
          700: '#111e3e',
          600: '#1b2d5a',
          accent: '#38bdf8',
          solar: '#f59e0b',
          plasma: '#10b981',
          danger: '#f43f5e',
        },
      },
    },
  },
};
