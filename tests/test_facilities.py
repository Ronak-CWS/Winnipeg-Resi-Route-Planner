from copy import deepcopy
from types import SimpleNamespace
import threading
import pytest
from partition_app.inputs import InputError
from routing_app.settings import settings
from routing_app.facilities import default_options,pairs
from routing_app import engine,api
from routing_app.facility_search import allocate
from routing_app.optimizer import load_plan


def configured():
    cfg=settings({'crew_start':'06:00','pretrip_minutes':0,'break_minutes':0,'minimum_paid_hours':0,
        'earliest_return':'06:01','preferred_return':'06:01','latest_return':'07:00','minimum_dump_fill_percent':0,
        'fleet_search_seconds':1,'local_solver_workers':1,'general_speed_factor':1,'active_speed_factor':1,
        'garbage':{'use_observed_collection_pace':False}})
    options=default_options(cfg)
    for group in ['depots','garbage_receivers']:
        first=options[group][0];first['name']=group+' A'
        second={**deepcopy(first),'id':group+'-2','name':group+' B','lat':first['lat']+.001}
        options[group].append(second)
    options['depot_mode']=options['garbage_mode']='multiple'
    return settings({**cfg,'facility_options':options})


def test_one_or_multiple_facilities_roundtrip_without_changing_legacy_inputs():
    cfg=configured()
    assert len(pairs(cfg,'garbage'))==4 and len(pairs(cfg,'recycling'))==2
    assert settings(cfg)==cfg
    options=deepcopy(cfg['facility_options'])
    options['depot_mode']='single'
    options['depots'][0]['selected']=False
    selected=settings({**cfg,'facility_options':options})
    assert selected['yard']['name']=='depots B' and len(pairs(selected,'garbage'))==2
    legacy=settings({'yard':{'name':'Only yard','address':'Example yard','lat':49.9,'lon':-97.2}})
    assert legacy['yard']['name']=='Only yard' and len(pairs(legacy,'garbage'))==1


@pytest.mark.parametrize('change',[
    lambda o:o.update(depot_mode='single'),
    lambda o:[v.update(selected=False) for v in o['depots']],
    lambda o:o['depots'][1].update(id=o['depots'][0]['id']),
    lambda o:o['garbage_receivers'][1].update(closes='05:00'),
    lambda o:o['depots'][1].update(lat=float('nan')),
    lambda o:o['depots'][1].update(selected='yes'),
])
def test_invalid_facilities_are_rejected_before_routing(change):
    cfg=configured();change(cfg['facility_options'])
    with pytest.raises(InputError):settings(cfg)


def test_whole_fleet_can_use_different_depots_and_receivers_with_real_load_clocks(tmp_path,monkeypatch):
    cfg=configured()
    atoms=[{'id':s,'section':s,'members':[s+'-1'],'count':1} for s in ['X','Y']]
    partition={'areas':{'features':[{'id':s,'properties':{}} for s in ['X','Y']]}}
    class Road:
        def facility(self,site):return {**site,'coordinate':[site['lon'],site['lat']]}
    monkeypatch.setattr(engine,'build_library',lambda p,c,cache,road,g,core,sites,key,progress:
        {'key':sites['yard']['name']+'-'+sites['garbage']['name']})
    monkeypatch.setattr(engine,'expand_library',lambda lib,*args:lib)
    def candidates(p,case,stream,groups,core,lib,road,graph,progress,macro,seeds,return_candidates):
        assert return_candidates
        output=[]
        for section in ['X','Y']:
            depot_a=case['yard']['name'].endswith(' A')
            receiver_a=case[stream]['receiver']['name'].endswith(' A')
            dispatch=60 if depot_a==(section=='X') else 600
            haul=60 if receiver_a==(section=='X') else 600
            plan=load_plan([{'id':section,'count':1}],{section:0},[],{section:dispatch},
                {section:haul},{section:haul},60,case,stream)
            output.append({'sections':[section],'sequence':[section],'plan':plan})
        return output,{'evaluated_orders':2,'physical_site_territories':2}
    monkeypatch.setattr(engine,'allocate',candidates)
    road=Road();sites={'yard':road.facility(cfg['yard']),'garbage':road.facility(cfg['garbage']['receiver']),
        'recycling':road.facility(cfg['recycling']['receiver'])}
    chosen,search=allocate(partition,cfg,'garbage',atoms,{}, {},road,{'X':set(),'Y':set()},lambda *args:None,
        macro=(atoms,{},{}),seeds=[],sites=sites,cache=tmp_path,anchor_key='source',expansion={})
    selected={c['sections'][0]:(c['facility']['depot']['name'],c['facility']['receiver']['name']) for c in chosen}
    assert selected=={'X':('depots A','garbage_receivers A'),'Y':('depots B','garbage_receivers B')}
    # Each day: 60 dispatch + 12.5 pickup + 60 RF + 900 unload + 60 return.
    assert all(c['plan']['seconds']==1092.5 for c in chosen)
    assert search['facility_combinations']==4
    assert sorted(s for c in chosen for s in c['sections'])==['X','Y']


def test_failed_partition_reports_the_real_check_without_starting_a_job(tmp_path):
    failed={'day':'WEDNESDAY','status':'FAILED','findings':[{'severity':'error','message':'Exported polygons overlap by 30.014 m2.'}]}
    handler=SimpleNamespace(reply=lambda body,status=200:(status,body))
    host=SimpleNamespace(LOCK=threading.RLock(),STATE={'active':None,'current':'bad'},CACHE=tmp_path,load_result=lambda key:failed)
    status,body=api.start(handler,host,{'partition_key':'bad'})
    assert status==422 and '30.014' in body['error'] and 'Wednesday' in body['error']
    assert not list(tmp_path.iterdir())
