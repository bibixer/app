/* Synthesized UI cues: no downloads, autoplay, or navigation delays. */
(() => {
  const api = window.AppUI = window.AppUI || {};
  if (document.body?.classList.contains('return-embedded') && window.parent !== window) {
    const forward = event => {
      if (!event.isTrusted) return;
      try { window.parent.AppUI?.unlockSound?.(event); } catch (_) {}
    };
    document.addEventListener('pointerdown', forward, true);
    document.addEventListener('keydown', forward, true);
    return; // One audio context and mute preference for the whole workspace.
  }
  const key = 'bh.ui-sounds.v1';
  const controls = [...document.querySelectorAll('[data-sound-toggle]')];
  let enabled = true, context, waking, lastCue = -Infinity;
  try { enabled = localStorage.getItem(key) !== 'off'; } catch (_) {}
  const render = () => controls.forEach(button => {
    button.setAttribute('data-ready', '');
    button.textContent = enabled ? '♫ Sound on' : '♫ Sound off';
    button.setAttribute('aria-pressed', String(enabled));
    button.setAttribute('aria-label', enabled ? 'Mute sound effects' : 'Enable sound effects');
    button.title = enabled ? 'Mute sound effects' : 'Enable sound effects';
  });
  function wake() {
    if (!enabled || document.hidden) return;
    try {
      const Audio = window.AudioContext || window.webkitAudioContext;
      if (!Audio) return;
      context ||= new Audio();
      if (context.state !== 'running') {
        // resume() is asynchronous in real browsers. Cues may wait briefly for
        // this attempt, never for an unrelated click several seconds later.
        waking = context.resume();
        waking.catch(() => {});
      }
    } catch (_) { /* Sound must never interrupt workflows. */ }
  }
  function unlock(event) {
    if (!event.isTrusted || !enabled || document.hidden) return;
    try { sessionStorage.setItem('bh.audio-authorized.v1', 'yes'); } catch (_) {}
    wake();
  }
  api.unlockSound = unlock;
  // Original, graphic-JRPG menu palette: clipped transients, filtered synth
  // swipes and syncopated minor/ninth accents, rather than rounded alert bells.
  // Each voice: start Hz, end Hz, beat offset, duration, gain, waveform, cutoff.
  const scores = {
    transition: [
      [110, 48, 0, .075, .09, 'triangle', 1400],
      [1350, 160, .008, .095, .035, 'sawtooth', 2600],
      [2200, 850, 0, .022, .018, 'square', 3600],
    ],
    success: [
      [587, 587, 0, .045, .055, 'square', 1800],
      [698, 698, .065, .05, .09, 'triangle', 2400],
      [1319, 1175, .145, .12, .085, 'triangle', 3200],
    ],
    error: [[147, 98, 0, .075, .065, 'sawtooth', 650],
      [139, 92, .095, .09, .06, 'square', 550]],
    warning: [[440, 294, 0, .085, .055, 'triangle', 1600]],
    info: [[1175, 880, 0, .04, .045, 'triangle', 2600]],
    select: [[1760, 1175, 0, .025, .025, 'triangle', 3000]],
  };
  api.playSound = type => {
    if (!enabled || document.hidden || !context || !scores[type]) return;
    if (context.state !== 'running') {
      if (waking) {
        const deadline = Date.now() + 700;
        // Do not recursively retry: blocked audio must not queue stale sounds.
        waking.then(() => {
          if (Date.now() <= deadline && context.state === 'running') api.playSound(type);
        }).catch(() => {});
      }
      return;
    }
    const now = context.currentTime;
    if (now - lastCue < .08) return;
    lastCue = now;
    try {
      for (const [from, to, offset, duration, volume, wave, cutoff] of scores[type]) {
        const oscillator = context.createOscillator(), gain = context.createGain();
        const start = now + offset, end = start + duration;
        oscillator.type = wave;
        oscillator.frequency.setValueAtTime(from, start);
        oscillator.frequency.exponentialRampToValueAtTime(to, end);
        gain.gain.setValueAtTime(0, start);
        gain.gain.linearRampToValueAtTime(volume, start + .002);
        gain.gain.exponentialRampToValueAtTime(.0001, end);
        // A low-pass sweep takes the harsh edge off square/saw transients.
        const filter = context.createBiquadFilter?.();
        if (filter) {
          filter.type = 'lowpass';
          filter.frequency.setValueAtTime(cutoff, start);
          filter.frequency.exponentialRampToValueAtTime(Math.max(300, cutoff * .4), end);
          filter.Q.setValueAtTime(.7, start);
          oscillator.connect(filter); filter.connect(gain);
        } else oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.onended = () => { oscillator.disconnect(); filter?.disconnect(); gain.disconnect(); };
        oscillator.start(start); oscillator.stop(end + .01);
      }
    } catch (_) { /* Unsupported audio must never interrupt a save. */ }
  };
  controls.forEach(button => button.addEventListener('click', event => {
    enabled = !enabled;
    try { localStorage.setItem(key, enabled ? 'on' : 'off'); } catch (_) {}
    render();
    if (!enabled) { try { context?.suspend().catch(() => {}); } catch (_) {} }
    else {
      unlock(event);
      api.playSound('success');
    }
  }));
  document.addEventListener('pointerdown', unlock, true);
  document.addEventListener('keydown', unlock, true);
  // A short menu tick for deliberate option changes, never for typing/hovering.
  document.addEventListener('change', event => {
    if (!event.isTrusted || !event.target.matches('select,input[type="checkbox"],input[type="radio"]')
        || event.target.disabled || event.target.readOnly) return;
    unlock(event); api.playSound('select');
  });
  window.addEventListener('storage', event => {
    if (event.key !== key) return;
    enabled = event.newValue !== 'off'; render();
    if (!enabled) { try { context?.suspend().catch(() => {}); } catch (_) {} }
  });
  window.addEventListener('pagehide', () => {
    waking = null;
    try { context?.suspend().catch(() => {}); } catch (_) {}
  });
  render();
  // Restore an already-requested audio session after a normal page navigation.
  // Browsers still enforce their autoplay policy; a blocked attempt stays silent
  // and the next trusted click/key retries it. First visits never start audio.
  try { if (sessionStorage.getItem('bh.audio-authorized.v1') === 'yes') wake(); } catch (_) {}
})();
