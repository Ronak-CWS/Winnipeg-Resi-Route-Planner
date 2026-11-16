// Real browser/form/API checks on a separate temporary server; no address uploads.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
const require=createRequire(import.meta.url),{chromium}=require('playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const audit=path.join(root,'outputs/2026-11-04_monday_map/audit/partition_app');
const fixture=path.join(audit,`facility-ui-fixture-${Date.now()}`);
const port=Number(process.env.FACILITY_TEST_PORT||8766),base=`http://127.0.0.1:${port}`;
const python=process.env.PYTHON_EXE||path.join(root,'.venv/Scripts/python.exe');
const child=spawn(python,['-u',path.join(root,'tests/facility_test_server.py'),'--port',String(port),'--storage',fixture],{cwd:root,windowsHide:true,stdio:'ignore'});
let browser;
try{
 let ready=false;
 for(let i=0;i<60;i++){try{const r=await fetch(base+'/api/state');if(r.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,200));}
 assert(ready,'Isolated UI fixture did not become ready');
 let executable=chromium.executablePath();
 try{await fs.access(executable);}catch{
  executable=undefined;
  for(const candidate of ['C:/Program Files/Google/Chrome/Application/chrome.exe','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe']){
   try{await fs.access(candidate);executable=candidate;break;}catch{}
  }
 }
 browser=await chromium.launch({headless:true,executablePath:executable,args:['--disable-background-networking']});
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),external=[],errors=[];
 page.on('pageerror',e=>{errors.push(e.message);console.error('Page error: '+e.message);});
 await page.route('**/*',route=>{const url=route.request().url();if(url.startsWith(base+'/')||url.startsWith('data:'))return route.continue();external.push(url);return route.abort();});
 await page.goto(base,{waitUntil:'networkidle'});
 await page.locator('#routes-view').click();await page.locator('#route-settings-button').click();
 await page.locator('#routing-settings-dialog').waitFor({state:'visible'});
 await page.locator('[name="crew_start"]').fill('06:20');
 const depot=page.locator('[data-facility-group="depots"]');
 await depot.getByRole('button',{name:'Add another depot'}).click();
 let card=depot.locator('[data-facility-id]').nth(1);
 await card.locator('[data-site-field="name"]').fill('Test north depot');
 await card.locator('[data-site-field="address"]').fill('Test depot address');
 await card.locator('[data-site-field="lat"]').fill('49.94');await card.locator('[data-site-field="lon"]').fill('-97.15');
 await depot.locator('select').selectOption('multiple');
 await depot.locator('[data-facility-selected]').first().check();
 assert.equal(await depot.locator('[data-facility-selected]:checked').count(),2);
 await depot.getByRole('button',{name:'Add another depot'}).click();
 await depot.locator('[data-facility-id]').nth(2).getByRole('button',{name:'Remove'}).click();
 assert.equal(await depot.locator('[data-facility-id]').count(),2);
 assert.equal(await page.locator('[name="crew_start"]').inputValue(),'06:20','Adding facilities lost another operating input');
 await page.getByText('Receiving facilities, capacity ranges & additional parameters',{exact:true}).click();
 const receiver=page.locator('[data-facility-group="garbage_receivers"]');
 await receiver.getByRole('button',{name:'Add another receiver'}).click();
 card=receiver.locator('[data-facility-id]').nth(1);
 await card.locator('[data-site-field="name"]').fill('Test transfer receiver');
 await card.locator('[data-site-field="address"]').fill('Test receiver address');
 await card.locator('[data-site-field="lat"]').fill('49.89');await card.locator('[data-site-field="lon"]').fill('-97.16');
 await card.locator('[data-site-field="opens"]').fill('07:00');await card.locator('[data-site-field="closes"]').fill('18:30');
 await card.locator('[data-site-field="onsite_minutes"]').fill('7.5');
 await receiver.locator('select').selectOption('multiple');await receiver.locator('[data-facility-selected]').first().check();
 await receiver.screenshot({path:path.join(audit,'facility_receivers_desktop.png')});
 await page.getByRole('button',{name:'Apply parameters',exact:true}).click();
 await page.locator('#routing-settings-dialog').waitFor({state:'hidden'});
 let data=await (await page.request.get(base+'/api/routing/settings')).json();
 assert.equal(data.settings.crew_start,'06:20');
 assert.equal(data.settings.facility_options.depots.length,2);
 assert.equal(data.settings.facility_options.depots.filter(s=>s.selected).length,2);
 assert.equal(data.settings.facility_options.garbage_receivers[1].onsite_minutes,7.5);
 await page.reload({waitUntil:'networkidle'});await page.locator('#routes-view').click();await page.locator('#route-settings-button').click();
 assert.equal(await depot.locator('[data-facility-id]').count(),2,'Saved locations disappeared on reload');
 assert.equal(await depot.locator('select').inputValue(),'multiple');
 await depot.locator('select').selectOption('single');await depot.locator('[data-facility-selected]').nth(1).check();
 assert.equal(await depot.locator('[data-facility-selected]:checked').count(),1);
 await page.getByRole('button',{name:'Apply parameters',exact:true}).click();
 await page.locator('#routing-settings-dialog').waitFor({state:'hidden'});
 data=await (await page.request.get(base+'/api/routing/settings')).json();
 assert.equal(data.settings.yard.name,'Test north depot');
 assert.equal(data.settings.facility_options.depot_mode,'single');
 await page.setViewportSize({width:390,height:844});await page.locator('#route-settings-button').click();
 await depot.scrollIntoViewIfNeeded();
 const overflow=await page.locator('#routing-settings-dialog').evaluate(node=>node.scrollWidth>node.clientWidth+1);
 assert.equal(overflow,false,'Facility controls overflow on mobile');
 await page.screenshot({path:path.join(audit,'facility_depots_mobile.png')});
 await page.locator('#close-routing-settings').click();
 await page.setViewportSize({width:1440,height:950});
 const submitted=[];
 await page.route(base+'/api/routing/run',async route=>{submitted.push(route.request().postDataJSON());await route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({error:'Isolated fixture: request inspected; no solver started.'})});});
 await page.evaluate(()=>{current={key:'fixture',day:'WEDNESDAY',status:'PROVISIONAL',partition_hash:'fixture',areas:{type:'FeatureCollection',features:[]},points:[]};window.routingUI.partitionChanged();});
 const garbage=page.locator('#route-calculate-garbage'),recycling=page.locator('#route-calculate-recycling'),run=page.locator('#route-run-button');
 assert(await garbage.isChecked()&&await recycling.isChecked(),'Both streams must default to selected');
 for(const selected of [['garbage'],['recycling'],['garbage','recycling']]){
  await garbage.setChecked(selected.includes('garbage'));await recycling.setChecked(selected.includes('recycling'));
  await run.click();await page.waitForFunction(()=>document.getElementById('notice').textContent.includes('Isolated fixture')).catch(()=>{});
  assert.deepEqual(submitted.at(-1).settings.streams,selected);
 }
 await garbage.uncheck();await recycling.uncheck();assert(await run.isDisabled(),'An empty selection cannot start a run');
 await recycling.check();
 await page.evaluate(()=>{const stream={trucks:1,pickups:10,paid_hours:8,overtime_hours:0,search:{overtime_first_comparison:{trucks:1,overtime_minutes:0}}};showRouteResult({key:'test',day:'WEDNESDAY',partition_hash:'fixture',settings:routeSettings,streams:{recycling:stream},validation:{recycling:{exactly_once:true}},routes:[],total_trucks:1,access_reviews:[],access_summary:{},work_areas:{type:'FeatureCollection',features:[]}});});
 assert(await page.locator('#route-stream-garbage').isDisabled());assert(await page.locator('#route-stream-recycling').isEnabled());
 assert.equal(await page.locator('#route-garbage-detail').textContent(),'Not calculated in this run');
 await page.screenshot({path:path.join(audit,'route_stream_selection_desktop.png')});
 assert.deepEqual(errors,[]);assert.deepEqual(external,[]);
 const receipt={add_remove:true,single_multiple:true,form_inputs_preserved:true,api_persistence_and_reload:true,selected_depot_used:true,stream_selections:submitted.map(p=>p.settings.streams),empty_stream_selection_blocked:true,single_stream_result_display:true,mobile_overflow:false,external_requests:0,address_uploads:0,console_errors:errors};
 await fs.writeFile(path.join(audit,'facility_form_validation.json'),JSON.stringify(receipt,null,2));
 console.log('PASS: Add/remove depots and receivers; one/multiple choices; saved selection and hours; reload; mobile; no uploads or public requests.');
}finally{if(browser)await browser.close();child.kill();}
