(() => {
  const choice = document.getElementById('advanceReceiptChoice');
  if (!choice) return;
  const amount = document.getElementById('advanceReceiptAmount');
  const hint = document.getElementById('advanceReceiptHint');
  function update() {
    const remaining = Number(choice.value.split(':')[1]);
    amount.max = (remaining / 100).toFixed(2);
    hint.textContent = `Up to ₹${(remaining / 100).toLocaleString('en-IN', {minimumFractionDigits:2, maximumFractionDigits:2})} for this advance. You can receive a partial amount.`;
  }
  choice.addEventListener('change', update);
  update();
  if (choice.form?.hasAttribute('data-recovery-draft')) {
    window.AppUI?.drafts?.trackForm(choice.form, 'the advance repayment');
  }
})();
