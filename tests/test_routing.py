"""Independent small operational examples, not production helper round trips."""
from copy import deepcopy
import json
import math
from pathlib import Path
import numpy as np
import pytest

from routing_app.settings import settings, clock_seconds
from routing_app.optimizer import load_plan, fleet_cover, solve_section, connected_sets,section_orders
from routing_app.roads import make_groups, address_street
from routing_app.api import csv_bytes


def fixture(capacity):
    cfg=settings({'minimum_paid_hours':0,'general_speed_factor':1,'active_speed_factor':1,'pickup_seconds':10,
        'use_observed_collection_pace':False,
        'garbage':{'capacity':capacity,'capacity_low':1,'capacity_high':capacity}})
    groups=[{'id':'a','count':3},{'id':'b','count':3}]
    return cfg,groups


def compute(capacity,join=50):
    cfg,g=fixture(capacity)
    return load_plan(g,{'a':10,'b':10},[join],{'a':60,'b':60},{'a':120,'b':120},
                     {'a':90,'b':90},60,cfg,'garbage')


def test_full_day_two_load_hand_calculation():
    # 900 pretrip + 60 dispatch + 80 collecting + 240 to RF + 90 from RF
    # + 1800 unloading + 60 return + 1800 breaks = 5030 seconds.
    result=compute(4)
    assert result['seconds']==5030
    assert result['paid_seconds']==5030
    assert [l['pickups'] for l in result['loads']]==[3,3]


def test_two_loads_is_not_a_fixed_rule_and_real_dump_cost_matters():
    result=compute(6)
    assert len(result['loads'])==1
    assert result['seconds']==3970  # one 50-second collection connector, one dump
    assert len(compute(6,5000)['loads'])==2  # receiver visit replaces a huge connector


def test_observed_pace_is_a_floor_not_an_additional_service_time():
    cfg,g=fixture(6);cfg['garbage']['use_observed_collection_pace']=True
    cfg['garbage']['active_collection_pickups_per_minute']=1
    result=load_plan(g,{'a':10,'b':10},[50],{'a':60,'b':60},{'a':120,'b':120},{'a':90,'b':90},60,cfg,'garbage')
    # Original collection 130 seconds becomes 6*60=360, NOT 490 seconds.
    assert result['seconds']==3970+230
    json.dumps(result,allow_nan=False)


def test_capacity_cannot_split_a_physical_run():
    cfg,g=fixture(2)
    assert load_plan(g,{'a':10,'b':10},[5],{'a':1,'b':1},{'a':1,'b':1},{'a':1,'b':1},1,cfg,'garbage') is None


def test_nine_tonnes_is_separate_from_pickup_capacity():
    cfg,g=fixture(6);cfg['garbage']['kg_per_pickup']=2000
    result=load_plan(g,{'a':10,'b':10},[5],{'a':1,'b':1},{'a':1,'b':1},{'a':1,'b':1},1,cfg,'garbage')
    assert result['capacity']==4
    assert len(result['loads'])==2


def test_recycling_preferred_capacity_is_not_the_hard_maximum():
    cfg=settings({'general_speed_factor':1,'active_speed_factor':1})
    g=[{'id':'site','count':1340}];cost={'site':100}
    result=load_plan(g,{'site':0},[],cost,cost,cost,100,cfg,'recycling')
    assert result['capacity']==1377 and result['normal_capacity']==1350 and len(result['loads'])==1
    assert result['loads'][0]['pickups']==1340
    assert load_plan([{'id':'site','count':1378}],{'site':0},[],cost,cost,cost,100,cfg,'recycling') is None


def test_load_fill_score_does_not_pad_time_and_final_partial_load_is_allowed():
    cfg=settings({'general_speed_factor':1,'active_speed_factor':1,'minimum_paid_hours':0})
    sites=[{'id':str(i),'count':1} for i in range(1500)]
    zero={g['id']:0 for g in sites};cost={g['id']:100 for g in sites}
    plan=load_plan(sites,zero,[1]*1499,cost,cost,cost,100,cfg,'recycling')
    assert [l['pickups'] for l in plan['loads']]==[810,690]
    assert plan['dump_fill_shortfall']==120 and plan['underfilled_dump_count']==1
    # 1500*8.5 service +1498 collection legs +5000 real fixed/travel seconds.
    assert plan['seconds']==19248
    assert plan['early_seconds']>0  # Never insert waiting to make this reach 15:00.


