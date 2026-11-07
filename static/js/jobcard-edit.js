// Preview an admin's return correction. Saving and permission checks stay on the server.
(() => {
  document.querySelectorAll('.restore-return').forEach(button => {
    const input = document.getElementById(button.dataset.returnInput);
    const feedback = button.parentElement.querySelector('.restore-feedback');
    if (!input || !feedback) return;

    const update = () => {
      if (input.matches(':disabled')) return;
      const original = Number(input.dataset.originalReturn);
      const current = Number(input.value);
      if (!input.value.trim() || !Number.isSafeInteger(current) || current < 0) {
        feedback.textContent = '';
        button.disabled = true;
        return;
      }
      button.disabled = current === 0;
      const restored = original - current;
      feedback.textContent = restored > 0
        ? `${restored} pieces will move back to given / pending after Save changes.`
        : restored < 0
          ? `${-restored} additional pieces will be counted as returned after Save changes.`
          : '';
    };

    button.addEventListener('click', () => {
      if (input.matches(':disabled')) return;
      input.value = '0';
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.focus();
    });
    input.addEventListener('input', update);
    update();
  });
})();
