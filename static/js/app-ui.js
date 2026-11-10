// Expand report details for printing, then restore the reader's view.
(() => {
  // Global workflow shortcuts are enabled only on authenticated app pages.
  const body = document.body;
  if (body && !body.classList.contains('is-guest')) {
    const shortcuts = {
      j: body.dataset.shortcutJob,
      r: body.dataset.shortcutReturn,
      h: body.dataset.shortcutPayroll
    };
    document.addEventListener('keydown', event => {
      const jobFieldId = body.dataset.shortcutReturnJobField;
      const workerFieldId = body.dataset.shortcutReturnWorkerField;
      if (!event.altKey && !event.ctrlKey && !event.metaKey && event.key === 'Tab' && jobFieldId && workerFieldId) {
        const jobField = document.getElementById(jobFieldId);
        const workerField = document.getElementById(workerFieldId);
        if (jobField && workerField && (document.activeElement === jobField || document.activeElement === workerField)) {
          event.preventDefault();
          (document.activeElement === workerField ? jobField : workerField).focus();
          return;
        }
      }
      if (!event.altKey || event.ctrlKey || event.metaKey || event.shiftKey || event.repeat) return;
      const destination = shortcuts[event.key.toLowerCase()];
      if (!destination) return;
      event.preventDefault();
      window.location.assign(destination);
    });
  }

  const openedForPrint = new Set();
  window.addEventListener('beforeprint', () => {
    document.querySelectorAll('#main-content details:not([open])').forEach(detail => {
      openedForPrint.add(detail);
      detail.open = true;
    });
  });
  window.addEventListener('afterprint', () => {
    openedForPrint.forEach(detail => { detail.open = false; });
    openedForPrint.clear();
  });
})();