def test_small_recycling_tolerance_avoids_a_second_trip_for_nine_pickups():
    cfg=settings({'general_speed_factor':1,'active_speed_factor':1,'minimum_paid_hours':0})
    groups=[{'id':'first','count':1342},{'id':'remaining','count':9}]
    zero={g['id']:0 for g in groups};travel={g['id']:100 for g in groups}
    plan=load_plan(groups,zero,[10],travel,travel,travel,100,cfg,'recycling')
    assert [l['pickups'] for l in plan['loads']]==[1351]
    # 900 pretrip + 100 dispatch + 10 joining + 1351*8.5 service
    # + 100 to receiver + 900 unload + 1800 breaks + 100 return.
    assert plan['seconds']==15393.5
    assert plan['load_preference_penalty']==30  # scoring only; not driver time
    cfg['recycling']['capacity_tolerance_percent']=0
    assert len(load_plan(groups,zero,[10],travel,travel,travel,100,cfg,'recycling')['loads'])==2


def test_small_final_unload_is_counted_as_underfilled_and_never_skipped():
    cfg=settings({'general_speed_factor':1,'active_speed_factor':1,'minimum_paid_hours':0})
    sites=[{'id':'site','count':100}];cost={'site':100}
    plan=load_plan(sites,{'site':0},[],cost,cost,cost,100,cfg,'recycling')
    assert plan['minimum_fill_pickups']==810
    assert plan['dump_fill_shortfall']==710 and plan['underfilled_dump_count']==1
    assert len(plan['loads'])==1 and plan['loads'][0]['unload_seconds']==900
    assert plan['seconds']==4750  # Includes the real required final unload.


def test_near_yard_section_then_near_receiver_uses_spare_load_capacity():
    cfg=settings({'general_speed_factor':1,'active_speed_factor':1,'pickup_seconds':10,
                  'use_observed_collection_pace':False,'minimum_paid_hours':0})
    a=[{'id':'a'+str(i),'count':30} for i in range(11)]
    b=[{'id':'b'+str(i),'count':30} for i in range(30)]
    zero={g['id']:0 for g in a+b}
    dispatch={g['id']:100 if g['id'][0]=='a' else 900 for g in a+b}
    receiver={g['id']:900 if g['id'][0]=='a' else 100 for g in a+b}
    forward=load_plan(a+b,zero,[1]*40,dispatch,receiver,receiver,100,cfg,'garbage')
    backward=load_plan(b+a,zero,[1]*40,dispatch,receiver,receiver,100,cfg,'garbage')
    assert len(forward['loads'])==2 and forward['loads'][0]['end']>len(a)
    assert forward['loads'][1]['end']==len(a+b)
    assert forward['seconds']<backward['seconds']


def test_receiver_break_can_interrupt_a_pass_without_splitting_its_truck_owner():
    # Two 599-address road passes require TWO 600-capacity loads. Requiring a
    # pass boundary for unloading would be an unrelated ownership restriction.
    cfg=settings({'use_observed_collection_pace':False,'garbage':{'capacity':600,'capacity_high':600}})
    sites=[{'id':str(i),'count':1} for i in range(1198)]
    zero={g['id']:0 for g in sites};gateway={g['id']:600 for g in sites}
    result=load_plan(sites,zero,[1]*1197,gateway,gateway,gateway,600,cfg,'garbage')
    assert len(result['loads'])==2
    assert sum(l['pickups'] for l in result['loads'])==1198
    assert all(l['pickups']<=600 for l in result['loads'])


def test_expansion_keeps_colocated_ids_and_road_replay_edges():
    from routing_app.load_sites import expand_passes,endpoint_key
    anchors={k:{'coordinate':[x,1],'bearing':90,'id':k} for k,x in [('a',0),('unit',0),('b',1)]}
    group={'id':'pass','section':'area','members':['a','unit','b'],'count':3}
    leg={'seconds':7,'meters':20,'reversals':0,'geometry':[[0,1],[1,1]]}
    atoms,core,edges,expansion=expand_passes([group],anchors,{'pass':{'legs':[leg]}},settings())
    assert [g['members'] for g in atoms]==[['a','unit'],['b']]
    assert edges[endpoint_key(anchors['a']),endpoint_key(anchors['b'])]['geometry']==leg['geometry']
    assert sum(g['count'] for g in atoms)==3


