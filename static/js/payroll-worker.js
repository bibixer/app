/* Use the same canonical master map as manual job creation. */
(() => {
  const form = document.getElementById('payrollWorkerForm');
  const input = document.getElementById('payrollWorker');
  const button = document.getElementById('openPayrollAccount');
  const status = document.getElementById('payrollWorkerMatch');
  const mapping = JSON.parse(document.getElementById('payrollMasterMap').textContent);
  const normalize = value => value.trim().replace(/\s+/g, ' ').toUpperCase();
  const editable = () => !input.readOnly && !input.disabled
    && !input.matches?.(':disabled,[aria-disabled="true"],[aria-readonly="true"]')
    && !input.closest?.('[inert],[aria-disabled="true"]');
  const resolve = () => {
    const key = normalize(input.value);
    return Object.hasOwn(mapping, key) ? mapping[key] : null;
  };
  function fill(report = false) {
    const full = resolve();
    if (!editable()) return Boolean(full);
    input.setCustomValidity(full ? '' : 'Select an existing outworker by name, alias or ID.');
    if (full) input.value = full;
    status.textContent = full ? `Selected: ${full}` : (input.value ? 'Choose an existing name, alias or exact ID.' : '');
    if (!full && report) input.reportValidity();
    return Boolean(full);
  }
  input.addEventListener('input', () => {
    if (!editable()) return;
    input.setCustomValidity('');
    const full = resolve();
    status.textContent = full ? `Matched: ${full}` : '';
  });
  input.addEventListener('change', () => fill());
  input.addEventListener('blur', () => fill());
  input.addEventListener('keydown', event => {
    if (!editable()) return;
    if (event.key !== 'Enter' || event.isComposing) return;
    event.preventDefault();
    if (fill(true)) button.focus();
  });
  button.addEventListener('keydown', event => {
    if (event.key !== 'Backspace') return;
    event.preventDefault();
    input.focus();
  });
  form.addEventListener('submit', event => {
    if (!fill(true)) { event.preventDefault(); input.focus(); }
  });
})();
