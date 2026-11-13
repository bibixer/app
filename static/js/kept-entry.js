const keptSection = document.querySelector('#kept-pieces');
if (keptSection && (location.hash === '#kept-pieces' || document.body.classList.contains('kept-popup'))) {
  keptSection.open = true;
}
document.querySelectorAll('.kept-product-form').forEach(form => {
  const input = form.querySelector('[name=pieces]');
  if (document.body.classList.contains('kept-popup')) {
    form.closest('details').open = true;
  }
  input.addEventListener('input', () => {
    const qty = Number(input.value), value = Number(input.dataset.unitValue);
    form.querySelector('.kept-recovery-preview').textContent = Number.isInteger(qty) && qty > 0 && input.validity.valid
      ? `${qty} kept × ₹${(value / 100).toFixed(2)} = ₹${(qty * value / 100).toFixed(2)} to recover. Kept pieces become eligible for payroll.`
      : 'Enter valid kept pieces.';
  });
  form.addEventListener('submit', event => {
    const draft = [...document.querySelectorAll('.return-input, .calc-pieces, .calc-count')]
      .find(field => field.value.trim() !== '');
    if (draft) {
      event.preventDefault();
      form.querySelector('.kept-recovery-preview').textContent = 'Save or clear this job’s unfinished physical return before recording kept pieces.';
      draft.focus();
    }
  });
});
