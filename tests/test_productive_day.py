import pytest
from routing_app.settings import settings,clock_seconds
from routing_app.optimizer import consolidation_candidates,section_orders,fleet_cover,load_plan
from routing_app.optimizer import pocket_affinity_regret,connected_sets
from routing_app.saved import retain_section_variants


def test_productive_window_and_legacy_scenarios():
    cfg=settings()
    assert (cfg['earliest_return'],cfg['preferred_return'],cfg['latest_return'])==('14:30','15:30','16:45')
    assert clock_seconds(cfg['latest_return'])-clock_seconds(cfg['crew_start'])==10.5*3600
    old=settings({'earliest_return':'15:00','latest_return':'16:00'})
    assert old['preferred_return']=='15:00'
    with pytest.raises(ValueError):settings({'preferred_return':'17:00'})


def test_all_section_entries_get_order_candidates():
    graph={s:set('abcdef')-{s} for s in 'abcdef'}
    costs={(a,b):1 for a in graph for b in graph if a!=b}
    orders=section_orders(graph,graph,costs)
    assert {o[0] for o in orders}==set(graph)
    assert len(orders)<=4*len(graph)


def test_short_truck_can_be_removed_into_two_neighbours_without_splitting_areas():
    graph={'a':{'x'},'x':{'a','y'},'y':{'x','b'},'b':{'y'}}
    counts={'a':700,'b':700,'x':200,'y':200}
    chosen=[{'sections':list(s),'plan':{'seconds':n}} for s,n in [(['a'],700),(['b'],700),(['x','y'],400)]]
    out=consolidation_candidates(chosen,graph,dict(zip(graph,graph)),counts,1000,
        lambda g:sum(counts[s] for s in g),1000)
    assert frozenset({'a','x'}) in out and frozenset({'b','y'}) in out
    assert not any({'a','b'}<=g for g in out)


def test_preferred_return_cannot_purchase_an_extra_truck_or_reward_extra_driving():
    def c(ids,seconds,preferred):return {'sections':ids,'plan':{'seconds':seconds,'paid_seconds':seconds,
        'early_seconds':0,'late_seconds':0,'overtime_seconds':max(0,seconds-28800),
        'preferred_return_shortfall_seconds':preferred}}
    candidates=[c(['a'],33000,0),c(['b'],33000,0),c(['a','b'],37000,0),c(['a','b'],35000,1000)]
    result,_=fleet_cover(['a','b'],candidates,4)
    assert len(result)==1 and result[0]['plan']['seconds']==35000


def test_preferred_return_is_not_added_to_actual_day():
    cfg=settings({'minimum_paid_hours':0,'general_speed_factor':1,'active_speed_factor':1})
    costs={'p':100}
    before=load_plan([{'id':'p','count':100}],{'p':0},[],costs,costs,costs,100,cfg,'recycling')
    cfg['preferred_return']='16:30'
    after=load_plan([{'id':'p','count':100}],{'p':0},[],costs,costs,costs,100,cfg,'recycling')
    assert before['seconds']==after['seconds']==4750
    assert after['preferred_return_shortfall_seconds']-before['preferred_return_shortfall_seconds']==3600


def test_small_pocket_prefers_nearest_real_road_neighbour_without_changing_clock():
    graph={'p':{'near','far'},'near':{'p'},'far':{'p'}}
    costs={('p','near'):60,('near','p'):80,('p','far'):600,('far','p'):700}
    counts={'p':8,'near':500,'far':1000}
    assert pocket_affinity_regret({'p','near'},graph,counts,costs)==0
    assert pocket_affinity_regret({'p','far'},graph,counts,costs)==540


def test_receiver_travel_ranks_crowded_beam_without_becoming_a_feasibility_veto():
    graph={s:set('abcd')-{s} for s in 'abcd'};counts={s:1 for s in graph}
    useful={frozenset('ac'),frozenset('bd')}
    estimate=lambda g:90 if g in {frozenset('ab'),frozenset('cd')} else 80
    ranking=lambda g:98 if g in useful else 130
    old=connected_sets(graph,graph,counts,4,max_sections=2,layer_limit=2,estimate=estimate,time_limit=100)
    revised=connected_sets(graph,graph,counts,4,max_sections=2,layer_limit=2,
        estimate=estimate,time_limit=100,rank_estimate=ranking)
    assert not useful<=set(old) and useful<=set(revised)
    complete=connected_sets(graph,graph,counts,4,max_sections=2,layer_limit=99,
        estimate=estimate,time_limit=100,rank_estimate=lambda g:10000)
    assert len([g for g in complete if len(g)==2])==6
    assert all(frozenset([s]) in revised for s in graph)


def test_longer_section_search_retains_compatible_earlier_complete_orders():
    new={s:[{'groups':['b','a','c']}] for s in ['garbage','recycling']}
    old={s:[{'groups':['a','b','c']},{'groups':['a','c']}] for s in new}
    merged=retain_section_variants(new,old,['a','b','c'])
    for stream in new:
        assert [v['groups'] for v in merged[stream]]==[['b','a','c'],['a','b','c']]
    assert retain_section_variants(new,new,['a','b','c'])==new
