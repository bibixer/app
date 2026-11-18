// Run: gjs tests/js/test_payroll_worker.js (no network/browser required).
const Gio = imports.gi.Gio;
const ByteArray = imports.byteArray;
const assert = (condition, message) => { if (!condition) throw new Error(message); };
function element() {
  return {value:'', textContent:'', listeners:{}, focused:false, validity:'',
    addEventListener(name, handler) { this.listeners[name] = handler; },
    focus() { this.focused = true; },
    setCustomValidity(value) { this.validity = value; },
    reportValidity() { this.reported = true; }};
}
const form=element(), input=element(), button=element(), status=element();
const full='1***RAM--CITY/-';
const elements={payrollWorkerForm:form,payrollWorker:input,openPayrollAccount:button,
  payrollWorkerMatch:status,payrollMasterMap:{textContent:JSON.stringify({
    '1':full,'RAM':full,'RAM CITY':full,[full]:full,
  })}};
const source=ByteArray.toString(Gio.File.new_for_path('static/js/payroll-worker.js').load_contents(null)[1]);
new Function('document',source)({getElementById:id=>elements[id]});
function event(key) { return {key,preventDefault(){this.prevented=true;}}; }
for (const value of ['1','ram',' ram   city ',full]) {
  input.value=value;
  input.listeners.input();
  assert(status.textContent.includes(full),'Exact matches show full saved name');
  const enter=event('Enter');
  input.listeners.keydown(enter);
  assert(enter.prevented && input.value===full && button.focused,'Enter resolves and moves to button');
}
input.value='unknown'; button.focused=false;
const invalid=event('Enter'); input.listeners.keydown(invalid);
assert(!button.focused && input.validity && input.reported,'Unknown values cannot continue');
const submit=event(); form.listeners.submit(submit);
assert(submit.prevented && input.focused,'Invalid submission is blocked');
input.value='1'; input.listeners.input();
assert(!input.validity,'Typing clears stale validation');
const validSubmit=event(); form.listeners.submit(validSubmit);
assert(!validSubmit.prevented && input.value===full,'Valid click submission resolves canonical name');
const back=event('Backspace'); button.listeners.keydown(back);
assert(back.prevented && input.focused,'Backspace on button returns to name input');
const normalBack=event('Backspace'); input.listeners.keydown(normalBack);
assert(!normalBack.prevented,'Backspace in text input edits normally');
for (const attribute of ['readOnly','disabled']) {
  input[attribute]=true;input.value='RAM CITY';button.focused=false;
  input.listeners.input();input.listeners.change();input.listeners.blur();
  const lockedEnter=event('Enter');input.listeners.keydown(lockedEnter);
  assert(input.value==='RAM CITY'&&!lockedEnter.prevented&&!button.focused,'Locked field must not canonicalize or intercept lookup navigation');
  input[attribute]=false;
}
print('PASS: payroll lookup normalization, alias/ID, Enter, Backspace, validation and submission');
