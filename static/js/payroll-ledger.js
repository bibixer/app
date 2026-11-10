/* Reorder existing rows only. Their historical running balances never change. */
(() => {
  const control = document.getElementById('payrollLedgerOrder');
  const body = document.getElementById('payrollLedgerRows');
  const status = document.getElementById('payrollLedgerOrderStatus');
  if (!control || !body) return;
  function reorder() {
    const oldest = control.value === 'oldest';
    const direction = oldest ? 1 : -1;
    const rows = [...body.querySelectorAll('tr[data-ledger-order]')];
    rows.sort((a, b) => direction * (Number(a.dataset.ledgerOrder) - Number(b.dataset.ledgerOrder)));
    rows.forEach(row => body.appendChild(row));
    status.textContent = `${oldest ? 'Oldest' : 'Newest'} first. Each balance is the amount remaining after that record.`;
  }
  control.addEventListener('change', reorder);
  reorder();
})();
