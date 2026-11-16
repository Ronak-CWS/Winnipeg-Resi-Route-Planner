"""Compare local CPU workers on saved Monday data, with HTTP disabled."""
import hashlib
import argparse
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from routing_app.engine import digest,measured_seconds
from routing_app.load_sites import expand_passes,expand_library,endpoint_key
from routing_app.osrm import OSRM
from routing_app.parallel import workers,bounded_map,territory_job,section_job,worker_count
from routing_app.roads import inventory
from routing_app.settings import settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repeats',type=int,default=2)
    arguments=parser.parse_args()
    if not 1<=arguments.repeats<=30:raise ValueError('Use 1-30 bounded repetitions.')
    audit=ROOT/'outputs/2026-11-04_monday_map/audit/partition_app'
    key=json.loads((audit/'current-routing.json').read_text())['key']
    result_path=audit/f'routing-{key}.result.json'
    original_hash=hashlib.sha256(result_path.read_bytes()).hexdigest()
    result=json.loads(result_path.read_text(encoding='utf-8'));cfg=settings(result['settings'])
    saved=json.loads((audit/f"routing-{result['anchor_cache_key']}.anchors.json").read_text(encoding='utf-8'))
    anchors=saved['anchors'];groups=saved['groups']
    if result['selected_iteration']:
        wanted={f['id'] for f in result['work_areas']['features']}
        for path in sorted(audit.glob('*.work-areas.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            candidate=json.loads(path.read_text(encoding='utf-8'))
            if {f['id'] for f in candidate['partition']['areas']['features']}==wanted:
                groups=candidate['groups'];break
        else:raise ValueError('The saved work-area input is required for this benchmark.')
    roads=inventory(audit,lambda *a:None)
    road=OSRM(audit,'directed-v1:'+roads['source_hash'])
    def no_network(*args,**kwargs):raise AssertionError('Benchmark road request was not cached; no HTTP allowed.')
    road.session.get=no_network
    try:
        core={g['id']:road.route([anchors[x] for x in g['members']]) for g in groups}
        owner_key=digest([result['anchor_cache_key'],[(g['id'],g['section']) for g in groups]]) if result['selected_iteration'] else result['anchor_cache_key']
        library_key=digest(['library-1',owner_key,cfg['search_seconds_per_section'],cfg['active_speed_factor'],
            cfg['general_speed_factor'],cfg['reversal_seconds'],result['sites']])
        library=json.loads((audit/f'routing-{library_key}.library.json').read_text())
        atoms,atom_core,edges,expansion=expand_passes(groups,anchors,core,cfg)
        fine=expand_library(library,atoms,expansion,road,result['sites'],audit,lambda *a:None)
        unit={g['id']:g for g in atoms};owner={x:g['id'] for g in atoms for x in g['members']}
        tasks=[];originals={}
        for route in result['routes']:
            if route['stream']!='recycling':continue
            ids=list(dict.fromkeys(owner[s['AddressId']] for s in route['stops']))
            sequence=[unit[g] for g in ids];joins=[]
            for a,b in zip(sequence,sequence[1:]):
                path=edges.get((endpoint_key(a['end']),endpoint_key(b['start'])))
                if path is None:path=road.route([a['end'],b['start']])
                joins.append(measured_seconds(path,cfg))
            args=([{'id':g['id'],'count':g['count']} for g in sequence],{g:0. for g in ids},joins,
                {g:fine['dispatch'][g] for g in ids},{g:fine['to_rf']['recycling'][g] for g in ids},
                {g:fine['from_rf']['recycling'][g] for g in ids},fine['return']['recycling'],cfg,'recycling')
            metadata={'sections':route['sections'],'sequence':ids,'variants':[]}
            tasks.append((route['id'],[(metadata,args)]));originals[route['id']]=route
        # Repeat the same complete alternatives to amortize process startup;
        # every timed run still includes worker startup and shutdown.
        tasks=tasks*arguments.repeats
        begin=perf_counter();serial=list(bounded_map(None,territory_job,tasks));serial_seconds=perf_counter()-begin
        begin=perf_counter()
        with workers(2) as pool:parallel=list(bounded_map(pool,territory_job,tasks))
        parallel_seconds=perf_counter()-begin
        assert serial==parallel
        for ident,candidates in serial:
            plan=candidates[0]['plan'];route=originals[ident]
            assert abs(plan['seconds']-route['estimated_seconds_before_replay'])<1e-6
            assert [l['pickups'] for l in plan['loads']]==[l['pickups'] for l in route['loads']]
        # One real complete section, four depot/receiver alternatives; no
        # independent route chunks or synthetic restart at the depot.
        from collections import defaultdict
        by_area=defaultdict(list)
        for g in groups:by_area[g['section']].append(g)
        section,units=max(by_area.items(),key=lambda row:len(row[1]))
        matrix,_=road.table([g['end'] for g in units],[g['start'] for g in units])
        section_tasks=[]
        for stream in ['garbage','recycling']:
            for origin in ['yard',stream]:
                incoming=library['dispatch'] if origin=='yard' else library['from_rf'][stream]
                section_tasks.append((matrix,[incoming[g['id']] for g in units],
                    [library['to_rf'][stream][g['id']] for g in units],max(1,cfg['search_seconds_per_section']//2)))
        begin=perf_counter();serial_orders=list(bounded_map(None,section_job,section_tasks));section_serial=perf_counter()-begin
        begin=perf_counter()
        with workers(2) as pool:parallel_orders=list(bounded_map(pool,section_job,section_tasks))
        section_parallel=perf_counter()-begin
        assert all(sorted(order)==list(range(len(units))) for order in serial_orders+parallel_orders)
        def costs(orders):
            return [round(task[1][order[0]]+task[2][order[-1]]+sum(matrix[a,b] for a,b in zip(order,order[1:])),3)
                    for order,task in zip(orders,section_tasks)]
        assert road.requests==0
        assert hashlib.sha256(result_path.read_bytes()).hexdigest()==original_hash
        report={'key':key,'worker_limit':worker_count(2),'network_requests':0,'published_result_unchanged':True,
            'load_evaluation':{'complete_route_alternatives':len(tasks),'serial_seconds':round(serial_seconds,3),
                'parallel_seconds':round(parallel_seconds,3),'speedup':round(serial_seconds/parallel_seconds,3),
                'identical_results':True,'matches_published_loads_and_allocation_clocks':True},
            'section_search':{'section':section,'directed_passes':len(units),'alternatives':len(section_tasks),
                'serial_seconds':round(section_serial,3),'parallel_seconds':round(section_parallel,3),
                'speedup':round(section_serial/section_parallel,3),'whole_sections_preserved':True,
                'serial_road_costs':costs(serial_orders),'parallel_road_costs':costs(parallel_orders)},
            'scope':'Component benchmark including process startup/shutdown; not a measured end-to-end speedup. Time-limited section orders may differ.'}
        (audit/'routing-worker-benchmark.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2),flush=True)
    finally:road.close()


if __name__=='__main__':main()
