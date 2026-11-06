// Expand report details for printing, then restore the reader's view.
(() => {
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
