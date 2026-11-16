"""Pool complete measured facility alternatives before assigning a whole fleet."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from .facilities import pairs,case_settings
from .optimizer import fleet_cover,reunion_exchanges,consolidation_candidates
from .settings import clock_seconds,stream_settings


def allocate(partition,cfg,stream,atoms,atom_core,library,road,graph,progress,macro,seeds,sites,cache,anchor_key,expansion):
    from . import engine
    choices=pairs(cfg,stream)
    if len(choices)==1:
        chosen,search=engine.allocate(partition,cfg,stream,atoms,atom_core,library,road,graph,progress,macro=macro,seeds=seeds)
        depot,receiver=choices[0]
        for candidate in chosen:
            candidate['facility']={'depot':depot,'receiver':receiver,'sites':{'yard':sites['yard'],stream:sites[stream]}}
        return chosen,search
    raw_groups,raw_core,raw_library=macro
    ids=sorted(graph)
    parents={f['id']:f['properties'].get('parent_section',f['id']) for f in partition['areas']['features']}
    counts=Counter(g['section'] for g in atoms for _ in g['members'])
    code=hashlib.sha256(Path(__file__).read_bytes()+Path(engine.__file__).read_bytes()).hexdigest()
    case_contexts=[]
    # Road requests and cache writes stay in this coordinator. Each bounded
    # worker task evaluates a whole order/load alternative, never half a fleet.
    for number,(depot,receiver) in enumerate(choices,1):
        progress(None,f'{stream.title()}: preparing facility choice {number}/{len(choices)}')
        case=case_settings(cfg,stream,depot,receiver)
        case_sites={**sites,'yard':road.facility(case['yard']),stream:road.facility(case[stream]['receiver'])}
        case_library=engine.build_library(partition,case,cache,road,raw_groups,raw_core,case_sites,
            engine.digest([anchor_key,[(g['id'],g['section']) for g in raw_groups]]),progress)
        fine_library=engine.expand_library(case_library,atoms,expansion,road,case_sites,cache,progress)
        case_contexts.append((depot,receiver,case,case_sites,case_library,fine_library))
    candidates=[];known=set();stats=[];requested=list(seeds);chosen=None;status=[]
    limits=stream_settings(cfg,stream)
    fixed=60*sum(limits[k] for k in ['pretrip_minutes','break_minutes','posttrip_minutes','fueling_minutes','unpaid_lunch_minutes'])
    hard=clock_seconds(cfg['latest_return'])-clock_seconds(cfg['crew_start'])
    pace=max(limits['pickup_seconds'],60/limits['active_collection_pickups_per_minute']) if limits['use_observed_collection_pace'] else limits['pickup_seconds']
    maximum=max(1,math.floor((hard-fixed)/pace))
    def optimistic(members):return fixed+sum(counts[s] for s in members)*pace
    for refinement in range(2):
        for number,(depot,receiver,case,case_sites,case_library,fine_library) in enumerate(case_contexts,1):
            progress(None,f'{stream.title()}: evaluating complete territories at facility choice {number}/{len(choices)}')
            key=engine.digest(['facility-pool-1',code,case_library['key'],case,stream,requested])
            path=cache/f'routing-{key}.facility-pool.json'
            if path.exists():
                saved=json.loads(path.read_text(encoding='utf-8'));pool,stat=saved['candidates'],saved['search']
            else:
                pool,stat=engine.allocate(partition,case,stream,atoms,atom_core,fine_library,road,graph,progress,
                    macro=(raw_groups,raw_core,case_library),seeds=requested,return_candidates=True)
                engine.dump(path,{'candidates':pool,'search':stat})
            stats.append(stat)
            for candidate in pool:
                identity=(depot['id'],receiver['id'],tuple(candidate['sections']),tuple(candidate['sequence']))
                if identity in known:continue
                known.add(identity)
                candidate=deepcopy(candidate)
                candidate['facility']={'depot':depot,'receiver':receiver,'sites':{'yard':case_sites['yard'],stream:case_sites[stream]}}
                candidates.append(candidate)
        progress(None,f'{stream.title()}: assigning the whole stream across all selected facility choices')
        chosen,status=fleet_cover(ids,candidates,cfg['fleet_search_seconds'],parent_sections=parents)
        if refinement:break
        exchanges=reunion_exchanges(chosen,graph,parents,counts,maximum)
        exchanges|=consolidation_candidates(chosen,graph,parents,counts,maximum,optimistic,hard)
        available={frozenset(c['sections']) for c in candidates}
        requested=sorted(exchanges-available,key=lambda v:tuple(sorted(v)))
        if not requested:break
    comparison,comparison_status=fleet_cover(ids,candidates,cfg['fleet_search_seconds'],overtime_first=True,parent_sections=parents)
    window_met=all(c['plan']['late_seconds']==0 and c['plan']['early_seconds']==0 for c in chosen)
    search={'facility_combinations':len(choices),'facility_search_rounds':refinement+1,
        'facility_choice_policy':'Each truck starts/ends at one selected depot and uses one selected receiver for its complete day.',
        'evaluated_orders':sum(s['evaluated_orders'] for s in stats),'feasible_candidates':len(candidates),
        'physical_site_territories':sum(s['physical_site_territories'] for s in stats),
        'local_solver_workers':cfg['local_solver_workers'],'solver_stages':status,'return_window_met':window_met,
        'search_method':'Measured full-day facility alternatives, whole-parent territories and reciprocal exchanges; one whole-stream fleet cover',
        'overtime_first_comparison':{'trucks':len(comparison),'overtime_minutes':round(sum(c['plan']['overtime_seconds'] for c in comparison)/60,1),
            'latest_return_violations':sum(c['plan']['late_seconds']>0 for c in comparison),'solver_stages':comparison_status}}
    return chosen,search
