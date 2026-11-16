"""Process isolation, full-route clocks and global ownership under parallel work."""
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
import os
import time

import numpy as np
import pytest

from routing_app.engine import allocate, build_library
from routing_app.optimizer import fleet_cover
from routing_app.parallel import bounded_map, territory_job, workers, worker_count
from routing_app.settings import settings


def process_probe(value):
    time.sleep(.1)
    return value, os.getpid()


def hand_task(token, capacity=6):
    cfg=settings({'minimum_paid_hours':0,'general_speed_factor':1,'active_speed_factor':1,
        'garbage':{'capacity':capacity,'capacity_low':1,'capacity_high':capacity,
                   'pickup_seconds':10,'use_observed_collection_pace':False}})
    sequence=[{'id':'a','count':3},{'id':'b','count':3}]
    args=(sequence,{'a':10,'b':10},[50],{'a':60,'b':60},{'a':120,'b':120},
          {'a':90,'b':90},60,cfg,'garbage')
    return token,[({'sections':['west','east'],'variants':[0,0],'sequence':['a','b']},args)]


def test_processes_are_local_bounded_and_joined():
    before={p.pid for p in multiprocessing.active_children()}
    with workers(2) as pool:
        result=list(bounded_map(pool,process_probe,range(8)))
    assert [x for x,_ in result]==list(range(8))
    assert len({pid for _,pid in result})==2
    assert all(pid!=os.getpid() for _,pid in result)
    assert {p.pid for p in multiprocessing.active_children()}==before


def test_parallel_hand_calculated_loads_and_one_global_fleet():
    tasks=[hand_task('one'),hand_task('two',4)]
    serial=list(bounded_map(None,territory_job,tasks))
    with workers(2) as pool:parallel=list(bounded_map(pool,territory_job,tasks))
    assert parallel==serial
    single=parallel[0][1][0];double=parallel[1][1][0]
    assert single['plan']['seconds']==3970
    assert double['plan']['seconds']==5030
    assert [l['pickups'] for l in double['plan']['loads']]==[3,3]
    # Workers only evaluate alternatives. One parent cover owns both sections.
    chosen,_=fleet_cover(['west','east'],[single,double],5)
    assert len(chosen)==1 and chosen[0]['sections']==['west','east']


class FakeRoad:
    def __init__(self):self.pid=os.getpid();self.calls=0
    def table(self,sources,destinations):
        assert os.getpid()==self.pid
        self.calls+=1
        matrix=np.full((len(sources),len(destinations)),50.)
        return matrix,matrix.copy()
    def route(self,points):
        assert os.getpid()==self.pid
        self.calls+=1
        return {'seconds':50.,'meters':100.,'reversals':0}


def allocation_fixture(count):
    cfg=settings({'local_solver_workers':count,'minimum_paid_hours':0,
        'general_speed_factor':1,'active_speed_factor':1,'fleet_search_seconds':5,
        'garbage':{'capacity':6,'capacity_low':1,'capacity_high':6,
                   'pickup_seconds':10,'use_observed_collection_pace':False}})
    groups=[{'id':s.lower(),'section':s,'count':3,'start':{'coordinate':[i,0]},
             'end':{'coordinate':[i,.01]}} for i,s in enumerate(['A','B'])]
    core={g['id']:{'seconds':10.,'meters':20.,'reversals':0} for g in groups}
    library={'sections':{},'dispatch':{'a':60,'b':60},'to_rf':{},'from_rf':{},'return':{}}
    for stream in ['garbage','recycling']:
        library['to_rf'][stream]={'a':120,'b':120};library['from_rf'][stream]={'a':90,'b':90}
        library['return'][stream]=60
    for g in groups:
        variant={'groups':[g['id']],'joins':[],'internal_seconds':10.,'start':g['start'],'end':g['end']}
        library['sections'][g['section']]={s:[variant] for s in ['garbage','recycling']}
    return cfg,groups,core,library


