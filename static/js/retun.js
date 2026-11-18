// Store calculator data for each row
      let calculatorData = {};

      function notifyReturnWorkspace(remaining) {
        if (window.RETURN_EMBEDDED && window.parent !== window && Number.isSafeInteger(remaining)) {
          window.parent.postMessage({type:'job-return-state',jobId:JOB_CARD.jobcard_id,remaining},window.location.origin);
        }
      }

      function positiveWholeNumber(value) {
        const number = Number(value);
        return Number.isSafeInteger(number) && number > 0 ? number : 0;
      }

      function focusAtEnd(input) {
        if (!input) return;
        input.focus();
      }

      function focusCalculatorForRow(rowIndex) {
        const calculator = calculatorData[rowIndex];
        if (!calculator) return;
        let targetRow = calculator.rows.find(row => !row.piecesInput.value || !row.countInput.value);
        if (!targetRow) {
          addCalculatorRow(rowIndex);
          targetRow = calculator.rows[calculator.rows.length - 1];
        }
        highlightActiveRow(rowIndex);
        const target = targetRow.piecesInput.value ? targetRow.countInput : targetRow.piecesInput;
        target.focus();
        target.scrollIntoView({ block: "nearest" });
      }

      function fillJobInfo() {
        document.getElementById("jobName").innerText = JOB_CARD.name;
        document.getElementById("jobDate").innerText = JOB_CARD.date;
      }

      function highlightActiveRow(rowIndex) {
        document.querySelectorAll('#returnTable tbody tr').forEach(row => {
          row.classList.remove('active-row');
        });
        const activeRow = document.querySelector(`#returnTable tbody tr[data-row-index="${rowIndex}"]`);
        if (activeRow) {
          activeRow.classList.add('active-row');
        }
      }

      function updateReturnTotal(rowIndex) {
        // Calculate total from all calculator rows
        let total = 0;
        if (calculatorData[rowIndex]) {
          calculatorData[rowIndex].rows.forEach(row => {
            const pieces = positiveWholeNumber(row.piecesInput.value);
            const count = positiveWholeNumber(row.countInput.value);
            total += pieces * count;
          });
        }

        const returnInput = document.getElementById(`return-input-${rowIndex}`);
        const maxRemaining = parseInt(returnInput?.getAttribute('data-remaining') || 0);

        if (returnInput) {
          if (total <= maxRemaining) {
            if (total !== 0) {
              returnInput.value = total;
              returnInput.dataset.entryMethod = 'calculator';
              returnInput.dispatchEvent(new Event('change'));
            } else if (returnInput.dataset.entryMethod === 'calculator') {
              returnInput.value = '';
              returnInput.dataset.entryMethod = 'direct';
            }
          } else if (total > maxRemaining && total > 0) {
            window.AppUI?.notify(`Total calculated (${total}) exceeds remaining balance (${maxRemaining}) for ${returnInput.getAttribute('data-name')}`, {type:'error'});
          }
        }

        // Update summary display
        const summarySpan = document.getElementById(`calc-summary-${rowIndex}`);
        if (summarySpan) {
          summarySpan.innerText = total;
        }

        return total;
      }

      function createCalculatorRow(rowIndex, rowId, piecesValue = '', countValue = '') {
        const container = document.getElementById(`calculator-rows-${rowIndex}`);
        if (!container) return null;

        const newRow = document.createElement('div');
        newRow.className = 'calc-row';
        newRow.id = `calc-row-${rowIndex}-${rowId}`;
        newRow.innerHTML = `
          <div class="calc-input">
            <label>Pcs:</label>
            <input type="number" class="calc-pieces" data-row="${rowIndex}" data-calc-id="${rowId}"
                   min="1" step="1" value="${piecesValue}" placeholder="0" style="width: 60px;">
          </div>
          <div class="calc-input">
            <label>× Cnt:</label>
            <input type="number" class="calc-count" data-row="${rowIndex}" data-calc-id="${rowId}"
                   min="1" step="1" value="${countValue}" placeholder="0" style="width: 60px;">
          </div>
          <span>=</span>
          <span class="calc-total" id="calc-total-${rowIndex}-${rowId}">0</span>
          <button class="remove-calc-btn" onclick="removeCalculatorRow(${rowIndex}, ${rowId})">×</button>
        `;

        container.appendChild(newRow);

        const piecesInput = newRow.querySelector('.calc-pieces');
        const countInput = newRow.querySelector('.calc-count');
        const totalSpan = newRow.querySelector(`.calc-total`);

        const updateTotalAndReturn = () => {
          const pieces = positiveWholeNumber(piecesInput.value);
          const count = positiveWholeNumber(countInput.value);
          const total = pieces * count;
          totalSpan.innerText = total;
          // Update the return field with total from ALL rows
          updateReturnTotal(rowIndex);
        };

        piecesInput.addEventListener('input', updateTotalAndReturn);
        countInput.addEventListener('input', updateTotalAndReturn);

        // KEYBOARD NAVIGATION FOR CALCULATOR
        piecesInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            if (piecesInput.value && piecesInput.value !== '0') {
              countInput.focus();
            } else {
              // If pieces is empty, move to return field
              const returnInput = document.getElementById(`return-input-${rowIndex}`);
              if (returnInput) {
                returnInput.focus();
                highlightActiveRow(rowIndex);
              }
            }
          }
        });

        countInput.addEventListener("keydown", (e) => {
          if (e.key === "Enter") {
            e.preventDefault();

            const pieces = positiveWholeNumber(piecesInput.value);
            const count = positiveWholeNumber(countInput.value);

            if (pieces === 0 && count === 0) {
              // Move to return field
              const returnInput = document.getElementById(`return-input-${rowIndex}`);
              if (returnInput) {
                returnInput.focus();
                highlightActiveRow(rowIndex);
              }
              return;
            }

            // Auto-fill is already happening via input events
            // Now add a new calculator row for next entry
            addCalculatorRow(rowIndex);

            // Focus on the new row's pieces input
            setTimeout(() => {
              const newRows = calculatorData[rowIndex].rows;
              const lastRow = newRows[newRows.length - 1];
              if (lastRow && lastRow.piecesInput) {
                lastRow.piecesInput.focus();
              } else {
                // If no new row, focus return field
                const returnInput = document.getElementById(`return-input-${rowIndex}`);
                if (returnInput) {
                  returnInput.focus();
                  highlightActiveRow(rowIndex);
                }
              }
            }, 50);
          }
        });

        // Initial update
        updateTotalAndReturn();

        return { id: rowId, piecesInput, countInput, totalSpan };
      }

      function addCalculatorRow(rowIndex, piecesValue = '', countValue = '') {
        if (!calculatorData[rowIndex]) {
          calculatorData[rowIndex] = { rows: [], nextId: 0 };
        }

        const newId = calculatorData[rowIndex].nextId++;
        const newRow = createCalculatorRow(rowIndex, newId, piecesValue, countValue);

        if (newRow) {
          calculatorData[rowIndex].rows.push(newRow);
        }

        return newId;
      }

      function removeCalculatorRow(rowIndex, rowId) {
        const rowToRemove = document.getElementById(`calc-row-${rowIndex}-${rowId}`);
        if (rowToRemove) {
          rowToRemove.remove();
          calculatorData[rowIndex].rows = calculatorData[rowIndex].rows.filter(r => r.id !== rowId);
          // Update return total after removal
          updateReturnTotal(rowIndex);

          // If all rows are removed, add an empty row
          if (calculatorData[rowIndex].rows.length === 0) {
            addCalculatorRow(rowIndex);
          }
        }
      }

      function escapeHistoryText(value) {
        return String(value ?? '').replace(/[&<>"']/g, character => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
        })[character]);
      }

      function renderHistory(history, given) {
        const givenRows = Array.isArray(given?.calculation_rows) ? given.calculation_rows : [];
        const givenHtml = given ? `<article class="history-entry given-entry">
          <div class="history-entry-head"><span>Given · ${escapeHistoryText(given.date)} · ${escapeHistoryText(given.time)}</span><strong>${Number(given.total) || 0} pcs given</strong></div>
          ${givenRows.length
            ? `<div class="history-lines">${givenRows.map(row => `<div><span>${Number(row.pieces)} × ${Number(row.count)}</span><strong>${Number(row.pieces) * Number(row.count)} pcs</strong></div>`).join('')}</div>`
            : '<p class="history-method">Bundle breakdown not recorded</p>'}
          <span class="history-user">Given by ${escapeHistoryText(given.entered_by)}</span>
        </article>` : '';
        const returnsHtml = !history || history.length === 0
          ? '<p class="history-empty">No returns recorded yet</p>'
          : history.map(entry => {
          const date = escapeHistoryText(entry.date);
          const time = escapeHistoryText(entry.time);
          const user = escapeHistoryText(entry.entered_by);
          const total = Number(entry.returned) || 0;
          const rows = Array.isArray(entry.calculation_rows) ? entry.calculation_rows : [];
          const detail = entry.entry_method === 'calculator' && rows.length
            ? `<div class="history-lines">${rows.map(row => `<div><span>${Number(row.pieces)} × ${Number(row.count)}</span><strong>${Number(row.pieces) * Number(row.count)} pcs</strong></div>`).join('')}</div>`
            : `<p class="history-method">${entry.entry_method === 'direct' ? 'Direct entry' : 'Older return · calculation not recorded'}</p>`;
          return `<article class="history-entry"><div class="history-entry-head"><span>${date} · ${time}</span><strong>${total} pcs returned</strong></div>${detail}<span class="history-user">Entered by ${user}</span></article>`;
          }).join('');
        return `<div class="history-given-panel"><h3>Given on job card</h3>${givenHtml}</div><div class="history-return-panel"><h3>Return entries</h3>${returnsHtml}</div>`;
      }

      function renderCompletedHistory(items) {
        const section = document.getElementById('completedHistory');
        const list = document.getElementById('completedHistoryList');
        if (!section || !list || !items?.length) return;
        section.hidden = false;
        list.innerHTML = items.map(item => `<details class="completed-item"><summary><span>${escapeHistoryText(item.product_name || item.name.replace(/_/g, " "))} <small>${escapeHistoryText(item.colour)}</small></span><span class="completed-status">${Number(item.given?.total) || 0} pcs given · Fully returned</span></summary><div class="history-content completed-content">${renderHistory(item.history, item.given)}</div></details>`).join('');
      }

      function renderTable(items) {
        const tbody = document.querySelector("#returnTable tbody");
        if (!tbody) return;
        tbody.innerHTML = items
          .map((item, index) => {
            const remaining = item.issued;
            const historyHtml = renderHistory(item.history, item.given);

            // Initialize calculator data for this row
            calculatorData[index] = { rows: [], nextId: 0 };

            return `
              <tr data-row-index="${index}">
                <td data-label="Row"><span class="id-badge">${index + 1}</span></td>
                <td class="name-badge" data-label="Product">
                  <div style="font-weight:600">${escapeHistoryText(item.product_name || item.name.replace(/_/g, " "))}</div>
                  <button type="button" class="history-toggle" onclick="toggleHistory(${index})" aria-expanded="false" aria-controls="history-${index}">
                    <span class="chevron" id="chevron-${index}">▶</span> Given &amp; return history
                  </button>
                </td>
                <td class="item-colour" data-label="Type">${escapeHistoryText(item.colour)}</td>
                <td data-label="Given"><span class="given-badge">${Number(item.given?.total) || 0} pcs</span></td>
                <td data-label="Balance"><span class="remaining-badge ${remaining < 10 ? "low" : ""}">${remaining} pcs</span></td>
                <td data-label="Return">
                  <input type="number" class="return-input" id="return-input-${index}"
                         min="0" max="${remaining}"
                         placeholder="0"
                         data-remaining="${remaining}"
                         data-name="${escapeHistoryText(item.product_name || item.name.replace(/_/g, " "))}"
                         data-row-index="${index}"
                         >
                </td>
                <td class="calculator-cell" data-label="Quick Calc">
                  <div class="calculator" id="calculator-${index}">
                    <div class="calculator-title">
                      📊 Quick Calc (Ctrl+C to open · Esc to return)
                    </div>
                    <div class="calc-rows-container" id="calculator-rows-${index}"></div>
                    <div class="calc-summary">
                      <span>Total: <strong id="calc-summary-${index}">0</strong> pcs</span>
                      <button class="apply-calc-btn" onclick="updateReturnTotal(${index})">Apply</button>
                    </div>
                  </div>
                </td>
              </tr>
              <tr class="history-row" id="history-${index}" hidden><td class="history-row-cell" colspan="7"><div class="history-content">${historyHtml}</div></td></tr>
            `;
          })
          .join("");

        // Add initial calculator rows for each item (2 rows for faster entry)
        items.forEach((item, index) => {
          addCalculatorRow(index);
        });
      }

      function toggleHistory(index) {
        const content = document.getElementById(`history-${index}`);
        const chevron = document.getElementById(`chevron-${index}`);
        if (content && chevron) {
          const isOpening = content.hidden;
          content.hidden = !isOpening;
          chevron.classList.toggle("open", isOpening);
          chevron.closest('button').setAttribute('aria-expanded', String(isOpening));
        }
      }
  const getCalculatorEntries = (rowIndex) => {
  const rows = calculatorData[rowIndex]?.rows || [];
  return rows
    .map(row => {
      const pieces = positiveWholeNumber(row.piecesInput?.value);
      const count = positiveWholeNumber(row.countInput?.value);
      return pieces > 0 && count > 0
        ? { pieces, count } : null;
    })
    .filter(Boolean);
};

