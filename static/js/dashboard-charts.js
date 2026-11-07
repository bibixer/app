// Each chart is rendered locally; its legend also works with keyboard focus.
(() => {
  document.querySelectorAll('[data-pie-chart]').forEach(chart => {
    const marks = [...chart.querySelectorAll('[data-slice]')];
    const readout = chart.querySelector('[data-pie-readout]');
    if (!readout) return;
    const reset = () => {
      marks.forEach(mark => mark.classList.remove('is-active', 'is-muted'));
      readout.textContent = readout.dataset.total;
    };
    const select = mark => {
      marks.forEach(other => {
        const selected = other.dataset.slice === mark.dataset.slice;
        other.classList.toggle('is-active', selected);
        other.classList.toggle('is-muted', !selected);
      });
      readout.textContent = `${mark.dataset.name} · ${Number(mark.dataset.quantity).toLocaleString()} pcs · ${mark.dataset.percent}%`;
    };
    marks.forEach(mark => {
      mark.addEventListener('mouseenter', () => select(mark));
      mark.addEventListener('focus', () => select(mark));
      mark.addEventListener('click', () => select(mark));
    });
    chart.addEventListener('mouseleave', () => {
      if (!chart.contains(document.activeElement)) reset();
    });
    chart.addEventListener('focusout', event => {
      if (!chart.contains(event.relatedTarget)) reset();
    });
    chart.addEventListener('keydown', event => { if (event.key === 'Escape') reset(); });
  });
})();