@pytest.mark.parametrize('macro',[False,True])
def test_full_allocation_matches_serial_and_keeps_road_access_in_parent(macro):
    answers=[]
    for count in [1,2]:
        cfg,groups,core,library=allocation_fixture(count);road=FakeRoad()
        # The web application runs its coordinator in a background thread.
        with ThreadPoolExecutor(max_workers=1) as coordinator:
            partition={'areas':{'features':[{'id':s,'properties':{}} for s in ['A','B']]}}
            chosen,_=coordinator.submit(allocate,partition,cfg,'garbage',groups,core,library,road,
                {'A':{'B'},'B':{'A'}},lambda *a:None,
                macro=(groups,core,library) if macro else None).result(timeout=20)
        assert road.calls>0
        assert len(chosen)==1 and set(chosen[0]['sections'])=={'A','B'}
        answers.append(chosen)
    assert answers[0]==answers[1]


def test_whole_section_variants_keep_all_passes_and_parent_cache(tmp_path):
    cfg,groups,core,_=allocation_fixture(2);cfg['search_seconds_per_section']=2
    for g in groups:g['section']='whole'
    road=FakeRoad();sites={s:{'coordinate':[0,0]} for s in ['yard','garbage','recycling']}
    result=build_library({},cfg,tmp_path,road,groups,core,sites,'fixture',lambda *a:None)
    for stream in ['garbage','recycling']:
        assert result['sections']['whole'][stream]
        assert all(sorted(v['groups'])==['a','b'] for v in result['sections']['whole'][stream])
    assert road.calls>0


def test_cancelled_section_phase_reuses_completed_section_work(tmp_path):
    cfg,groups,core,_=allocation_fixture(1)
    sites={s:{'coordinate':[0,0]} for s in ['yard','garbage','recycling']}
    def interrupt(percent,message):
        if message.startswith('Sequencing complete section 2/2 ('):
            raise InterruptedError('cancel before the second section')
    with pytest.raises(InterruptedError):
        build_library({},cfg,tmp_path,FakeRoad(),groups,core,sites,'resumable',interrupt)
    road=FakeRoad()
    result=build_library({},cfg,tmp_path,road,groups,core,sites,'resumable',lambda *a:None)
    assert set(result['sections'])=={'A','B'}
    # Two gateway matrices, two receiver returns and only B's section matrix.
    assert road.calls==5


def test_cancelled_pool_has_no_leftover_workers():
    before={p.pid for p in multiprocessing.active_children()};calls=0
    def cancel():
        nonlocal calls
        calls+=1
        if calls>=2:raise InterruptedError('test cancellation')
    with pytest.raises(InterruptedError):
        with workers(2) as pool:list(bounded_map(pool,process_probe,range(20),cancel))
    assert {p.pid for p in multiprocessing.active_children()}==before


@pytest.mark.parametrize('value',[0,5,1.5,True])
def test_worker_limit_rejects_unbounded_or_invalid_values(value):
    with pytest.raises(ValueError):settings({'local_solver_workers':value})


def test_worker_count_respects_local_cpu_limit(monkeypatch):
    monkeypatch.setattr(os,'cpu_count',lambda:2)
    assert worker_count(4)==1


def test_reported_fleet_benchmark_does_not_constrain_or_change_assignment():
    cfg,groups,core,library=allocation_fixture(1)
    partition={'areas':{'features':[{'id':s,'properties':{}} for s in ['A','B']]}}
    graph={'A':{'B'},'B':{'A'}};results=[]
    for benchmark in [1,99]:
        cfg['garbage_trucks_comparison']=benchmark;cfg['recycling_trucks_comparison']=benchmark
        chosen,_=allocate(partition,cfg,'garbage',groups,core,library,FakeRoad(),graph,lambda *a:None)
        results.append(chosen)
    assert results[0]==results[1] and len(results[0])==1
