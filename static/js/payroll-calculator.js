/* No request is made for calculation. Confirmation still uses server validation. */
function calculatePayrollLocally(data, jobIds, advanceIds) {
  const wantedJobs = new Set(jobIds.map(String));
  const wantedAdvances = new Set(advanceIds.map(String));
  const jobs = data.jobs.filter(job => wantedJobs.has(String(job.id)));
  if (jobs.length !== wantedJobs.size) throw new Error('Select available jobs from this account.');
  if (jobs.some(job => job.errors.length)) throw new Error('Set missing product rates before calculating these jobs.');
  const advances = data.advances.filter(row => wantedAdvances.has(String(row.id)) && row.remaining_paise > 0);
  if (advances.length !== wantedAdvances.size) throw new Error('Select available advances from this account.');
  if (!jobs.length) {
    if (!advances.length) throw new Error('Select jobs to pay or tick advances to receive money back.');
    const amount = advances.reduce((sum, row) => sum + row.remaining_paise, 0);
    if (!Number.isSafeInteger(amount) || amount > 99999999999) throw new Error('Selected advance total exceeds the supported payment limit.');
    return {mode:'recovery', jobs, advances, gross:0, deduction:amount, net:0,
      remaining:data.available - amount, pieces:0,
      recoveries:advances.map(row => ({id:row.id, amount:row.remaining_paise}))};
  }
  const gross = jobs.reduce((sum, job) => sum + job.gross_paise, 0);
  if (!Number.isSafeInteger(gross) || gross > 99999999999) throw new Error('Payroll total exceeds the supported payment limit.');
  let left = gross;
  const recoveries = [];
  for (const advance of advances) {
    const amount = Math.min(left, advance.remaining_paise);
    if (amount) recoveries.push({id:advance.id, amount});
    left -= amount;
  }
  const deduction = gross - left;
  return {mode:'payroll', jobs, advances, recoveries, gross, deduction, net:left,
    remaining:data.available - deduction, pieces:jobs.reduce((sum, job) => sum + job.pieces, 0)};
}

