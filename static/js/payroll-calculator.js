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
  const paymentForm = document.getElementById('payrollLocalPayment');
  const excessChoice = document.getElementById('payrollExcessAdvance');
  const carryAdvance = document.getElementById('payrollCarryAdvance');
  const collectAdvance = document.getElementById('payrollCollectAdvance');
  const repaymentField = document.getElementById('payrollLocalRepayment');
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
      const selectedBalance = result.advances.reduce((sum, advance) => sum + advance.remaining_paise, 0);
      const excess = receiving ? 0 : selectedBalance - result.deduction;
      let repayment = 0;
      if (excessChoice) {
        if (open || !excess) carryAdvance.checked = true;
        excessChoice.hidden = excess <= 0;
        excessChoice.querySelector('[data-payroll-carry-amount]').textContent = money(excess);
        excessChoice.querySelector('[data-payroll-collect-amount]').textContent = money(selectedBalance);
        repayment = excess > 0 && collectAdvance.checked ? selectedBalance : 0;
        repaymentField.disabled = !repayment;
        repaymentField.value = repayment ? (repayment / 100).toFixed(2) : '';
      }
      if (open) {
        document.getElementById('payrollLocalBreakdown').innerHTML = result.jobs.map(job => `
          <section class="payroll-bill-job">
            <h3>Job #${job.id} <span>· paying ${job.pieces} pieces</span></h3>
            <div class="table-wrap">
              <table aria-label="Charges for job ${job.id}">
                <thead><tr><th scope="col">Product</th><th scope="col">Qty</th><th scope="col">Rate / pc</th><th scope="col">Amount</th></tr></thead>
                <tbody>${job.lines.map(line => `
                  <tr>
                    <td><strong>${escape(line.product)}</strong><small class="payroll-bill-type">${escape(String(line.type).replaceAll('_', ' '))}</small></td>
                    <td>${line.pieces}</td>
                    <td>₹${escape(line.rate)}<small>${escape(line.rate_source)}</small></td>
                    <td><strong>${money(line.amount_paise)}</strong></td>
                  </tr>`).join('')}</tbody>
                <tfoot><tr><th scope="row" colspan="3">Job subtotal</th><td>${money(job.gross_paise)}</td></tr></tfoot>
              </table>
            </div>
            <details class="payroll-bill-piece-details">
              <summary>Job piece history</summary>
              <p>Given ${job.given} · Returned ${job.returned} · Kept ${job.kept || 0} · Previously paid ${job.already_paid} · Awaiting return ${job.pending_return}</p>
            </details>
          </section>`).join('');
      }
      const jobCount = result.jobs.length;
      document.getElementById('payrollLocalHeading').textContent = receiving ? 'Advance repayment'
        : `Payroll bill · ${jobCount} ${jobCount === 1 ? 'job' : 'jobs'} · ${result.pieces} pieces`;
      document.getElementById('payrollLocalAction').value = receiving ? 'recover_selected_advances' : 'pay';
      const deduction = repayment ? 0 : result.deduction;
      const net = repayment ? result.gross : result.net;
      const remaining = repayment ? data.available - repayment : result.remaining;
      document.getElementById('payrollModalHelp').textContent = repayment ? 'Confirm after collecting the advance and paying the payroll.'
        : receiving ? 'Confirm after receiving the money.' : 'Preview · unsaved';
      if (modalBoxes.length) {
        document.getElementById('payrollModalAdvancesHeading').textContent = receiving ? 'Advances being repaid' : 'Deduct advances';
        document.getElementById('payrollModalAdvanceHelp').textContent = receiving ? 'Tick the advances being repaid in full.' : 'Tick the advances to deduct from payroll.';
      }
      document.getElementById('payrollLocalMethodLabel').textContent = repayment ? 'Method for both transactions' : receiving ? 'Received by' : 'Payment method';
      const adjustments = repayment ? result.advances.map(row => ({id:row.id, amount:row.remaining_paise})) : result.recoveries;
      const advanceLines = adjustments.map(row => `
        <div class="payroll-bill-adjustment"><dt>Advance #${row.id}</dt><dd>${receiving || repayment ? '' : '−'}${money(row.amount)}</dd></div>`).join('');
      document.getElementById('payrollLocalTotals').innerHTML = `<dl class="payroll-bill-totals">
        ${receiving ? '' : `<div><dt>Gross payroll</dt><dd>${money(result.gross)}</dd></div>`}
        ${!receiving && !repayment ? `<div><dt>Advance deduction</dt><dd>${deduction ? '−' : ''}${money(deduction)}</dd></div>` : ''}
        ${repayment ? '' : advanceLines}
        <div class="payroll-bill-final"><dt>${receiving ? 'Amount to receive' : 'Final payment'}</dt><dd>${money(receiving ? deduction : net)}</dd></div>
        ${repayment ? `<div class="payroll-bill-final"><dt>Collect from outworker</dt><dd>${money(repayment)}</dd></div>` : ''}
        ${repayment ? advanceLines : ''}
        ${repayment ? `<div class="payroll-bill-final"><dt>Cash to take</dt><dd>${money(repayment - net)}</dd></div>` : ''}
        <div class="payroll-bill-balance"><dt>Advance balance carried forward</dt><dd>${money(remaining)}</dd></div>
      </dl>`;
      document.getElementById('payrollLocalSelectedIds').innerHTML = jobIds.map(id => `<input type="hidden" name="job_ids" value="${escape(id)}">`).join('') + advanceIds.map(id => `<input type="hidden" name="advance_ids" value="${escape(id)}">`).join('');
      document.getElementById('payrollLocalDeduction').value = (deduction / 100).toFixed(2);
      confirm.textContent = receiving ? `Record money received · ${money(result.deduction)}`
        : repayment ? `Save payroll & record ${money(repayment)} received`
        : `Record payment · ${money(result.net)}`;
      confirm.disabled = false;
      if (oldReview) oldReview.hidden = true;
      status.textContent = 'Calculated on this page. Review in the popup; nothing is saved until you confirm.';
      modalStatus.textContent = '';
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
      if (excessChoice) excessChoice.hidden = repaymentField.disabled = true;
      document.getElementById('payrollLocalSelectedIds').innerHTML = '';
      document.getElementById('payrollLocalAction').value = '';
      document.getElementById('payrollLocalDeduction').value = '0.00';
      document.getElementById('payrollLocalTotals').innerHTML = '';
      status.textContent = error.message;
      modalStatus.textContent = error.message;
      globalThis.AppUI?.notify(error.message, {type:'error'});
      if (!review.open) status.focus();
      return false;
    }
    return true;
  }
  function syncModalAdvances() {
    if (carryAdvance) carryAdvance.checked = true;
    const chosen = new Set(modalBoxes.filter(box => box.checked).map(box => box.value));
    const mainBoxes = [...form.querySelectorAll('input[name="advance_ids"][type="checkbox"]')];
    mainBoxes.forEach(box => { box.checked = chosen.has(box.value); });
    updateAll(document.getElementById('selectAllAdvances'), mainBoxes);
    updateAll(modalAll, modalBoxes);
    renderReview();
  }
  excessChoice?.addEventListener('change', () => renderReview());
  modalBoxes.forEach(box => box.addEventListener('change', syncModalAdvances));
  if (modalAll) modalAll.addEventListener('change', () => {
    modalBoxes.forEach(box => { box.checked = modalAll.checked; });
    syncModalAdvances();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    renderReview(true);
  });

  const drafts = globalThis.AppUI?.drafts;
  if (!drafts) return;
  const snapshot = () => JSON.stringify([
    selected('job_ids'), selected('advance_ids'),
    ...['method', 'reference', 'note'].map(name => paymentForm.elements[name].value),
  ]);
  const baseline = snapshot();
  drafts.register({
    form: paymentForm,
    label:'the payroll or advance recovery selection',
    dirty: () => snapshot() !== baseline,
    capture: () => JSON.parse(snapshot()),
    restore([jobs, advances, method, reference, note]) {
      for (const [name, ids, allId] of [
        ['job_ids', jobs, 'selectAllJobs'], ['advance_ids', advances, 'selectAllAdvances'],
      ]) {
        const boxes = [...form.querySelectorAll(`input[name="${name}"]:not(:disabled)`)];
        boxes.forEach(box => { box.checked = ids.includes(box.value); });
        updateAll(document.getElementById(allId), boxes);
      }
      paymentForm.elements.method.value = method;
      paymentForm.elements.reference.value = reference;
      paymentForm.elements.note.value = note;
    },
  });
  for (const [action, label] of [['advance', 'the advance given'], ['recover_advance', 'the money received']]) {
    const entry = document.querySelector(`form input[name=action][value="${action}"]`)?.form;
    if (entry) drafts.trackForm(entry, label);
  }
})();
