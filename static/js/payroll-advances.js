(() => {
  const all = document.getElementById('selectAllAdvances');
  if (!all) return;
  const boxes = [...all.form.querySelectorAll('input[name="advance_ids"][type="checkbox"]')];
  function update() {
    const checked = boxes.filter(box => box.checked).length;
    all.checked = boxes.length > 0 && checked === boxes.length;
    all.indeterminate = checked > 0 && checked < boxes.length;
  }
  all.addEventListener('change', () => { boxes.forEach(box => { box.checked = all.checked; }); update(); });
  boxes.forEach(box => box.addEventListener('change', update));
  update();
})();
