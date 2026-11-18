/* One accessible notification system for full-page and asynchronous workflows. */
(() => {
  const root = document.getElementById('appNotifications');
  if (!root) return;
  const active = new Map();
  const seen = new WeakMap();
  const types = {success:['Saved successfully','✓'], error:['Please check','!'],
    warning:['Needs attention','!'], info:['Update','i']};
  const normalize = type => ({danger:'error', message:'info'}[type] || (types[type] ? type : 'info'));
  const api = window.AppUI = window.AppUI || {};

  function notify(message, options = {}) {
    const text = String(message || '').trim();
    if (!text) return;
    const type = normalize(options.type || 'info');
    // Embedded return forms send feedback to the surrounding workspace, where
    // it stays visible even when their iframe is below the viewport.
    if (document.body.classList.contains('return-embedded') && window.parent !== window) {
      try {
        if (window.parent.AppUI?.notify) return window.parent.AppUI.notify(text, {...options, type});
      } catch (_) { /* Standalone feedback is still available if embedding changes. */ }
    }
    // Place feedback inside an open modal so it is not hidden behind its backdrop
    // or made inert by the browser's modal focus management.
    const host = [...document.querySelectorAll('dialog[open]')].at(-1) || document.body;
    if (root.parentElement !== host) host.append(root);
    const key = `${type}\0${text}`;
    if (active.has(key)) {
      const item = active.get(key);
      item.restart();
      item.element.classList.remove('app-toast-repeat');
      void item.element.offsetWidth;
      item.element.classList.add('app-toast-repeat');
      return item.element;
    }
    api.playSound?.(type);
    const toast = document.createElement('section');
    toast.className = `app-toast app-toast-${type}`;
    toast.dataset.notificationType = type;
    toast.setAttribute('role', type === 'error' || type === 'warning' ? 'alert' : 'status');
    toast.setAttribute('aria-atomic', 'true');
    const icon = document.createElement('span');
    icon.className = 'app-toast-icon'; icon.textContent = types[type][1];
    icon.setAttribute('aria-hidden', 'true');
    const content = document.createElement('div'); content.className = 'app-toast-content';
    const title = document.createElement('strong'); title.textContent = options.title || types[type][0];
    const detail = document.createElement('p'); detail.textContent = text;
    content.append(title, detail);
    const close = document.createElement('button');
    close.type = 'button'; close.className = 'app-toast-close'; close.textContent = '×';
    close.setAttribute('aria-label', 'Dismiss notification');
    toast.append(icon, content, close);
    const duration = type === 'success' ? 6500 : type === 'info' ? 8000 : 0;
    const returnFocus = document.activeElement;
    let timer, removed = false;
    const pause = () => clearTimeout(timer);
    const dismiss = () => {
      if (removed) return;
      removed = true; pause(); active.delete(key);
      // Do not leave keyboard focus on a disappearing dismiss button.
      if (toast.contains(document.activeElement)) {
        const destination = returnFocus?.isConnected && !returnFocus.disabled && returnFocus.getClientRects().length
          ? returnFocus : host.matches('dialog') ? host : document.getElementById('main-content');
        destination?.focus({preventScroll:true});
      }
      toast.classList.add('app-toast-leaving');
      setTimeout(() => toast.remove(), 180);
    };
    const restart = () => {
      pause();
      if (duration && !document.hidden && !toast.matches(':hover') && !toast.contains(document.activeElement)) {
        timer = setTimeout(dismiss, duration);
      }
    };
    close.addEventListener('click', dismiss);
    toast.addEventListener('pointerenter', pause);
    toast.addEventListener('pointerleave', restart);
    toast.addEventListener('focusin', pause);
    toast.addEventListener('focusout', () => setTimeout(restart, 0));
    root.prepend(toast);
    active.set(key, {element:toast, restart, pause}); restart();
    return toast;
  }
  api.notify = notify;
  document.addEventListener('submit', event => {
    const form = event.target, button = event.submitter;
    queueMicrotask(() => {
      if (event.defaultPrevented || form.method.toLowerCase() !== 'post') return;
      form.setAttribute('aria-busy', 'true');
      button?.classList.add('app-saving');
    });
  });
  window.addEventListener('pageshow', () => {
    document.querySelectorAll('.app-saving').forEach(button => button.classList.remove('app-saving'));
    document.querySelectorAll('form[aria-busy="true"]').forEach(form => form.removeAttribute('aria-busy'));
  });
  document.addEventListener('visibilitychange', () => active.forEach(item => document.hidden ? item.pause() : item.restart()));
  // Restore the notification portal after closing a dialog. Otherwise feedback
  // created inside that dialog would disappear with it.
  document.addEventListener('close', () => {
    const host = [...document.querySelectorAll('dialog[open]')].at(-1) || document.body;
    if (root.parentElement !== host) host.append(root);
  }, true);

  const selector = '[data-app-notice], [role="alert"], .invalid-feedback, .field-error';
  function collect() {
    document.querySelectorAll(selector).forEach(node => {
      if (root.contains(node)) return;
      if (node.closest('[hidden], [aria-hidden="true"]') || !node.getClientRects().length) {
        seen.delete(node); return;
      }
      const text = node.textContent.trim();
      if (!text) { seen.delete(node); return; }
      if (seen.get(node) === text) return;
      seen.set(node, text);
      const type = node.dataset.appNotice || (node.matches('.success,.alert-success') ? 'success' :
        node.matches('.warning,.alert-warning') ? 'warning' : 'error');
      const name = node.closest('.mb-3,.field')?.querySelector('label')?.textContent.trim();
      notify(name && node.matches('.invalid-feedback') ? `${name}: ${text}` : text, {type});
      if (node.closest('[data-app-flashes]')) node.hidden = true;
    });
  }
  collect();
  let scheduled = false;
  new MutationObserver(records => {
    if (records.every(record => root.contains(record.target))) return;
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; collect(); });
  }).observe(document.getElementById('main-content'), {
    subtree:true, childList:true, characterData:true, attributes:true,
    attributeFilter:['hidden','class','aria-hidden']
  });

  // Native form validity errors get the same popup without changing validation
  // rules or submitting invalid data. Keep focus on the first invalid field.
  let invalidField;
  document.addEventListener('invalid', event => {
    event.preventDefault();
    if (invalidField) return;
    invalidField = event.target;
    queueMicrotask(() => {
      const field = invalidField; invalidField = null;
      const label = field.labels?.[0]?.textContent.trim() || field.getAttribute('aria-label') || field.name || 'This field';
      notify(`${label}: ${field.validationMessage}`, {type:'error'});
      field.focus();
    });
  }, true);
})();
