from types import SimpleNamespace
import numpy as np
import pytest
from shapely.geometry import box,mapping
from partition_app.inputs import InputError
from routing_app import engine,api,facility_search
from routing_app.settings import settings
from routing_app.optimizer import load_plan


@pytest.mark.parametrize('streams',[[],['organics'],['garbage','garbage'],'garbage',None])
def test_invalid_or_empty_stream_selection_is_rejected(streams):
    with pytest.raises(InputError):settings({'streams':streams})


@pytest.mark.parametrize('selected',[['garbage'],['recycling'],['garbage','recycling']])
def test_only_selected_streams_are_sequenced_allocated_replayed_and_exported(tmp_path,monkeypatch,selected):
    cfg=settings({'streams':selected,'crew_start':'06:00','pretrip_minutes':0,'break_minutes':0,
        'minimum_paid_hours':0,'earliest_return':'06:01','preferred_return':'06:01','latest_return':'07:00',
        'minimum_dump_fill_percent':0,'local_solver_workers':1,'search_seconds_per_section':1,
        'general_speed_factor':1,'active_speed_factor':1})
    anchor={'id':'one','address':'1 Test Road','coordinate':[-97.15,49.9],
        'original':[-97.15,49.9],'bearing':0,'review':[],'road_name':'Test Road'}
    group={'id':'pass','section':'A','members':['one'],'count':1,'start':anchor,'end':anchor,'road_name':'Test Road'}
    snapped=[];sequenced=[];allocated=[]
    class Road:
        requests=0;hits=0
        def facility(self,site):
            snapped.append(site['name']);return {**site,'coordinate':[site['lon'],site['lat']]}
        def route(self,points):
            return {'seconds':60 if len(points)>1 else 0,'meters':100 if len(points)>1 else 0,
                'geometry':[p['coordinate'] for p in points],'reversals':0,'legs':[]}
        def table(self,a,b):return np.full((len(a),len(b)),60.),None
        def close(self):self.closed=True
    road=Road()
    monkeypatch.setattr(engine,'inventory',lambda *a:{'source_hash':'fixture'})
    monkeypatch.setattr(engine,'make_groups',lambda *a:([group],{'one':anchor},[]))
    monkeypatch.setattr(engine,'OSRM',lambda *a:road)
    def orders(pool,operation,jobs,checkpoint):
        sequenced.extend(jobs);return [[0] for _ in jobs]
    monkeypatch.setattr(engine,'bounded_map',orders)
    def allocate(partition,cfg,stream,atoms,core,library,road,graph,progress,**kwargs):
        allocated.append(stream)
        plan=load_plan(atoms,{a['id']:0 for a in atoms},[],library['dispatch'],library['from_rf'][stream],
            library['to_rf'][stream],library['return'][stream],cfg,stream)
        return [{'sections':['A'],'sequence':[a['id'] for a in atoms],'plan':plan}],{}
    monkeypatch.setattr(facility_search,'allocate',allocate)
    partition={'key':'fixture','partition_hash':'fixture','day':'WEDNESDAY','status':'PROVISIONAL',
        'points':[{'id':'one'}],'areas':{'type':'FeatureCollection','features':[
            {'type':'Feature','id':'A','properties':{'id':'A'},'geometry':mapping(box(-97.16,49.89,-97.14,49.91))}]}}
    result=engine.run(partition,cfg,tmp_path);result['key']='test'
    assert set(result['streams'])==set(selected)==set(result['validation'])
    assert allocated==selected and len(sequenced)==2*len(selected)
    assert snapped==[cfg['yard']['name'],*[cfg[s]['receiver']['name'] for s in selected]]
    assert {r['stream'] for r in result['routes']}==set(selected)
    assert all(v['exactly_once'] and v['final_unload'] for v in result['validation'].values())
    assert road.closed and result['total_trucks']==len(selected)
    monkeypatch.setattr(api,'truck_map',lambda result:b'offline fixture')
    exported=api.export_files(result)['Wednesday_route_schedules.csv'].decode('utf-8-sig')
    for stream in ['garbage','recycling']:assert (stream in exported)==(stream in selected)
    assert api.key_for(partition,cfg)!=api.key_for(partition,settings({'streams':['recycling'] if selected==['garbage'] else ['garbage']}))
