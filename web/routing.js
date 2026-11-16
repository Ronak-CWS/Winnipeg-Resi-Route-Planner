'use strict';
// One existing Leaflet map; routing never creates or automatically reloads it.
let routingMode=false,routeResult=null,routeSettings=null,routeStream='garbage',routeSelected=null,routeJob=null;
let routingInitialising=false,routingSessionRestored=false;
let routeLayer=null,routeSites=null,routeArrows=null,routeTimer=null,workAreaLayer=null,routePointIds=null;
const routeDetails=new Map();
const routePalette=['#126e62','#4666a8','#b17824','#8758a0','#bb5b59','#338690','#56783d','#a96a36'];
const minutes=s=>Math.round(s/60),hours=s=>(s/3600).toFixed(2),duration=s=>`${Math.floor(Math.round(s/60)/60)}h ${Math.round(s/60)%60}m`;
function pickupAccess(s){
 const offset=Number.isFinite(s.PickupOffsetM)?s.PickupOffsetM:map.distance([s.Latitude,s.Longitude],[s.PickupLatitude,s.PickupLongitude]);
 const unresolved=offset>80||/oneway_opposite|road_direction|street_name_unmatched|construction_tagged|ambiguous_property/.test(s.AccessIssues||'');
 return {unresolved,text:`${unresolved?'Pickup access unresolved':'Inferred right-curb service'} · ${Math.round(offset)} m from property${s.PickupRoad?' · '+s.PickupRoad:''}`};
}
const navigation=document.createElement('nav');navigation.className='workflow-nav';navigation.setAttribute('aria-label','Planning workflow');
navigation.innerHTML='<button id="sections-view" aria-pressed="true">1 · Service areas</button><button id="routes-view" aria-pressed="false">2 · Truck routes</button>';
document.querySelector('.header-middle').before(navigation);
const toolbar=document.createElement('div');toolbar.id='routing-toolbar';toolbar.className='routing-toolbar';toolbar.hidden=true;
toolbar.innerHTML='<div class="routing-copy" id="routing-params-summary">Loading your operating parameters…</div><button id="route-settings-button" class="secondary">Operating parameters</button><button id="route-run-button" class="primary">Generate both route plans →</button><a id="route-export" class="secondary" hidden>↓ Routing package</a>';
$('notice').before(toolbar);
const jobBox=document.createElement('div');jobBox.id='route-progress';jobBox.className='route-job';jobBox.hidden=true;
jobBox.innerHTML='<span id="route-progress-text"></span> <button id="route-cancel" class="text-button">Cancel</button><progress id="route-progress-bar" max="100" value="0"></progress>';
toolbar.after(jobBox);
const htmlLink=document.createElement('a');htmlLink.id='route-html-export';htmlLink.className='secondary';htmlLink.textContent='Truck review HTML';htmlLink.hidden=true;toolbar.appendChild(htmlLink);
const stats=document.createElement('div');stats.id='routing-stats';stats.className='routing-stats';stats.hidden=true;
stats.innerHTML='<div><small>GARBAGE · ASL</small><strong id="route-garbage-trucks">—</strong><span id="route-garbage-detail">Trucks to calculate</span></div><div><small>RECYCLING · REAR LOAD</small><strong id="route-recycling-trucks">—</strong><span id="route-recycling-detail">Trucks to calculate</span></div><div><small>TRUCKS IN THIS PLAN</small><strong id="route-total-trucks">—</strong><span id="route-fleet-detail">Independent stream plans</span></div><div><small>ADDRESS ASSIGNMENT</small><strong id="route-coverage">—</strong><span id="route-coverage-detail">Every address, both streams</span></div>';
$('summary-stats').after(stats);
const review=document.createElement('details');review.id='routing-review';review.className='routing-review';review.hidden=true;stats.after(review);
const explorer=document.createElement('aside');explorer.id='route-explorer';explorer.className='route-explorer';explorer.hidden=true;explorer.setAttribute('aria-label','Truck routes');
explorer.innerHTML='<div class="stream-toggle"><button id="route-stream-garbage" aria-pressed="true">Garbage</button><button id="route-stream-recycling" aria-pressed="false">Recycling</button></div><div id="route-selected-detail" class="route-detail" hidden></div><div id="route-list" class="route-list"><div class="route-empty">Your section boundaries are ready.<br><br>Check your prefilled operating parameters, then generate separate garbage and recycling plans.</div></div>';
$('area-explorer').after(explorer);
const dialog=document.createElement('dialog');dialog.id='routing-settings-dialog';
dialog.innerHTML='<button id="close-routing-settings" class="dialog-close" aria-label="Close operating parameters">×</button><span id="routing-day-label" class="eyebrow">OPERATING PARAMETERS</span><h2>Your collection day.</h2><p>Prefilled from your instructions. Planning sections stay intact. Overlong sections can share trucks along clean mapped boundaries; load counts are optimized.</p><form id="routing-settings-form"><div id="routing-form-fields" class="routing-form-grid"></div><p id="routing-form-error" class="notice error" hidden></p><div class="routing-form-actions"><span>One pickup per address per stream · right-side curb collection</span><button class="primary" type="submit">Apply parameters</button></div></form>';
document.body.append(dialog);
map.createPane('routing');map.getPane('routing').style.zIndex=402;
const routeRenderer=L.canvas({padding:.25,pane:'routing'});

