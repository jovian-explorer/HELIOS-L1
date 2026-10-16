/**
 * HELIOS-L1: SYNTHESIZED WEB AUDIO MISSION CONTROL SOUND ENGINE
 * Pure client-side Web Audio API procedural synthesis.
 * 100% offline, zero external audio assets required.
 */

class SoundEngine {
  constructor() {
    this.ctx = null;
    this.enabled = true;
  }

  init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) {
        this.ctx = new AudioCtx();
      }
    }
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
  }

  toggle() {
    this.enabled = !this.enabled;
    const icon = document.getElementById('icon-audio');
    const text = document.getElementById('text-audio');
    if (this.enabled) {
      if (icon) icon.className = 'fa-solid fa-volume-high text-cyan-400';
      if (text) text.innerText = 'Audio: ON';
      this.blip();
    } else {
      if (icon) icon.className = 'fa-solid fa-volume-xmark text-slate-500';
      if (text) text.innerText = 'Audio: OFF';
    }
    return this.enabled;
  }

  blip(freq = 880, duration = 0.06) {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(freq, this.ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(freq * 1.5, this.ctx.currentTime + duration);

      gain.gain.setValueAtTime(0.04, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + duration);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start();
      osc.stop(this.ctx.currentTime + duration);
    } catch (e) {
      // Audio autoplay policy catch
    }
  }

  radarPing() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();

      osc.type = 'sine';
      osc.frequency.setValueAtTime(1450, this.ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(720, this.ctx.currentTime + 0.35);

      gain.gain.setValueAtTime(0.08, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.0001, this.ctx.currentTime + 0.35);

      osc.connect(gain);
      gain.connect(this.ctx.destination);

      osc.start();
      osc.stop(this.ctx.currentTime + 0.35);
    } catch (e) {}
  }

  sonifySolarWind(speed = 450, bz = -2.5, density = 6.0, duration = 2.4) {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    try {
      const now = this.ctx.currentTime;
      // 1. Base carrier frequency mapped to bulk solar wind speed (300 - 1000 km/s -> 180 - 540 Hz)
      const normSpeed = Math.max(0, Math.min(1, (speed - 300) / 700));
      const fBase = 180 + normSpeed * 360;

      // 2. Harmonic interval based on IMF Bz orientation (consonant vs discordant reconnection)
      const isReconnecting = bz < 0;
      const fHarmonic = isReconnecting ? fBase * 1.414 : fBase * 1.5; // Tritone vs Perfect Fifth

      // 3. Tremolo modulation frequency mapped to proton plasma density (2 - 25 cm⁻³ -> 3 - 12 Hz)
      const normDensity = Math.max(0, Math.min(1, (density - 2) / 23));
      const lfoFreq = 3 + normDensity * 9;

      // Primary carrier
      const osc1 = this.ctx.createOscillator();
      const gain1 = this.ctx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(fBase, now);
      osc1.frequency.linearRampToValueAtTime(fBase * 1.05, now + duration);

      // Secondary harmonic
      const osc2 = this.ctx.createOscillator();
      const gain2 = this.ctx.createGain();
      osc2.type = isReconnecting ? 'triangle' : 'sine';
      osc2.frequency.setValueAtTime(fHarmonic, now);
      osc2.frequency.linearRampToValueAtTime(fHarmonic * 0.98, now + duration);

      // LFO amplitude modulator for plasma density turbulence
      const lfo = this.ctx.createOscillator();
      const lfoGain = this.ctx.createGain();
      lfo.frequency.setValueAtTime(lfoFreq, now);
      lfoGain.gain.setValueAtTime(0.025, now);
      // Tremolo of the carrier: +-0.025 on its gain of 0.05 (the LFO used to drive the gain of an
      // unconnected node, so density had no audible effect).
      lfo.connect(lfoGain);
      lfoGain.connect(gain1.gain);

      // Master output envelope
      const masterGain = this.ctx.createGain();
      masterGain.gain.setValueAtTime(0.0001, now);
      masterGain.gain.exponentialRampToValueAtTime(0.07, now + 0.3);
      masterGain.gain.exponentialRampToValueAtTime(0.0001, now + duration);

      // Connect graph
      gain1.gain.setValueAtTime(0.05, now);
      gain2.gain.setValueAtTime(isReconnecting ? 0.04 : 0.03, now);

      osc1.connect(gain1);
      osc2.connect(gain2);
      gain1.connect(masterGain);
      gain2.connect(masterGain);
      masterGain.connect(this.ctx.destination);

      osc1.start(now);
      osc2.start(now);
      lfo.start(now);

      osc1.stop(now + duration);
      osc2.stop(now + duration);
      lfo.stop(now + duration);
    } catch (e) {
      console.warn('Sonification playback exception:', e);
    }
  }

}

window.soundEngine = new SoundEngine();
function playBlip() { window.soundEngine?.blip(); }
function playRadarPing() { window.soundEngine?.radarPing(); }
function toggleAudio() { window.soundEngine?.toggle(); }
