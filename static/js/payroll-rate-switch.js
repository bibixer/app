(() => {
  const filter=document.getElementById('ratesProductFilter');
  if(!filter)return;
  const select=filter.querySelector('select[name=product_id]');
  const opened=filter.dataset.openedProduct;
  const fields=[...document.querySelectorAll('form.rate-row input[name=rate],form.rate-row input[name=product_value]')];
  const original=new Map(fields.map(field=>[field,field.value]));
  const dialog=document.getElementById('ratesSwitchDialog');
  const save=document.getElementById('ratesSaveAndSwitch');
  const discard=document.getElementById('ratesDiscardAndSwitch');
  const keep=document.getElementById('ratesKeepEditing');
  const error=document.getElementById('ratesSwitchError');
  const reviewAll=document.getElementById('ratesReviewAll');
  const drafts=window.AppUI?.drafts;
  let target=null,token=null,saving=false,leaving=false;
  const isEdited=field=>field.value!==original.get(field) || field.validity.badInput;
  const dirty=()=>fields.filter(isEdited);
  const label=field=>field.name==='product_value'?'Product value per piece':field.closest('form').querySelector('h3').textContent;
  const destination=id=>{const url=new URL(filter.action || location.href);url.search='';url.searchParams.set('product_id',id);return url.href;};
  const go=url=>window.AppUI?.navigate ? window.AppUI.navigate(url) : location.assign(url);
  const leave=url=>{leaving=true;drafts?.allowDeparture();go(url);};
  const cancel=()=>{if(saving)return;dialog.close();select.value=opened;target=null;select.focus();};
  function switchProduct(next){
    if(!next || next===opened)return;
    if(!dirty().length){leave(destination(next));return;}
    review(next);
  }
  function review(next){
    target=next;token=crypto.randomUUID();select.value=opened;
    const switching=next!==opened;
    discard.hidden=!switching;
    save.textContent=switching?'Save changes & switch':'Save all changes';
    document.getElementById('ratesSwitchTitle').textContent=switching?'Save before switching products?':'Review all changes';
    const name=[...select.options].find(option=>option.value===next)?.textContent || 'another product';
    document.getElementById('ratesSwitchDescription').textContent=switching
      ? `The current product has unsaved values. Save or discard them before opening ${name}.`
      : 'Confirm to save these rates and values together.';
    const list=document.getElementById('ratesChangedFields');list.replaceChildren();
    dirty().forEach(field=>{
      const row=document.createElement('li');
      const price=value=>value===''?'Unset':`₹${value}`;
      row.textContent=`${label(field)} · ${price(original.get(field))} → ${field.validity.badInput?'Invalid number':price(field.value)}`;
      list.append(row);
    });
    error.hidden=true;dialog.showModal();keep.focus();
  }
  fields.forEach((field,index)=>{
    drafts?.trackForm(field.form, label(field));
    const marker=document.createElement('small');
    marker.id=`rate-edited-${index}`;
    marker.className='rate-edited-label';
    marker.textContent='Unsaved change';
    field.after(marker);
    const description=field.getAttribute('aria-describedby');
    const update=()=>{
      const edited=isEdited(field);
      field.classList.toggle('rate-edited',edited);
      marker.hidden=!edited;
      const describedBy=[description,edited ? marker.id : null].filter(Boolean).join(' ');
      if(describedBy)field.setAttribute('aria-describedby',describedBy);
      else field.removeAttribute('aria-describedby');
      reviewAll.disabled=!dirty().length;
    };
    field.addEventListener('input',update);
    window.addEventListener('pageshow',update);
    update();
  });
  reviewAll?.addEventListener('click',()=>{if(dirty().length)review(opened);});
  select.addEventListener('change',()=>switchProduct(select.value));
  filter.addEventListener('submit',event=>{event.preventDefault();switchProduct(select.value);});
  keep.addEventListener('click',cancel);
  dialog.addEventListener('cancel',event=>{event.preventDefault();cancel();});
  discard.addEventListener('click',()=>{if(!saving && target!==opened)leave(destination(target));});
  save.addEventListener('click',async()=>{
    if(saving || !target)return;
    const changed=dirty();
    const invalid=changed.find(field=>!field.checkValidity());
    if(invalid){error.textContent=`Check ${label(invalid)}: ${invalid.validationMessage}`;error.hidden=false;return;}
    const changes=changed.map(field=>{
      const form=field.closest('form');
      return {field:field.name,value:field.value,
        bundle_type:form.querySelector('[name=bundle_type]')?.value || '',
        version:form.querySelector('[name=version],[name=expected_value]').value};
    });
    const body=new FormData();
    const csrf=document.querySelector('form.rate-row [name=csrf_token]');
    if(csrf)body.set('csrf_token',csrf.value);
    body.set('submission_token',token);body.set('action','save_and_switch');
    body.set('product_id',opened);body.set('next_product_id',target);body.set('changes',JSON.stringify(changes));
    saving=true;[save,discard,keep].forEach(button=>button.disabled=true);error.hidden=true;
    try{
      const response=await fetch(filter.action || location.href,{method:'POST',body,headers:{Accept:'application/json'}});
      const result=await response.json();
      if(!response.ok || !result.success){
        error.textContent=result.message || 'Changes could not be saved. Your edits are still here.';
        error.hidden=false;return;
      }
      leave(result.next_url);
    }catch(problem){error.textContent='Could not confirm the save. Your changes may already be saved. Retry Save changes & switch safely to confirm.';error.hidden=false;}
    finally{saving=false;[save,discard,keep].forEach(button=>button.disabled=false);}
  });
  if(!drafts) window.addEventListener('beforeunload',event=>{if(!leaving&&dirty().length){event.preventDefault();event.returnValue='';}});
})();