def test_work_split_requires_mapped_boundary_and_never_cuts_a_pass():
    from types import SimpleNamespace
    from shapely.geometry import box,LineString,mapping,Point
    from shapely.strtree import STRtree
    from partition_app.geography import unproject
    from routing_app.work_areas import best_split
    parent=box(600000,5500000,600400,5500400)
    line=LineString([(600200,5499990),(600200,5500410)])
    feature={'id':'Example','geometry':mapping(unproject(parent)),'properties':{}}
    anchors={};groups=[]
    for side,x in [('west',600100),('east',600300)]:
        members=[]
        for i in range(120):
            ident=side+str(i);point=unproject(Point(x,5500020+i*3))
            anchors[ident]={'original':[point.x,point.y]};members.append(ident)
        groups.append({'members':members})
    geo=SimpleNamespace(roads=[],base_roads=[],parcels=[],parcel_tree=STRtree([]),nearby_features=lambda *a:[])
    assert best_split(feature,groups,anchors,geo)[0] is None
    geo.base_roads=[{'id':'mapped','name':'Example Road','type':'ROAD','geometry':line}]
    assert best_split(feature,groups,anchors,geo)[0] is not None
    assert best_split(feature,[{'members':list(anchors)}],anchors,geo)[0] is None
    geo.parcels=[{'id':'occupied','geometry':box(600080,5500005,600320,5500395)}]
    geo.parcel_tree=STRtree([geo.parcels[0]['geometry']])
    assert best_split(feature,groups,anchors,geo)[0] is None
    geo.parcels=[];geo.parcel_tree=STRtree([])
    for ident,anchor in anchors.items():
        point=unproject(Point(600180 if ident.startswith('west') else 600220,
                              5500020+int(ident.removeprefix('west').removeprefix('east'))*3))
        anchor['original']=[point.x,point.y]
    geo.nearby_features=lambda shape,categories:[{'id':'alley','category':'alley','geometry':line}] if 'alley' in categories else []
    assert best_split(feature,groups,anchors,geo)[0] is None


def test_source_ids_on_opposite_curbs_get_opposite_directions():
    inventory={'roads':[{'id':'road','coords':[[-97.2,49.85],[-97.19,49.85]],'tags':{'highway':'residential'},'name':'Example Street'}]}
    points=[{'id':'north','section':'S','address':'1 Example St','lat':49.85015,'lon':-97.196},
            {'id':'south','section':'S','address':'2 Example St','lat':49.84985,'lon':-97.196},
            {'id':'unit','section':'S','address':'2 Example St Unit 1','lat':49.84985,'lon':-97.196}]
    groups,anchors,reviews=make_groups({'points':points},inventory)
    assert len(groups)==2 and sum(g['count'] for g in groups)==3
    assert abs(anchors['south']['bearing']-90)<3
    assert abs(anchors['north']['bearing']-270)<3
    assert anchors['unit']['coordinate']==anchors['south']['coordinate']
    assert not reviews


def test_generic_unit_and_punctuation_street_normalization():
    assert address_street("10 Queen's Road Unit 3")=='queens rd'
    assert address_street('44 Example Point')=='example pt'


def test_one_complete_directed_sequence_uses_all_runs():
    matrix=np.array([[0,1,100],[100,0,1],[100,100,0]],dtype=float)
    assert solve_section(matrix,[0,100,100],[100,100,0],1)==[0,1,2]


def test_connected_territories_do_not_jump_over_missing_neighbours():
    graph={'A':{'B'},'B':{'A'},'C':set()}
    sets=connected_sets(list(graph),graph,dict.fromkeys(graph,100),500)
    assert frozenset({'A','B'}) in sets
    assert not any('C' in s and len(s)>1 for s in sets)


def test_connected_territory_can_transit_a_served_piece_without_collecting_it_again():
    # Three leaves around one central piece have no Hamiltonian adjacency
    # path. They can still form one coherent truck territory.
    graph={'centre':{'a','b','c'},'a':{'centre'},'b':{'centre'},'c':{'centre'}}
    costs={(a,b):1 for a in graph for b in graph if a!=b}
    orders=section_orders(set(graph),graph,costs)
    assert orders and all(sorted(o)==sorted(graph) for o in orders)
    disconnected={**graph,'isolated':set()}
    assert not section_orders(set(disconnected),disconnected,costs)


