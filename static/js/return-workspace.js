(() => {
  for (const frame of document.querySelectorAll('.return-job-frame')) {
    const jobId = frame.closest('[data-job-id]').dataset.jobId;
    window.AppUI?.drafts?.register({
      label: `job #${jobId} return or kept pieces`,
      dirty: () => [...(frame.contentDocument?.querySelectorAll(
        '.return-input, .calc-pieces, .calc-count, .kept-product-form input:not([type=hidden])'
      ) || [])].some(field => field.value.trim() !== '' || field.validity.badInput),
      busy: () => Boolean(frame.contentDocument?.querySelector('.btn-submit.app-saving')),
    });
  }

  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.data?.type !== 'job-return-state') return;
    const section = [...document.querySelectorAll('[data-job-id]')].find(node =>
      node.dataset.jobId === String(event.data.jobId) && node.querySelector('iframe').contentWindow === event.source);
    if (!section) return;
    const {height, remaining} = event.data;
    if (Number.isFinite(height) && height > 0 && height < 1000000) section.querySelector('iframe').style.height = `${height}px`;
    if (!Number.isSafeInteger(remaining) || remaining < 0) return;
    section.dataset.remaining = remaining;
    section.querySelector('[data-job-pending]').textContent = remaining ? `${remaining} pieces pending` : 'Complete · no pieces pending';
    const jobs = [...document.querySelectorAll('[data-job-id]')];
    document.querySelector('#open-return-count').textContent = jobs.filter(job => Number(job.dataset.remaining) > 0).length;
    document.querySelector('#open-return-pieces').textContent = jobs.reduce((sum,job) => sum + Number(job.dataset.remaining),0);
  });
})();
