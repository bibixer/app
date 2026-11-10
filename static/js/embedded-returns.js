(() => {
  if (!window.RETURN_EMBEDDED || window.parent === window) return;
  const main = document.querySelector('main');
  let lastHeight = 0;
  let lastRemaining = null;
  const notify = () => {
    const height = Math.ceil(main.getBoundingClientRect().height + 12);
    const remaining = JOB_CARD.items.reduce((sum,item) => sum + Number(item.issued),0);
    if (height === lastHeight && remaining === lastRemaining) return;
    lastHeight = height;
    lastRemaining = remaining;
    parent.postMessage({type:'job-return-state', jobId:JOB_CARD.jobcard_id, height,
      remaining}, location.origin);
  };
  new ResizeObserver(notify).observe(main);
  window.addEventListener('load', notify);
  notify();
})();
