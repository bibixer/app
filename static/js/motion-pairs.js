/* 32 authored full-screen close -> open combinations. Ordered, never random.
 * Select the destination's exact entrance before its first paint. */
(() => {
  const api = window.AppUI = window.AppUI || {};
  const pairs = Object.freeze([
    ['slash','split'], ['split','blinds'], ['blinds','prism'], ['prism','sweep'],
    ['sweep','fold'], ['fold','orbit'], ['orbit','cascade'], ['cascade','slash'],
    ['slash','blinds'], ['split','prism'], ['blinds','sweep'], ['prism','fold'],
    ['sweep','orbit'], ['fold','cascade'], ['orbit','slash'], ['cascade','split'],
    ['slash','prism'], ['split','sweep'], ['blinds','fold'], ['prism','orbit'],
    ['sweep','cascade'], ['fold','slash'], ['orbit','split'], ['cascade','blinds'],
    ['slash','fold'], ['split','orbit'], ['blinds','cascade'], ['prism','slash'],
    ['sweep','split'], ['fold','blinds'], ['orbit','prism'], ['cascade','sweep'],
  ].map(([close, open], id) => Object.freeze({id, close, open})));
  const handoffKey = 'bh.full-motion-handoff.v1';
  const cursorKey = 'bh.full-motion-cursor.v1';
  const trailKey = 'bh.blue-motion-trail.v1';
  let trail = [], pair = pairs[0], cursor = 0, direction = 'forward';
  try {
    const saved = JSON.parse(sessionStorage.getItem(cursorKey));
    if (Number.isInteger(saved) && saved >= 0 && saved < pairs.length) cursor = saved;
  } catch (_) {}
  try {
    const saved = JSON.parse(sessionStorage.getItem(trailKey));
    if (Array.isArray(saved)) trail = saved.filter(path => typeof path === 'string' && path.startsWith('/') && path.length < 512).slice(-12);
  } catch (_) {}
  try {
    const handoff = JSON.parse(sessionStorage.getItem(handoffKey));
    sessionStorage.removeItem(handoffKey);
    if (handoff && Number.isInteger(handoff.pair) && pairs[handoff.pair]
        && Number.isFinite(handoff.time) && Date.now()-handoff.time >= 0 && Date.now()-handoff.time < 15000) {
      pair = pairs[handoff.pair];
      if (['forward','back','confirm'].includes(handoff.direction)) direction = handoff.direction;
    } else if (window.performance?.getEntriesByType('navigation')[0]?.type === 'back_forward') direction = 'back';
  } catch (_) {}
  function rememberCurrent(history = false) {
    const current = window.location.pathname;
    const previous = trail.lastIndexOf(current);
    if (history && previous >= 0) trail = trail.slice(0, previous + 1);
    else if (trail.at(-1) !== current) {
      if (trail.at(-2) === current) trail.pop();
      else trail.push(current);
    }
    trail = trail.slice(-12);
    try { sessionStorage.setItem(trailKey, JSON.stringify(trail)); } catch (_) {}
  }
  rememberCurrent(direction === 'back');
  document.documentElement.dataset.scene = pair.open;
  document.documentElement.dataset.motionDirection = direction;
  document.documentElement.dataset.motionPair = String(pair.id);
  api.motion = Object.freeze({pairs, handoffKey, revisit() {
    try {
      const saved = JSON.parse(sessionStorage.getItem(trailKey));
      if (Array.isArray(saved)) trail = saved.filter(path => typeof path === 'string' && path.startsWith('/') && path.length < 512).slice(-12);
    } catch (_) {}
    rememberCurrent(true);
  }, nextPair(options = {}) {
    const direction = options.confirm ? 'confirm' : options.back || (options.destination && new URL(options.destination, window.location.href).pathname === trail.at(-2)) ? 'back' : 'forward';
    const pair = pairs[cursor];
    cursor = (cursor + 1) % pairs.length;
    try { sessionStorage.setItem(cursorKey, JSON.stringify(cursor)); } catch (_) {}
    return {...pair, direction};
  }});
})();
