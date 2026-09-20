/**
 * HELIOS-L1: SYNTHESIZED WEB AUDIO MISSION CONTROL SOUND ENGINE
 * Pure client-side Web Audio API procedural synthesis.
 * 100% offline, zero external audio assets required.
 */

class SoundEngine {
  constructor() {
    this.ctx = null;
    this.enabled = true;
    this.ambientGain = null;
    this.ambientOsc = null;
    this.isAmbientPlaying = false;
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
      this.stopAmbient();
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

  warningKlaxon() {
    if (!this.enabled) return;
    this.init();
    if (!this.ctx) return;

    try {
      const now = this.ctx.currentTime;
      for (let i = 0; i < 2; i++) {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();

        const tStart = now + i * 0.22;
        osc.type = 'sawtooth';
        osc.frequency.setValueAtTime(580, tStart);
        osc.frequency.linearRampToValueAtTime(880, tStart + 0.12);

        gain.gain.setValueAtTime(0.06, tStart);
        gain.gain.exponentialRampToValueAtTime(0.001, tStart + 0.18);

        osc.connect(gain);
        gain.connect(this.ctx.destination);

        osc.start(tStart);
        osc.stop(tStart + 0.18);
      }
    } catch (e) {}
  }

  stopAmbient() {
    if (this.ambientOsc) {
      try {
        this.ambientOsc.stop();
        this.ambientOsc.disconnect();
      } catch (e) {}
      this.ambientOsc = null;
    }
    this.isAmbientPlaying = false;
  }
}

window.soundEngine = new SoundEngine();
function playBlip() { window.soundEngine?.blip(); }
function playRadarPing() { window.soundEngine?.radarPing(); }
function playWarningKlaxon() { window.soundEngine?.warningKlaxon(); }
function toggleAudio() { window.soundEngine?.toggle(); }
