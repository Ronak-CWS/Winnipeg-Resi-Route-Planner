'use strict';
const $ = id => document.getElementById(id);
const fmt = n => Number(n).toLocaleString('en-CA');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let session, inputId, current, selected=null, jobActive=false, pollTimer, pointVisible=true;
let inputDay=null, inputLoading=false, lastUploadFile=null;
let areaLayer, pointLayer, contextLayer, municipalLayer, glBase, basemapPolicy, highlight;
let expandedMap=false;
const areaPaths=new Map(), groups=new Map();
const map=L.map('map',{preferCanvas:true,zoomAnimation:false,fadeAnimation:false,zoomSnap:.25,maxZoom:19,maxBoundsViscosity:1});
const cityBounds=L.latLngBounds([49.68,-97.55],[50.08,-96.9]);
const allowedBounds=L.latLngBounds([49.23,-98.25],[50.53,-96.20]);
map.setMaxBounds(allowedBounds);map.setMinZoom(map.getBoundsZoom(allowedBounds));map.fitBounds(cityBounds,{animate:false,padding:[25,25]});
map.createPane('context');map.getPane('context').style.zIndex=210;
map.createPane('areas');map.getPane('areas').style.zIndex=390;
map.createPane('points');map.getPane('points').style.zIndex=410;
map.createPane('municipal');map.getPane('municipal').style.zIndex=420;
map.getPane('municipal').style.pointerEvents='none';
// Separate renderers preserve pane order and hit testing. A context canvas
// must never capture address clicks or cover polygon click targets.
const renderer=L.canvas({padding:.25,pane:'context'});
const pointRenderer=L.canvas({padding:.25,pane:'points'});
const areaRenderer=L.svg({pane:'areas'});
map.attributionControl.setPrefix('');
map.attributionControl.addAttribution('Local reference: <a href="https://data.winnipeg.ca/" target="_blank" rel="noopener">City of Winnipeg</a> · OGL Winnipeg');
let mapSize='';
new ResizeObserver(entries=>{const rect=entries[0].contentRect,key=`${Math.round(rect.width)},${Math.round(rect.height)}`;if(key!==mapSize){mapSize=key;map.invalidateSize({pan:false,debounceMoveend:true});}}).observe($('map'));
window.partitionMap=map;
window.partitionApp={mapInstances:1,basemapInstances:0,activeJob:false,ready:false,mode:'target',result:null};

function dayName(day=current?.day||inputDay){return day?day.charAt(0).toUpperCase()+day.slice(1).toLowerCase():'';}
function setDayLabels(){
  const name=dayName(),scope=name?name+' ':'',upper=(current?.day||inputDay||'').toUpperCase();
  document.title=name?`${name} · Service Area Studio`:'Service Area Studio';
  $('workspace-day').textContent=name||'Day from your file';
  $('workspace-eyebrow').textContent=(upper?upper+' / ':'')+'SERVICE AREA PLANNING';
  $('stat-addresses-label').textContent=(upper||'SERVICE')+' ADDRESSES';
  $('map').setAttribute('aria-label',scope+'service area map');
  $('fit-button').title=`Fit ${name||'service'} addresses`;
  $('fit-button').setAttribute('aria-label',$('fit-button').title);
  if(session?.demo_days?.includes(upper)){$('example-day').value=upper;exampleChanged();}
}
function exampleChanged(){
  const day=$('example-day').value,name=dayName(day);
  $('demo-button').textContent=`Load ${name} addresses ↗`;
  $('empty-demo').textContent=`Load ${name} addresses →`;
  $('download-input').textContent=`Download ${name} Excel upload ↓`;
  $('download-input').href='/api/workbook?day='+encodeURIComponent(day);
}
function resetForUpload(){
  inputId=null;inputDay=null;current=null;selected=null;
  window.partitionApp.result=null;window.partitionApp.input=null;window.partitionApp.ready=false;
  map.closePopup();for(const layer of [areaLayer,pointLayer,highlight])if(layer)map.removeLayer(layer);
  areaLayer=pointLayer=highlight=null;areaPaths.clear();groups.clear();
  $('input-receipt').hidden=true;$('selected-detail').hidden=true;$('area-search').value='';
  for(const id of ['areas-list','checks-list','sources-list'])$(id).replaceChildren();
  for(const id of ['stat-addresses','stat-areas','stat-coverage'])$(id).textContent='—';
  $('stat-assigned').textContent='Loading addresses';$('stat-range').textContent='Natural geography first';
  $('stat-check').textContent='Every AddressId, once';$('status-pill').textContent='Waiting for input';$('status-pill').className='pill neutral';
  $('areas-badge').textContent='0';$('checks-badge').textContent='0';
  $('export-button').disabled=true;$('export-menu').hidden=true;
  for(const link of document.querySelectorAll('[data-kind]'))link.removeAttribute('href');
  $('map-empty').hidden=false;$('empty-demo').hidden=true;
  $('map-empty-title').textContent='Loading your address list.';$('map-empty-copy').textContent='The collection day will appear here.';
  $('workspace-title').textContent='Service areas.';$('workspace-subtitle').textContent='Loading your address list.';
  $('footer-meta').textContent='Day from your file · Address IDs preserved';
  setDayLabels();window.routingUI?.inputChanged();setSetupVisible(true);
}

