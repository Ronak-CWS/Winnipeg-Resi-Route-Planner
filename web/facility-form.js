'use strict';
window.FacilityForm=(()=>{
 const groups=[['depots','depot_mode','depot','yard'],['garbage_receivers','garbage_mode','receiver','garbage'],['recycling_receivers','recycling_mode','receiver','recycling']];
 const mounts=new WeakMap();
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 function defaults(config){
  if(config.facility_options)return structuredClone(config.facility_options);
  const result={};
  for(const [group,mode,,kind] of groups){result[mode]='single';result[group]=[{...structuredClone(kind==='yard'?config.yard:config[kind].receiver),id:group+'-1',selected:true}];}
  return result;
 }
 function mount(root,config){
  mounts.get(root)?.dispose();
  const draft=defaults(config);
  function input(site,key,label,type='text',wide=false){return `<label class="routing-field${wide?' wide':''}">${label}<input data-site-field="${key}" type="${type}" ${type==='number'?'step="any"':''} value="${escape(site[key])}" required></label>`;}
  function draw(group){
   const [,mode,kind]=groups.find(v=>v[0]===group),node=root.querySelector(`[data-facility-group="${group}"]`);
   const multiple=draft[mode]==='multiple';
   node.innerHTML=`<label class="facility-mode">Locations for this run<select data-facility-mode="${group}"><option value="single" ${multiple?'':'selected'}>Choose one</option><option value="multiple" ${multiple?'selected':''}>Choose multiple</option></select></label>
    <div class="facility-cards">${draft[group].map(site=>`<div class="facility-card" data-facility-id="${escape(site.id)}"><div class="facility-card-actions"><label><input data-facility-selected type="${multiple?'checkbox':'radio'}" name="facility-choice-${group}" ${site.selected?'checked':''}> Use this ${kind}</label><button type="button" class="text-button" data-facility-action="remove" data-facility-group-key="${group}" data-facility-key="${escape(site.id)}" ${draft[group].length===1?'disabled':''}>Remove</button></div><div class="routing-fields">${input(site,'name','Name','text',true)}${input(site,'address','Address','text',true)}${input(site,'lat','Latitude','number')}${input(site,'lon','Longitude','number')}${kind==='receiver'?input(site,'opens','Opens','time')+input(site,'closes','Closes','time')+input(site,'onsite_minutes','Onsite minutes','number'):''}</div></div>`).join('')}</div>
    <button type="button" class="secondary facility-add" data-facility-action="add" data-facility-group-key="${group}">+ Add another ${kind}</button>`;
  }
  function collect(group){
   const [,mode]=groups.find(v=>v[0]===group),node=root.querySelector(`[data-facility-group="${group}"]`);
   draft[mode]=node.querySelector('[data-facility-mode]').value;
   draft[group]=[...node.querySelectorAll('[data-facility-id]')].map(card=>{
    const old=draft[group].find(s=>s.id===card.dataset.facilityId),site={...old,selected:card.querySelector('[data-facility-selected]').checked};
    for(const field of card.querySelectorAll('[data-site-field]'))site[field.dataset.siteField]=field.type==='number'?(field.value===''?null:Number(field.value)):field.value;
    if(['address','lat','lon'].some(k=>site[k]!==old[k]))site.coordinate_source='User-entered facility coordinates';
    return site;
   });
  }
  function click(event){
   const button=event.target.closest('[data-facility-action]');if(!button)return;
   const group=button.dataset.facilityGroupKey;collect(group);
   const [,mode,kind]=groups.find(v=>v[0]===group);
   if(button.dataset.facilityAction==='add'){
    if(draft[group].length>=25)return;
    let number=1;while(draft[group].some(s=>s.id===group+'-'+number))number++;
    const selected=draft[mode]==='single';if(selected)draft[group].forEach(s=>s.selected=false);
    draft[group].push({id:group+'-'+number,selected,name:`New ${kind} ${number}`,address:'',lat:null,lon:null,coordinate_source:'User-entered facility coordinates',...(kind==='receiver'?{opens:'06:00',closes:'18:00',onsite_minutes:15}:{})});
   }else{
    if(draft[group].length===1)return;
    draft[group]=draft[group].filter(s=>s.id!==button.dataset.facilityKey);
    if(!draft[group].some(s=>s.selected))draft[group][0].selected=true;
   }
   draw(group);
  }
  function change(event){
   const group=event.target.dataset.facilityMode;if(!group)return;
   collect(group);const [,mode]=groups.find(v=>v[0]===group);
   if(draft[mode]==='single'){
    const chosen=draft[group].find(s=>s.selected)||draft[group][0];draft[group].forEach(s=>s.selected=s.id===chosen.id);
   }
   draw(group);
  }
  for(const [group] of groups)draw(group);
  root.addEventListener('click',click);root.addEventListener('change',change);
  const controller={read(){for(const [group] of groups)collect(group);return structuredClone(draft);},dispose(){root.removeEventListener('click',click);root.removeEventListener('change',change);}};
  mounts.set(root,controller);return controller;
 }
 return {defaults,mount};
})();
