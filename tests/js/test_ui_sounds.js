// Run: gjs tests/js/test_ui_sounds.js
const Gio = imports.gi.Gio;
const ByteArray = imports.byteArray;
const source = ByteArray.toString(Gio.File.new_for_path('static/js/ui-sounds.js').load_contents(null)[1]);
const assert = (value, message) => { if (!value) throw new Error(message); };
function fixture(options = {}) {
  let created = 0, notes = 0, disconnected = 0, stored = options.saved, authorized = options.authorized, clock = 1000;
  const documentEvents = {}, windowEvents = {}, voices = [], waves = [];
  const button = {attributes:{}, setAttribute(k,v){this.attributes[k]=v;},
    addEventListener(k,fn){this[k]=fn;}};
  const param = () => ({setValueAtTime(){}, exponentialRampToValueAtTime(){}, linearRampToValueAtTime(){}});
  class Audio {
    constructor(){created++; this.state=options.delayed?'suspended':'running'; this.currentTime=1; voices.push(this);}
    resume(){
      if(options.delayed)return new Promise(resolve=>{this.finishResume=()=>{this.state='running';resolve();};});
      this.state='running';return Promise.resolve();
    }
    suspend(){this.state='suspended';return Promise.resolve();}
    createOscillator(){return {frequency:param(), connect(){}, disconnect(){disconnected++;},
      start(){notes++;waves.push(this.type);}, stop(){this.onended();}};}
    createGain(){return {gain:param(),connect(){},disconnect(){disconnected++;}};}
  }
  const window = {AudioContext:options.unsupported ? undefined : Audio,
    addEventListener(k,fn){windowEvents[k]=fn;}};
  const document = {hidden:false, querySelectorAll(){return [button];},
    addEventListener(k,fn){documentEvents[k]=fn;}};
  const storage = {getItem(){if(options.blocked)throw new Error('blocked');return stored;},
    setItem(k,v){if(options.blocked)throw new Error('blocked');stored=v;}};
  const session = {getItem(){return authorized;},setItem(k,v){authorized=v;}};
  new Function('window','document','localStorage','sessionStorage','Date',source)(window,document,storage,session,{now:()=>clock});
  return {window,document,button,documentEvents,windowEvents,voices,waves,
    expire(){clock+=1000;},get authorized(){return authorized;},
    get created(){return created;},get notes(){return notes;},get disconnected(){return disconnected;},get stored(){return stored;}};
}
const f=fixture(), play=type=>f.window.AppUI.playSound(type);
play('success'); assert(f.created===0 && f.notes===0,'No autoplay or eager audio context');
f.documentEvents.pointerdown({isTrusted:false});
assert(f.created===0,'Synthetic gestures cannot unlock audio');
f.documentEvents.keydown({isTrusted:true}); play('success');
assert(f.created===1 && f.notes===3 && f.disconnected===6,'Success chime plays after real gesture and cleans nodes');
assert(f.waves.join(',')==='square,triangle,triangle','Save cue uses a sharp attack and soft synth flourish, not sine bells');
play('error'); assert(f.notes===3,'Rapid repeated cues are throttled');
f.voices[0].currentTime+=1;play('error');assert(f.notes===5,'Error has distinct two-note cue');
f.voices[0].currentTime+=1;play('transition');assert(f.notes===8,'Layered percussive navigation cue plays');
assert(f.waves.slice(-3).join(',')==='triangle,sawtooth,square','Transition combines bass punch, swipe and click');
f.button.click({isTrusted:true});
assert(f.stored==='off' && f.button.attributes['aria-pressed']==='false','Mute persists and is accessible');
f.voices[0].currentTime+=1;play('success');assert(f.notes===8,'Muted feedback stays silent');
f.button.click({isTrusted:true});f.voices[0].currentTime+=1;play('warning');
assert(f.stored==='on' && f.notes===12,'Unmute confirms with a chime, then warning plays');
f.document.hidden=true;f.voices[0].currentTime+=1;play('success');
assert(f.notes===12,'Background tab stays silent');f.document.hidden=false;
f.windowEvents.storage({key:'bh.ui-sounds.v1',newValue:'off'});play('success');
assert(f.notes===12 && f.button.attributes['aria-pressed']==='false','Other-tab mute synchronizes');
f.windowEvents.storage({key:'bh.ui-sounds.v1',newValue:'on'});
f.documentEvents.keydown({isTrusted:true});f.windowEvents.pagehide();play('success');
assert(f.notes===12,'Leaving page suspends sound');
const muted=fixture({saved:'off'});muted.documentEvents.keydown({isTrusted:true});
assert(muted.created===0,'Remembered mute never creates audio context');
const selection=fixture();
selection.documentEvents.change({isTrusted:true,target:{matches:()=>true}});
assert(selection.notes===1,'Deliberate option changes play a short menu tick');
selection.voices[0].currentTime+=1;
selection.documentEvents.change({isTrusted:false,target:{matches:()=>true}});
selection.documentEvents.change({isTrusted:true,target:{matches:()=>false}});
assert(selection.notes===1,'Synthetic changes and text typing are silent');
for(const options of [{unsupported:true},{blocked:true}]){
  const safe=fixture(options);safe.documentEvents.pointerdown({isTrusted:true});
  safe.window.AppUI.playSound('success');safe.button.click({isTrusted:true});
}
print('PASS: sound unlock, cues, cleanup, throttle, mute persistence, cross-tab mute, background and fallback safety');
let forwarded=0;
const childEvents={},child={parent:{AppUI:{unlockSound(){forwarded++;}}}};
new Function('window','document',source)(child,{
  body:{classList:{contains:()=>true}},addEventListener(name,handler){childEvents[name]=handler;},
});
childEvents.pointerdown({isTrusted:false});childEvents.keydown({isTrusted:true});
assert(forwarded===1 && !child.AppUI.playSound,'Embedded gestures unlock only parent audio without duplicate playback');
const GLib=imports.gi.GLib, loop=new GLib.MainLoop(null,false);
let failure;
(async()=>{
  const slow=fixture({delayed:true});
  slow.documentEvents.keydown({isTrusted:true});
  slow.window.AppUI.playSound('success');
  assert(slow.notes===0 && slow.authorized==='yes','Resume is pending; trusted consent is remembered');
  slow.voices[0].finishResume();await Promise.resolve();
  assert(slow.notes===3,'First cue plays after asynchronous resume');
  const next=fixture({authorized:'yes',delayed:true});
  next.window.AppUI.playSound('success');next.voices[0].finishResume();await Promise.resolve();
  assert(next.notes===3,'Fresh server flash plays after navigation restores audio');
  const stale=fixture({delayed:true});stale.documentEvents.keydown({isTrusted:true});
  stale.window.AppUI.playSound('error');stale.expire();stale.voices[0].finishResume();await Promise.resolve();
  assert(stale.notes===0,'Expired feedback cannot play on a later gesture');
  const off=fixture({authorized:'yes',saved:'off',delayed:true});
  assert(off.created===0,'Remembered mute blocks navigation restore');
  print('PASS: async browser unlock, cross-page restoration, confirmation chime and stale-cue expiry');
})().catch(error=>{failure=error;}).finally(()=>loop.quit());
loop.run();if(failure)throw failure;
