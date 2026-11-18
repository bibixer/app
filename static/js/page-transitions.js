/* Close the current screen, then let the destination's own CSS reveal it. */
(() => {
  const body = document.body;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const api = window.AppUI = window.AppUI || {};
  const handoffKey = api.motion?.handoffKey || 'bh.full-motion-handoff.v1';
  const closeDuration = 160;
  let closeSequence = 0;
  let layerTimer;
  const releaseLayers = () => body.classList.remove('is-motion-active');
  const warmLayers = () => {
    clearTimeout(layerTimer);
    body.classList.add('is-motion-active');
    layerTimer = setTimeout(releaseLayers, 340);
  };
  if (!reduced.matches && !body.classList.contains('return-embedded') && !body.classList.contains('no-page-motion')) warmLayers();
  let pending = false, recovery, ownedHandoff;
  const reset = () => {
    pending = false; clearTimeout(recovery); body.classList.remove('is-page-closing');
    try {
      const saved = JSON.parse(sessionStorage.getItem(handoffKey));
      if (ownedHandoff && saved?.id === ownedHandoff) sessionStorage.removeItem(handoffKey);
    } catch (_) { /* Visual state is optional. */ }
    ownedHandoff = null;
  };
  function closeScreen(options = {}) {
    warmLayers();
    api.playSound?.('transition');
    document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
    const pair = api.motion?.nextPair(options) || {id:0, close:'slash', direction:'forward'};
    document.documentElement.dataset.scene = pair.close;
    document.documentElement.dataset.motionPair = String(pair.id);
    document.documentElement.dataset.motionDirection = pair.direction;
    ownedHandoff = `${Date.now()}-${++closeSequence}`;
    try {
      sessionStorage.setItem(handoffKey, JSON.stringify({pair:pair.id,direction:pair.direction,time:Date.now(),id:ownedHandoff}));
    } catch (_) { /* Restricted storage falls back to the default entrance. */ }
    body.classList.add('is-page-closing');
    // CSS starts the new close animation itself. Avoid a synchronous style flush
    // and restarting every layer here, which stalls the first animation frame.
  }
  function navigate(destination, options = {}) {
    const url = new URL(destination, location.href);
    const leave = () => options.replace ? location.replace(url.href) : location.assign(url.href);
    if (url.origin !== location.origin || reduced.matches || body.classList.contains('return-embedded')) {
      leave(); return;
    }
    if (pending) return;
    pending = true;
    closeScreen({...options, destination:url.href});
    setTimeout(() => {
      leave();
      // An unsaved-changes prompt may cancel navigation; never leave the screen
      // covered indefinitely. No form is re-submitted or replayed here.
      recovery = setTimeout(reset, 1000);
    }, closeDuration);
  }
  api.navigate = navigate;
  document.addEventListener('click', event => {
    if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    const link = event.target.closest('a[href]');
    if (!link || link.hasAttribute('download') || (link.target && link.target !== '_self')) return;
    if (link.getAttribute('href').startsWith('#')) return;
    const url = new URL(link.href, location.href);
    if (!/^https?:$/.test(url.protocol) || url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return;
    event.preventDefault(); navigate(url.href);
  });
  document.addEventListener('submit', event => {
    // Authentication must succeed on the server before login may animate.
    if (event.target.id === 'loginForm') return;
    if (event.target.method === 'dialog') return;
    const target = event.submitter?.formTarget || event.target.target;
    if (target && target !== '_self') return;
    if (pending) { event.preventDefault(); return; }
    // Native forms keep browser validation, their original submitter, and exactly
    // one request. Close visually while that request starts; never delay a POST.
    if (!event.defaultPrevented && !reduced.matches && !body.classList.contains('return-embedded')) {
      pending = true;
      closeScreen({confirm:true});
      recovery = setTimeout(reset, 1000);
    }
  });
  window.addEventListener('pageshow', event => {
    reset();
    if (!event.persisted || reduced.matches || body.classList.contains('return-embedded')) return;
    api.motion?.revisit();
    warmLayers();
    document.documentElement.dataset.motionDirection = 'back';
    const pair = api.motion?.pairs[Number(document.documentElement.dataset.motionPair)];
    document.documentElement.dataset.scene = pair?.open || 'split';
    // Cached pages do not rerun head scripts: replay only the decorative layers.
    for (const animation of document.querySelector('.app-page-cut')?.getAnimations?.({subtree:true}) || []) {
      animation.currentTime = 0; animation.play();
    }
  });
})();
