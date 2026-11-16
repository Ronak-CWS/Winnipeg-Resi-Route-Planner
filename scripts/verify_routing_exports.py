"""Independent saved-output reconciliation; does not call the routing evaluator."""
import csv
import hashlib
import json
import math
from html.parser import HTMLParser
from collections import Counter, defaultdict
from pathlib import Path
from pyproj import Transformer
from shapely.geometry import LineString, Point, shape
from shapely.ops import transform, unary_union
from shapely import set_precision,make_valid
from shapely.strtree import STRtree


def verify():
    delivery=Path('outputs/2026-11-04_monday_map');cache=delivery/'audit/partition_app'
    current=json.loads((cache/'current-routing.json').read_text())
    result=json.loads((cache/f"routing-{current['key']}.result.json").read_text(encoding='utf-8'))
    partition=json.loads((cache/f"{result['partition_key']}.result.json").read_text(encoding='utf-8'))
    source={r['AddressId']:r for r in csv.DictReader((delivery/'Monday_addresses_lat_long.csv').open(encoding='utf-8-sig'))}
    owners={p['id']:p['section'] for p in partition['points']}
    assert set(source)==set(owners)
    assert result['partition_hash']==partition['partition_hash']
    projection=Transformer.from_crs(4326,32614,always_xy=True).transform
    polygons={f['id']:transform(projection,shape(f['geometry'])) for f in result['work_areas']['features']}
    parent_polygons={f['id']:set_precision(make_valid(transform(projection,shape(f['geometry']))),.01) for f in partition['areas']['features']}
    work_parents={f['id']:f['properties'].get('parent_section',f['id']) for f in result['work_areas']['features']}
    for parent,polygon in parent_polygons.items():
        children=[polygons[w] for w,p in work_parents.items() if p==parent]
        assert children and set_precision(unary_union(children),.01).symmetric_difference(polygon).area<.6,parent
        # Independently bound any projection-grid difference to centimetres.
        raw_parent=transform(projection,shape(next(f for f in partition['areas']['features'] if f['id']==parent)['geometry']))
        assert unary_union(children).difference(raw_parent.buffer(.02)).area<.01,parent
        assert raw_parent.difference(unary_union(children).buffer(.02)).area<.01,parent
        assert abs(sum(c.area for c in children)-unary_union(children).area)<.1,parent
    for change in result['work_area_changes']:
        if change['status']=='SHARED_BY_CLEAN_WORK_AREAS':assert all(change['checks'].values())
    graph=defaultdict(set)
    for link in result['adjacency']:
        a,b=link['a'],link['b']
        assert polygons[a].distance(polygons[b])<=80.1 or (link['kind']=='road_gap_connection' and link['gap_m']<=link['nearest_component_gap_m']*1.35+300.1)
        assert link['road_connection_m']>=0
        graph[a].add(b);graph[b].add(a)
    reported_access=defaultdict(set)
    for review in result['access_reviews']:reported_access[review['id']].update(review['issues'])
    checked_points=0;path_outliers=[];time_failures=[];early_returns=[];access_offsets=[];underfilled_dumps=[]
    for stream in ['garbage','recycling']:
        routes=[r for r in result['routes'] if r['stream']==stream]
        counts=Counter(s['AddressId'] for r in routes for s in r['stops'])
        assert set(counts)==set(source) and all(n==1 for n in counts.values())
        area_counts=Counter(s['WorkArea'] for r in routes for s in r['stops'])
        assert all(f['properties']['addresses']==area_counts[f['id']] for f in result['work_areas']['features'])
        section_owner=defaultdict(set)
        coordinate_owner=defaultdict(set)
        pass_owner=defaultdict(set)
        for route in routes:
            cfg={**result['settings'],**result['settings'][stream]};stops=route['stops'];loads=route['loads']
            assert [s['Sequence'] for s in stops]==list(range(1,len(stops)+1))
            assert route['pickups']==len(stops)
            run_sequence=[]
            for s in stops:
                original=source[s['AddressId']]
                assert s['Address']==original['CombinedAddress']
                assert s['Latitude']==float(original['Latitude']) and s['Longitude']==float(original['Longitude'])
                assert s['Section']==owners[s['AddressId']]
                assert reported_access[s['AddressId']]<=set(s['AccessIssues'].split('; ')),s['AddressId']
                section_owner[s['WorkArea']].add(route['id'])
                assert work_parents[s['WorkArea']]==s['Section']
                pass_owner[s['RoadPass']].add(route['id'])
                original_point=Point(*projection(s['Longitude'],s['Latitude']))
                pickup_point=Point(*projection(s['PickupLongitude'],s['PickupLatitude']))
                offset=original_point.distance(pickup_point)
                if 'PickupOffsetM' in s:
                    assert abs(s['PickupOffsetM']-offset)<.2
                    if s.get('AccessBasis')=='connected_site_access':assert offset<=60.1
                if offset>80.1:
                    assert 'property_setback_over_80m' in s['AccessIssues']
                    access_offsets.append({'route':route['id'],'id':s['AddressId'],'offset_m':round(offset,2)})
                assert polygons[s['WorkArea']].distance(original_point)<.04
                coordinate_owner[(s['Latitude'],s['Longitude'])].add((route['id'],s['Load']))
                if not run_sequence or run_sequence[-1]!=s['WorkArea']:run_sequence.append(s['WorkArea'])
            assert run_sequence==route['sections']
            assert len(run_sequence)==len(set(run_sequence))
            visited={route['sections'][0]}
            while True:
                expanded=visited|set().union(*(graph[s]&set(route['sections']) for s in visited))
                if expanded==visited:break
                visited=expanded
            assert visited==set(route['sections'])
            for load in loads:
                rows=[s for s in stops if s['Load']==load['load']]
                assert len(rows)==load['pickups']<=load['capacity']
                normal=cfg[stream]['capacity_high']
                maximum=normal+math.floor(normal*cfg[stream].get('capacity_tolerance_percent',0)/100+1e-9)
                if stream=='garbage' and cfg['garbage']['kg_per_pickup']:
                    mass_cap=math.floor(cfg['garbage']['payload_tonnes']*1000/cfg['garbage']['kg_per_pickup'])
                    normal=min(normal,mass_cap);maximum=min(maximum,mass_cap)
                assert load['capacity']==maximum
                if 'minimum_dump_fill_percent' in cfg:
                    threshold=math.ceil(normal*cfg['minimum_dump_fill_percent']/100)
                    assert load['minimum_fill_pickups']==threshold
                    assert load['minimum_fill_met']==(load['pickups']>=threshold)
                    assert abs(load['fill_percent']-100*load['pickups']/normal)<.051
                    if not load['minimum_fill_met']:underfilled_dumps.append({'route':route['id'],'load':load['load'],'pickups':load['pickups'],'minimum_pickups':threshold})
                if stream=='garbage' and cfg['garbage']['kg_per_pickup']:
                    assert len(rows)*cfg['garbage']['kg_per_pickup']<=cfg['garbage']['payload_tonnes']*1000
            events=route['events'];event_seconds=Counter()
            for event in events:event_seconds[event['type']]+=event['seconds']
            assert set(event_seconds)<={'pretrip','fueling','collection_drive','pickup','collection_allowance',
                'dispatch','receiver_return','to_receiver','receiver_wait','unload','break','unpaid_lunch','yard_return','posttrip'}
            assert event_seconds['receiver_wait']==0  # Current receivers open before dispatch; no padded waits.
            assert abs(sum(event_seconds.values())-route['elapsed_seconds'])<.02
            assert abs(event_seconds['pickup']-len(stops)*cfg['pickup_seconds'])<.001
            assert event_seconds['pretrip']==60*cfg['pretrip_minutes']
            assert event_seconds['break']==60*cfg['break_minutes']
            assert event_seconds['unload']==60*cfg[stream]['receiver']['onsite_minutes']*len(loads)
            assert sum(e['type']=='dispatch' for e in events)==1
            assert sum(e['type']=='yard_return' for e in events)==1
            assert sum(e['type']=='unload' for e in events)==len(loads)
            for leg in route['legs']:
                factor=cfg['active_speed_factor'] if leg['type']=='collection_drive' else cfg['general_speed_factor']
                assert abs(leg['seconds']-(leg['raw_osrm_seconds']/factor+leg['reversals']*cfg['reversal_seconds']))<.0011
            assert abs(sum(l['seconds'] for l in route['legs'])-(route['collection_drive_seconds']+route['deadhead_seconds']))<.02
            for load in loads:
                expected=max(0,load['pickups']*60/cfg['active_collection_pickups_per_minute']-load['base_collection_seconds']) if cfg['use_observed_collection_pace'] else 0
                assert abs(load['collection_allowance_seconds']-expected)<1e-7
            paid=max(route['elapsed_seconds']-60*cfg['unpaid_lunch_minutes'],cfg['minimum_paid_hours']*3600)
            assert abs(route['paid_seconds']-paid)<1e-6
            assert abs(route['overtime_seconds']-max(0,paid-3600*cfg['preferred_paid_hours']))<1e-6
            def clock(value):
                hours,minutes=map(int,value.split(':'));return hours*3600+minutes*60
            actual_return=clock(cfg['crew_start'])+sum(event_seconds.values())
            assert abs(route['late_seconds']-max(0,actual_return-clock(cfg['latest_return'])))<.02
            assert abs(route['early_seconds']-max(0,clock(cfg['earliest_return'])-actual_return))<.02
            if 'preferred_return_shortfall_seconds' in route:
                assert abs(route['preferred_return_shortfall_seconds']-max(0,clock(cfg['preferred_return'])-actual_return))<.02
            if route['late_seconds']>0:time_failures.append({'route':route['id'],'sections':route['sections'],'return':route['return'],'late_minutes':round(route['late_seconds']/60,1)})
            if route.get('early_seconds',0)>0:early_returns.append({'route':route['id'],'return':route['return'],'early_minutes':round(route['early_seconds']/60,1)})
            lines=[transform(projection,shape(f['geometry'])) for f in route['geometry']['features']]
            tree=STRtree(lines)
            for s in stops:
                q=Point(*projection(s['PickupLongitude'],s['PickupLatitude']))
                distance=q.distance(lines[int(tree.nearest(q))])
                checked_points+=1
                limit=8.5 if s.get('AccessBasis')=='connected_site_access' else 36
                if distance>limit:path_outliers.append({'id':s['AddressId'],'route':route['id'],'distance_m':round(distance,2)})
            assert route['legs'][-1]['type']=='yard_return'
            assert route['legs'][-1]['from']==result['sites'][stream]['coordinate']
            assert route['legs'][-1]['to']==result['sites']['yard']['coordinate']
        assert all(len(v)==1 for v in section_owner.values())
        assert all(len(v)==1 for v in pass_owner.values())
        assert all(len(v)==1 for v in coordinate_owner.values())
    exported=list(csv.DictReader((delivery/'Monday_route_pickup_order.csv').open(encoding='utf-8-sig')))
    assert len(exported)==2*len(source)
    assert Counter((r['Stream'],r['AddressId']) for r in exported)==Counter((r['stream'],s['AddressId']) for r in result['routes'] for s in r['stops'])
    source_hash=hashlib.sha256(Path('data/source/Winnipeg - Area 1 addresses.xlsx').read_bytes()).hexdigest()
    assert source_hash=='fbff92cbe50d4a56aa39883a8fafbe0de97ac3a542c47df2f02a8e106c18d5a2'
    originals=json.loads((cache/'source-preservation-street-alley.json').read_text())['coordinate_deliverables_unchanged']
    assert all(hashlib.sha256((delivery/name).read_bytes()).hexdigest()==value for name,value in originals.items())
    class ReviewHTML(HTMLParser):
        def __init__(self):super().__init__();self.data='';self.inside=False;self.external=[];self.csp=''
        def handle_starttag(self,tag,attrs):
            attrs=dict(attrs)
            if tag=='script' and attrs.get('id')=='data':self.inside=True
            if tag in {'script','img','link','iframe'} and (attrs.get('src') or attrs.get('href')):self.external.append(attrs)
            if tag=='meta' and attrs.get('http-equiv')=='Content-Security-Policy':self.csp=attrs['content']
        def handle_endtag(self,tag):
            if tag=='script':self.inside=False
        def handle_data(self,data):
            if self.inside:self.data+=data
    html=ReviewHTML();html.feed((delivery/'Monday_truck_route_maps.html').read_text(encoding='utf-8'))
    assert not html.external and "connect-src 'none'" in html.csp
    mapped=json.loads(html.data)
    assert mapped['key']==result['key'] and mapped['settings']==result['settings']
    assert len(mapped['routes'])==len(result['routes'])
    for shown,route in zip(mapped['routes'],result['routes']):
        assert shown['id']==route['id'] and shown['geometry']==route['geometry']
        assert [(s['AddressId'],s['Load'],s['Sequence'],s['Latitude'],s['Longitude']) for s in shown['stops']]==[(s['AddressId'],s['Load'],s['Sequence'],s['Latitude'],s['Longitude']) for s in route['stops']]
    assert not path_outliers,path_outliers[:8]
    if access_offsets or underfilled_dumps:assert not result['fleet_recommendation_supported']
    receipt={'artifact_checks':'PASS','route_status':result['status'],'fleet_recommendation_supported':result['fleet_recommendation_supported'],
        'key':result['key'],'partition_hash':result['partition_hash'],'source_ids_per_stream':len(source),'exported_service_events':len(exported),
        'route_count':len(result['routes']),'planning_sections_preserved':True,'whole_work_areas':True,'connected_territories':True,'shared_coordinates_single_load':True,
        'road_passes_single_truck':True,'physical_sites_single_load':True,'independent_clock_reconciliation':True,'derived_pickups_near_displayed_road_path':checked_points,
        'standalone_html_complete_and_offline':True,'original_coordinate_deliverables_unchanged':True,
        'minimum_truck_pickups':{s:min(r['pickups'] for r in result['routes'] if r['stream']==s) for s in ['garbage','recycling']},
        'path_outliers':path_outliers,'latest_return_failures':time_failures,'earliest_return_failures':early_returns,'no_artificial_waiting':True,'source_workbook_hash':source_hash,
        'property_access_over_80m_events':len(access_offsets),'source_to_pickup_access_checked':True,
        'underfilled_dumps':underfilled_dumps,'bounded_capacity_tolerance_checked':True,
        'individual_pickup_access_diagnostics_preserved':True,
        'meaning':'Artifact checks do not make time-limit or access failures acceptable.'}
    (cache/'routing-independent-validation.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':verify()