function field(path,label,type='number',step='1',wide=false){
 const value=path.split('.').reduce((o,k)=>o[k],routeSettings);
 return `<label class="routing-field${wide?' wide':''}">${esc(label)}<input name="${path}" type="${type}" ${type==='number'?`step="${step}"`:''} value="${esc(value??'')}" ${path==='garbage.kg_per_pickup'?'placeholder="Not supplied"':'required'}></label>`;
}
function fillRouteForm(){
 $('routing-day-label').textContent=(current?.day?current.day+' / ':'')+'OPERATING PARAMETERS';
 const fields=$('routing-form-fields');
 fields.innerHTML=`<fieldset><legend>Working day</legend><div class="routing-fields">${field('crew_start','Crew start','time')}${field('pretrip_minutes','Pretrip / FLHA · minutes')}${field('minimum_paid_hours','Minimum paid hours','number','.25')}${field('preferred_paid_hours','Overtime starts after paid hours','number','.25')}${field('earliest_return','Earliest acceptable return','time')}${field('preferred_return','Preferred return from','time')}${field('latest_return','Latest yard return','time')}${field('break_minutes','Total breaks · minutes')}${field('garbage.pickup_seconds','Garbage stationary pickup · seconds','number','.5')}</div><p>Departure follows pretrip. Pickup time excludes driving. Observed active pace: 3–3.5 pickups/minute, including local driving.</p></fieldset>
 <fieldset><legend>Loads & receiver visits</legend><div class="routing-fields">${field('garbage.capacity','Garbage preferred pickups / load')}${field('recycling.capacity','Recycling preferred pickups / load')}${field('minimum_dump_fill_percent','Minimum planned dump fill (%)')}${field('garbage.receiver.onsite_minutes','Brady onsite · minutes')}${field('recycling.receiver.onsite_minutes','MRF onsite · minutes')}${field('garbage.payload_tonnes','Garbage payload · tonnes','number','.1')}${field('garbage.kg_per_pickup','Garbage kg / pickup · optional','number','.1')}</div><p>The normal maximum plus its tolerance sets the absolute load limit. Default recycling: 1,350 plus 2% = 1,377. Fill is measured against the normal maximum. Aim for the selected minimum at every dump, including the required final unload. Two loads is a reference, not a limit.</p></fieldset>
 <fieldset><legend>Depot & mapped access</legend><div class="routing-fields">${field('yard.address','Yard address','text','',true)}${field('yard.lat','Latitude','number','any')}${field('yard.lon','Longitude','number','any')}</div><p>Mapped access points are used for departure and return travel.</p></fieldset>
 <fieldset><legend>Road time & calculation</legend><div class="routing-fields">${field('active_speed_factor','Active driving factor','number','.001')}${field('general_speed_factor','Other driving factor','number','.001')}${field('reversal_seconds','Confirmed reversal · seconds')}${field('search_seconds_per_section','Section search budget · seconds')}${field('fleet_search_seconds','Fleet solver budget · seconds')}${field('local_solver_workers','Local solver workers · 1–4')}${field('table_locations','Local table request ceiling')}</div><p>Road time ÷ factor. Reversal time is separate. Request batching never splits section ownership or pickup order. Local workers evaluate independent alternatives in parallel; each fleet is assigned together. Solver budgets apply per solve, not to total elapsed runtime.</p></fieldset>
 <details><summary>Receiving facilities, capacity ranges & additional parameters</summary><div class="routing-form-grid">${['garbage','recycling'].map(s=>`<fieldset><legend>${s==='garbage'?'Garbage · Brady Landfill':'Recycling · Canada Fibers / GFL'}</legend><div class="routing-fields">${field(s+'.receiver.address','Receiver address','text','',true)}${field(s+'.receiver.lat','Latitude','number','any')}${field(s+'.receiver.lon','Longitude','number','any')}${field(s+'.receiver.opens','Opens','time')}${field(s+'.receiver.closes','Closes','time')}${field(s+'.capacity_low','Preferred minimum pickups / load')}${field(s+'.capacity_high','Normal maximum pickups / load')}${field(s+'.capacity_tolerance_percent','Load capacity tolerance (%)')}</div></fieldset>`).join('')}<fieldset><legend>Other time allowances</legend><div class="routing-fields">${field('unpaid_lunch_minutes','Extra unpaid lunch · minutes')}${field('posttrip_minutes','Posttrip · minutes')}${field('fueling_minutes','Fueling · minutes')}${field('reversal_sensitivity_seconds','Reversal sensitivity · seconds')}</div><p>The supplied scenario uses zero extra lunch, posttrip and fueling time.</p></fieldset><fieldset><legend>Fleet comparison only</legend><p>${fmt(routeSettings.garbage_trucks_comparison)} garbage / ${fmt(routeSettings.recycling_trucks_comparison)} recycling; reported fleet ${fmt(routeSettings.available_trucks_comparison)}.</p><p>The solver calculates the truck count. These comparisons do not set a truck quota, limit or objective.</p></fieldset><fieldset><legend>Pickup sensitivity</legend><div class="routing-fields">${field('garbage.pickup_seconds_low','Fast pickup · seconds','number','.5')}${field('garbage.pickup_seconds_high','Slow pickup · seconds','number','.5')}${field('garbage.observed_pickups_per_minute_low','Observed minimum / minute','number','.1')}${field('garbage.observed_pickups_per_minute_high','Observed maximum / minute','number','.1')}${field('recycling.pickup_seconds_low','Recycling fast pickup - seconds','number','.5')}${field('recycling.pickup_seconds_high','Recycling slow pickup - seconds','number','.5')}</div><p>Observed rates are a comparison, not an extra delay. ASL garbage; rear-load recycling. No organics in this scenario.</p></fieldset></div></details>`;
 const workerInput=fields.querySelector('input[name="local_solver_workers"]');workerInput.min=1;workerInput.max=4;
 const timeGrid=fields.querySelector('fieldset .routing-fields');
 timeGrid.insertAdjacentHTML('beforeend',field('recycling.pickup_seconds','Recycling stationary pickup - seconds','number','.5'));
 timeGrid.insertAdjacentHTML('beforeend',field('garbage.active_collection_pickups_per_minute','Active pickups / minute','number','.05')+`<label class="routing-field">Use observed collection pace<input name="garbage.use_observed_collection_pace" type="checkbox" ${routeSettings.garbage.use_observed_collection_pace?'checked':''}></label>`);
 fields.querySelector('fieldset p').textContent='Fewer trucks come before avoiding overtime. The preferred window does not add waiting or extra driving. From 06:15, a 16:45 finish is 10.5 paid hours. Garbage uses the observed combined pace; recycling uses 7-10 seconds plus driving.';
}
function paramsSummary(){if(!routeSettings)return;$('routing-params-summary').textContent=`${routeSettings.crew_start} start · prefer ${routeSettings.preferred_return}-${routeSettings.latest_return} (earliest ${routeSettings.earliest_return}) · Garbage ${routeSettings.garbage.active_collection_pickups_per_minute}/min, recycling ${routeSettings.recycling.pickup_seconds}s + driving · ${routeSettings.break_minutes}m breaks · ${fmt(routeSettings.garbage.capacity)} / ${fmt(routeSettings.recycling.capacity)} per load`;}
function routeMode(value){
 document.querySelector('.map-legend span').innerHTML='<i class="legend-area"></i> '+(value?'Truck work area':'Planning area');
 routingMode=value;$('workspace').classList.toggle('routing-mode',value);$('sections-view').setAttribute('aria-pressed',String(!value));$('routes-view').setAttribute('aria-pressed',String(value));
 toolbar.hidden=!value;stats.hidden=!value||expandedMap;review.hidden=!value||!routeResult||expandedMap;
 $('summary-stats').hidden=value||expandedMap;$('area-explorer').hidden=value||expandedMap;explorer.hidden=!value||expandedMap;
 $('export-button').hidden=value;$('settings-button').hidden=value;
 if(value){selected=null;map.closePopup();setSetupVisible(false);notice(routeResult?.requires_recalculation?'Showing the saved plan. Recalculate to apply the updated productive-day and nearby-territory rules.':'');$('workspace-title').textContent=`${dayName()?dayName()+' truck':'Truck'} routes.`;$('workspace-subtitle').textContent='Clean adjacent work areas · separate garbage and recycling plans';}
 else{clearRouteLayers();if(workAreaLayer)map.removeLayer(workAreaLayer);workAreaLayer=null;routePointIds=null;if(current)showResult(current,false);else{$('workspace-title').textContent=`${dayName()?dayName()+' service':'Service'} areas.`;$('workspace-subtitle').textContent='Natural boundaries first · Load your addresses to begin.';}}
 $('route-run-button').disabled=!current||!!routeJob||jobActive;
 if(value&&routeResult)renderRoutes();map.invalidateSize({pan:false});
}
function clearRouteLayers(){for(const layer of [routeLayer,routeSites,routeArrows])if(layer)map.removeLayer(layer);routeLayer=routeSites=routeArrows=null;}
function matchingRouteResult(result){return !!current&&result.partition_hash===current.partition_hash&&(result.day||'MONDAY')===current.day;}
function clearRoutingResult(){
 routeResult=null;routeSelected=null;routePointIds=null;routeDetails.clear();clearRouteLayers();
 if(workAreaLayer)map.removeLayer(workAreaLayer);workAreaLayer=null;
 $('route-export').hidden=true;$('route-export').removeAttribute('href');htmlLink.hidden=true;htmlLink.removeAttribute('href');review.hidden=true;review.replaceChildren();$('route-selected-detail').hidden=true;$('route-selected-detail').replaceChildren();
 for(const stream of ['garbage','recycling']){$('route-'+stream+'-trucks').textContent='—';$('route-'+stream+'-detail').textContent='Calculate for these service areas';}
 $('route-total-trucks').textContent='—';$('route-fleet-detail').textContent='Truck count to calculate';
 $('route-coverage').textContent='—';$('route-coverage-detail').textContent='Generate routes after partitioning';
 $('route-list').innerHTML='<div class="route-empty">Create service areas, then generate routes for this collection day.</div>';
 $('route-run-button').disabled=!current||!!routeJob||jobActive;
}
function showRouteResult(result){
 if(!matchingRouteResult(result))return;
 routeResult=result;routeSelected=null;routeDetails.clear();if(!routeSettings)routeSettings=structuredClone(result.settings);paramsSummary();
 for(const s of ['garbage','recycling']){const x=result.streams[s];$('route-'+s+'-trucks').textContent=fmt(x.trucks);$('route-'+s+'-detail').textContent=`${fmt(Math.round(x.pickups/x.trucks))} pickups/truck${x.comparison_trucks?` | comparison ${x.comparison_trucks} trucks`:''} | ${x.paid_hours.toFixed(1)} worker hours · ${x.overtime_hours.toFixed(1)}h overtime`;}
 $('route-total-trucks').textContent=fmt(result.total_trucks);$('route-fleet-detail').textContent=`${fmt(result.settings.available_trucks_comparison)} available for comparison`;
 const coverage=Object.values(result.validation).every(v=>v.exactly_once);$('route-coverage').textContent=coverage?'100%':'Incomplete';$('route-coverage-detail').textContent=`${fmt(result.streams.garbage.pickups)} pickups per stream`;
 const lowLoads=result.routes.flatMap(r=>r.loads).filter(l=>l.minimum_fill_met===false).length;
 const early=result.routes.filter(r=>r.early_seconds>0).length;const late=result.routes.filter(r=>r.late_seconds>0).length,ot=result.routes.filter(r=>r.overtime_seconds>0).length; $('route-fleet-detail').textContent=(late||early?'Time limits unmet · ':'')+`${fmt(result.settings.available_trucks_comparison)} available for comparison`;
 if(routingMode)notice(result.requires_recalculation?'Showing the saved plan. Recalculate to apply the updated productive-day and nearby-territory rules.':'');
 review.innerHTML=`<summary>${lowLoads?`${lowLoads} dump visits below the minimum fill | `:""}${early?`${early} trucks return before ${esc(result.settings.earliest_return)} - unresolved | `:''}${late?`${late} trucks exceed the latest return · `:''}${ot?`${ot} trucks need overtime`:'All trucks within the preferred day'} · Planning assumptions & checks</summary><p>Objective: fewer trucks, then less total paid work, with all work completed by the return limit. Nearby road connections include isolated pickups. Best tested fleet with coherent work areas. ${fmt(result.access_review_count??result.access_reviews.length)} access records have mapped-road issues. Property-to-curb positions are inferred.</p><p>Garbage mass: ${result.settings.garbage.kg_per_pickup?'count and supplied mass checked':'9-tonne limit recorded; kg per pickup not supplied'}.</p>${Object.entries(result.access_summary).map(([k,v])=>`<p>${esc(k.replaceAll('_',' '))}: ${fmt(v)}</p>`).join('')}<p>Overtime-first comparisons: ${['garbage','recycling'].map(s=>{const x=result.streams[s].search.overtime_first_comparison;return `${s} ${x.trucks} trucks / ${x.overtime_minutes} min overtime`}).join(' · ')}.</p>`;
 $('route-export').href='/api/routing/download?key='+result.key+'&kind=package';$('route-export').hidden=false;htmlLink.hidden=false;htmlLink.href='/api/routing/download?key='+result.key+'&kind=maps';
 if(routingMode){renderRoutes();review.hidden=expandedMap;}
}
function renderRoutes(){
 if(!routeResult)return;
 const routes=routeResult.routes.filter(r=>r.stream===routeStream),container=$('route-list');container.replaceChildren();
 for(const [i,r] of routes.entries()){const button=document.createElement('button');button.className='route-card'+(routeSelected===r.id?' active':'');button.dataset.route=r.id;
  button.innerHTML=`<strong><span style="color:${routePalette[i%routePalette.length]}">${esc(r.id)}</span><span>${fmt(r.pickups)}</span></strong><small>${esc(r.sections.join(' · '))}</small><small>${r.load_count} ${r.load_count===1?"load":"loads"} · ${duration(r.paid_seconds)} · return ${esc(r.return)}</small>${r.early_seconds?`<small class="late">Before earliest return - ${minutes(r.early_seconds)} min underfilled</small>`:''}${r.overtime_seconds?`<small class="${r.late_seconds?'late':'ot'}">${minutes(r.overtime_seconds)} min overtime${r.late_seconds?' · late return':''}</small>`:''}`;button.onclick=()=>selectRoute(r.id,true);container.appendChild(button);
 }
 for(const s of ['garbage','recycling'])$('route-stream-'+s).setAttribute('aria-pressed',String(routeStream===s));
 const owner=new Map(routes.flatMap((r,i)=>r.sections.map(s=>[s,{id:r.id,colour:routePalette[i%routePalette.length]}])));
 if(areaLayer)map.removeLayer(areaLayer);
 if(workAreaLayer)map.removeLayer(workAreaLayer);
 workAreaLayer=L.geoJSON(routeResult.work_areas||current.areas,{pane:'areas',renderer:areaRenderer,bubblingMouseEvents:false,
  style:f=>{const o=owner.get(f.id);return {color:o?.colour||'#81918a',fillColor:o?.colour||'#81918a',fillOpacity:routeSelected?(o?.id===routeSelected ? .23 : .035):.17,weight:routeSelected&&o?.id===routeSelected?2.5:1.2};},
  onEachFeature:(f,layer)=>layer.on('click',event=>{L.DomEvent.stopPropagation(event);openWorkArea(f,event.latlng);})}).addTo(map);
 routePointIds=routeSelected&&routeDetails.has(routeSelected)?new Set(routeDetails.get(routeSelected).stops.map(s=>s.AddressId)):null;
 drawPoints();
}
async function openWorkArea(feature,latlng){
 const key=routeResult?.key;
 const route=routeResult?.routes.find(r=>r.stream===routeStream&&r.sections.includes(feature.id));
 if(!route)return;
 await selectRoute(route.id,false);
 if(routeResult?.key!==key||!routingMode)return;
 const p=feature.properties;
 const unresolved=(routeDetails.get(route.id)?.stops||[]).filter(s=>s.WorkArea===feature.id&&pickupAccess(s).unresolved).length;
 L.popup({maxWidth:300}).setLatLng(latlng).setContent(`<div class="popup-title">${esc(feature.id)} · Truck work area</div><div class="popup-record"><b>${esc(p.name)}</b><div class="popup-count">${fmt(p.addresses)} addresses</div><small>${esc(route.id)} · ${esc(route.equipment)}</small>${unresolved?`<small>${fmt(unresolved)} pickups have unresolved road access</small>`:''}${p.parent_section?`<small>Planning section ${esc(p.parent_section)} · ${esc(p.routing_boundary)}</small>`:''}</div>`).openOn(map);
}
async function selectRoute(id,fit=false){
 if(!routeResult)return;
 const key=routeResult.key;
 try{
  routeSelected=id;renderRoutes();let r=routeDetails.get(id);
  if(!r){r=await api('/api/routing/route?key='+key+'&id='+encodeURIComponent(id));if(routeResult?.key!==key)return;routeDetails.set(id,r);}
  if(routeSelected!==id||!routingMode)return;
  clearRouteLayers();const all=routeResult.routes.filter(x=>x.stream===routeStream),colour=routePalette[Math.max(0,all.findIndex(x=>x.id===id))%routePalette.length];
  routeLayer=L.geoJSON(r.geometry,{pane:'routing',renderer:routeRenderer,style:f=>({color:colour,weight:f.properties.kind==='collection_drive'?3.2:2,opacity:.85,dashArray:f.properties.kind==='collection_drive'?null:'6 5'}),onEachFeature:(f,layer)=>layer.bindPopup(`<strong>${esc(id)} · Load ${f.properties.load}</strong><br>${esc(f.properties.kind.replaceAll('_',' '))}`)}).addTo(map);
  routeSites=L.layerGroup().addTo(map);for(const [key,site] of Object.entries(routeResult.sites)){if(key!=='yard'&&key!==routeStream)continue;L.marker([site.coordinate[1],site.coordinate[0]],{icon:L.divIcon({className:'site-dot',html:key==='yard'?'Y':'RF',iconSize:[23,23]})}).addTo(routeSites).bindPopup(`<strong>${esc(site.name)}</strong><br>${esc(site.address)}`);}
  routeArrows=L.layerGroup().addTo(map);const features=r.geometry.features.filter(f=>f.properties.kind==='collection_drive');const step=Math.max(1,Math.ceil(features.length/65));
  for(let i=0;i<features.length;i+=step){const c=features[i].geometry.coordinates;if(c.length<2)continue;let best=-1,dx=0,dy=0,n=0;for(let j=0;j<c.length-1;j++){const x=(c[j+1][0]-c[j][0])*Math.cos(c[j][1]*Math.PI/180),y=-(c[j+1][1]-c[j][1]);if(x*x+y*y>best){best=x*x+y*y;dx=x;dy=y;n=j;}}if(best<1e-16)continue;const deg=Math.atan2(dy,dx)*180/Math.PI;L.marker([c[n][1],c[n][0]],{interactive:false,icon:L.divIcon({className:'route-arrow',html:`<span style="display:block;color:${colour};transform:rotate(${deg}deg)">➜</span>`,iconSize:[18,18]})}).addTo(routeArrows);}
  const detail=$('route-selected-detail');detail.hidden=false;detail.innerHTML=`<button id="route-clear" class="text-button">← All ${esc(routeStream)} trucks</button><h3>${esc(id)} · ${esc(r.equipment)}</h3><div class="mini-grid"><span>Pickups<b>${fmt(r.pickups)}</b></span><span>Return to yard<b>${esc(r.return)}</b></span><span>Paid time<b>${duration(r.paid_seconds)}</b></span><span>Distance<b>${r.km.toFixed(1)} km</b></span></div><p>${esc(r.sections.join(' → '))}</p><table><thead><tr><th>Load</th><th>Pickups</th><th>Fill</th><th>Unload by</th></tr></thead><tbody>${r.loads.map(l=>`<tr><td>${l.load}</td><td>${fmt(l.pickups)} / ${fmt(l.capacity)}</td><td>${l.fill_percent??Math.round(100*l.pickups/l.capacity)}%${l.minimum_fill_met===false?" - below target":""}</td><td>${esc(l.unloaded)}</td></tr>`).join('')}</tbody></table><details><summary>Time breakdown & sequence</summary><p>Pickup ${duration(r.pickup_seconds)} · active driving ${duration(r.collection_drive_seconds)} · other driving ${duration(r.deadhead_seconds)} · unloading ${duration(r.unload_seconds)} · breaks ${minutes(r.break_seconds)}m.</p><p>Active pace ${r.active_pickups_per_minute.toFixed(2)} pickups/minute. ${r.reversals} mapped reversals; +${minutes(r.sensitivity_60s_extra_seconds)}m at the conservative reversal setting.</p><p>${r.stops.slice(0,6).map(s=>`${s.Sequence}. ${esc(s.Address)}`).join('<br>')}<br>… ${fmt(r.stops.length)} pickups in the export.</p><a href="/api/routing/download?key=${routeResult.key}&kind=pickups">Download full pickup order · CSV</a></details>`;
  if(Object.keys(r.pace_sensitivity||{}).length)detail.querySelector('details').insertAdjacentHTML('beforeend',`<p>Observed-pace allowance: ${duration(r.collection_allowance_seconds||0)}. This is only the difference above pickup plus modeled local driving.</p><p>Same-order pace sensitivity: ${Object.entries(r.pace_sensitivity||{}).map(([pace,v])=>`${pace} pickups/min: ${v.paid_hours.toFixed(2)} paid hours`).join(' / ')}.</p>`);
  detail.insertAdjacentHTML('beforeend','<button id="route-full-trip" class="text-button">Show yard, receiver and full trip</button>');$('route-full-trip').onclick=()=>{if(routeLayer?.getBounds().isValid())map.fitBounds(routeLayer.getBounds(),{padding:[35,35],animate:false});};
  if(Object.keys(r.pickup_time_sensitivity||{}).length)detail.querySelector('details').insertAdjacentHTML('beforeend',`<p>Recycling pickup sensitivity, same roads and loads: ${Object.entries(r.pickup_time_sensitivity).map(([seconds,v])=>`${seconds}s: ${v.paid_hours.toFixed(2)} paid hours`).join(' / ')}.</p>`);
  $('route-clear').onclick=()=>{routeSelected=null;detail.hidden=true;clearRouteLayers();renderRoutes();};
  routePointIds=new Set(r.stops.map(s=>s.AddressId));drawPoints();if(fit&&r.stops.length)map.fitBounds(L.latLngBounds(r.stops.map(s=>[s.Latitude,s.Longitude])),{padding:[35,35],animate:false,maxZoom:16});
 }catch(error){notice(error.message,true);}
}
async function pollRoute(id){
 try{const job=await api('/api/job?id='+encodeURIComponent(id));$('route-progress-text').textContent=job.message+` · ${Math.round((job.elapsed_seconds||0)/60)}m`;$('route-progress-bar').value=job.progress;
  if(job.state==='done'){routeJob=null;jobBox.hidden=true;showRouteResult(await api('/api/routing/result?key='+job.result));$('route-run-button').disabled=false;busyInput(false);}
  else if(['error','cancelled'].includes(job.state)){routeJob=null;jobBox.hidden=true;$('route-run-button').disabled=false;busyInput(false);notice(job.message,job.state==='error');}
  else routeTimer=setTimeout(()=>pollRoute(id),1500);
 }catch(error){$('route-progress-text').textContent='Progress connection stopped. Reload to reconnect. '+error.message;}
}
async function initialiseRouting(){
 if(routingInitialising)return;routingInitialising=true;
 try{const data=await api('/api/routing/settings'+(current?.day?'?day='+encodeURIComponent(current.day):''));routeSettings=data.settings;paramsSummary();
  if(data.current){const result=await api('/api/routing/result?key='+data.current.key);showRouteResult(result);}
  if(session&&!routingSessionRestored){routingSessionRestored=true;if(session.active_kind==='routing'){routeJob=session.active;routeMode(true);jobBox.hidden=false;busyInput(true);pollRoute(routeJob);}}
 }catch(error){$('routing-params-summary').textContent=error.message;}finally{routingInitialising=false;}
}
$('sections-view').onclick=()=>routeMode(false);$('routes-view').onclick=()=>routeMode(true);
$('route-settings-button').onclick=()=>{if(!routeSettings)return;fillRouteForm();$('routing-form-error').hidden=true;dialog.showModal();};$('close-routing-settings').onclick=()=>dialog.close();
$('routing-settings-form').onsubmit=async event=>{event.preventDefault();const next=structuredClone(routeSettings);for(const input of event.target.querySelectorAll('input[name]')){const parts=input.name.split('.');let target=next;for(const p of parts.slice(0,-1))target=target[p];target[parts.at(-1)]=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):input.value;}try{const saved=await api('/api/routing/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({settings:next})});routeSettings=saved.settings;paramsSummary();dialog.close();if(routeResult)notice('Parameters saved. Generate both route plans to use them.');}catch(error){$('routing-form-error').hidden=false;$('routing-form-error').textContent=error.message;}};
$('route-run-button').onclick=async()=>{if(!current||routeJob)return;try{notice('');const response=await api('/api/routing/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({partition_key:current.key,settings:routeSettings})});routeJob=response.job_id;jobBox.hidden=false;$('route-run-button').disabled=true;busyInput(true);pollRoute(routeJob);}catch(error){notice(error.message,true);}};
$('route-cancel').onclick=async()=>{await api('/api/cancel',{method:'POST',body:'{}'});$('route-progress-text').textContent='Stopping at the next road or solve checkpoint…';};
for(const s of ['garbage','recycling'])$('route-stream-'+s).onclick=()=>{routeStream=s;routeSelected=null;$('route-selected-detail').hidden=true;clearRouteLayers();renderRoutes();};
window.routingUI={isActive:()=>routingMode,jobActive:()=>!!routeJob,inputChanged:()=>{clearRoutingResult();routeMode(false);},openAt:latlng=>{const f=routeResult?.work_areas?.features.find(f=>{const polygons=f.geometry.type==='Polygon'?[f.geometry.coordinates]:f.geometry.coordinates;return polygons.some(rings=>insideRing(latlng.lng,latlng.lat,rings[0])&&!rings.slice(1).some(r=>insideRing(latlng.lng,latlng.lat,r)));});if(f)openWorkArea(f,latlng);},selectSection:id=>{const r=routeResult?.routes.find(r=>r.stream===routeStream&&r.sections.includes(id));if(r)selectRoute(r.id,false);},pointVisible:p=>!routingMode||!routeSelected||!!routePointIds?.has(p.id),
 pointDetails:records=>{if(!routingMode||!routeSelected)return '';const r=routeDetails.get(routeSelected);if(!r)return '';const ids=new Set(records.map(p=>p.id));return r.stops.filter(s=>ids.has(s.AddressId)).map(s=>`<div class="popup-record"><strong>${esc(s.Truck)} · Load ${s.Load} · Pickup ${fmt(s.Sequence)}</strong><small>${esc(pickupAccess(s).text)} · bearing ${s.TravelBearing}°</small></div>`).join('');},
 resized:()=>{if(routingMode){explorer.hidden=expandedMap;stats.hidden=expandedMap;review.hidden=expandedMap||!routeResult;$('summary-stats').hidden=true;$('area-explorer').hidden=true;}},
 partitionChanged:()=>{
  if(routeResult&&!matchingRouteResult(routeResult))clearRoutingResult();
  $('route-run-button').disabled=!current||!!routeJob||jobActive;
 }};

// The partition initialisation owns session loading; no repeated map polling.
document.addEventListener('partition-ready',()=>{window.routingUI.partitionChanged();if(!routeSettings||!routeResult)initialiseRouting();});
if(session)initialiseRouting();
