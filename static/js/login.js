/* Authenticate first; only confirmed success may trigger a page transition. */
(() => {
  const form = document.getElementById('loginForm');
  if (!form || !window.fetch || !window.FormData) return;
  form.dataset.asyncLogin = 'true';
  const button = form.querySelector('[type="submit"]');
  const password = form.querySelector('[name="password"]');
  let pending = false;
  const ready = () => {
    pending = false; form.removeAttribute('aria-busy');
    if (button) { button.disabled = false; button.classList.remove('app-saving'); }
  };
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (pending) return;
    pending = true; form.setAttribute('aria-busy', 'true');
    if (button) { button.disabled = true; button.classList.add('app-saving'); }
    let authenticated = false;
    try {
      const response = await fetch(form.action || location.href, {
        method:'POST', body:new FormData(form), credentials:'same-origin',
        headers:{Accept:'application/json'}, cache:'no-store', redirect:'error',
      });
      const data = await response.json();
      if (!response.ok || data.success !== true) {
        window.AppUI?.notify(data.message || 'Login could not be confirmed. Please try again.', {type:'error'});
        if (response.status === 401 && password) { password.value = ''; password.focus(); }
        return;
      }
      const destination = new URL(data.redirect, location.href);
      if (destination.origin !== location.origin) throw new Error('Invalid login destination');
      if (window.AppUI?.navigate) window.AppUI.navigate(destination.href, {replace:true});
      else location.replace(destination.href);
      authenticated = true;
    } catch (_) {
      window.AppUI?.notify('Could not confirm login. Check your connection and try again.', {type:'error'});
    } finally {
      if (!authenticated) ready();
    }
  });
  window.addEventListener('pageshow', event => {
    if (!event.persisted) return;
    ready(); if (password) password.value = '';
  });
})();
