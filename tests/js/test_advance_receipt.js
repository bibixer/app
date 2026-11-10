// Run: gjs tests/js/test_advance_receipt.js
const Gio=imports.gi.Gio, ByteArray=imports.byteArray;
const source=ByteArray.toString(Gio.File.new_for_path('static/js/advance-receipt.js').load_contents(null)[1]);
const choice={value:'1:30000',addEventListener(name,fn){this.change=fn;}}, amount={value:'100'}, hint={};
const elements={advanceReceiptChoice:choice,advanceReceiptAmount:amount,advanceReceiptHint:hint};
new Function('document',source)({getElementById:id=>elements[id]});
if(amount.max!=='300.00')throw new Error('Initial limit incorrect');
choice.value='2:1250';choice.change();
if(amount.max!=='12.50'||amount.value!=='100'||!hint.textContent.includes('12.50'))throw new Error('Selection must update limit without changing entered amount');
new Function('document',source)({getElementById:()=>null});
print('PASS: direct receipt amount limits, selected advance, preserved input and empty state');
