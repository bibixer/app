// Expand report details for printing, then restore the reader's view.
(() => {
  document.addEventListener('wheel', event => {
    const field = document.activeElement;
    if (field?.matches('input[type="number"]') && event.target === field) {
      // Release focus before the browser handles the wheel so it scrolls the page.
      field.blur();
    }
  }, {capture:true, passive:true});

  document.addEventListener('input', event => {
    const field = event.target;
    if (!field.matches('input[data-decimal-places]')) return;
    const places = Number(field.dataset.decimalPlaces);
    const decimal = new RegExp(`^(?:[0-9]+(?:\\.[0-9]{1,${places}})?|\\.[0-9]{1,${places}})$`);
    field.setCustomValidity(field.value && !decimal.test(field.value)
      ? `Use digits and a decimal point only, with up to ${places} decimal places.`
      : '');
  }, {capture:true});

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
      if (body.classList.contains('return-embedded') && window.frameElement?.matches('.return-job-frame')) {
        const workspace = window.parent;
        if (workspace.AppUI?.navigate) workspace.AppUI.navigate(destination);
        else workspace.location.assign(destination);
        return;
      }
      if (window.AppUI?.navigate) window.AppUI.navigate(destination);
      else window.location.assign(destination);
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
