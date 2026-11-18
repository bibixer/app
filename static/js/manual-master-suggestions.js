// One option per worker, with ID/name/alias search and keyboard selection.
function initManualMasterSuggestions({input, list, status, workers, mapping, onCommit, onInvalid}) {
  const editable = () => !input.matches(':disabled,[readonly],[aria-disabled="true"],[aria-readonly="true"]')
    && !input.closest('[inert],[aria-disabled="true"]');
  const normalize = value => String(value || '').trim().replace(/\s+/g, ' ').toUpperCase();
  const byId = new Map(workers.map(worker => [String(worker.id), {...worker, terms:[]} ]));
  const byValue = new Map([...byId.values()].map(worker => [worker.full, worker]));
  for (const [term, value] of Object.entries(mapping)) {
    if (byValue.has(value)) byValue.get(value).terms.push(normalize(term));
  }
  const unique = [...byId.values()];
  let matches = [], active = -1;
  const close = () => {
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  };
  const highlight = index => {
    active = index;
    [...list.querySelectorAll('[role=option]')].forEach((option, i) => {
      option.setAttribute('aria-selected', String(i === active));
      if (i === active) {
        input.setAttribute('aria-activedescendant', option.id);
        option.scrollIntoView({block:'nearest'});
      }
    });
  };
  const commit = worker => {
    if (!editable()) { close(); return; }
    input.value = worker.full;
    status.textContent = `Master #${worker.id}: ${worker.name} · ${worker.adders}`;
    close();
    onCommit();
  };
  const render = () => {
    if (!editable()) { close(); return; }
    const query = normalize(input.value);
    const exact = byValue.get(mapping[query]);
    matches = exact ? [exact] : unique.filter(worker => !query || (
      /^\d+$/.test(query) ? String(worker.id).startsWith(query) :
      normalize(`${worker.name} ${worker.adders}`).includes(query) || worker.terms.some(term => term.includes(query))));
    active = -1;
    input.removeAttribute('aria-activedescendant');
    list.replaceChildren();
    for (const worker of matches) {
      const option = document.createElement('div');
      option.id = `master-option-${worker.id}`;
      option.dataset.workerId = String(worker.id);
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      const name = document.createElement('strong');
      name.textContent = `#${worker.id} · ${worker.name}`;
      const address = document.createElement('small');
      address.textContent = worker.adders;
      option.append(name, address);
      option.addEventListener('click', () => commit(worker));
      list.append(option);
    }
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No matching outworkers. Check the ID, name or alias.';
      list.append(empty);
    }
    status.textContent = matches.length === 1 ? `Master #${matches[0].id}: ${matches[0].name}` : `${matches.length} matching outworkers · ↑↓ choose · Enter select`;
    list.hidden = false;
    // Size to five actual rows, including wrapped names/addresses.
    const visibleRows = [...list.children].slice(0, 5);
    const style = getComputedStyle(list);
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    list.style.maxHeight = `${Math.ceil(visibleRows.reduce((height, row) => height + row.getBoundingClientRect().height, 0)
      + (style.boxSizing === 'border-box' ? padding + border : 0))}px`;
    input.setAttribute('aria-expanded', 'true');
  };
  list.addEventListener('pointerdown', event => {
    if (event.target.closest('[role=option]')) event.preventDefault();
  });
  input.addEventListener('input', render);
  input.addEventListener('bh:lookup-locked',close);
  input.addEventListener('focus', render);
  input.addEventListener('blur', () => {
    const full = mapping[normalize(input.value)];
    if (editable() && full) input.value = full;
    close();
  });
  input.addEventListener('keydown', event => {
    if (!editable()) { close(); return; }
    if (event.isComposing) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); return; }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (list.hidden) render();
      if (matches.length) highlight(event.key === 'ArrowDown' ? (active + 1) % matches.length : (active <= 0 ? matches.length - 1 : active - 1));
    } else if (event.key === 'Enter') {
      event.preventDefault();
      if (list.hidden) render();
      const query = normalize(input.value);
      const exact = byValue.get(mapping[query]);
      // A partial number is only a search, never a substitute for an exact ID.
      const singleNameMatch = query && !/^\d+$/.test(query) && matches.length === 1 ? matches[0] : null;
      const worker = active >= 0 ? matches[active] : exact || singleNameMatch;
      if (worker) commit(worker);
      else onInvalid();
    }
  });
  if (document.activeElement === input) render();
}
