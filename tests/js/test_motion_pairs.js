// Run: gjs tests/js/test_motion_pairs.js
const Gio=imports.gi.Gio,ByteArray=imports.byteArray;
const source=ByteArray.toString(Gio.File.new_for_path('static/js/motion-pairs.js').load_contents(null)[1]);
const assert=(value,message)=>{if(!value)throw new Error(message);};
const memory=new Map();
function load(path='/manual_jobcard',blocked=false,history=false){
  const window={location:{pathname:path,href:'http://test'+path},performance:{getEntriesByType:()=>[{type:history?'back_forward':'navigate'}]}},document={documentElement:{dataset:{}}};
  const storage={getItem(key){if(blocked)throw new Error('blocked');return memory.get(key)??null;},
    setItem(key,value){if(blocked)throw new Error('blocked');memory.set(key,value);},
    removeItem(key){if(blocked)throw new Error('blocked');memory.delete(key);}};
  new Function('window','document','sessionStorage','Math','URL',source)(window,document,storage,
    {random(){throw new Error('No random transition selection');}},
    class {constructor(url){this.pathname=url.replace('http://test','').split('?')[0];}});
  return {motion:window.AppUI.motion,opening:document.documentElement.dataset.scene,direction:document.documentElement.dataset.motionDirection};
}
const first=load();
assert(first.opening==='split','Default entrance uses the first authored opening');
assert(first.motion.pairs.length===32 && new Set(first.motion.pairs.map(p=>p.close+'>'+p.open)).size===32,'32 distinct authored combinations');
const second=load('/payroll');
assert(second.motion.nextPair({destination:'/manual_jobcard?private=data'}).direction==='back','Returning to previous workspace unwinds motion');
assert(second.motion.nextPair({destination:'/edit'}).direction==='forward','New workspace moves forward');
assert(second.motion.nextPair({confirm:true}).direction==='confirm','Native save has its own restrained confirmation');
assert(second.motion.nextPair({back:true}).direction==='back','Explicit back navigation is supported');
assert(!memory.get('bh.blue-motion-trail.v1').includes('private'),'Queries and account names are never stored');
for(const pair of first.motion.pairs){
  memory.set(first.motion.handoffKey,JSON.stringify({pair:pair.id,direction:'confirm',time:Date.now()}));
  const destination=load('/edit');
  assert(destination.opening===pair.open && destination.direction==='confirm','Paired entrance and direction survive navigation');
  assert(!memory.has(first.motion.handoffKey),'Handoff consumed once');
}
for(const handoff of [{pair:99,time:Date.now()},{pair:-1,time:Date.now()},{pair:0,time:Date.now()-20000},{pair:1,time:Date.now()+20000}]){
  memory.set(first.motion.handoffKey,JSON.stringify(handoff));
  assert(load().opening==='split','Invalid/stale/future handoffs ignored');
}
assert(load('/manual_jobcard',false,true).direction==='back','History navigation has return choreography');
assert(load('/manual_jobcard',true).motion.nextPair().direction==='forward','Blocked storage cannot break navigation');
memory.set('bh.blue-motion-trail.v1','not json');assert(load().opening==='split','Malformed history is safe');
memory.set('bh.full-motion-cursor.v1','0');
const history=[];
for(let index=0;index<100;index++){
  const pair=load().motion.nextPair();
  assert(pair.id===index%32,'Ordered rotation persists across page loads and wraps at 32');
  for(const recent of history.slice(-3))assert(pair.close!==recent.close && pair.open!==recent.open,'Each phase avoids its last three styles');
  history.push(pair);
}
for(const invalid of ['null','-1','32','1.5','"3"','broken']){
  memory.set('bh.full-motion-cursor.v1',invalid);
  assert(load().motion.nextPair().id===0,'Malformed cursor safely resets');
}
print('PASS: 32 unique ordered combinations, three-style cooldown, paired handoff, directions, privacy and safe fallback');