def test_time_beam_keeps_a_feasible_combination_and_prior_territory():
    graph={s:set('abcd')-{s} for s in 'abcd'}
    counts=dict(a=100,b=100,c=900,d=900)
    seconds=dict(a=100,b=100,c=1000,d=1000)
    estimate=lambda group:sum(seconds[s] for s in group)
    groups=connected_sets(list(graph),graph,counts,3000,layer_limit=1,
        estimate=estimate,time_limit=1100,seeds=[{'b','d'}])
    assert frozenset({'b','d'}) in groups
    assert not any({'c','d'}<=g for g in groups)
    assert any(len(g)==2 for g in groups)


def test_fleet_reduces_trucks_and_total_work_instead_of_buying_a_truck_to_avoid_overtime():
    def c(sections,seconds,ot):
        return {'sections':sections,'plan':{'late_seconds':0,'overtime_seconds':ot,'seconds':seconds}}
    candidates=[c(['A'],20000,0),c(['B'],20000,0),c(['A','B'],30000,1200)]
    chosen,_=fleet_cover(['A','B'],candidates,4)
    assert len(chosen)==1
    fewer,_=fleet_cover(['A','B'],candidates,4,overtime_first=True)
    assert len(fewer)==2


@pytest.mark.parametrize('payload',[{'pickup_seconds':float('nan')},{'break_minutes':-1},
    {'crew_start':'25:00'},{'latest_return':'05:00'},{'garbage':{'capacity':700}},
    {'collection_side':'left'},{'unknown':True},{'yard':{'lat':0}}])
def test_bad_operating_settings_are_rejected(payload):
    with pytest.raises(ValueError):settings(payload)


def test_defaults_respect_latest_user_answers():
    cfg=settings()
    assert cfg['break_minutes']==30
    assert cfg['garbage']['capacity_high']==650
    assert cfg['recycling']['capacity_high']==1350
    assert cfg['recycling']['pickup_seconds']==8.5
    assert not cfg['recycling']['use_observed_collection_pace']
    assert cfg['unpaid_lunch_minutes']==cfg['posttrip_minutes']==cfg['fueling_minutes']==0
    assert clock_seconds(cfg['crew_start'])+cfg['pretrip_minutes']*60==clock_seconds('06:30')
    assert clock_seconds(cfg['crew_start'])+cfg['preferred_paid_hours']*3600==clock_seconds('14:15')
    assert cfg['garbage']['receiver']['name']=='Brady Landfill'
    assert 'Canada Fibers' in cfg['recycling']['receiver']['name']
    assert cfg['final_unload_required'] and cfg['preserve_planning_sections']
    assert cfg['allow_shared_overlong_sections']


def test_csv_does_not_execute_address_formula():
    out=csv_bytes([{'AddressId':'7','Address':'=HYPERLINK("bad")'}]).decode('utf-8-sig')
    assert "'=HYPERLINK" in out

def test_connected_search_keeps_deep_chains_and_each_geographic_seed():
    ids=[str(i) for i in range(12)]
    graph={s:{t for t in ids if t!=s} for s in ids}
    groups=connected_sets(ids,graph,dict.fromkeys(ids,10),100,layer_limit=36)
    assert max(map(len,groups))==10
    assert all(any(s in g and len(g)==8 for g in groups) for s in ids)
    assert len(groups)<=12+9*36


def test_two_finite_streets_can_form_clean_composite_boundary():
    from types import SimpleNamespace
    from shapely.geometry import box,LineString,mapping,Point
    from shapely.strtree import STRtree
    from partition_app.geography import unproject
    from routing_app.work_areas import best_split
    parent=box(600000,5500000,600400,5500400)
    roads=[{'id':'a','name':'First','type':'ROAD','geometry':LineString([(599990,5500200),(600200,5500200)])},
           {'id':'b','name':'Second','type':'ROAD','geometry':LineString([(600200,5500200),(600200,5500410)])}]
    geo=SimpleNamespace(roads=[],base_roads=roads,parcels=[],parcel_tree=STRtree([]),nearby_features=lambda *a:[])
    anchors={};groups=[]
    for side,(x,y) in enumerate([(600100,5500300),(600300,5500100)]):
        members=[]
        for i in range(110):
            ident=f'{side}-{i}';p=unproject(Point(x+i*.1,y))
            anchors[ident]={'original':[p.x,p.y]};members.append(ident)
        groups.append({'members':members})
    feature={'id':'Example','geometry':mapping(unproject(parent)),'properties':{}}
    best,_=best_split(feature,groups,anchors,geo)
    assert best and best['boundary']['kind']=='connected_city_streets'
    assert sorted(best['sizes'].values())==[110,110]
    assert best['parts'][0].union(best['parts'][1]).symmetric_difference(parent).area<.1
