(() => {
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.data?.type !== 'job-return-state') return;
    const section = [...document.querySelectorAll('[data-job-id]')].find(node =>
      node.dataset.jobId === String(event.data.jobId) && node.querySelector('iframe').contentWindow === event.source);
    if (!section) return;
    const {height, remaining} = event.data;
    if (Number.isFinite(height) && height > 0 && height < 1000000) section.querySelector('iframe').style.height = `${height}px`;
    if (!Number.isSafeInteger(remaining) || remaining < 0) return;
    section.dataset.remaining = remaining;
    section.querySelector('[data-job-pending]').textContent = remaining ? `${remaining} pieces pending` : 'Fully returned';
    const jobs = [...document.querySelectorAll('[data-job-id]')];
    document.querySelector('#open-return-count').textContent = jobs.filter(job => Number(job.dataset.remaining) > 0).length;
    document.querySelector('#open-return-pieces').textContent = jobs.reduce((sum,job) => sum + Number(job.dataset.remaining),0);
  });
})();