function notice(message, error=false, details=[]){
  const box=$('notice');box.hidden=!message;box.className='notice'+(error?' error':'');
  box.innerHTML=message?`<button aria-label="Dismiss notice">×</button>${esc(message)}${details.length?`<ul>${details.slice(0,8).map(e=>`<li>Row ${esc(e.row)}${e.id?` · ID ${esc(e.id)}`:''}: ${esc(e.message)}</li>`).join('')}</ul>`:''}`:'';
  if(message)box.querySelector('button').onclick=()=>{box.hidden=true;};
}
async function api(path,options={}){
  const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),45000);
  try{
    const response=await fetch(path,{...options,signal:controller.signal,headers:{...(options.method?{'X-CWS-Local':session.csrf}:{}),...options.headers}});
    const payload=await response.json();
    if(!response.ok){const error=new Error(payload.error||'Local request failed.');error.details=payload.errors||[];error.availableDays=payload.available_days||{};error.availableSheets=payload.available_sheets||[];throw error;}
    return payload;
  }finally{clearTimeout(timer);}
}
function busyInput(busy){inputLoading=busy;const locked=busy||jobActive||!!window.routingUI?.jobActive();for(const id of ['demo-button','empty-demo','file-input','example-day','collection-day','sheet-input'])$(id).disabled=locked;$('run-button').disabled=locked||!inputId;}
async function loadInput(file){
  lastUploadFile=file||null;busyInput(true);notice('');resetForUpload();
  try{
    const path=file?`/api/upload?day=${encodeURIComponent($('collection-day').value)}&sheet=${encodeURIComponent($('sheet-input').value.trim())}`:'/api/demo?day='+encodeURIComponent($('example-day').value);
    const data=await api(path,{method:'POST',headers:file?{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(file.name)}:{},body:file?await file.arrayBuffer():undefined});
    inputId=data.input_id;inputDay=data.day;window.partitionApp.input=data;setDayLabels();
    $('input-receipt').hidden=false;
    $('input-receipt').innerHTML=`<strong>✓ ${fmt(data.count)} ${esc(dayName())} addresses</strong><span>${fmt(data.distinct_coordinates)} locations · ${data.excluded?fmt(data.excluded)+' other-day rows excluded':'Every source ID retained'}</span><span class="filename">${esc(data.source)}${data.sheet?' / '+esc(data.sheet):''}</span>`;
    $('stat-addresses').textContent=fmt(data.count);$('stat-assigned').textContent='Validated input · ready to partition';
    $('workspace-title').textContent=`${dayName()} service areas.`;$('workspace-subtitle').textContent=`${fmt(data.count)} addresses loaded. Create service areas to see the partition.`;
    $('map-empty-title').textContent=`${dayName()} addresses are loaded.`;$('map-empty-copy').textContent='Choose your preferred range, then create service areas.';
    $('status-pill').textContent='Ready to partition';$('footer-meta').textContent=`${dayName()} · Address IDs preserved`;
    if(data.warnings.length)notice(data.warnings.join(' '));
  }catch(error){
    const choices=Object.entries(error.availableDays||{}).map(([day,count])=>`${dayName(day)} (${fmt(count)})`);
    const sheets=error.availableSheets||[];
    notice(error.message+(choices.length?' Available: '+choices.join(', ')+'.':'')+(sheets.length?' Sheets: '+sheets.join(', ')+'.':''),true,error.details);
    $('upload-options').open=true;$('map-empty-title').textContent='Choose your address input.';
    $('map-empty-copy').textContent='Update the upload options or choose another file.';$('stat-assigned').textContent='No input accepted';
    $('workspace-subtitle').textContent='No input accepted. Check the upload message.';
  }
  finally{busyInput(false);$('file-input').value='';}
}
function preferencePayload(){
  const minimum=Number($('minimum-input').value), maximum=Number($('maximum-input').value);
  if(!Number.isInteger(minimum)||!Number.isInteger(maximum)||minimum<1||maximum>10000||minimum>=maximum||Math.round((minimum+maximum)/2)<50)throw new Error('Enter a range from 1 to 10,000 with minimum below maximum and midpoint at least 50.');
  return {minimum,maximum,use_mapped_alleys:false};
}
function previewPreference(){
  try{const p=preferencePayload(),target=Math.round((p.minimum+p.maximum)/2);
    const supplied=(p.maximum-p.minimum)*50/target,tolerance=Math.max(10,supplied);
    const lo=supplied>=10?p.minimum:Math.ceil(target*(1-tolerance/100)), hi=supplied>=10?p.maximum:Math.floor(target*(1+tolerance/100));
    $('range-preview').textContent=`Aim for ${fmt(lo)}–${fmt(hi)}. Preserve useful natural areas; avoid tiny fragments.${supplied<10?' Minimum ±10% applied.':''}`;
  }catch(error){$('range-preview').textContent=error.message;}
}
async function startJob(){
  if(!inputId||jobActive)return;
  let preference;try{preference=preferencePayload();}catch(error){notice(error.message,true);return;}
  jobActive=true;window.partitionApp.activeJob=true;busyInput(true);$('progress-box').hidden=false;$('job-progress').value=0;$('progress-message').textContent='Starting local worker…';notice('');
  try{const job=await api('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({input_id:inputId,...preference})});await pollJob(job.job_id);}
  catch(error){endJob();notice(error.message,true,error.details);}
}
function endJob(){jobActive=false;window.partitionApp.activeJob=false;clearTimeout(pollTimer);$('progress-box').hidden=true;busyInput(false);}
async function pollJob(id){
  try{
    const job=await api('/api/job?id='+encodeURIComponent(id));
    $('job-progress').value=job.progress;$('progress-message').textContent=job.message;
    if(job.state==='done'){
      const result=await api('/api/result?key='+job.result);endJob();showResult(result,true);
      const unmet=result.summary.areas_above_limit||0;
      const below=result.summary.areas_below_range||0;
      notice(result.status==='FAILED'?'Final geometry checks failed. Review Checks before using this partition.':unmet||below?`${unmet} above range and ${below} below. Review the natural-boundary and neighbour reasons; these exceptions are not counted as meeting your range.`:`${dayName()} areas are ready for review. Address ownership is checked; road access and operational routing remain unverified.`,result.status==='FAILED'||unmet>0);
    }else if(['error','cancelled'].includes(job.state)){endJob();notice(job.message,job.state==='error');}
    else{pollTimer=setTimeout(()=>pollJob(id),1100);}
  }catch(error){endJob();notice('Progress connection stopped. The local worker may still be running; reload to reconnect. '+error.message,true);}
}
function areaStyle(feature){const active=selected===feature.id;return{pane:'areas',color:active?'#123f36':feature.properties.colour,fillColor:feature.properties.colour,weight:active?3:1.6,opacity:active?1:.8,fillOpacity:selected?(active?.23:.07):.13,interactive:true};}
function setSetupVisible(visible){
  if(visible&&expandedMap)setExpandedMap(false);
  $('setup-panel').hidden=!visible;$('workspace').classList.toggle('setup-hidden',!visible);
  $('settings-button').setAttribute('aria-expanded',String(visible));
  $('settings-button').textContent=visible?'Hide settings':'Addresses & settings';
  map.invalidateSize({pan:false});
}
function setExpandedMap(value){
  expandedMap=value;$('workspace').classList.toggle('expanded-map',value);
  $('area-explorer').hidden=value;$('summary-stats').hidden=value;
  $('expand-map-button').setAttribute('aria-pressed',String(value));
  $('expand-map-button').textContent=value?'Show panels':'Expand map';
  if(value)setSetupVisible(false);else map.invalidateSize({pan:false});
  window.routingUI?.resized();
}
function showResult(result,fit){
  const firstResult=!current;
  current=result;inputDay=result.day;selected=null;window.partitionApp.result=result;window.partitionApp.ready=true;setDayLabels();
  map.closePopup();
  if(highlight){map.removeLayer(highlight);highlight=null;}
  if(result.settings.preferred_minimum){$('minimum-input').value=result.settings.preferred_minimum;$('maximum-input').value=result.settings.maximum_addresses;}previewPreference();
  const extent=L.latLngBounds(result.points.map(p=>[p.lat,p.lon])),latPad=50/111.32,lonPad=50/(111.32*Math.cos(extent.getCenter().lat*Math.PI/180));
  const allowed=L.latLngBounds([extent.getSouth()-latPad,extent.getWest()-lonPad],[extent.getNorth()+latPad,extent.getEast()+lonPad]);
  map.setMaxBounds(allowed);map.setMinZoom(map.getBoundsZoom(allowed));window.partitionApp.allowedBounds=allowed.toBBoxString();
  $('map-empty').hidden=true;$('workspace-title').textContent=`${dayName()} service areas.`;
  $('workspace-subtitle').textContent=`${result.settings.mode==='natural'?'Natural sections':fmt(result.settings.preferred_minimum)+'–'+fmt(result.settings.maximum_addresses)+' preferred · from '+fmt(result.summary.natural_areas??result.summary.areas)+' natural areas'} · Click an area to inspect it.`;
  $('stat-addresses').textContent=fmt(result.summary.addresses);$('stat-assigned').textContent=`${fmt(result.summary.assigned)} assigned · ${result.summary.estimated} estimated points`;
  $('stat-areas').textContent=fmt(result.summary.areas);$('stat-range').textContent=`${result.settings.mode==='target'?fmt(result.summary.within_preferred_range||0)+' within range · ':''}${fmt(result.summary.smallest)}–${fmt(result.summary.largest)} addresses`;
  $('stat-coverage').textContent=result.validation.exactly_once?'100%':'Review';$('stat-check').textContent=result.validation.exactly_once?'All source IDs assigned once':'Coverage check failed';
  const targetUnmet=(result.summary.areas_above_limit||0)>0;
  const belowRange=(result.summary.areas_below_range||0)>0;
  $('status-pill').textContent=result.status==='FAILED'?'Needs correction':targetUnmet?'Target unresolved':belowRange?'Range review':'Provisional';$('status-pill').className='pill'+(result.status==='FAILED'||targetUnmet?' failed':'');
  if(result.status==='FAILED')notice((result.findings||[]).filter(f=>f.severity==='error').map(f=>f.message).join('; ')||'Service areas failed validation. Open Checks for the cause.',true);
  else if(targetUnmet)notice(`${result.summary.areas_above_limit} areas exceed the ${fmt(result.settings.maximum_addresses)} upper bound. The target is unresolved; inspect the reasons in Areas or Checks.`,true);
  else if(result.settings.use_mapped_alley_evidence)notice('Provisional boundaries use mapped rear-alley evidence. Actual pickup access remains unknown and needs confirmation.');
  $('areas-badge').textContent=result.summary.areas;$('checks-badge').textContent=result.summary.errors+result.summary.warnings;
  $('footer-meta').textContent=`${result.partition_hash.slice(0,10)} · ${result.settings.mode==='natural'?'Natural baseline':'Range '+fmt(result.settings.preferred_minimum)+'–'+fmt(result.settings.maximum_addresses)} · ${dayName()}${result.requires_recalculation?' · Saved with '+result.engine+'; recreate service areas to apply updated rules':''}`;
  $('export-button').disabled=false;
  for(const link of document.querySelectorAll('[data-kind]'))link.href=`/api/download?key=${result.key}&kind=${link.dataset.kind}`;
  if(areaLayer)map.removeLayer(areaLayer);
  areaPaths.clear();
  areaLayer=L.geoJSON(result.areas,{pane:'areas',renderer:areaRenderer,bubblingMouseEvents:false,style:areaStyle,onEachFeature:(feature,layer)=>{areaPaths.set(feature.id,layer);layer.on('click',event=>{L.DomEvent.stopPropagation(event);openArea(feature,event.latlng);});}}).addTo(map);
  groups.clear();for(const point of result.points){const key=`${point.lat},${point.lon}`;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(point);}
  $('area-search').value='';drawPoints();renderAreas();renderChecks();renderSources();
  $('selected-detail').hidden=true;$('area-search').value='';
  if(firstResult)setSetupVisible(false);
  if(fit)fitAddresses();
  document.dispatchEvent(new Event('partition-ready'));
}
function drawPoints(){
  if(pointLayer)map.removeLayer(pointLayer);pointLayer=L.layerGroup();if(!current)return;
  const colours=new Map(current.areas.features.map(f=>[f.id,f.properties.colour]));
  for(const records of groups.values()){
    const p=records[0];if(selected&&p.section!==selected)continue;
    if(window.routingUI&&!window.routingUI.pointVisible(p))continue;
    const marker=L.circleMarker([p.lat,p.lon],{pane:'points',renderer:pointRenderer,bubblingMouseEvents:false,radius:selected?3:2.2,stroke:!p.trusted,color:'#ac6a2c',weight:1,fillColor:colours.get(p.section),fillOpacity:selected?.85:.65});
    marker.on('click',event=>{L.DomEvent.stopPropagation(event);marker.bindPopup(popup(records),{maxWidth:310}).openPopup();});pointLayer.addLayer(marker);
  }
  if(pointVisible)pointLayer.addTo(map);
}
function popup(records){return `<div class="popup-title">${records.length===1?esc(dayName()||'Selected day')+' service address':fmt(records.length)+' service records at this point'}</div>`+records.map(p=>`<div class="popup-record"><b>${esc(p.address)}</b><small>AddressId ${esc(p.id)} · ${esc(p.section)}</small><small>${esc(p.quality)} · ${p.lat.toFixed(6)}, ${p.lon.toFixed(6)}</small></div>`).join('')+(window.routingUI?.pointDetails(records)||'');}
function fitAddresses(){if(current?.points.length)map.fitBounds(L.latLngBounds(current.points.map(p=>[p.lat,p.lon])),{animate:false,padding:[35,35],maxZoom:17});}
function boundaryNotice(properties){
  const quality=properties.boundary_quality;
  const streets=quality?.street_breaks?.length||0,alleys=quality?.alley_side_splits?.length||0;
  return streets+alleys?`<small class="over-limit">Boundary issue: ${fmt(streets)} street cut${streets===1?'':'s'} and ${fmt(alleys)} opposing alley split${alleys===1?'':'s'} remain.</small>`:'';
}
function areaPopup(feature){const p=feature.properties;return `<div class="popup-title">${esc(feature.id)} · Planning area</div><div class="popup-record"><b>${esc(p.name)}</b><div class="popup-count">${fmt(p.addresses)} ${p.addresses===1?'address':'addresses'}</div><small>${p.area_km2.toFixed(2)} km² · ${p.estimated} estimated locations</small>${boundaryNotice(p)}${p.small_area_reason?`<small>Below 100: ${esc(p.small_area_reason)}</small>`:''}${p.planning_reason?`<small>${esc(p.planning_reason)}</small>`:p.size_status==='SMALL_NATURAL_AREA'?'<small>Below preferred range; review the boundary</small>':''}${p.nearby_small_area_group?'<small>Nearby pieces share this address list. Road access needs review.</small>':''}${p.oversize_reason?`<small class="over-limit">Target unresolved: ${esc(p.oversize_reason)}</small>`:''}</div>`;}
function insideRing(lon,lat,ring){let inside=false;for(let i=0,j=ring.length-1;i<ring.length;j=i++){const [xi,yi]=ring[i],[xj,yj]=ring[j];if((yi>lat)!==(yj>lat)&&lon<(xj-xi)*(lat-yi)/(yj-yi)+xi)inside=!inside;}return inside;}
function areaAt(latlng){
  if(!current)return null;
  return current.areas.features.find(f=>{if(!areaPaths.get(f.id).getBounds().contains(latlng))return false;const polygons=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;return polygons.some(rings=>insideRing(latlng.lng,latlng.lat,rings[0])&&!rings.slice(1).some(r=>insideRing(latlng.lng,latlng.lat,r)));})||null;
}
function openArea(feature,latlng){selectArea(feature.id,false,false);L.popup({maxWidth:310}).setLatLng(latlng).setContent(areaPopup(feature)).openOn(map);}
// Canvas address layers capture their transparent background too. Explicit
// geometry hit testing keeps empty-space area clicks available.
map.on('click',event=>{if(window.routingUI?.isActive()){window.routingUI.openAt(event.latlng);return;}const f=areaAt(event.latlng);if(f)openArea(f,event.latlng);});
function selectArea(id,fit=true,toggle=true){
  if(window.routingUI?.isActive()){window.routingUI.selectSection(id);return;}
  selected=toggle&&selected===id?null:id;
  for(const [sid,layer] of areaPaths)layer.setStyle(areaStyle(current.areas.features.find(f=>f.id===sid)));
  drawPoints();renderAreas();
  const detail=$('selected-detail');detail.hidden=!selected;
  if(selected){const f=current.areas.features.find(f=>f.id===selected);detail.innerHTML=`<div class="selected-summary">${areaPopup(f)}<button id="clear-selection">Show all ${esc(dayName())} areas ×</button></div>`;$('clear-selection').onclick=()=>selectArea(selected,false);if(fit)map.fitBounds(areaPaths.get(selected).getBounds(),{animate:false,padding:[35,35],maxZoom:17});}
}
function renderAreas(){
  const container=$('areas-list');if(!current)return;
  const q=$('area-search').value.trim().toUpperCase();container.replaceChildren();
  const areaMatches=current.areas.features.filter(f=>(f.id+' '+f.properties.name).toUpperCase().includes(q));
  if(q){const points=current.points.filter(p=>(p.id+' '+p.address).toUpperCase().includes(q)).slice(0,30);for(const point of points){const row=document.createElement('button');row.className='record-match';row.innerHTML=`${esc(point.address)}<small>ID ${esc(point.id)} · ${esc(point.section)}</small>`;row.onclick=()=>{map.setView([point.lat,point.lon],17,{animate:false});if(highlight)map.removeLayer(highlight);highlight=L.circleMarker([point.lat,point.lon],{radius:7,color:'#173c32',weight:2,fillColor:'#fff',fillOpacity:.6}).addTo(map).bindPopup(popup(groups.get(`${point.lat},${point.lon}`))).openPopup();};container.appendChild(row);}if(points.length===30){const note=document.createElement('div');note.className='check-card';note.textContent='First 30 matching addresses. Refine the search for more.';container.appendChild(note);}}
  for(const feature of areaMatches){const p=feature.properties,button=document.createElement('button');button.className='area-row'+(selected===feature.id?' selected':'')+(p.size_status==='ABOVE_LIMIT'?' over-limit':'');button.dataset.area=feature.id;button.innerHTML=`<span class="area-swatch" style="background:${p.colour}"></span><span class="area-copy"><span class="area-id">${esc(feature.id)}</span><span class="area-name">${esc(p.name)}</span><span class="area-meta">${p.area_km2.toFixed(2)} km²${p.size_status==='ABOVE_LIMIT'?' · TARGET UNRESOLVED':p.size_status==='SMALL_NATURAL_AREA'?' · below range':''}${p.review_count?' · '+p.review_count+' review '+(p.review_count===1?'item':'items'):''}</span></span><span class="area-count">${fmt(p.addresses)}<small>addresses</small></span>`;button.onclick=()=>selectArea(feature.id);container.appendChild(button);}
  if(!container.children.length)container.innerHTML='<div class="explorer-empty"><p>No matching addresses or areas.</p></div>';
}
function renderChecks(){
  const v=current.validation;
  const gates=[['Source coverage',v.exactly_once,`${fmt(v.source_ids)} source IDs, assigned exactly once.`],['Reliable point containment',v.reliable_points_outside===0,`${v.reliable_points_outside} reliable points outside their assigned polygon.`],['Protected groups',v.split_protected_groups===0,`${v.split_protected_groups} split coordinate / site / ordinary-segment groups.`],['Serviced parcel checks',v.material_parcel_cuts===0,`${fmt(v.serviced_parcels_checked)} parcels checked; ${v.material_parcel_cuts} material cuts. ${fmt(v.reliable_points_without_parcel||0)} reliable records need parcel-reference review.`],['Area overlap',v.overlap_m2<=1,`${v.overlap_m2.toFixed(3)} m² of numeric overlap.`]];
  gates.push(['Area boundaries',v.published_geometries_valid===true,`${(v.nearby_small_area_groups||[]).length} nearby address lists retain separate geographic pieces under the 500 m rule. Road access still needs review.`]);
  if(current.settings.mode==='target')gates.unshift(['Preferred address range',v.preferred_range_met===true,`${fmt(current.summary.within_preferred_range||0)} areas within ${fmt(current.settings.preferred_minimum)}–${fmt(current.settings.maximum_addresses)}; ${(v.areas_above_limit||[]).length} above and ${(v.below_preferred_range||[]).length} below. Review the boundary and neighbour reasons for each exception.`]);
  if((v.last_resort_boundary_review||[]).length)gates.push(['Boundary access review',false,`${v.last_resort_boundary_review.length} areas use last-resort boundary evidence. Review each area's reason and pickup access.`]);
  if((v.longitudinal_street_boundary_exceptions||[]).length)gates.push(['Continuous street boundary review',false,`${v.longitudinal_street_boundary_exceptions.length} City street boundaries replaced fragmented seams. Opposite curbs can lie in different areas; actual pickup access remains unconfirmed.`]);
  $('checks-list').innerHTML=gates.map(([title,pass,body])=>`<div class="check-card${pass?'':' error'}"><strong class="${pass?'pass':''}">${pass?'✓':'!'} ${esc(title)}</strong>${esc(body)}</div>`).join('')+current.findings.map(f=>`<div class="check-card ${f.severity==='error'?'error':''}"><strong>${f.severity==='error'?'!':'↗'} ${esc(f.section||f.code.replaceAll('_',' ').toLowerCase())}</strong>${esc(f.message)}</div>`).join('');
}
function renderSources(){
  $('sources-list').innerHTML=`<div class="source-card"><strong>Service universe</strong>${esc(current.source)}${current.sheet?' / '+esc(current.sheet):''}<small>${fmt(current.summary.addresses)} ${esc(dayName())} rows · Original source IDs retained</small></div>`+current.geography_sources.sources.map(s=>`<div class="source-card"><strong>${esc(s.name||'Physical feature reference')}</strong>${s.catalog_url?`<a href="${esc(s.catalog_url)}" target="_blank" rel="noopener">City of Winnipeg open data ↗</a>`:'Extracted from the existing local Manitoba PBF. No OSM tile or Overpass requests.'}<small>${fmt(s.rows||s.features)} reference features · ${esc(s.license)}</small><small>Frozen ${esc((s.retrieved_at||'').slice(0,10))} · SHA-256 ${esc(s.sha256.slice(0,12))}…</small></div>`).join('')+`<div class="source-card"><strong>Review limits</strong>Parcel references cover a bounded part of Winnipeg. The Checks tab reports records without a parcel match. Complete water/land-use multipolygon relations, road reachability, crossing permissions and pickup locations remain unverified.</div>`;
}
async function enableBasemap(){
  if(glBase){const visible=map.hasLayer(glBase);if(visible)map.removeLayer(glBase);else glBase.addTo(map);$('basemap-button').textContent=visible?'Street detail ↗':'Hide street detail';return;}
  $('basemap-button').disabled=true;
  const cached=new Set(session.basemap_cached_urls);
  basemapPolicy=new CwsBasemapRequestPolicy({fetch:(url,options)=>{const canonical=new URL(url).href;return cached.has(canonical)?fetch('/api/basemap-cache?url='+encodeURIComponent(canonical),options):fetch(canonical,options);},onStop:reason=>{$('basemap-notice').hidden=false;$('basemap-notice').textContent='Street detail paused: '+reason+' Local roads, areas and addresses remain available.';$('basemap-label').textContent='Street detail paused · local map available';}});
  maplibregl.setMaxParallelImageRequests(4);maplibregl.setWorkerCount(2);
  maplibregl.addProtocol('cws-ofm',(parameters,controller)=>basemapPolicy.request(parameters,controller));
  glBase=L.maplibreGL({style:'https://tiles.openfreemap.org/styles/liberty',padding:0,interactive:false,attributionControl:false,renderWorldCopies:false,refreshExpiredTiles:false,transformRequest:url=>({url:'cws-ofm://'+encodeURIComponent(url)})}).addTo(map);
  const gl=glBase.getMaplibreMap();window.partitionApp.basemapInstances=1;window.partitionBasemap={policy:basemapPolicy,map:gl};
  map.attributionControl.addAttribution('<a href="https://openfreemap.org/">OpenFreeMap</a> · <a href="https://www.openmaptiles.org/">OpenMapTiles</a> · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>');
  // These handlers report readiness/errors only. They never fit, reload or recreate a map.
  gl.on('idle',()=>{if(!basemapPolicy.stopped&&gl.isStyleLoaded()&&gl.areTilesLoaded())$('basemap-label').textContent=`Bounded street detail · ${basemapPolicy.snapshot().started} cached / live resources`;});
  gl.on('error',event=>basemapPolicy.stop(event.error?.message||'Map resource failed.'));
  $('basemap-button').disabled=false;$('basemap-button').textContent='Hide street detail';
}
async function initialise(){
  busyInput(true);
  try{
    session=await api('/api/state');
    const examples=session.demo_days||['MONDAY'];
    $('example-day').innerHTML=examples.map(day=>`<option value="${esc(day)}">${esc(dayName(day))}</option>`).join('');
    $('example-day').value=examples.includes(session.day)?session.day:examples[0];exampleChanged();
    if(!session.geography_prepared)notice('The local geography has not been prepared. See README for the one-time setup.',true);
    // Frozen local roads give a useful offline map. No public basemap is loaded
    // until the user explicitly selects Street detail.
    const response=await fetch('/api/context');if(!response.ok)throw new Error('Local street reference could not load.');const context=await response.json();
    municipalLayer=L.geoJSON({type:'FeatureCollection',features:context.features.filter(f=>f.properties.kind==='community')},
      {pane:'municipal',interactive:false,style:{color:'#b45309',weight:2.5,dashArray:'9 6',fill:false,opacity:.95}});
    contextLayer=L.geoJSON(context,{pane:'context',renderer,interactive:false,style:f=>{const kind=f.properties.kind;return kind==='community'?{color:'#64796d',fill:false,weight:.8,dashArray:'4 5',opacity:.5}:kind==='park'?{color:'#c7d6be',fillColor:'#dce8cf',fillOpacity:.7,weight:.5}:kind==='landuse'?{color:'#d8cdbf',fillColor:'#e6ddd1',fillOpacity:.5,weight:.5}:kind==='water_area'?{color:'#b5d4d3',fillColor:'#b5d4d3',fillOpacity:.75,weight:.7}:kind==='waterway'?{color:'#aeced0',weight:f.properties.name?.includes('River')?9:2,opacity:.8}:kind==='railway'?{color:'#9fae9b',weight:1,dashArray:'4 5',opacity:.6}:{color:'#fffef7',weight:1.2,opacity:.95};}}).addTo(map);
    map.attributionControl.addAttribution('Physical reference: © OpenStreetMap contributors, ODbL (local cache)');
    if(session.current)showResult(await api('/api/result?key='+session.current),true);
    if(session.active&&session.active_kind!=='routing'){jobActive=true;window.partitionApp.activeJob=true;$('progress-box').hidden=false;busyInput(true);pollJob(session.active);}
    window.partitionApp.initialised=true;
    document.dispatchEvent(new Event('partition-ready'));
  }catch(error){notice(error.message,true);}finally{busyInput(false);}
}
$('example-day').onchange=exampleChanged;
for(const id of ['collection-day','sheet-input'])$(id).onchange=()=>{if(lastUploadFile&&!inputLoading&&!jobActive&&!window.routingUI?.jobActive())loadInput(lastUploadFile);};
$('demo-button').onclick=()=>loadInput();$('empty-demo').onclick=()=>loadInput();$('file-input').onchange=event=>{if(event.target.files[0])loadInput(event.target.files[0]);};
$('dropzone').addEventListener('dragover',event=>{event.preventDefault();$('dropzone').classList.add('dragging');});$('dropzone').addEventListener('dragleave',()=>$('dropzone').classList.remove('dragging'));
$('dropzone').addEventListener('drop',event=>{event.preventDefault();$('dropzone').classList.remove('dragging');if(!inputLoading&&!jobActive&&!window.routingUI?.jobActive()&&event.dataTransfer.files[0])loadInput(event.dataTransfer.files[0]);});
$('run-button').onclick=startJob;
for(const id of ['minimum-input','maximum-input'])$(id).oninput=previewPreference;
$('cancel-button').onclick=async()=>{try{await api('/api/cancel',{method:'POST',body:'{}'});$('progress-message').textContent='Stopping at the next processing checkpoint…';}catch(error){notice(error.message,true);}};
$('fit-button').onclick=fitAddresses;$('points-button').onclick=()=>{pointVisible=!pointVisible;$('points-button').setAttribute('aria-pressed',String(pointVisible));if(pointLayer){if(pointVisible)pointLayer.addTo(map);else map.removeLayer(pointLayer);}};
$('area-search').oninput=renderAreas;
for(const button of document.querySelectorAll('[data-tab]'))button.onclick=()=>{for(const tab of ['areas','checks','sources']){$(tab+'-panel').hidden=button.dataset.tab!==tab;$(tab+'-tab').classList.toggle('active',button.dataset.tab===tab);$(tab+'-tab').setAttribute('aria-selected',String(button.dataset.tab===tab));}};
$('export-button').onclick=()=>$('export-menu').hidden=!$('export-menu').hidden;document.addEventListener('click',event=>{if(!event.target.closest('.export-control'))$('export-menu').hidden=true;});
$('basemap-button').onclick=enableBasemap;
$('municipal-button').onclick=()=>{if(!municipalLayer)return;const show=!map.hasLayer(municipalLayer);
  if(show)municipalLayer.addTo(map);else map.removeLayer(municipalLayer);
  $('municipal-button').setAttribute('aria-pressed',String(show));
  $('municipal-button').textContent=show?'Hide City boundaries':'City boundaries';
  $('municipal-legend').hidden=!show;};
$('settings-button').onclick=()=>{setSetupVisible($('setup-panel').hidden);$('export-menu').hidden=true;};
$('expand-map-button').onclick=()=>{setExpandedMap(!expandedMap);$('export-menu').hidden=true;};
$('help-button').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=()=>$('help-dialog').close();$('help-done').onclick=()=>$('help-dialog').close();
previewPreference();initialise();