(() => {
  const source = document.getElementById('payrollClientData');
  if (!source) return;
  const data = JSON.parse(source.textContent);
  const form = document.getElementById('payrollSelectionForm');
  const review = document.getElementById('payroll-local-review');
  const status = document.getElementById('payrollCalculationStatus');
  const confirm = document.getElementById('payrollLocalConfirm');
  const oldReview = document.getElementById('payroll-preview');
  const modalStatus = document.getElementById('payrollModalStatus');
  const modalBoxes = [...review.querySelectorAll('[data-payroll-advance]')];
  const modalAll = document.getElementById('payrollModalSelectAll');
  let opener;
  const escape = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  const money = value => `₹${(value / 100).toLocaleString('en-IN', {minimumFractionDigits:2,maximumFractionDigits:2})}`;
  const selected = name => [...form.querySelectorAll(`input[name="${name}"]:checked`)].map(box => box.value);
  function updateAll(control, boxes) {
    if (!control) return;
    const count = boxes.filter(box => box.checked).length;
    control.checked = boxes.length > 0 && count === boxes.length;
    control.indeterminate = count > 0 && count < boxes.length;
  }
  function closeReview() { if (review.open) review.close(); }
  document.getElementById('payrollReviewClose').addEventListener('click', closeReview);
  document.getElementById('payrollReviewBack').addEventListener('click', closeReview);
  review.addEventListener('close', () => {
    document.body.classList.remove('payroll-review-open');
    if (opener && opener.isConnected) opener.focus();
  });
  function invalidate() {
    closeReview();
    confirm.disabled = true;
    if (oldReview) oldReview.hidden = true;
    status.textContent = 'Selection changed. Calculate again to review the updated amounts.';
  }
  form.addEventListener('change', invalidate);
  function renderReview(open = false) {
    try {
      const jobIds = selected('job_ids'), advanceIds = selected('advance_ids');
      const result = calculatePayrollLocally(data, jobIds, advanceIds);
      const receiving = result.mode === 'recovery';
      const jobs = result.jobs.map(job => `<h3>Job #${job.id} · paying ${job.pieces} pieces</h3><p class="small muted">Given ${job.given} · Returned ${job.returned} · Kept ${job.kept || 0} · Previously paid ${job.already_paid} · Awaiting return ${job.pending_return}</p><div class="table-wrap receipt-job"><table><thead><tr><th>Product</th><th>Type</th><th>Pieces</th><th>₹ / piece</th><th>Rate used</th><th>Amount</th></tr></thead><tbody>${job.lines.map(line => `<tr><td>${escape(line.product)}</td><td>${escape(line.type)}</td><td>${line.pieces}</td><td>₹${escape(line.rate)}</td><td>${escape(line.rate_source)}</td><td class="number">${money(line.amount_paise)}</td></tr>`).join('')}<tr class="total-row"><td colspan="5">Job total</td><td>${money(job.gross_paise)}</td></tr></tbody></table></div>`).join('');
      const metrics = receiving ? [['Money to receive back',result.deduction],['Amount still to recover',result.remaining]] : [['Gross payroll',result.gross],['Advance deduction',result.deduction],['Final payment',result.net],['Advance left after payment',result.remaining]];
      const recoveries = result.recoveries.length ? `<div class="advance-review"><h3>${receiving ? 'Advances being received back' : 'Advances being deducted'}</h3>${result.recoveries.map(row => `<p>Advance #${row.id}<strong>− ${money(row.amount)}</strong></p>`).join('')}</div>` : '';
      document.getElementById('payrollLocalHeading').textContent = receiving ? `Receive money back · ${result.advances.length} advances` : `Payroll calculation · ${result.jobs.length} jobs · ${result.pieces} pieces`;
      document.getElementById('payrollLocalAction').value = receiving ? 'recover_selected_advances' : 'pay';
      document.getElementById('payrollModalHelp').textContent = receiving ? 'No job is selected. Confirm only after receiving this money from the outworker. No payroll will be issued.' : 'Nothing has been saved. Check the deduction and payment below.';
      document.getElementById('payrollModalAdvancesHeading').textContent = receiving ? 'Money to receive · select advances' : 'Amount to reduce · select advances';
      document.getElementById('payrollModalAdvanceHelp').textContent = receiving ? 'Tick advances being returned by the outworker. Totals update immediately. For partial repayment, use Receive money back on the account page.' : 'Tick the advances to deduct from this payment. Totals update immediately. Unticked or unused amounts stay to recover later.';
      document.getElementById('payrollLocalMethodLabel').textContent = receiving ? 'Received by' : 'Payment method';
      document.getElementById('payrollLocalBreakdown').innerHTML = jobs + `<div class="metrics">${metrics.map(([label,value]) => `<div class="metric"><span>${label}</span><strong>${money(value)}</strong></div>`).join('')}</div>` + recoveries;
      document.getElementById('payrollLocalSelectedIds').innerHTML = jobIds.map(id => `<input type="hidden" name="job_ids" value="${escape(id)}">`).join('') + advanceIds.map(id => `<input type="hidden" name="advance_ids" value="${escape(id)}">`).join('');
      document.getElementById('payrollLocalDeduction').value = (result.deduction / 100).toFixed(2);
      confirm.textContent = receiving ? `Record money received · ${money(result.deduction)}` : `Record payment & issue payroll · ${money(result.net)}`;
      confirm.disabled = false;
      if (oldReview) oldReview.hidden = true;
      status.textContent = 'Calculated on this page. Review in the popup; nothing is saved until you confirm.';
      modalStatus.textContent = receiving ? `Receive ${money(result.deduction)} from the outworker. No payroll payment.` : `Advance deduction ${money(result.deduction)} · Final payment ${money(result.net)}.`;
      if (open) {
        const chosen = new Set(advanceIds);
        modalBoxes.forEach(box => { box.checked = chosen.has(box.value); });
        updateAll(modalAll, modalBoxes);
        opener = document.activeElement;
        if (!review.open) review.showModal();
        document.body.classList.add('payroll-review-open');
      }
    } catch (error) {
      confirm.disabled = true;
      document.getElementById('payrollLocalSelectedIds').innerHTML = '';
      document.getElementById('payrollLocalAction').value = '';
      document.getElementById('payrollLocalDeduction').value = '0.00';
      document.getElementById('payrollLocalBreakdown').innerHTML = '';
      status.textContent = error.message;
      modalStatus.textContent = error.message;
      if (!review.open) status.focus();
    }
  }
  function syncModalAdvances() {
    const chosen = new Set(modalBoxes.filter(box => box.checked).map(box => box.value));
    const mainBoxes = [...form.querySelectorAll('input[name="advance_ids"][type="checkbox"]')];
    mainBoxes.forEach(box => { box.checked = chosen.has(box.value); });
    updateAll(document.getElementById('selectAllAdvances'), mainBoxes);
    updateAll(modalAll, modalBoxes);
    renderReview();
  }
  modalBoxes.forEach(box => box.addEventListener('change', syncModalAdvances));
  if (modalAll) modalAll.addEventListener('change', () => {
    modalBoxes.forEach(box => { box.checked = modalAll.checked; });
    syncModalAdvances();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    renderReview(true);
  });
})();
