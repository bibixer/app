(() => {
  const dialog = document.getElementById('unsavedChanges');
  if (!dialog) return;
  const api = window.AppUI = window.AppUI || {};
  const keep = dialog.querySelector('[data-draft-keep]');
  const sources = [];
  const embeddedJob = document.body.classList.contains('return-embedded')
    ? new URLSearchParams(location.search).get('jobcard_id') : null;
  const handoffKey = embeddedJob ? `bh.section-drafts.return.${embeddedJob}` : 'bh.section-drafts';
  let destination, leaving = false, leaveTimer, opener;
  const dirty = () => sources.filter(source => source.dirty());
  const pageKey = url => url.pathname + url.search;

  function carryDrafts(url, savedForm) {
    const drafts = dirty().filter(source => source.form !== savedForm && source.capture)
      .map(source => [source.label, source.capture()]);
    if (drafts.length) {
      sessionStorage.setItem(handoffKey, JSON.stringify({
        page: pageKey(new URL(url, location.href)), drafts, expires: Date.now() + 60000,
      }));
    }
    allowDeparture();
  }

  function allowDeparture() {
    leaving = true;
    clearTimeout(leaveTimer);
    leaveTimer = setTimeout(() => { leaving = false; }, 1500);
  }

  function proceed() {
    const leave = destination;
    destination = null;
    dialog.close();
    allowDeparture();
    leave();
  }

  function cancel() {
    destination = null;
    dialog.close();
    opener?.focus();
  }

  api.drafts = {
    register(source) { sources.push(source); },
    carryDrafts,
    allowDeparture,
    trackForm(form, label) {
      const fields = [...form.querySelectorAll('input:not([type=hidden]), select, textarea')];
      const capture = () => fields.map(field => field.type === 'checkbox' ? field.checked : field.value);
      const baseline = JSON.stringify(capture());
      sources.push({
        form, label,
        capture() {
          if (fields.some(field => field.validity.badInput)) throw new Error(`Correct the unfinished number in ${label} first.`);
          return capture();
        },
        dirty: () => JSON.stringify(capture()) !== baseline || fields.some(field => field.validity.badInput),
        restore(values) { fields.forEach((field, i) => {
          if (values[i] === undefined) return;
          if (field.type === 'checkbox') field.checked = values[i];
          else field.value = values[i];
          field.dispatchEvent(new Event('input', {bubbles:true}));
        }); if (form.closest('details')) {
          form.closest('details').open = true;
          form.closest('#kept-pieces')?.setAttribute('open', '');
        } },
      });
    },
    guard(leave) {
      if (leaving) return false;
      if (destination) return true;
      if (savingSection || sources.some(source => source.busy?.())) {
        api.notify?.('A save is in progress. Wait for it to finish before leaving.', {type:'warning'});
        return true;
      }
      const drafts = dirty();
      if (!drafts.length) return false;
      destination = leave;
      opener = document.activeElement;
      if (opener?.matches('.return-job-frame')) opener = opener.contentDocument?.activeElement || opener;
      document.getElementById('unsavedChangesDescription').textContent =
        `You have unsaved changes in ${drafts.map(source => source.label).join(', ')}.`;
      dialog.showModal();
      keep.focus();
      return true;
    },
  };

  let savingSection = false;
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (event.defaultPrevented || !sources.some(source => source.form === form)) return;
    if (savingSection || sources.some(source => source.busy?.())) {
      event.preventDefault();
      api.notify?.('Wait for the current save to finish.', {type:'warning'});
      return;
    }
    const others = dirty().filter(source => source.form !== form);
    if (!others.length) {
      allowDeparture();
      return;
    }
    event.preventDefault();
    savingSection = true;
    let saved = false;
    const url = new URL(location.href);
    try {
      if (others.some(source => !source.capture)) throw new Error('Finish the other edited section before saving this one.');
      carryDrafts(url, form);
      leaving = false;
      const response = await fetch(form.action, {
        method:'POST', body:new FormData(form, event.submitter), headers:{Accept:'application/json'},
      });
      if (!response.headers.get('Content-Type')?.includes('application/json')) {
        throw new Error('Could not confirm the save. Your entries are still here.');
      }
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.message || 'This section could not be saved.');
      saved = true;
      carryDrafts(url, form);
      location.replace(url.href);
    } catch (error) {
      leaving = false;
      try { sessionStorage.removeItem(handoffKey); } catch (_) { /* Storage may be unavailable. */ }
      api.notify?.(saved ? `Section saved. The page stayed open to preserve your other edits. ${error.message}` : error.message,
        {type:saved ? 'warning' : 'error'});
    } finally {
      savingSection = false;
    }
  });

  keep.addEventListener('click', cancel);
  dialog.addEventListener('keydown', event => {
    if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) return;
    const actions = [...dialog.querySelectorAll('.rates-switch-actions button:not(:disabled)')];
    if (actions.length < 2) return;
    event.preventDefault();
    const current = actions.indexOf(document.activeElement);
    const direction = ['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1;
    actions[(current + direction + actions.length) % actions.length].focus();
  });
  dialog.addEventListener('cancel', event => { event.preventDefault(); cancel(); });
  dialog.querySelector('[data-draft-discard]').addEventListener('click', proceed);
  window.addEventListener('beforeunload', event => {
    if (embeddedJob) return; // The workspace prompts for all of its job cards together.
    if (leaving || (!savingSection && !dirty().length && !sources.some(source => source.busy?.()))) return;
    event.preventDefault();
    event.returnValue = '';
  });
  window.addEventListener('pageshow', () => {
    leaving = false;
    let handoff;
    try {
      handoff = JSON.parse(sessionStorage.getItem(handoffKey));
      if (!handoff) return;
      sessionStorage.removeItem(handoffKey);
    } catch (_) { return; }
    if (handoff.page !== pageKey(location) || handoff.expires < Date.now()) return;
    for (const [label, values] of handoff.drafts) {
      sources.find(source => source.label === label)?.restore?.(values);
    }
  });
})();
