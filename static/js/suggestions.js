/* Shared lookup UI. Canonical values and existing form validation stay intact. */
(() => {
  const normalize = value => String(value ?? '').trim().replace(/\s+/g,' ').toUpperCase();
  const editable = input => !input.matches(':disabled,[readonly],[aria-disabled="true"],[aria-readonly="true"]')
    && !input.closest('[inert],[aria-disabled="true"]');
  const controllers = new WeakMap();
  let current = null, matches = [], active = -1, selecting = false;
  const list = document.createElement('div');
  list.id = 'bhSuggestionList'; list.className = 'bh-suggestions';
  list.setAttribute('role','listbox'); list.setAttribute('aria-label','Matching entries'); list.hidden = true;
  const close = () => {
    if (current) { current.input.setAttribute('aria-expanded','false'); current.input.removeAttribute('aria-activedescendant'); }
    current = null; active = -1; list.hidden = true;
  };
  const position = () => {
    if (!current || list.hidden) return;
    if (!current.input.isConnected || !editable(current.input)) { close(); return; }
    const rect = current.input.getBoundingClientRect();
    if(rect.bottom<0 || rect.top>innerHeight){close();return;}
    list.style.width = `${Math.min(Math.max(rect.width,220),innerWidth-16)}px`;
    list.style.left = `${Math.max(8,Math.min(rect.left,innerWidth-parseFloat(list.style.width)-8))}px`;
    const height = [...list.children].slice(0,5).reduce((sum,row)=>sum+row.getBoundingClientRect().height,0)+14;
    const below=innerHeight-rect.bottom-13, above=rect.top-13;
    const openAbove=below<100 && above>below;
    const visibleHeight=Math.min(height,Math.max(40,openAbove?above:below));
    list.style.maxHeight = `${visibleHeight}px`;
    list.style.top = `${openAbove?Math.max(8,rect.top-visibleHeight-5):rect.bottom+5}px`;
  };
  const commit = item => {
    const controller = current;
    if (!controller) return;
    if (!editable(controller.input)) { close(); return; }
    close(); selecting = true;
    try {
      controller.input.value = item.value;
      if (controller.dispatchEvents !== false) {
        controller.input.dispatchEvent(new Event('input',{bubbles:true}));
        controller.input.dispatchEvent(new Event('change',{bubbles:true}));
      }
      controller.onSelect?.(item.value,item);
    } finally { selecting = false; }
  };
  function render(controller) {
    if (!editable(controller.input)) { close(); return; }
    if (current !== controller) close();
    current = controller; active = -1;
    const query = normalize(controller.input.value);
    const unique = new Map();
    const source = typeof controller.items === 'function' ? controller.items() : controller.items;
    for (const raw of source) {
      const item = typeof raw === 'string' ? {value:raw,label:raw} : raw;
      if (!item || item.value == null) continue;
      const key = normalize(item.value);
      if (!unique.has(key)) unique.set(key,{...item,value:String(item.value),terms:[String(item.value),...(item.terms||[])]});
    }
    const items = [...unique.values()];
    const exact = items.filter(item=>item.terms.some(term=>normalize(term)===query));
    matches = exact.length===1 ? exact : items.filter(item=>!query || normalize(item.label).includes(query)
      || item.terms.some(term=>normalize(term).includes(query)));
    controller.input.removeAttribute('aria-activedescendant'); list.replaceChildren(); list.scrollTop=0;
    matches.forEach((item,index)=>{
      const row=document.createElement('div'); row.setAttribute('role','option');
      row.id=`bh-suggestion-${index}`; row.setAttribute('aria-selected','false');
      const label=document.createElement('strong');label.textContent=item.label||item.value;row.append(label);
      if(item.detail){const detail=document.createElement('small');detail.textContent=item.detail;row.append(detail);}
      row.addEventListener('click',()=>commit(item));list.append(row);
    });
    if(!matches.length){const empty=document.createElement('p');empty.className='bh-suggestions-empty';empty.textContent='No matching entries. Check the name, alias or ID.';list.append(empty);}
    list.hidden=false;controller.input.setAttribute('aria-expanded','true');position();
  }
  function attach(input, options) {
    if (!input) return;
    if (controllers.has(input)) {
      const controller=controllers.get(input);Object.assign(controller,options);
      if(document.activeElement===input && controller.openOnFocus!==false)render(controller);
      return controller;
    }
    const controller={input,openOnFocus:input.dataset.suggestionOpenOnFocus!=='false',...options};controllers.set(input,controller);
    input.removeAttribute('list');input.autocomplete='off';input.setAttribute('role','combobox');
    input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-haspopup','listbox');
    input.setAttribute('aria-controls',list.id);input.setAttribute('aria-expanded','false');
    input.addEventListener('focus',()=>{if(controller.openOnFocus!==false)render(controller);});
    input.addEventListener('click',()=>{if(controller.openOnFocus===false)render(controller);});
    input.addEventListener('bh:lookup-locked',close);
    input.addEventListener('input',()=>{if(!selecting)render(controller);});
    input.addEventListener('blur',()=>{
      if(current!==controller)return;
      const exact=matches.filter(item=>item.terms.some(term=>normalize(term)===normalize(input.value)));
      if(editable(input) && controller.canonicalizeOnBlur!==false && exact.length===1)input.value=exact[0].value;
      close();
    });
    input.addEventListener('keydown',event=>{
      if(!editable(input)){close();return;}
      if(event.isComposing)return;
      if(event.key==='Escape'){event.preventDefault();close();return;}
      if(event.key==='Tab'){close();return;}
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();if(current!==controller||list.hidden)render(controller);
        if(!matches.length)return;
        active=event.key==='ArrowDown'?(active+1)%matches.length:(active<=0?matches.length-1:active-1);
        [...list.children].forEach((row,index)=>{row.setAttribute('aria-selected',String(index===active));if(index===active){input.setAttribute('aria-activedescendant',row.id);row.scrollIntoView({block:'nearest'});}});
      }else if(event.key==='Enter' && current===controller && !list.hidden){
        const exact=matches.filter(item=>item.terms.some(term=>normalize(term)===normalize(input.value)));
        const item=active>=0?matches[active]:(input.value.trim()&&exact.length===1?exact[0]:null);
        if(item){
          event.preventDefault();commit(item);
          // Existing page-specific Enter handlers (for example payroll) run
          // first; otherwise continue to the next visible form field.
          if(!controller.onSelect)queueMicrotask(()=>{
            if(document.activeElement!==input || !input.form)return;
            const fields=[...input.form.elements].filter(field=>editable(field)
              && field.type!=='hidden' && field.offsetParent!==null);
            fields[fields.indexOf(input)+1]?.focus();
          });
        }
      }
    },true);
    if(document.activeElement===input && controller.openOnFocus!==false)render(controller);
    return controller;
  }
  function fromOptions(options) {
    const fullByLabel=new Map(),groups=new Map();
    for(const option of options)if(/^\d+\*\*\*/.test(option.value))fullByLabel.set(option.label,option.value);
    for(const option of options){
      if(option.value==null)continue;
      const value=String(option.canonical||fullByLabel.get(option.label)||option.value);
      if(!groups.has(value))groups.set(value,{value,label:option.label||value,terms:[],detail:''});
      groups.get(value).terms.push(String(option.value));
    }
    for(const item of groups.values()){
      const full=item.value.match(/^(\d+)\*\*\*(.*?)--(.*)\/-$/);
      if(full){item.label=`#${full[1]} · ${full[2]}`;item.detail=full[3];item.terms.push(full[1],full[2]);}
      const aliases=[...new Set(item.terms)].filter(term=>normalize(term)!==normalize(item.value)&&!/^\d+$/.test(term)&&(!full||normalize(term)!==normalize(full[2])));
      if(aliases.length)item.detail=[item.detail,`Aliases: ${aliases.join(' / ')}`].filter(Boolean).join(' · ');
    }
    return [...groups.values()];
  }
  window.BHSuggestions={attach,fromOptions,close};
  document.addEventListener('DOMContentLoaded',()=>{
    document.body.append(list);
    // Close an already-open lookup if the field or an ancestor becomes locked.
    // One observer also covers the manual job page's dedicated lookup widgets.
    new MutationObserver(()=>{
      if(current && !editable(current.input))close();
      document.querySelectorAll('[role="combobox"][aria-expanded="true"]').forEach(input=>{
        if(!editable(input))input.dispatchEvent(new Event('bh:lookup-locked'));
      });
    }).observe(document.body,{subtree:true,attributes:true,
      attributeFilter:['disabled','readonly','aria-disabled','aria-readonly','inert']});
    document.querySelectorAll('input[list]').forEach(input=>{
      const datalist=document.getElementById(input.getAttribute('list'));
      if(!datalist)return;
      const items=fromOptions([...datalist.options].map(option=>({value:option.value,label:option.getAttribute('label')||option.value,canonical:option.dataset.canonical})));
      attach(input,{items});
    });
    document.querySelectorAll('script[data-suggestion-for]').forEach(source=>{
      const values=JSON.parse(source.textContent);
      if(!Array.isArray(values))return;
      const options=values.map(value=>typeof value==='string'?{value,label:value}:{value:value.full||value.value||value.name,label:value.label||value.name||value.full});
      attach(document.getElementById(source.dataset.suggestionFor),{items:fromOptions(options)});
    });
  });
  list.addEventListener('pointerdown',event=>{if(event.target.closest('[role=option]'))event.preventDefault();});
  window.addEventListener('resize',position);
  document.addEventListener('scroll',event=>{if(!list.contains(event.target))position();},true);
})();
