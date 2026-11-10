// Run from the app directory: gjs tests/js/test_return_workspace.js
// Exercises the real scripts without a browser, network, database, or printer.
const Gio = imports.gi.Gio;
const GLib = imports.gi.GLib;
const ByteArray = imports.byteArray;
const read = path => ByteArray.toString(Gio.File.new_for_path(path).load_contents(null)[1]);
const assert = (condition, message) => { if (!condition) throw new Error(message); };
const origin = 'http://app.test';

async function run() {
  let listener;
  const firstWindow = {};
  const secondWindow = {};
  const firstDraft = {value:'3',dataset:{entryMethod:'direct',remaining:'10'}};
  const secondDraft = {value:'7'};
  const badge = {textContent:''};
  const counters = {'#open-return-count':{textContent:''},'#open-return-pieces':{textContent:''}};
  const first = {dataset:{jobId:'1',remaining:'10'},querySelector:selector =>
    selector === 'iframe' ? {contentWindow:firstWindow,style:{}} : badge};
  const second = {dataset:{jobId:'2',remaining:'10'},querySelector:selector =>
    selector === 'iframe' ? {contentWindow:secondWindow,style:{}} : {textContent:''}};
  new Function('window','document','location',read('static/js/return-workspace.js'))(
    {addEventListener:(name,callback) => {listener=callback;}},
    {querySelectorAll:()=>[first,second],querySelector:selector=>counters[selector]}, {origin});
  listener({origin:'http://other.test',source:firstWindow,data:{type:'job-return-state',jobId:1,remaining:0}});
  assert(first.dataset.remaining === '10','Foreign origins must be ignored');
  listener({origin,source:secondWindow,data:{type:'job-return-state',jobId:1,remaining:0}});
  assert(first.dataset.remaining === '10','Another job iframe must not update this job');

  const redirects=[],alerts=[],messages=[];
  Object.assign(firstWindow,{RETURN_EMBEDDED:true,location:{origin,replace:value=>redirects.push(value),reload:()=>redirects.push('reload')},open:()=>null});
  firstWindow.parent={postMessage:(data,target)=>{messages.push(data);listener({origin:target,source:firstWindow,data});}};
  const source=read('static/js/retun.js');
  const prefix=source.slice(0,source.indexOf('      document.addEventListener("DOMContentLoaded"'));
  const job={name:'1***RAM--CITY/-',jobcard_id:1,items:[{item_id:1,name:'VIMAL',colour:'lump'}]};
  const response={success:true,remaining:7,jobData:{code:101,jobData:{date:'08-11-2026',jobcard_id:1,party:job.name,username:'admin',items:[{name_of_product:'VIMAL',type:'lump',returned:3,note:''}]}}};
  let failPrint=false;
  const submit=new Function('document','window','JOB_CARD','crypto','fetch','alert','console','Blob','URL',prefix+'\nreturn submitReturn;')(
    {querySelectorAll:()=>[{}],getElementById:()=>firstDraft,createElement:()=>{if(failPrint)throw new Error('printer unavailable');return {click(){}};}},
    firstWindow,job,{randomUUID:()=>String(Math.random())},async()=>({json:async()=>response}),
    message=>alerts.push(message),{log(){},error(){}},class {},{createObjectURL:()=>'blob:test'});
  await submit();
  assert(messages.length===1 && messages[0].remaining===7,'Saved returns must immediately notify their workspace');
  assert(Number(first.dataset.remaining)===7 && counters['#open-return-pieces'].textContent===17,'Parent totals must reflect the confirmed remaining quantity');
  assert(secondDraft.value==='7' && second.dataset.remaining==='10','Other jobs must retain their draft and original balance');
  assert(redirects[0]==='/job_retun?jobcard_id=1&embedded=1','Only the saved job iframe should refresh');
  assert(!alerts.length,'Successful save must not show an error');

  // A receipt failure is separate from the already committed return.
  failPrint=true;
  const printSubmit=new Function('document','window','JOB_CARD','crypto','fetch','alert','console','Blob','URL',prefix+'\nreturn submitReturn;')(
    {querySelectorAll:()=>[{}],getElementById:()=>firstDraft,createElement:()=>{throw new Error('printer unavailable');}},
    firstWindow,job,{randomUUID:()=>'key'},async()=>({json:async()=>response}),message=>alerts.push(message),
    {log(){},error(){}},class {},{createObjectURL:()=>'blob:test'});
  await printSubmit();
  assert(alerts.some(message=>message.startsWith('Return saved.')),'Receipt failure must accurately report that the return was saved');
  assert(!alerts.some(message=>message.includes('Error submitting')),'Receipt failure must not be reported as a failed save');
  assert(redirects.length===2,'A printing failure must still refresh the saved job');

  // Balance updates must not depend on a change in layout height.
  let resize;
  const events=[];
  const frame={RETURN_EMBEDDED:true,parent:{},addEventListener(){}};
  const mutableJob={jobcard_id:1,items:[{issued:10}]};
  new Function('window','document','JOB_CARD','ResizeObserver','parent','location',read('static/js/embedded-returns.js'))(
    frame,{querySelector:()=>({getBoundingClientRect:()=>({height:500})})},mutableJob,
    class {constructor(callback){resize=callback;}observe(){}}, {postMessage:data=>events.push(data)}, {origin});
  mutableJob.items[0].issued=7;
  resize();
  assert(events.length===2 && events[1].remaining===7,'A changed balance at unchanged height must be sent');
  resize();
  assert(events.length===2,'Unchanged resize notifications should not repeat');
  print('PASS: saved balances, draft isolation, origin/source validation, receipt failure, unchanged-height updates');
}
const loop=new GLib.MainLoop(null,false);
run().then(()=>loop.quit()).catch(error=>{printerr(error.stack);imports.system.exit(1);});
loop.run();
