// Exercise the actual upload and routing UI together, without map-provider requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const elements=new Map(),removed=[],requests=[];
let mapCreations=0;
function makeElement(id=''){
  const node={value:({'example-day':'TUESDAY','minimum-input':'900','maximum-input':'1100'})[id]||'',
    hidden:false,disabled:false,dataset:{},style:{},attributes:{},textContent:'',innerHTML:'',
    classList:{toggle(){},add(){},remove(){}},setAttribute(k,v){this.attributes[k]=v;},removeAttribute(k){delete this.attributes[k];delete this[k];},
    addEventListener(){},replaceChildren(){this.innerHTML='';},querySelector(){return makeElement();},
    appendChild(){},append(){},before(){},after(){},insertAdjacentHTML(){}};
  let identity=id;
  Object.defineProperty(node,'id',{get:()=>identity,set:value=>{identity=value;if(value)elements.set(value,node);}});
  return node;
}
function element(id){if(!elements.has(id))elements.set(id,makeElement(id));return elements.get(id);}
const exportLink=makeElement('assignment-export');exportLink.dataset.kind='assignments';exportLink.href='/api/download?key=monday';
const map={createPane(){},getPane(){return {style:{}}},setMaxBounds(){},setMinZoom(){},getBoundsZoom(){return 10;},fitBounds(){},invalidateSize(){},getContainer(){return element('map');},
  on(){},hasLayer(){return false;},removeLayer(layer){removed.push(layer);},closePopup(){},attributionControl:{setPrefix(){},addAttribution(){}}};
const layer=()=>({addTo(){return this;},addLayer(){},on(){return this;},bindPopup(){return this;}});
let nextResponse,finishRoute;
const pendingRoute=new Promise(resolve=>finishRoute=resolve);
const context={console,AbortController,structuredClone,setTimeout,clearTimeout,Event,ResizeObserver:class{observe(){}},
  document:{getElementById:element,querySelector:()=>makeElement(),querySelectorAll:s=>s==='[data-kind]'?[exportLink]:[],createElement:()=>makeElement(),addEventListener(){},dispatchEvent(){},body:makeElement()},window:{},
  fetch:async(path,options)=>{requests.push({path,options});if(path.startsWith('/api/routing/route?'))return pendingRoute;return nextResponse;},
  L:{map(){mapCreations++;return map;},canvas:o=>o,svg:o=>o,latLngBounds:()=>({}),geoJSON:layer,layerGroup:layer,DomEvent:{stopPropagation(){}}}};
vm.createContext(context);
const evaluate=code=>vm.runInContext(code,context);
evaluate(fs.readFileSync(new URL('../web/app.js',import.meta.url),'utf8').replace('previewPreference();initialise();',''));
evaluate(fs.readFileSync(new URL('../web/routing.js',import.meta.url),'utf8'));
evaluate(`session={csrf:'test',demo_days:['MONDAY','TUESDAY']};$('example-day').value='MONDAY';current={day:'MONDAY',partition_hash:'monday'};routeResult={day:'MONDAY',key:'old',partition_hash:'monday'};
  areaLayer={name:'areas'};pointLayer={name:'points'};highlight={name:'highlight'};routeLayer={name:'roads'};workAreaLayer={name:'work areas'};routeSites={name:'sites'};
  routingMode=true;$('route-export').href='old';$('route-html-export').href='old';`);
context.uploadFile={name:'Tuesday_addresses.csv',arrayBuffer:async()=>new ArrayBuffer(0)};
const preview={input_id:'tuesday-input',day:'TUESDAY',count:21233,distinct_coordinates:21100,excluded:0,source:'Tuesday_addresses.csv',sheet:'',warnings:[]};
nextResponse={ok:true,json:async()=>preview};
await evaluate('loadInput(uploadFile)');
assert.equal(evaluate('current'),null);
assert.equal(evaluate('routeResult'),null);
assert.equal(evaluate('routingMode'),false);
assert.equal(evaluate('inputDay'),'TUESDAY');
assert.equal(element('workspace-title').textContent,'Tuesday service areas.');
assert.equal(element('workspace-day').textContent,'Tuesday');
assert.equal(element('example-day').value,'TUESDAY');
assert.equal(element('download-input').href,'/api/workbook?day=TUESDAY');
assert.equal(element('stat-addresses-label').textContent,'TUESDAY ADDRESSES');
assert.equal(element('stat-addresses').textContent,'21,233');
assert.equal(element('run-button').disabled,false);
assert.equal(element('export-button').disabled,true);
assert.equal(exportLink.href,undefined);
assert.equal(element('route-export').href,undefined);
assert.equal(element('route-html-export').href,undefined);
assert.equal(element('route-run-button').disabled,true);
assert.equal(removed.length,6,'All old partition, point, route and work-area layers are removed');
assert.equal(requests[0].path,'/api/upload?day=&sheet=');
assert.equal(requests[0].options.headers['X-Filename'],'Tuesday_addresses.csv');
assert.equal(requests.some(r=>r.path==='/api/run'),false,'Uploading must wait for the user to create service areas');
evaluate('exampleChanged()');
assert.equal(element('download-input').href,'/api/workbook?day=TUESDAY');

// Matching counts or a matching old hash cannot make another day's routes current.
evaluate(`current={day:'TUESDAY',partition_hash:'same'};showRouteResult({day:'MONDAY',partition_hash:'same'});`);
assert.equal(evaluate('routeResult'),null);

// An invalid/mixed-day replacement must leave no accepted input or stale result.
nextResponse={ok:false,json:async()=>({error:'Choose a collection day.',available_days:{MONDAY:1,TUESDAY:2}})};
await evaluate('loadInput(uploadFile)');
assert.equal(evaluate('inputId'),null);
assert.equal(evaluate('current'),null);
assert.equal(element('run-button').disabled,true);
assert.match(element('notice').innerHTML,/Monday \(1\), Tuesday \(2\)/);
assert.equal(element('upload-options').open,true);
assert.equal(element('stat-addresses').textContent,'—');

// An in-flight old route response cannot restore a previous day's lines or popup.
evaluate(`current={day:'MONDAY',partition_hash:'monday',areas:{type:'FeatureCollection',features:[]}};
  routeResult={day:'MONDAY',key:'old',partition_hash:'monday',work_areas:{type:'FeatureCollection',features:[]},routes:[{id:'G-01',stream:'garbage',sections:['MON-001'],pickups:1,load_count:1,paid_seconds:60,return:'15:30'}]};routingMode=true;`);
const oldRequest=evaluate("selectRoute('G-01')");
nextResponse={ok:true,json:async()=>preview};
await evaluate('loadInput(uploadFile)');
finishRoute({ok:true,json:async()=>({id:'G-01',stops:[]})});
await oldRequest;
assert.equal(evaluate('routeResult'),null);
assert.equal(evaluate('routeDetails.size'),0);
assert.equal(evaluate('routeLayer'),null);
assert.equal(element('workspace-title').textContent,'Tuesday service areas.');
assert.equal(mapCreations,1,'Day changes reuse the existing map');
assert.ok(requests.every(r=>r.path.startsWith('/api/')));
console.log('PASS: Tuesday labels/input, mixed-day errors, day-isolated routes, cleared old layers/downloads and stale-response protection. No external requests.');
