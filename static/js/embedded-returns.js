(() => {
  if (!window.RETURN_EMBEDDED || window.parent === window) return;
  const main = document.querySelector('main');
  let lastHeight = 0;
  const notify = () => {
    const height = Math.ceil(main.getBoundingClientRect().height + 12);
    if (height === lastHeight) return;
    lastHeight = height;
    parent.postMessage({type:'job-return-state', jobId:JOB_CARD.jobcard_id, height,
      remaining:JOB_CARD.items.reduce((sum,item) => sum + Number(item.issued),0)}, location.origin);
  };
  new ResizeObserver(notify).observe(main);
  window.addEventListener('load', notify);
  notify();
})();
