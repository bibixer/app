(() => {
  function setup(id, name) {
    const all = document.getElementById(id);
    if (!all) return;
    const boxes = [...all.form.querySelectorAll(`input[name="${name}"][type="checkbox"]`)].filter(box => !box.disabled);
    function update() {
      const checked = boxes.filter(box => box.checked).length;
      all.disabled = boxes.length === 0;
      all.checked = boxes.length > 0 && checked === boxes.length;
      all.indeterminate = checked > 0 && checked < boxes.length;
    }
    all.addEventListener('change', () => { boxes.forEach(box => { box.checked = all.checked; }); update(); });
    boxes.forEach(box => box.addEventListener('change', update));
    update();
  }
  setup('selectAllAdvances', 'advance_ids');
  setup('selectAllJobs', 'job_ids');
})();
