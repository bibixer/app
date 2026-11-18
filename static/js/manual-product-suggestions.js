// Group names and aliases into one option per canonical product.
function initManualProductSuggestions({input, list, mapping, onCommit}) {
  const editable = () => !input.matches(':disabled,[readonly],[aria-disabled="true"],[aria-readonly="true"]')
    && !input.closest('[inert],[aria-disabled="true"]');
  const normalize = value => String(value || '').trim().replace(/\s+/g, ' ').toUpperCase();
  const grouped = new Map();
  for (const [term, name] of Object.entries(mapping)) {
    const key = normalize(name);
    if (!grouped.has(key)) grouped.set(key, {name, aliases: new Set()});
    if (normalize(term) !== key) grouped.get(key).aliases.add(term);
  }
  const products = [...grouped.values()];
  let matches = [], active = -1;
  const close = () => {
    list.hidden = true;
    active = -1;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
  };
  const render = () => {
    if (!editable()) { close(); return; }
    const query = normalize(input.value);
    matches = products.filter(product => !query || normalize(product.name).includes(query)
      || [...product.aliases].some(alias => normalize(alias).includes(query)));
    active = -1;
    input.removeAttribute('aria-activedescendant');
    list.replaceChildren();
    matches.forEach((product, index) => {
      const option = document.createElement('div');
      option.id = `${list.id}-option-${index}`;
      option.setAttribute('role', 'option');
      option.setAttribute('aria-selected', 'false');
      const name = document.createElement('strong');
      name.textContent = product.name;
      option.append(name);
      if (product.aliases.size) {
        const aliases = document.createElement('small');
        aliases.textContent = `Aliases: ${[...product.aliases].join(' / ')}`;
        option.append(aliases);
      }
      option.addEventListener('click', () => {
        if (!editable()) { close(); return; }
        input.value = product.name;
        close();
        onCommit();
      });
      list.append(option);
    });
    if (!matches.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No matching products. Select an existing name or alias.';
      list.append(empty);
    }
    list.hidden = false;
    // Only five rows are visible; all remaining matches stay scrollable.
    const style = getComputedStyle(list);
    const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
    const border = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
    list.style.maxHeight = `${Math.ceil([...list.children].slice(0, 5)
      .reduce((height, row) => height + row.getBoundingClientRect().height, 0)
      + (style.boxSizing === 'border-box' ? padding + border : 0))}px`;
    input.setAttribute('aria-expanded', 'true');
  };
  list.addEventListener('pointerdown', event => {
    if (event.target.closest('[role=option]')) event.preventDefault();
  });
  input.addEventListener('input', render);
  input.addEventListener('bh:lookup-locked',close);
  input.addEventListener('focus', render);
  input.addEventListener('blur', close);
  // Registered before the row navigation handler: resolve the selection here,
  // then let its Enter keyup move to pieces (including blank-row submit flow).
  input.addEventListener('keydown', event => {
    if (!editable()) { close(); return; }
    if (event.isComposing) return;
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      if (list.hidden) render();
      if (!matches.length) return;
      active = event.key === 'ArrowDown' ? (active + 1) % matches.length
        : (active <= 0 ? matches.length - 1 : active - 1);
      [...list.children].forEach((option, index) => {
        option.setAttribute('aria-selected', String(index === active));
        if (index === active) {
          input.setAttribute('aria-activedescendant', option.id);
          option.scrollIntoView({block:'nearest'});
        }
      });
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      if (!list.hidden && active >= 0) input.value = matches[active].name;
      // Exact aliases are canonicalized by the existing row validation.
      close();
    }
  });
}
