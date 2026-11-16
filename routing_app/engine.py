"""Reusable full-section routes, independent stream fleets and exact road replay."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter

import numpy as np
from shapely.geometry import shape

from partition_app.geography import project
from . import VERSION
from .settings import settings as validate_settings, clock_seconds, clock_label,stream_settings,load_limits
from .roads import inventory, make_groups, angle
from .osrm import OSRM, coordinate
from .optimizer import connected_sets, section_orders, fleet_cover,cohesive_candidates,reunion_exchanges,consolidation_candidates,pocket_affinity_regret
from .load_sites import expand_passes, expand_library, endpoint_key
from .work_areas import subdivide_overlong
from .parallel import workers, bounded_map, section_job, territory_job, worker_count
from .saved import section_library_key, retain_section_variants


def dump(path, value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False),encoding='utf-8')
    temporary.replace(path)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def prepare(partition, cfg, cache, progress):
    roads=inventory(cache,progress)
    anchor_key=digest([partition['partition_hash'],roads['source_hash'],
        hashlib.sha256(Path(__file__).with_name('roads.py').read_bytes()).hexdigest()])
    anchor_path=cache/f'routing-{anchor_key}.anchors.json'
    if anchor_path.exists():
        saved=json.loads(anchor_path.read_text(encoding='utf-8'))
        groups,anchors,reviews=saved['groups'],saved['anchors'],saved['reviews']
    else:
        progress(5,'Inferring right-side road passes from the local street network')
        groups,anchors,reviews=make_groups(partition,roads)
        dump(anchor_path,{'groups':groups,'anchors':anchors,'reviews':reviews})
    road=OSRM(cache,'directed-v1:'+roads['source_hash'],progress,cfg['table_locations'])
    sites={'yard':road.facility(cfg['yard']), **{s:road.facility(cfg[s]['receiver']) for s in ['garbage','recycling']}}
    core={}
    for i,g in enumerate(groups):
        progress(6+15*i/max(1,len(groups)),f"Road pass {i+1:,}/{len(groups):,}: {g['road_name']}")
        result=road.route([anchors[x] for x in g['members']])
        core[g['id']]=result
        # Geometry and costs use the same anchors; original property points are
        # never substituted into a replay of cached road-side coordinates.
        unique=[]
        for ident in g['members']:
            a=anchors[ident]
            if not unique or a['coordinate']!=unique[-1]['coordinate'] or a['bearing']!=unique[-1]['bearing']:
                unique.append(a)
        for j,leg in enumerate(result['legs']):
            if leg['meters']>2 and (angle(unique[j]['bearing'],leg['departure_bearing'])>65 or
                                   angle(unique[j+1]['bearing'],leg['arrival_bearing'])>65):
                reviews.append({'id':unique[j]['id'],'section':g['section'],'issues':['road_direction_replay_mismatch']})
    # A replay diagnostic must also travel with the individual pickup export
    # and popup. A global warning alone must not leave that point labelled as
    # supported right-curb service. This does not change geometry or route cost.
    for review in reviews:
        anchor=anchors[review['id']]
        anchor['review']=list(dict.fromkeys([*anchor['review'],*review['issues']]))
    return road,groups,anchors,reviews,core,sites,anchor_key


def measured_seconds(path,cfg,active=True):
    return path['seconds']/cfg['active_speed_factor' if active else 'general_speed_factor']+path['reversals']*cfg['reversal_seconds']


def build_library(partition,cfg,cache,road,groups,core,sites,anchor_key,progress,previous=None):
    with workers(cfg.get('local_solver_workers',1)) as pool:
        return _build_library(partition,cfg,cache,road,groups,core,sites,anchor_key,progress,previous,pool)


def _build_library(partition,cfg,cache,road,groups,core,sites,anchor_key,progress,previous,pool):
    key=section_library_key(anchor_key,cfg,sites)
    path=cache/f'routing-{key}.library.json'
    if path.exists():
        progress(52,'Reusing complete section orders and their measured road costs')
        return json.loads(path.read_text(encoding='utf-8'))
    # A longer time-limited solve need not beat every shorter solve. Keep a
    # bounded portfolio from an exact compatible lower-budget library, never
    # an arbitrary cache file or a library with different road ownership.
    earlier=None
    for budget in range(cfg['search_seconds_per_section']-1,0,-1):
        for version in ['library-2-portfolio','library-1']:
            prior_key=section_library_key(anchor_key,cfg,sites,budget,version)
            prior_path=cache/f'routing-{prior_key}.library.json'
            if prior_path.exists():
                candidate=json.loads(prior_path.read_text(encoding='utf-8'))
                if candidate.get('key')==prior_key:earlier=candidate;break
        if earlier:break
    by_section=defaultdict(list)
    for g in groups:by_section[g['section']].append(g)
    # Three-to-many / many-to-two gateway tables, never citywide all-pairs.
    progress(22,'Calculating depot and receiver travel for every road pass')
    enter,_=road.table([sites['yard'],sites['garbage'],sites['recycling']],[g['start'] for g in groups])
    leave,_=road.table([g['end'] for g in groups],[sites['garbage'],sites['recycling']])
    result={'sections':{},'dispatch':{},'from_rf':{},'to_rf':{},'return':{},'key':key}
    checkpoint_path=cache/f'routing-{key}.library-progress.json'
    if checkpoint_path.exists():
        saved=json.loads(checkpoint_path.read_text(encoding='utf-8'))
        if saved.get('key')==key:result['sections']=saved.get('sections',{})
    indices={g['id']:i for i,g in enumerate(groups)}
    result['dispatch']={g['id']:float(enter[0,i]) for i,g in enumerate(groups)}
    for s,stream in enumerate(['garbage','recycling']):
        result['from_rf'][stream]={g['id']:float(enter[s+1,i]) for i,g in enumerate(groups)}
        result['to_rf'][stream]={g['id']:float(leave[i,s]) for i,g in enumerate(groups)}
        result['return'][stream]=road.route([sites[stream],sites['yard']])['seconds']
    if not all(math.isfinite(v) for x in [result['dispatch'],*result['from_rf'].values(),*result['to_rf'].values()] for v in x.values()):
        raise ValueError('Some road passes cannot reach their depot/receiver. Check the access diagnostics; no straight-line travel was substituted.')
    for k,(section,units) in enumerate(sorted(by_section.items())):
        cached_section=result['sections'].get(section)
        if cached_section and all(cached_section.get(s) and all(sorted(v['groups'])==sorted(g['id'] for g in units)
                for v in cached_section[s]) for s in ['garbage','recycling']):
            progress(24+27*k/len(by_section),f'Reusing completed section {k+1}/{len(by_section)}')
            continue
        if previous and section in previous['sections']:
            result['sections'][section]=previous['sections'][section]
            continue
        progress(24+27*k/len(by_section),f"Sequencing complete section {k+1}/{len(by_section)} ({len(units)} directed road passes)")
        matrix,_=road.table([g['end'] for g in units],[g['start'] for g in units])
        jobs=[];streams=[]
        for s,stream in enumerate(['garbage','recycling']):
            for origin in [0,s+1]:
                inc=[enter[origin,indices[g['id']]] for g in units]
                out=[leave[indices[g['id']],s] for g in units]
                jobs.append((matrix,inc,out,max(1,cfg['search_seconds_per_section']//2)));streams.append(stream)
        checkpoint=lambda:progress(None,f"Sequencing complete section {k+1}/{len(by_section)} with {worker_count(cfg.get('local_solver_workers',1))} local solver workers")
        orders=bounded_map(pool,section_job,jobs,checkpoint)
        library={s:[] for s in ['garbage','recycling']};seen=defaultdict(set)
        for stream,order in zip(streams,orders):
            ids=[units[i]['id'] for i in order]
            if tuple(ids) in seen[stream]:continue
            seen[stream].add(tuple(ids))
            joins=[];reversals=0
            for a,b in zip(order,order[1:]):
                connector=road.route([units[a]['end'],units[b]['start']])
                joins.append(measured_seconds(connector,cfg))
                reversals+=connector['reversals']
            internal=sum(measured_seconds(core[g],cfg) for g in ids)+sum(joins)
            library[stream].append({'groups':ids,'joins':joins,'internal_seconds':internal,'reversals':reversals,
                                   'start':units[order[0]]['start'],'end':units[order[-1]]['end']})
        result['sections'][section]=retain_section_variants(library,
            earlier['sections'].get(section,{}) if earlier else {},[g['id'] for g in units])
        # Durable per-section checkpoint even if a later section fails.
        dump(cache/f'routing-{key}.library-progress.json',result)
    dump(path,result)
    return result


def adjacency(partition, library, road, progress):
    polygons={f['id']:project(shape(f['geometry'])) for f in partition['areas']['features']}
    ids=sorted(polygons);links=[];graph={s:set() for s in ids}
    for i,a in enumerate(ids):
        for b in ids[i+1:]:
            distance=polygons[a].distance(polygons[b])
            shared=polygons[a].boundary.intersection(polygons[b].boundary).length
            if shared<5 and distance>80:continue
            va=library['sections'][a]['garbage'];vb=library['sections'][b]['garbage']
            # An actual road path corroborates a geographic neighbour. Endpoint
            # routes may be longer than the shared edge; retain their distances.
            options=[road.route([x['end'],y['start']]) for x in va[:1] for y in vb[:1]]
            if not options:continue
            graph[a].add(b);graph[b].add(a)
            links.append({'a':a,'b':b,'gap_m':round(distance,2),'shared_boundary_m':round(shared,2),
                          'road_connection_m':round(options[0]['meters'],1),'kind':'geographic_adjacency'})
    # A service-free gap does not demand a dedicated truck. Connect each
    # disconnected component to its nearest operational neighbours via actual
    # roads. These remain explicit gap links, never invented shared boundaries.
    components=[];seen=set()
    for start in ids:
        if start in seen:continue
        component={start};todo=[start]
        while todo:
            for nxt in graph[todo.pop()]-component:component.add(nxt);todo.append(nxt)
        components.append(component);seen.update(component)
    main=max(components,key=len)
    for component in components:
        if component==main:continue
        pairs=sorted((polygons[a].distance(polygons[b]),a,b) for a in component for b in main)
        nearest=pairs[0][0]
        eligible=[p for p in pairs if p[0]<=nearest*1.35+300][:3]
        for distance,a,b in eligible:
            progress(None,f'Checking road access from isolated service area {a} to nearby {b}')
            x=library['sections'][a]['garbage'][0];y=library['sections'][b]['garbage'][0]
            forward=road.route([x['end'],y['start']]);reverse=road.route([y['end'],x['start']])
            graph[a].add(b);graph[b].add(a)
            links.append({'a':a,'b':b,'kind':'road_gap_connection','gap_m':round(distance,2),
                'shared_boundary_m':0,'nearest_component_gap_m':round(nearest,2),
                'road_connection_m':round(min(forward['meters'],reverse['meters']),1),
                'reason':'Isolated service component connected to its nearest road-accessible neighbours; polygons preserved'})
    return graph,links


def choose_variants(order,variants,connections,cfg,stream,library):
    # Entry/exit DP over entire section variants; no interleaved section visits.
    states=[]
    for i,section in enumerate(order):
        row=[]
        for v,variant in enumerate(variants[section]):
            work=variant['internal_seconds']
            if i==0:
                row.append((work+library['dispatch'][variant['groups'][0]]/cfg['general_speed_factor'],[v]))
            else:
                row.append(min((previous[0]+connections[(order[i-1],u,section,v)]+work,previous[1]+[v])
                               for u,previous in enumerate(states[-1])))
        states.append(row)
    return [p[1] for p in sorted(states[-1],key=lambda p:p[0])]


def allocate(partition,cfg,stream,groups,core,library,road,graph,progress,macro=None,seeds=()):
    with workers(cfg.get('local_solver_workers',1)) as pool:
        return _allocate(partition,cfg,stream,groups,core,library,road,graph,progress,macro,seeds,pool)


def _allocate(partition,cfg,stream,groups,core,library,road,graph,progress,macro,seeds,pool):
    cfg=stream_settings(cfg,stream)
    normal_capacity,hard_capacity=load_limits(cfg,stream)
    unit={g['id']:g for g in groups};ids=sorted(library['sections'])
    variants={s:library['sections'][s][stream] for s in ids}
    # Small gateway matrix only, not all service addresses. Actual connector
    # geometry and reversal costs are loaded lazily for shortlisted orders.
    gateways=[(s,i,v) for s in ids for i,v in enumerate(variants[s])]
    matrix,_=road.table([v['end'] for _,_,v in gateways],[v['start'] for _,_,v in gateways])
    costs={}
    for i,(a,_,_) in enumerate(gateways):
        for j,(b,_,_) in enumerate(gateways):
            if a!=b:costs[a,b]=min(costs.get((a,b),math.inf),matrix[i,j]/cfg['active_speed_factor'])
    class Connectors(dict):
        def __missing__(self,key):
            a,i,b,j=key
            self[key]=measured_seconds(road.route([variants[a][i]['end'],variants[b][j]['start']]),cfg)
            return self[key]
    joins=Connectors()
    counts=Counter()
    for g in groups:counts[g['section']]+=g['count']
    fixed=60*sum(cfg[k] for k in ['pretrip_minutes','break_minutes','posttrip_minutes','fueling_minutes','unpaid_lunch_minutes'])
    hard=clock_seconds(cfg['latest_return'])-clock_seconds(cfg['crew_start'])
    minimum_seconds_per_pickup=max(cfg['pickup_seconds'],60/cfg['active_collection_pickups_per_minute']) if cfg['use_observed_collection_pace'] else cfg['pickup_seconds']
    max_count=math.floor((hard-fixed)/minimum_seconds_per_pickup)
    work={s:min(v['internal_seconds'] for v in variants[s])+counts[s]*cfg['pickup_seconds'] for s in ids}
    def estimate(members):
        quantity=sum(counts[s] for s in members)
        dispatch=min(library['dispatch'][v['groups'][0]] for s in members for v in variants[s])
        receiver=min(library['to_rf'][stream][v['groups'][-1]] for s in members for v in variants[s])
        collection=sum(work[s] for s in members)
        if cfg['use_observed_collection_pace']:
            collection=max(collection,quantity*60/cfg['active_collection_pickups_per_minute'])
        return (fixed+collection+(dispatch+receiver+library['return'][stream])/cfg['general_speed_factor']+
            math.ceil(quantity/hard_capacity)*cfg[stream]['receiver']['onsite_minutes']*60)
    def rank_estimate(members):
        quantity=sum(counts[s] for s in members)
        intermediate=max(0,math.ceil(quantity/hard_capacity)-1)
        haul=min(library['to_rf'][stream][v['groups'][-1]]+
                 library['from_rf'][stream][v['groups'][0]] for s in members for v in variants[s])
        # Rank crowded beams with real receiver travel, but do not turn this
        # approximation into a new feasibility veto. Full load DP/replay still
        # charges the actual dump locations, road paths and elapsed time.
        return estimate(members)+intermediate*haul/cfg['general_speed_factor']
    parents={f['id']:f['properties'].get('parent_section',f['id']) for f in partition['areas']['features']}
    from .boundary_affinity import weights,separation_cost
    seam_affinities=weights(partition,graph,parents)
    cohesive=cohesive_candidates(ids,graph,parents,counts,max_count)
    territories=connected_sets(ids,graph,counts,max_count,estimate=estimate,time_limit=hard,
        seeds=[*seeds,*cohesive],rank_estimate=rank_estimate)
    internal={g['id']:measured_seconds(core[g['id']],cfg) for g in groups}
    candidates=[];tested=0;refined=0
    if macro:
        macro_groups,macro_core,macro_library=macro
        screen_unit={g['id']:g for g in macro_groups}
        screen_internal={g['id']:measured_seconds(macro_core[g['id']],cfg) for g in macro_groups}
        screen_variants={s:macro_library['sections'][s][stream] for s in ids}
    else:screen_unit,screen_internal,screen_variants,macro_library=unit,internal,variants,library
    def prepare_evaluation(order,selected,fine=False):
        selected_unit,selected_internal,selected_variants,selected_library=(unit,internal,variants,library) if fine else (screen_unit,screen_internal,screen_variants,macro_library)
        sequence=[];connectors=[]
        for t,(s,v) in enumerate(zip(order,selected)):
            variant=selected_variants[s][v]
            if t:connectors.append(joins[order[t-1],selected[t-1],s,v])
            sequence.extend(selected_unit[g] for g in variant['groups']);connectors.extend(variant['joins'])
        if not fine and any(g['count']>hard_capacity for g in sequence):
            return prepare_evaluation(order,selected,True)
        ids=[g['id'] for g in sequence]
        # Workers receive only numeric route costs/counts, not geometry, road
        # sessions or cache connections. The entire candidate stays one job.
        metadata={'sections':order,'variants':selected,'sequence':ids,
                  'pocket_affinity_regret':pocket_affinity_regret(order,graph,counts,costs),
                  'weak_boundary_separation_cost':separation_cost(order,seam_affinities)}
        arguments=([{ 'id':g['id'],'count':g['count']} for g in sequence],
            {g:selected_internal[g] for g in ids},connectors,
            {g:selected_library['dispatch'][g] for g in ids},
            {g:selected_library['to_rf'][stream][g] for g in ids},
            {g:selected_library['from_rf'][stream][g] for g in ids},
            selected_library['return'][stream],cfg,stream)
        return metadata,arguments
    def preference(c):return (c['plan']['late_seconds'],c['plan']['seconds']+c['plan']['load_preference_penalty'])
    options={}
    last_message=[f'{stream.title()}: evaluating connected territories']
    def checkpoint():progress(None,last_message[0])
    def screen_tasks(requested):
        nonlocal tested
        for k,members in enumerate(requested):
            last_message[0]=f"{stream.title()}: evaluating adjacent section groups {k+1}/{len(requested)} with {worker_count(cfg.get('local_solver_workers',1))} local workers"
            checkpoint()
            minimum=sum(min(v['internal_seconds'] for v in variants[s])+counts[s]*cfg['pickup_seconds'] for s in members)
            if cfg['use_observed_collection_pace']:
                minimum=max(minimum,sum(counts[s] for s in members)*60/cfg['active_collection_pickups_per_minute'])
            minimum+=fixed
            if len(members)>1 and minimum>hard:continue
            orders=section_orders(members,graph,costs)
            # Rank complete orders; never impose a named-road direction or a
            # receiver trip at every section seam.
            orders.sort(key=lambda order:min(library['dispatch'][v['groups'][0]] for v in variants[order[0]])/cfg['general_speed_factor']+
                sum(costs[a,b] for a,b in zip(order,order[1:]))+
                min(library['to_rf'][stream][v['groups'][-1]] for v in variants[order[-1]])/cfg['general_speed_factor'])
            alternatives=[]
            for order in orders[:6]:
                for selected in choose_variants(order,variants,joins,cfg,stream,library):
                    alternatives.append(prepare_evaluation(order,selected));tested+=1
            yield k,alternatives
    def evaluate(requested):
        for _,trial in bounded_map(pool,territory_job,screen_tasks(requested),checkpoint):
            if trial:
                trial.sort(key=preference);best=trial[0]
                options[len(candidates)]=[(c['sections'],c['variants']) for c in trial[:3]]
                candidates.append(best)
    evaluate(territories)
    # Whole-pass plans screen the fleet candidates cheaply. Real dump decisions
    # are ALWAYS refined at physical pickup sites before a route is delivered.
    # Also refine near-window alternatives so coarse dump positions cannot hide
    # a useful multi-section truck day.
    done=set()
    def refine(indices):
        nonlocal refined
        pending=sorted(set(indices)-done)
        def tasks():
            for n,i in enumerate(pending):
                last_message[0]=f'{stream.title()}: optimizing real load breaks {n+1}/{len(pending)} with {worker_count(cfg.get("local_solver_workers",1))} local workers'
                yield i,[prepare_evaluation(order,selected,True) for order,selected in options[i]]
        for i,choices in bounded_map(pool,territory_job,tasks(),checkpoint):
            if choices:candidates[i]=min(choices,key=preference)
            else:raise ValueError('A screened territory has no physical-site load plan.')
            done.add(i);refined+=1
    if macro:
        promising=set()
        for section in ids:
            eligible=[i for i,c in enumerate(candidates) if section in c['sections']]
            eligible.sort(key=lambda i:(candidates[i]['plan']['late_seconds']+candidates[i]['plan']['early_seconds'],
                candidates[i]['plan']['paid_seconds']/sum(counts[s] for s in candidates[i]['sections'])))
            promising.update(eligible[:14])
        refine(promising)
    while True:
        chosen,status=fleet_cover(ids,candidates,cfg['fleet_search_seconds'],parent_sections=parents)
        pending=[i for i,c in enumerate(candidates) if any(c is selected for selected in chosen) and i not in done]
        if not macro or not pending:break
        refine(pending)
    fewer,status_fewer=fleet_cover(ids,candidates,cfg['fleet_search_seconds'],overtime_first=True,parent_sections=parents)
    if macro:
        refine([i for i,c in enumerate(candidates) if any(c is selected for selected in fewer)])
        # Refinement can change costs. Report comparisons from the same exact
        # physical-site candidate pool, excluding all unrefined screens.
        exact=[c for i,c in enumerate(candidates) if i in done]
        chosen,status=fleet_cover(ids,exact,cfg['fleet_search_seconds'],parent_sections=parents)
        fewer,status_fewer=fleet_cover(ids,exact,cfg['fleet_search_seconds'],overtime_first=True,parent_sections=parents)
    exchange_count=0;exchange_rounds=0;consolidation_count=0
    for _ in range(3):
        consolidation=consolidation_candidates(chosen,graph,parents,counts,max_count,estimate,hard,
            rank_estimate=rank_estimate)
        proposed=reunion_exchanges(chosen,graph,parents,counts,max_count)|consolidation
        known={frozenset(c['sections']) for c in candidates}
        new=sorted(proposed-known,key=lambda s:tuple(sorted(s)))
        if new:evaluate(new)
        indices={i for i,c in enumerate(candidates) if frozenset(c['sections']) in proposed}
        pending=indices-done if macro else set()
        if not new and not pending:break
        exchange_rounds+=1
        exchange_count+=len(new)
        consolidation_count+=len(set(new)&consolidation)
        if macro:refine(pending)
        exact=[c for i,c in enumerate(candidates) if not macro or i in done]
        progress(None,f'{stream.title()}: testing truck removal, nearby transfers and whole-section exchanges')
        chosen,status=fleet_cover(ids,exact,cfg['fleet_search_seconds'],parent_sections=parents)
    if exchange_rounds:
        exact=[c for i,c in enumerate(candidates) if not macro or i in done]
        fewer,status_fewer=fleet_cover(ids,exact,cfg['fleet_search_seconds'],overtime_first=True,parent_sections=parents)
    window_met=all(c['plan']['late_seconds']==0 and c['plan']['early_seconds']==0 for c in chosen)
    return chosen,{'candidate_territories':len(territories),'evaluated_orders':tested,'feasible_candidates':len(candidates),
        'physical_site_territories':refined,'local_solver_workers':worker_count(cfg.get('local_solver_workers',1)),
        'search_method':'Whole-parent and connected territories, physical-site loads, truck-removal/transfer and reunion proposals, fleet-wide cover',
        'whole_parent_candidate_count':len(cohesive),'additional_reunion_territories':exchange_count,'reunion_rounds':exchange_rounds,
        'additional_consolidation_territories':consolidation_count,
        'connected_beam_per_depth':1200,'beam_ranking':'Estimated day including intermediate receiver round trips; ranking only, not a feasibility constraint',
        'solver_stages':status,'scope':'Best tested connected work-area variants; not a proof of global fleet minimum',
        'objective_order':(['return_window'] if window_met else ['latest_return'])+['trucks','dump_fill_shortfall','small_pocket_road_regret','planning_section_fragmentation','weak_boundary_separation','total_paid_time']+([] if window_met else ['earliest_return'])+['preferred_return','overtime'],
        'weak_boundary_separation_cost':sum(c.get('weak_boundary_separation_cost',0) for c in chosen),
        'small_pocket_road_regret':sum(c.get('pocket_affinity_regret',0) for c in chosen),
        'return_window_met':window_met,'early_return_fallback':'Never reward extra driving solely to reduce an unavoidable early-return shortfall.',
        'dump_fill_shortfall':sum(c['plan'].get('dump_fill_shortfall',0) for c in chosen),
        'planning_section_fragmentation':sum(len({parents.get(s,s) for s in c['sections']}) for c in chosen)-len(set(parents.values())),
        'overtime_first_comparison':{'trucks':len(fewer),'overtime_minutes':round(sum(c['plan']['overtime_seconds'] for c in fewer)/60,1),
            'latest_return_violations':sum(c['plan']['late_seconds']>0 for c in fewer),'solver_stages':status_fewer}}


def replay(candidate,stream,index,cfg,unit,core,anchors,sites,road,pass_edges=None):
    cfg=stream_settings(cfg,stream)
    route_id=('G' if stream=='garbage' else 'R')+f'-{index:02d}'
    now=clock_seconds(cfg['crew_start']);begin=now
    events=[];legs=[];stops=[];loads=[];geometry=[];stats=Counter();load_index=0
    def event(kind,seconds,**extra):
        nonlocal now
        events.append({'type':kind,'start':clock_label(now),'end':clock_label(now+seconds),'seconds':round(seconds,6),**extra})
        now+=seconds;stats[kind]+=seconds
    def drive(a,b,active,kind):
        path=(pass_edges or {}).get((endpoint_key(a),endpoint_key(b))) if active else None
        if path is None:path=road.route([a,b])
        seconds=measured_seconds(path,cfg,active)
        start=now;event(kind,seconds)
        legs.append({'type':kind,'load':load_index,'seconds':round(seconds,6),'raw_osrm_seconds':path['seconds'],
            'meters':path['meters'],'reversals':path['reversals'],'from':coordinate(a),'to':coordinate(b)})
        if len(path['geometry'])>1:geometry.append({'type':'Feature','properties':{'route':route_id,'load':load_index,'kind':kind},
            'geometry':{'type':'LineString','coordinates':path['geometry']}})
        stats['meters']+=path['meters'];stats['reversals']+=path['reversals']
    event('pretrip',cfg['pretrip_minutes']*60)
    if cfg['fueling_minutes']:event('fueling',cfg['fueling_minutes']*60)
    sequence=[unit[g] for g in candidate['sequence']]
    current=sites['yard'];break_taken=False
    receiver=sites[stream]
    opens=clock_seconds(cfg[stream]['receiver']['opens']);closes=clock_seconds(cfg[stream]['receiver']['closes'])
    for load_index,load in enumerate(candidate['plan']['loads'],1):
        load_begin=now;count=0;start_sequence=len(stops)+1;rf_window=True
        active_before=stats['collection_drive']+stats['pickup']
        for position in range(load['begin'],load['end']):
            g=sequence[position]
            first=position==load['begin']
            drive(current,g['start'],not first,'dispatch' if first and load_index==1 else 'receiver_return' if first else 'collection_drive')
            path=core[g['id']]
            active_seconds=measured_seconds(path,cfg)
            count+=g['count']
            service_start=now
            event('collection_drive',active_seconds,section=g['section'],road=g['road_name'])
            event('pickup',g['count']*cfg['pickup_seconds'],section=g['section'])
            stats['meters']+=path['meters'];stats['reversals']+=path['reversals']
            legs.append({'type':'collection_drive','load':load_index,'section':g['section'],'group':g['id'],
                'seconds':active_seconds,'raw_osrm_seconds':path['seconds'],'meters':path['meters'],'reversals':path['reversals'],
                'from':coordinate(g['start']),'to':coordinate(g['end'])})
            if len(path['geometry'])>1:geometry.append({'type':'Feature','properties':{'route':route_id,'load':load_index,'kind':'collection_drive','group':g['id']},
                'geometry':{'type':'LineString','coordinates':path['geometry']}})
            for offset,ident in enumerate(g['members']):
                a=anchors[ident]
                stops.append({'AddressId':ident,'Address':a['address'],'Stream':stream,'Truck':route_id,'Load':load_index,
                    'Sequence':len(stops)+1,'Section':g.get('parent_section',g['section']),
                    'WorkArea':g['section'],'RoadPass':g.get('road_pass',g['id']),
                    'Latitude':a['original'][1],'Longitude':a['original'][0],
                    'PickupLatitude':a['coordinate'][1],'PickupLongitude':a['coordinate'][0],
                    'PickupRoad':a.get('road_name') or 'Unnamed site access',
                    'PickupOffsetM':a.get('setback_m'),'AccessBasis':a.get('match_method','named_street'),
                    'TravelBearing':a['bearing'],'Access':'Inferred curbside','AccessIssues':'; '.join(a['review']),
                    'EstimatedServiceTime':clock_label(service_start+offset*(cfg['pickup_seconds']+active_seconds/max(g['count'],1)))})
            current=g['end']
        raw_active=stats['collection_drive']+stats['pickup']-active_before
        allowance=max(0,count*60/cfg['active_collection_pickups_per_minute']-raw_active) if cfg['use_observed_collection_pace'] else 0
        if allowance:event('collection_allowance',allowance,load=load_index)
        drive(current,receiver,False,'to_receiver')
        if now<opens:event('receiver_wait',opens-now)
        arrival=now
        event('unload',cfg[stream]['receiver']['onsite_minutes']*60,receiver=receiver['name'],load=load_index,pickups=count)
        rf_window=now<=closes
        loads.append({'load':load_index,'pickups':count,'capacity':candidate['plan']['capacity'],
            'normal_capacity':candidate['plan'].get('normal_capacity',candidate['plan']['capacity']),
            'fill_percent':round(100*count/candidate['plan'].get('normal_capacity',candidate['plan']['capacity']),1),
            'minimum_fill_pickups':candidate['plan'].get('minimum_fill_pickups',0),
            'minimum_fill_met':count>=candidate['plan'].get('minimum_fill_pickups',0),
            'first_sequence':start_sequence,'last_sequence':len(stops),'start':clock_label(load_begin),
            'receiver_arrival':clock_label(arrival),'unloaded':clock_label(now),'seconds':now-load_begin,
            'receiver_window_met':rf_window,'base_collection_seconds':raw_active,'collection_allowance_seconds':allowance,
            'sections':list(dict.fromkeys(s['Section'] for s in stops[start_sequence-1:]))})
        current=receiver
        if not break_taken:
            event('break',cfg['break_minutes']*60)
            if cfg['unpaid_lunch_minutes']:event('unpaid_lunch',cfg['unpaid_lunch_minutes']*60)
            break_taken=True
    drive(receiver,sites['yard'],False,'yard_return')
    if cfg['posttrip_minutes']:event('posttrip',cfg['posttrip_minutes']*60)
    elapsed=now-begin;paid=max(elapsed-cfg['unpaid_lunch_minutes']*60,cfg['minimum_paid_hours']*3600)
    active=stats['collection_drive']+stats['pickup']+stats['collection_allowance']
    overtime=max(0,paid-cfg['preferred_paid_hours']*3600)
    late=max(0,now-clock_seconds(cfg['latest_return']))
    early=max(0,clock_seconds(cfg['earliest_return'])-now)
    preferred_shortfall=max(0,clock_seconds(cfg.get('preferred_return',cfg['earliest_return']))-now)
    return {'id':route_id,'stream':stream,'equipment':cfg[stream]['equipment'],'sections':candidate['sections'],
        'planning_sections':list(dict.fromkeys(g.get('parent_section',g['section']) for g in sequence)),
        'pickups':len(stops),'load_count':len(loads),'loads':loads,'events':events,'legs':legs,'stops':stops,
        'geometry':{'type':'FeatureCollection','features':geometry},'start':cfg['crew_start'],'return':clock_label(now),
        'elapsed_seconds':elapsed,'paid_seconds':paid,'overtime_seconds':overtime,'late_seconds':late,'early_seconds':early,
        'preferred_return_shortfall_seconds':preferred_shortfall,
        'km':stats['meters']/1000,'pickup_seconds':stats['pickup'],'collection_drive_seconds':stats['collection_drive'],
        'deadhead_seconds':stats['dispatch']+stats['receiver_return']+stats['to_receiver']+stats['yard_return'],
        'unload_seconds':stats['unload'],'break_seconds':stats['break'],'reversals':stats['reversals'],
        'collection_allowance_seconds':stats['collection_allowance'],
        'pace_sensitivity':{str(pace):{'paid_hours':(paid+sum(max(l['base_collection_seconds'],l['pickups']*60/pace)-
            l['base_collection_seconds']-l['collection_allowance_seconds'] for l in loads))/3600,
            'scope':'Same orders and loads; fleet not reoptimized'} for pace in ([cfg['observed_pickups_per_minute_low'],cfg['observed_pickups_per_minute_high']] if cfg['use_observed_collection_pace'] else [])},
        'pickup_time_sensitivity':{str(seconds):{'paid_hours':(paid+len(stops)*(seconds-cfg['pickup_seconds']))/3600,
            'scope':'Same driving, orders and loads; fleet not reoptimized'} for seconds in ([cfg['pickup_seconds_low'],cfg['pickup_seconds_high']] if not cfg['use_observed_collection_pace'] else [])},
        'sensitivity_60s_extra_seconds':stats['reversals']*max(0,cfg['reversal_sensitivity_seconds']-cfg['reversal_seconds']),
        'active_pickups_per_minute':len(stops)*60/active if active else None,
        'status':'OVER_LATEST_RETURN' if late else 'UNDERFILLED_DAY' if early else 'OVERTIME' if overtime else 'WITHIN_PREFERRED_DAY',
        'receiver_windows_met':all(l['receiver_window_met'] for l in loads),
        'estimated_seconds_before_replay':candidate['plan']['seconds']}


def run(partition,cfg,cache,progress=lambda *a:None):
    cfg=validate_settings(cfg)
    if partition['status']=='FAILED':raise ValueError('Fix the failed partition before routing.')
    road=None;started=perf_counter();timings=[]
    allocation_code=digest([hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ['engine.py','optimizer.py','parallel.py']])
    solve_settings={k:v for k,v in cfg.items() if not k.endswith('_comparison')}
    def timed(stage,operation,iteration=0):
        begin=perf_counter()
        try:return operation()
        finally:timings.append({'stage':stage,'iteration':iteration,'wall_seconds':round(perf_counter()-begin,3)})
    try:
        road,groups,anchors,reviews,core,sites,anchor_key=timed('road_preparation',lambda:prepare(partition,cfg,cache,progress))
        library=timed('section_sequencing',lambda:build_library(partition,cfg,cache,road,groups,core,sites,anchor_key,progress))
        work_partition=partition;split_audit=[];baseline=None;geography=None
        previous_plans={};best_iteration=None;iteration_audit=[]
        for iteration in range(4):
            atoms,atom_core,edges,expansion=expand_passes(groups,anchors,core,cfg)
            site_library=timed('pickup_site_gateways',lambda:expand_library(library,atoms,expansion,road,sites,cache,progress),iteration)
            graph,links=timed('adjacency',lambda:adjacency(work_partition,library,road,progress),iteration)
            plans={};overlong=set();underfilled=set();reduction_seeds=set()
            for stream in ['garbage','recycling']:
                atom_owner={g['id']:g['section'] for g in atoms}
                seeds=[sorted({atom_owner[x] for x in c['sequence']}) for c in previous_plans.get(stream,[])]
                allocation_key=digest(['fleet-window-7-consolidation',allocation_code,library['key'],solve_settings,stream,links,seeds,
                    [(g['id'],g['section']) for g in groups]])
                allocation_path=cache/f'routing-{allocation_key}.allocation.json'
                if allocation_path.exists():
                    saved=json.loads(allocation_path.read_text());chosen,search=saved['chosen'],saved['search']
                else:
                    chosen,search=timed(stream+'_allocation',lambda:allocate(work_partition,cfg,stream,atoms,atom_core,site_library,road,graph,progress,macro=(groups,core,library),seeds=seeds),iteration)
                    dump(allocation_path,{'chosen':chosen,'search':search})
                plans[stream]=(chosen,search)
                overlong.update(s for c in chosen if c['plan']['late_seconds']>0 for s in c['sections'])
                underfilled.update(s for c in chosen if c['plan']['early_seconds']>0 or c['plan'].get('dump_fill_shortfall',0)>0 for s in c['sections'])
                # Meeting the day window is not a proof that truck count is
                # minimal. Also explore clean rebalancing around the lightest
                # territories, independently of any comparison fleet number.
                lightest=sorted(chosen,key=lambda c:(c['plan']['paid_seconds'],tuple(c['sections'])))[:max(1,math.ceil(len(chosen)/4))]
                reduction_seeds.update(s for c in lightest for s in c['sections'])
            scored=[c for chosen,_ in plans.values() for c in chosen]
            parents={f['id']:f['properties'].get('parent_section',f['id']) for f in work_partition['areas']['features']}
            fragmentation=sum(sum(len({parents.get(s,s) for s in c['sections']}) for c in chosen)-len(set(parents.values()))
                for chosen,_ in plans.values())
            early=sum(c['plan']['early_seconds'] for c in scored)
            objective=(sum(c['plan']['late_seconds'] for c in scored),int(early>0),
                len(scored),sum(c['plan'].get('dump_fill_shortfall',0) for c in scored),sum(c.get('pocket_affinity_regret',0) for c in scored),fragmentation,
                sum(c.get('weak_boundary_separation_cost',0) for c in scored),
                sum(c['plan']['paid_seconds'] for c in scored),early)
            iteration_audit.append({'iteration':iteration,'work_areas':len(work_partition['areas']['features']),
                'objective':list(objective),'streams':{s:{'trucks':len(p[0]),'early':sum(c['plan']['early_seconds']>0 for c in p[0]),
                    'late':sum(c['plan']['late_seconds']>0 for c in p[0])} for s,p in plans.items()}})
            if best_iteration is None or objective<best_iteration['objective']:
                best_iteration={'objective':objective,'iteration':iteration,'plans':plans,'partition':work_partition,
                    'groups':groups,'atoms':atoms,'atom_core':atom_core,'edges':edges,'links':links,'changes':list(split_audit),'library_key':library['key']}
            previous_plans={s:p[0] for s,p in plans.items()}
            if baseline is None:
                baseline={s:{'trucks':len(p[0]),'late_routes':sum(c['plan']['late_seconds']>0 for c in p[0])} for s,p in plans.items()}
            if iteration==3:break
            counts=Counter(g['section'] for g in groups for _ in g['members'])
            # Operational granularity must allow adjacent work to be rebalanced
            # into useful days. Only mapped clean subdivisions are permitted.
            refine=set(overlong)
            for section in underfilled|reduction_seeds:
                refine.update(s for s in ({section}|graph[section]) if counts[s]>400)
            if not refine:break
            split_key=digest([anchor_key,library['key'],sorted(refine),
                hashlib.sha256(Path(__file__).with_name('work_areas.py').read_bytes()).hexdigest()])
            split_path=cache/f'routing-{split_key}.work-areas.json'
            if split_path.exists():
                saved=json.loads(split_path.read_text(encoding='utf-8'))
                next_partition,next_groups,changes=saved['partition'],saved['groups'],saved['changes']
            else:
                if geography is None:
                    progress(None,'Loading municipal geometry for clean truck-day rebalancing')
                    from partition_app.geography import Geography
                    geography=Geography()
                next_partition,next_groups,changes=timed('clean_subdivision',lambda:subdivide_overlong(work_partition,groups,anchors,refine,progress,geography),iteration)
                dump(split_path,{'partition':next_partition,'groups':next_groups,'changes':changes})
            split_audit.extend(changes)
            if not any(c['status']=='SHARED_BY_CLEAN_WORK_AREAS' for c in changes):break
            work_partition,groups=next_partition,next_groups
            library=timed('section_sequencing',lambda:build_library(work_partition,cfg,cache,road,groups,core,sites,
                digest([anchor_key,[(g['id'],g['section']) for g in groups]]),progress,previous=library),iteration+1)
        # A refinement is an experiment, not permission to discard a better
        # measured fleet. Publish the best complete tested iteration.
        plans=best_iteration['plans'];work_partition=best_iteration['partition'];groups=best_iteration['groups']
        atoms=best_iteration['atoms'];atom_core=best_iteration['atom_core'];edges=best_iteration['edges']
        links=best_iteration['links'];split_audit=best_iteration['changes']
        streams={};routes=[];unit={g['id']:g for g in atoms}
        for stream,(chosen,search) in plans.items():
            selected=[]
            for n,candidate in enumerate(sorted(chosen,key=lambda c:tuple(c['sections'])),1):
                progress(None,f"Replaying {stream} truck {n}/{len(chosen)} on local roads")
                selected.append(timed(stream+'_replay',lambda:replay(candidate,stream,n,cfg,unit,atom_core,anchors,sites,road,edges),best_iteration['iteration']))
            routes.extend(selected)
            streams[stream]={'trucks':len(selected),'pickups':sum(r['pickups'] for r in selected),
                'loads':sum(r['load_count'] for r in selected),'km':sum(r['km'] for r in selected),
                'paid_hours':sum(r['paid_seconds'] for r in selected)/3600,
                'overtime_hours':sum(r['overtime_seconds'] for r in selected)/3600,
                'latest_return':max(r['return'] for r in selected),
                'earliest_return':min(r['return'] for r in selected),
                'underfilled_days':sum(r['early_seconds']>0 for r in selected),
                'before_preferred_return':sum(r['preferred_return_shortfall_seconds']>0 for r in selected),
                'comparison_trucks':cfg[stream+'_trucks_comparison'],
                'trucks_above_comparison':len(selected)-cfg[stream+'_trucks_comparison'],
                'average_pickups':sum(r['pickups'] for r in selected)/len(selected),
                'over_latest_return':sum(r['late_seconds']>0 for r in selected),'search':search}
        expected={p['id'] for p in partition['points']};validation={}
        unresolved_access={'property_setback_over_80m','street_name_unmatched',
            'oneway_opposite_curb_requires_review','construction_tagged_street_access_proxy',
            'road_direction_replay_mismatch','ambiguous_property_side'}
        pickup_access_supported=not any(unresolved_access.intersection(r['issues']) for r in reviews)
        for stream in streams:
            selected=[r for r in routes if r['stream']==stream]
            counts=Counter(s['AddressId'] for r in selected for s in r['stops'])
            owners=defaultdict(set)
            for r in selected:
                for section in r['sections']:owners[section].add(r['id'])
            contiguous=all(list(dict.fromkeys(s['WorkArea'] for s in r['stops']))==r['sections'] for r in selected)
            validation[stream]={'exactly_once':set(counts)==expected and all(n==1 for n in counts.values()),
                'whole_work_areas':all(len(v)==1 for v in owners.values()),'section_order_contiguous':contiguous,
                'capacity_safe':all(l['pickups']<=l['capacity'] for r in selected for l in r['loads']),
                'minimum_dump_fill_met':all(l['minimum_fill_met'] for r in selected for l in r['loads']),
                'receiver_windows_met':all(r['receiver_windows_met'] for r in selected),
                'latest_return_met':all(r['late_seconds']==0 for r in selected),
                'earliest_return_met':all(r['early_seconds']==0 for r in selected),
                'preferred_day_met':all(r['overtime_seconds']==0 for r in selected),
                'pickup_access_supported':pickup_access_supported,
                'source_ids':len(expected),'serviced_ids':len(counts),
                'final_unload':all(r['loads'] and r['events'][-1]['type'] in {'yard_return','posttrip'} for r in selected)}
        if not all(v['exactly_once'] and v['whole_work_areas'] and v['section_order_contiguous'] and v['capacity_safe'] for v in validation.values()):
            raise ValueError('Routing coverage, section ownership, order or load validation failed.')
        # Work-area properties describe their own geometry and demand, never
        # inherited parent totals. Planning features themselves stay untouched.
        work_counts=Counter(g['section'] for g in atoms for _ in g['members'])
        for feature in work_partition['areas']['features']:
            props=feature['properties'];ident=feature['id']
            if props.get('parent_section'):
                feature['properties']={k:props[k] for k in ['id','name','parent_section','routing_boundary'] if k in props}
                feature['properties'].update(addresses=work_counts[ident],
                    area_km2=round(project(shape(feature['geometry'])).area/1e6,4),operational_work_area=True)
        result={'version':VERSION,'created_at':datetime.now(timezone.utc).isoformat(),
            'partition_key':partition['key'],'partition_hash':partition['partition_hash'],'day':partition.get('day','MONDAY'),
            'settings':cfg,'sites':sites,'streams':streams,'routes':routes,'validation':validation,
            'total_trucks':sum(s['trucks'] for s in streams.values()),'adjacency':links,'access_reviews':reviews,
            'access_summary':dict(Counter(issue for r in reviews for issue in r['issues'])),
            'work_areas':work_partition['areas'],'work_area_changes':split_audit,'before_sharing':baseline,
            'fleet_iterations':iteration_audit,'selected_iteration':best_iteration['iteration'],
            'planning_sections_preserved':True,'road_passes':len(groups),'road_cache':{'requests':road.requests,'hits':road.hits},
            'performance':{'computation_wall_seconds':round(perf_counter()-started,3),'local_solver_workers':worker_count(cfg['local_solver_workers']),
                'phases':timings,'scope':'Local CPU workers evaluate complete independent alternatives. Road requests and fleet-wide ownership remain coordinated.'},
            'status':('PLANNING_ROUTES' if all(v['minimum_dump_fill_met'] for v in validation.values()) else 'LOAD_UTILIZATION_UNMET') if all(v['earliest_return_met'] and v['latest_return_met'] and v['receiver_windows_met'] for v in validation.values()) else 'TIME_LIMITS_UNMET',
            'fleet_recommendation_supported':all(v['earliest_return_met'] and v['latest_return_met'] and v['receiver_windows_met'] and v['minimum_dump_fill_met'] for v in validation.values()) and pickup_access_supported,
            'limitations':['Property-to-curb access is inferred. One-way opposite-curb and ambiguous road matches remain explicit.',
                'OSRM car-road connectivity does not certify truck dimensions or field turn restrictions.',
                'Garbage mass is unchecked unless kg per pickup is supplied; the nine-tonne payload and pickup capacity are separate.',
                'Fleet is the best tested connected work-area plan, not a proven global minimum.'],
            'anchor_cache_key':anchor_key,'selected_library_key':best_iteration['library_key']}
        progress(97,'Checking every source ID, load, clock and work-area owner')
        return result
    finally:
        if road:road.close()
