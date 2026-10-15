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
      '../helios/gui/static/js/glossary.js',
    ],
  },
  darkMode: 'class',
  theme: {
    // One font family (figures line up through tabular numerals in style.css).
    fontFamily: {
      sans: ['system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'Arial', 'sans-serif'],
      mono: ['system-ui', '-apple-system', '"Segoe UI"', 'Roboto', 'Arial', 'sans-serif'],
    },
    extend: {
      // A calm palette: neutral greys, one accent (every decorative hue maps to it) and muted
      // status colours (green / amber / red) for levels and alerts.
      colors: (() => {
        const scale = v => Object.fromEntries([50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((k, i) => [k, v[i]]));
        const neutral = scale(['#f6f7f8', '#eaebed', '#d6d8db', '#b9bcc1', '#9a9ea5', '#888c94', '#5f636a', '#43464c', '#2b2e33', '#1e2024', '#141518']);
        const accent = scale(['#eff4fa', '#dce7f3', '#bdd2e8', '#9bbadb', '#7fa5cf', '#6690bf', '#4f77a3', '#3f5f83', '#334c68', '#2a3f55', '#1b2938']);
        const green = scale(['#eef7f1', '#d6ecdd', '#b0d9bf', '#8cc6a1', '#6db487', '#529b6e', '#407d58', '#336448', '#2a503b', '#234232', '#13241b']);
        const amber = scale(['#fbf6ea', '#f4e8c8', '#ebd6a2', '#dfc078', '#d2aa57', '#b98f3f', '#9a7332', '#7b5a29', '#634825', '#523c21', '#2e2111']);
        const red = scale(['#fbf0f0', '#f6dddd', '#edc0c0', '#e29c9c', '#d77e7e', '#c26262', '#a44e4e', '#874141', '#6e3737', '#5b2f2f', '#331818']);
        return {
          space: { 950: '#141518', 900: '#191b1e', 800: '#1f2125', 700: '#272a2f', 600: '#30343a',
                   accent: '#7fa5cf', solar: '#d2aa57', plasma: '#6db487', danger: '#d77e7e' },
          slate: neutral, gray: neutral, zinc: neutral,
          sky: accent, cyan: accent, blue: accent, indigo: accent, purple: accent, violet: accent,
          fuchsia: accent, pink: accent, teal: accent, lime: accent,
          emerald: green, green,
          amber, yellow: amber, orange: amber,
          rose: red, red,
        };
      })(),
    },
  },
};
