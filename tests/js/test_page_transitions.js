// Run: gjs tests/js/test_page_transitions.js
const Gio=imports.gi.Gio,ByteArray=imports.byteArray;
const source=ByteArray.toString(Gio.File.new_for_path('static/js/page-transitions.js').load_contents(null)[1]);
const assert=(ok,message)=>{if(!ok)throw new Error(message);};
function fixture(reduced=false){
  const classes=new Set(),timers=[],events={},leaves=[],storage=new Map();
  const document={body:{classList:{contains:k=>classes.has(k),add:k=>classes.add(k),remove:k=>classes.delete(k)}},
    documentElement:{dataset:{}},querySelectorAll:()=>[],querySelector:()=>null,
    addEventListener:(k,fn)=>{events[k]=fn;}};
  const window={AppUI:{motion:{handoffKey:'handoff',nextPair:options=>({id:options.confirm?2:0,close:'flow-out',direction:options.confirm?'confirm':'forward'})}},addEventListener:(k,fn)=>{events[k]=fn;}};
  const location={href:'http://test/manual_jobcard',origin:'http://test',assign:url=>leaves.push(url),replace:url=>leaves.push(url)};
  const storageApi={getItem:key=>storage.get(key)??null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  class URL {constructor(url){this.href=url.startsWith('http')?url:'http://test'+url;this.origin=this.href.startsWith('http://test/')?'http://test':'http://other';}}
  new Function('window','document','matchMedia','location','URL','setTimeout','clearTimeout','sessionStorage',source)(window,document,()=>({matches:reduced}),location,URL,
    (fn,delay)=>{timers.push({fn,delay});return timers.length;},()=>{},storageApi);
  return {window,document,events,timers,leaves,classes};
}
const reduced=fixture(true);reduced.window.AppUI.navigate('/payroll');
assert(reduced.leaves.length===1 && reduced.timers.length===0 && reduced.classes.size===0,'Reduced motion bypasses all transition delays');
const normal=fixture();normal.window.AppUI.navigate('/payroll');normal.window.AppUI.navigate('/edit');
assert(normal.timers.filter(t=>t.delay===160).length===1 && normal.classes.has('is-page-closing'),'Navigation closes once without duplicate redirects');
normal.timers.find(t=>t.delay===160).fn();assert(normal.leaves.length===1,'One timed navigation');
normal.events.pageshow({persisted:false});assert(!normal.classes.has('is-page-closing'),'Recovery clears closing state');
const native=fixture();let prevented=false;
native.events.submit({target:{method:'post',target:''},defaultPrevented:false,preventDefault(){prevented=true;}});
assert(!prevented && !native.timers.some(t=>t.delay===160) && native.document.documentElement.dataset.motionDirection==='confirm','Native save is not delayed, prevented or resubmitted');
const cancelled=fixture();cancelled.events.submit({target:{method:'post',target:''},defaultPrevented:true});
assert(!cancelled.classes.has('is-page-closing') && !cancelled.timers.some(t=>t.delay===160 || t.delay===1000),'Client validation failure does not animate a save');
normal.timers.filter(t=>t.delay===340).forEach(t=>t.fn());
assert(!normal.classes.has('is-motion-active'),'Temporary layer promotion and paused waves are released');
let duplicatePrevented=false;
native.events.submit({target:{method:'post',target:''},defaultPrevented:false,preventDefault(){duplicatePrevented=true;}});
assert(duplicatePrevented,'Repeated native submit is blocked while the first is pending');
print('PASS: reduced motion, one navigation, recovery, native POST safety and cancelled validation');
const login=fixture();
login.events.submit({target:{id:'loginForm',method:'post',target:''},defaultPrevented:false});
assert(!login.classes.has('is-page-closing'),'Unverified login POST must never start a transition');