const buildPayload = () => {
  const rows = document.querySelectorAll("#returnTable tbody tr[data-row-index]");
  const items = [];

  rows.forEach((row, index) => {
    const input = document.getElementById(`return-input-${index}`);
    if (!input) return;

    const itemData = JOB_CARD.items[index];
    const returnedValue = Number(input.value) || 0;

    // Get calculator entries for this row
    const calculationRows = input.dataset.entryMethod === 'calculator' ? getCalculatorEntries(index) : [];

    items.push({
      item_id: itemData.item_id,
      returned: returnedValue,
      type_R: itemData.colour,
      remaining: Number(input.dataset.remaining),
      name: itemData.name,
      entry_method: calculationRows.length ? 'calculator' : 'direct',
      calculation_rows: calculationRows,
    });
  });

  return items;
};

      let activeReturnRequestId = crypto.randomUUID();
      let returnSubmitInFlight = false;

      async function submitReturn() {

const items = buildPayload();

        for (const [index, item] of items.entries()) {
          if (item.entry_method !== 'calculator') continue;
          const rows = calculatorData[index]?.rows || [];
          const incompleteRow = rows.find(row => {
            const pieces = row.piecesInput.value.trim();
            const count = row.countInput.value.trim();
            return (pieces || count) && (!positiveWholeNumber(pieces) || !positiveWholeNumber(count));
          });
          if (incompleteRow) {
            window.AppUI?.notify(`Item #${item.item_id}: Complete each Quick Calc line with whole numbers before saving.`, {type:'error'});
            (incompleteRow.piecesInput.value ? incompleteRow.countInput : incompleteRow.piecesInput).focus();
            return;
          }
          const sum = item.calculation_rows.reduce((total, row) => total + row.pieces * row.count, 0);
          if (sum !== item.returned) {
            window.AppUI?.notify(`Item #${item.item_id}: Quick Calc total must match the Return quantity.`, {type:'error'});
            return;
          }
        }

        for (const item of items) {
          if (item.returned < 0) {
            window.AppUI?.notify(`Item #${item.item_id}: Returned amount cannot be negative.`, {type:'error'});
            return;
          }

          if (item.returned > item.remaining) {
            window.AppUI?.notify(
              `Item #${item.item_id}: Returned pieces (${item.returned}) cannot exceed remaining pieces (${item.remaining}).`,
              {type:'error'},
            );
            return;
          }
        }

const payload = {
  name: JOB_CARD.name,
  jobcard_id: JOB_CARD.jobcard_id,
  request_id: activeReturnRequestId,
  items: items
    .filter((item) => item.returned > 0)
    .map((item) => ({
      item_id: item.item_id,
      returned: item.returned,
      name_of_product: item.name,
      entry_method: item.entry_method,
      calculation_rows: item.calculation_rows,
      type: item.type_R,
    })),
};

        if (payload.items.length === 0) {
          window.AppUI?.notify("Please enter at least one return quantity.", {type:'error'});
          return;
        }

        if (returnSubmitInFlight) return;
        returnSubmitInFlight = true;
        const submitButton = document.querySelector('.btn-submit');
        submitButton?.classList.add('app-saving');

        try {
          const response = await fetch("/summit-retune", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });

          const data_R = await response.json();
          if (data_R.duplicate && !(data_R.jobData && data_R.jobData.jobData)) {
            notifyReturnWorkspace(data_R.remaining);
            window.AppUI?.notify(data_R.message || 'This return was already saved.', {type:'info'});
            const destination = `/job_retun?jobcard_id=${encodeURIComponent(JOB_CARD.jobcard_id)}${window.RETURN_EMBEDDED ? '&embedded=1' : ''}`;
            if (window.AppUI?.navigate) window.AppUI.navigate(destination, {replace:true});
            else window.location.replace(destination);
            return;
          }
          if (data_R.success) {
            activeReturnRequestId = crypto.randomUUID();
            notifyReturnWorkspace(data_R.remaining);
            const savedPage = new URL('/job_retun', window.location.origin);
            savedPage.searchParams.set('jobcard_id', JOB_CARD.jobcard_id);
            savedPage.searchParams.set('saved_return', payload.request_id);
            if (window.RETURN_EMBEDDED) savedPage.searchParams.set('embedded', '1');
            if (data_R.jobData.print_warning) savedPage.searchParams.set('csv_warning', '1');
            if (window.AppUI?.navigate) window.AppUI.navigate(savedPage.href, {replace:true});
            else window.location.replace(savedPage.href);
          } else {
            returnSubmitInFlight = false;
            window.AppUI?.notify(data_R.message || "Return could not be saved. Refresh this job card to see its latest balance.", {type:'error'});
            // Preserve the draft and request key; a failed save must not silently
            // discard the user's quantities or automatically submit them again.
          }
        } catch (error) {
          returnSubmitInFlight = false;
          console.error("Error submitting return:", error);
          window.AppUI?.notify("Could not confirm the return save. Your entries are still here; retry with the same request key.", {type:'error'});
        } finally {
          submitButton?.classList.remove('app-saving');
        }

      }

      document.addEventListener("DOMContentLoaded", () => {
        fillJobInfo();
        renderTable(JOB_CARD.items);
        renderCompletedHistory(JOB_CARD.completed_items || []);

        document.querySelectorAll('.return-input').forEach(input => {
          input.addEventListener('input', () => { input.dataset.entryMethod = 'direct'; });
        });

        const getInputs = () => Array.from(document.querySelectorAll(".return-input"));

        // Auto-focus first input
        const first = getInputs()[0];
        const savedPreview = document.getElementById('savedReturnPreview');
        if (!window.RETURN_EMBEDDED) {
          if (savedPreview) savedPreview.focus();
          else if (first) focusAtEnd(first);
        }

        // Keyboard Navigation Logic for Return Inputs
        document.addEventListener("keydown", (e) => {
          const el = document.activeElement;
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c" && el?.classList.contains("return-input")) {
            e.preventDefault();
            focusCalculatorForRow(Number(el.dataset.rowIndex));
            return;
          }
          if (e.key === "Escape" && el?.matches(".calc-pieces, .calc-count")) {
            e.preventDefault();
            const rowIndex = Number(el.dataset.row);
            focusAtEnd(document.getElementById(`return-input-${rowIndex}`));
            highlightActiveRow(rowIndex);
            return;
          }
          if (!el || !el.classList.contains("return-input")) return;

          const inputs = getInputs();
          const index = inputs.indexOf(el);

          // ENTER: Move to next row
          if (e.key === "Enter") {
            e.preventDefault();
            if (index < inputs.length - 1) {
              focusAtEnd(inputs[index + 1]);
              const nextRowIndex = inputs[index + 1].getAttribute('data-row-index');
              highlightActiveRow(parseInt(nextRowIndex));
            } else {
              document.querySelector(".btn-submit")?.focus();
            }
          }

          // BACKSPACE: Move to previous row if current is empty
          if (e.key === "Backspace" && el.value === "") {
            if (index > 0) {
              e.preventDefault();
              focusAtEnd(inputs[index - 1]);
              const prevRowIndex = inputs[index - 1].getAttribute('data-row-index');
              highlightActiveRow(parseInt(prevRowIndex));
            }
          }
        });

        // Keyboard shortcut for submit (Ctrl+A)
        document.addEventListener("keydown", (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "m") {
            e.preventDefault();
            submitReturn();
          }
        });
      });
