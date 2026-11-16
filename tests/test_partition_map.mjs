// Geometry and event-routing regression tests; no browser or provider requests.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const elements=new Map(), handlers={}, markers=[], popups=[];
let mapCreations=0,fitCalls=0;
function element(id){if(!elements.has(id))elements.set(id,{value:id==='preference-type'?'target':id==='tolerance-input'?'15':'600',hidden:false,checked:false,classList:{toggle(){},add(){},remove(){}},setAttribute(){},addEventListener(){},replaceChildren(){},querySelector(){return {onclick:null}},textContent:'',innerHTML:''});return elements.get(id);}
const map={createPane(){},getPane(){return {style:{}}},setMaxBounds(){},setMinZoom(){},getBoundsZoom(){return 10},fitBounds(){fitCalls++},invalidateSize(){},getContainer(){return element('map')},on(name,fn){handlers[name]=fn},hasLayer(){return false},removeLayer(){},closeTooltip(){},attributionControl:{setPrefix(){},addAttribution(){}}};
const context={document:{getElementById:element,querySelectorAll:()=>[],addEventListener(){}},window:{},ResizeObserver:class{observe(){}},AbortController,console,setTimeout,clearTimeout,
  L:{map:()=>{mapCreations++;return map},canvas:options=>options,svg:options=>options,latLngBounds:()=>({}),DomEvent:{stopPropagation(e){e.stopped=true}},
    popup:()=>{const p={setLatLng(){return this},setContent(content){this.content=content;return this},openOn(){popups.push(this);return this}};return p;},
    layerGroup:()=>({addLayer(){},addTo(){}}),circleMarker:(latlng,options)=>{const m={latlng,options,events:{},on(name,fn){this.events[name]=fn;return this},bindPopup(content){this.content=content;return this},openPopup(){return this}};markers.push(m);return m;}}};
vm.createContext(context);
vm.runInContext(fs.readFileSync(new URL('../web/app.js',import.meta.url),'utf8').replace('previewPreference();initialise();',''),context);
const evaluate=code=>vm.runInContext(code,context);
assert.equal(evaluate('insideRing(5,5,[[0,0],[10,0],[10,10],[0,10],[0,0]])'),true);
assert.equal(evaluate('insideRing(12,5,[[0,0],[10,0],[10,10],[0,10],[0,0]])'),false);
evaluate(`current={areas:{features:[{id:'A',properties:{colour:'#000',name:'Sample area',addresses:2,area_km2:.1,estimated:0},geometry:{type:'Polygon',coordinates:[[[0,0],[10,0],[10,10],[0,10],[0,0]],[[4,4],[6,4],[6,6],[4,6],[4,4]]]}}]}};areaPaths.set('A',{getBounds:()=>({contains:()=>true})});`);
assert.equal(evaluate('areaAt({lng:1,lat:1}).id'),'A');
assert.equal(evaluate('areaAt({lng:5,lat:5})'),null,'A real hole is not clickable area land');
assert.equal(evaluate('areaAt({lng:12,lat:5})'),null);
evaluate(`groups.set('1,1',[{lat:1,lon:1,section:'A',id:'42',address:'<address>',quality:'Exact address',trusted:true}]);drawPoints();`);
assert.equal(markers[0].options.pane,'points');
assert.equal(markers[0].options.renderer.pane,'points');
assert.equal(markers[0].options.bubblingMouseEvents,false);
const event={};markers[0].events.click(event);
assert.equal(event.stopped,true,'Address click must stop area popup propagation');
assert.match(markers[0].content,/AddressId 42/);
assert.match(markers[0].content,/&lt;address&gt;/);
assert.equal(typeof handlers.click,'function','Empty canvas clicks have map-level area hit testing');
assert.equal(handlers.mousemove,undefined,'Moving across an area must not reveal its details');
evaluate('selectArea=id=>window.testSelection=id');
handlers.click({latlng:{lng:1,lat:1}});
assert.equal(context.window.testSelection,'A');
assert.match(popups[0].content,/Sample area/);
assert.match(popups[0].content,/2 addresses/);
evaluate(`current.areas.features[0].properties.boundary_quality={street_breaks:[{},{}],alley_side_splits:[{}]};current.areas.features[0].properties.planning_reason='Within the requested range.';`);
assert.match(evaluate('areaPopup(current.areas.features[0])'),/Boundary issue: 2 street cuts and 1 opposing alley split remain/);
assert.equal(evaluate('boundaryNotice({boundary_quality:{street_breaks:[],alley_side_splits:[]}})'), '');
evaluate(`current.areas.features[0].geometry={type:'MultiPolygon',coordinates:[[[[0,0],[3,0],[3,3],[0,3],[0,0]]],[[[7,7],[10,7],[10,10],[7,10],[7,7]]]]};`);
assert.equal(evaluate('areaAt({lng:1,lat:1}).id'),'A');
assert.equal(evaluate('areaAt({lng:8,lat:8}).id'),'A','Both nearby pieces use one address list');
assert.equal(evaluate('areaAt({lng:5,lat:5})'),null,'The geographic gap is never treated as area land');
handlers.click({latlng:{lng:8,lat:8}});
assert.equal(context.window.testSelection,'A');
element('minimum-input').value='590';element('maximum-input').value='610';evaluate('previewPreference()');
assert.match(element('range-preview').textContent,/540–660/);
element('minimum-input').value='500';element('maximum-input').value='700';evaluate('previewPreference()');
assert.match(element('range-preview').textContent,/500–700/);
const fitsBefore=fitCalls;
element('settings-button').onclick();
assert.equal(element('setup-panel').hidden,true);
element('expand-map-button').onclick();
assert.equal(element('area-explorer').hidden,true);
assert.equal(element('summary-stats').hidden,true);
element('expand-map-button').onclick();
assert.equal(element('area-explorer').hidden,false);
assert.equal(mapCreations,1,'Layout changes must reuse the existing map');
assert.equal(fitCalls,fitsBefore,'Expanding the layout must not trigger automatic fits');
console.log('PASS: area interiors/holes, independent point canvas, address click precedence, click-only area details, count/range previews. Zero network calls.');
