// Run: gjs tests/js/test_payroll_advances.js
const Gio=imports.gi.Gio, ByteArray=imports.byteArray;
const source=ByteArray.toString(Gio.File.new_for_path('static/js/payroll-advances.js').load_contents(null)[1]);
const assert=(value,message)=>{if(!value)throw new Error(message);};
const element=()=>({checked:false,listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}});
const all=element(), a=element(), b=element();
all.form={querySelectorAll:()=>[a,b]};
new Function('document',source)({getElementById:()=>all});
assert(!all.checked&&!all.indeterminate,'None initially selected');
a.checked=true; a.listeners.change();
assert(!all.checked&&all.indeterminate,'Single selection marks select-all partial');
all.checked=true; all.listeners.change();
assert(a.checked&&b.checked&&all.checked&&!all.indeterminate,'Select all ticks every amount');
all.checked=false; all.listeners.change();
assert(!a.checked&&!b.checked&&!all.indeterminate,'Untick all clears every amount');
new Function('document',source)({getElementById:()=>null});
print('PASS: individual amount ticks, select all, clear all, partial and empty state');
