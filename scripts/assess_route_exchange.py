"""Replay a user-proposed two-truck work-area exchange without publishing it."""
import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from routing_app.engine import dump, measured_seconds, replay,choose_variants
from routing_app.load_sites import expand_passes, expand_library
from routing_app.optimizer import load_plan,section_orders
from routing_app.osrm import OSRM
from routing_app.settings import stream_settings,settings
from routing_app.saved import saved_library


def assess(truck_a, truck_b, area_a, area_b, latest_settings=False):
    cache=Path('outputs/2026-11-04_monday_map/audit/partition_app')
    key=json.loads((cache/'current-routing.json').read_text())['key']
    result=json.loads((cache/f'routing-{key}.result.json').read_text('utf-8'))
    routes=[next(r for r in result['routes'] if r['id']==name) for name in [truck_a,truck_b]]
    assert routes[0]['stream']==routes[1]['stream']
    assert (area_a=='-' or area_a in routes[0]['sections']) and (area_b=='*' or area_b in routes[1]['sections'])
    config=result['settings']
    if latest_settings:
        config=settings(json.loads((cache/'routing-settings.json').read_text('utf-8')))
    else:
        # A new default must not silently alter an older counterfactual.
        config={**config,'minimum_dump_fill_percent':config.get('minimum_dump_fill_percent',0)}
        config={**config,**{s:{**config[s],'capacity_tolerance_percent':config[s].get('capacity_tolerance_percent',0)} for s in ['garbage','recycling']}}
        config=settings(config)
    stream=routes[0]['stream'];cfg=stream_settings(config,stream)
    outgoing=set() if area_a=='-' else {area_a}
    incoming=set(routes[1]['sections']) if area_b=='*' else {area_b}
    desired=[(set(routes[0]['sections'])-outgoing)|incoming,
             (set(routes[1]['sections'])-incoming)|outgoing]
    desired=[members for members in desired if members]
    library,groups,anchors=saved_library(result,cache)
    inventory=json.loads((cache/'routing-road-inventory.json').read_text('utf-8'))
    selected=set.union(*desired)
    groups=[g for g in groups if g['section'] in selected]
    library={**library,'sections':{s:v for s,v in library['sections'].items() if s in selected}}
    graph={s:set() for s in selected}
    for link in result['adjacency']:
        if link['a'] in selected and link['b'] in selected:
            graph[link['a']].add(link['b']);graph[link['b']].add(link['a'])
    for members in desired:
        visited={min(members)}
        while True:
            more=visited|set().union(*(graph[s]&members for s in visited))
            if more==visited:break
            visited=more
        assert visited==members,'The proposed exchange disconnects a territory.'
    road=OSRM(cache,'directed-v1:'+inventory['source_hash'],table_locations=cfg['table_locations'])
    try:
        core={g['id']:road.route([anchors[i] for i in g['members']]) for g in groups}
        atoms,paths,edges,expansion=expand_passes(groups,anchors,core,cfg)
        fine=expand_library(library,atoms,expansion,road,result['sites'],cache,lambda *a:None)
        unit={a['id']:a for a in atoms};internal={a['id']:0 for a in atoms}
        proposed=[];trials=[]
        for index,members in enumerate(desired):
            variants={s:fine['sections'][s][stream] for s in members}
            candidates=[]
            connectors={}
            costs={}
            for a,b in itertools.permutations(members,2):
                for i,va in enumerate(variants[a]):
                    for j,vb in enumerate(variants[b]):
                        connectors[a,i,b,j]=measured_seconds(road.route([va['end'],vb['start']]),cfg)
                costs[a,b]=min(v for (x,_,y,_),v in connectors.items() if x==a and y==b)
            orders=section_orders(members,graph,costs)
            for order in orders:
                for options in choose_variants(order,variants,connectors,cfg,stream,fine):
                    sequence=[];joins=[]
                    for n,(section,option) in enumerate(zip(order,options)):
                        v=variants[section][option]
                        if n:
                            previous=variants[order[n-1]][options[n-1]]
                            joins.append(connectors[order[n-1],options[n-1],section,option])
                        sequence.extend(unit[g] for g in v['groups']);joins.extend(v['joins'])
                    plan=load_plan(sequence,internal,joins,fine['dispatch'],fine['to_rf'][stream],
                        fine['from_rf'][stream],fine['return'][stream],cfg,stream)
                    if plan:candidates.append({'sections':list(order),'variants':list(options),
                        'sequence':[g['id'] for g in sequence],'plan':plan})
            best=min(candidates,key=lambda c:(c['plan']['late_seconds'],
                c['plan']['paid_seconds']+c['plan']['load_preference_penalty']))
            actual=replay(best,stream,int(routes[index]['id'].split('-')[1]),cfg,unit,paths,
                anchors,result['sites'],road,edges)
            expected={s['AddressId'] for r in routes for s in r['stops'] if s['WorkArea'] in members}
            assert Counter(s['AddressId'] for s in actual['stops'])==Counter({i:1 for i in expected})
            proposed.append(actual);trials.append(len(candidates))
        fields=['id','sections','pickups','return','paid_seconds','early_seconds','late_seconds','km']
        short=lambda r:{**{k:r[k] for k in fields},'loads':[l['pickups'] for l in r['loads']]}
        output={'source_result':key,'request':{'truck_a':truck_a,'truck_b':truck_b,'area_a':area_a,'area_b':area_b},
            'current':[short(r) for r in routes],'proposed':[short(r) for r in proposed],
            'orders_and_variants_tested':trials,'both_territories_connected':True,
            'source_ids_unchanged':True,'published_files_unchanged':True,
            'road_requests':road.requests,'cache_hits':road.hits,
            'operating_changes':{'recycling_capacity_tolerance_percent':cfg['recycling'].get('capacity_tolerance_percent',0),'minimum_dump_fill_percent':cfg['minimum_dump_fill_percent']},
            'scope':'Actual replay of best tested complete orders and entry/exit variants. A counterfactual, not a published reassignment.'}
        kind='merge' if area_b=='*' else 'transfer' if area_a=='-' else 'exchange'
        dump(cache/f'route-{kind}-{truck_a}-{truck_b}-assessment.json',output)
        print(json.dumps(output,indent=2),flush=True)
    finally:road.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['truck_a','truck_b','area_a','area_b']:parser.add_argument(name)
    parser.add_argument('--latest-settings',action='store_true')
    args=parser.parse_args()
    assess(args.truck_a,args.truck_b,args.area_a,args.area_b,args.latest_settings)
