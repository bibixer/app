// Run: gjs tests/js/test_payroll_ledger.js
const Gio=imports.gi.Gio, ByteArray=imports.byteArray;
const source=ByteArray.toString(Gio.File.new_for_path('static/js/payroll-ledger.js').load_contents(null)[1]);
const assert=(value,message)=>{if(!value)throw new Error(message);};
const control={value:'newest',addEventListener(name,fn){this.change=fn;}}, status={};
const rows=[{dataset:{ledgerOrder:'0'},balance:100},{dataset:{ledgerOrder:'2'},balance:250},{dataset:{ledgerOrder:'1'},balance:300}];
const body={rows:[...rows],querySelectorAll(){return this.rows;},appendChild(row){this.rows=this.rows.filter(value=>value!==row);this.rows.push(row);}};
const elements={payrollLedgerOrder:control,payrollLedgerRows:body,payrollLedgerOrderStatus:status};
new Function('document',source)({getElementById:id=>elements[id]});
assert(body.rows.map(row=>row.dataset.ledgerOrder).join(',')==='2,1,0','Default newest first');
control.value='oldest';control.change();
assert(body.rows.map(row=>row.dataset.ledgerOrder).join(',')==='0,1,2','Switch to oldest first');
assert(body.rows.map(row=>row.balance).join(',')==='100,300,250','Historical balances unchanged');
control.value='newest';control.change();
assert(body.rows.map(row=>row.dataset.ledgerOrder).join(',')==='2,1,0','Switch back to newest');
body.rows=[];control.change();
assert(body.rows.length===0,'Empty ledger handled');
new Function('document',source)({getElementById:()=>null});
print('PASS: ledger newest/oldest order, preserved balances and empty state');
