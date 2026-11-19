(() => {
  const input = document.getElementById('recoveryWorker');
  const status = document.getElementById('recoveryWorkerStatus');
  const apply = document.getElementById('recoveryApplyWorker');
  const {workers, mapping} = JSON.parse(document.getElementById('recoveryWorkerData').textContent);

  input.addEventListener('input', () => status.classList.remove('is-error'));
  initManualMasterSuggestions({
    input,
    list: document.getElementById('recoveryWorkerOptions'),
    status,
    workers,
    mapping,
    onCommit() {
      status.classList.remove('is-error');
      apply.focus();
    },
    onInvalid() {
      if (!input.value.trim()) {
        status.classList.remove('is-error');
        apply.focus();
        return;
      }
      status.textContent = 'Choose an outworker from the suggestions.';
      status.classList.add('is-error');
    },
  });
})();
