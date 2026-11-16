"""Resolve a saved plan's exact section library without guessing from filenames."""
from copy import deepcopy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def section_library_key(anchor,cfg,sites,budget=None,version='library-2-portfolio'):
    return digest([version,anchor,cfg['search_seconds_per_section'] if budget is None else budget,
                   cfg['active_speed_factor'],cfg['general_speed_factor'],cfg['reversal_seconds'],sites])


def retain_section_variants(current,previous,expected):
    """Keep new orders and up to two compatible earlier complete orders."""
    result={};expected=sorted(expected)
    for stream in ['garbage','recycling']:
        result[stream]=[];seen=set()
        for variant in [*current.get(stream,[]),*previous.get(stream,[])[:2]]:
            order=tuple(variant['groups'])
            if sorted(order)!=expected or order in seen:continue
            seen.add(order);result[stream].append(variant)
    return result


def saved_library(result,cache):
    anchors_record=json.loads((cache/f"routing-{result['anchor_cache_key']}.anchors.json").read_text('utf-8'))
    groups=deepcopy(anchors_record['groups']);owners={}
    for route in result['routes']:
        for stop in route['stops']:
            ident=stop['AddressId'];owner=stop['WorkArea']
            if ident in owners and owners[ident]!=owner:raise ValueError('Streams disagree about saved work-area ownership.')
            owners[ident]=owner
    parents={f['id']:f['properties'].get('parent_section',f['id']) for f in result['work_areas']['features']}
    for group in groups:
        assigned={owners[i] for i in group['members']}
        if len(assigned)!=1:raise ValueError('A saved work area cuts a complete directed road pass.')
        group['section']=assigned.pop();group['parent_section']=parents[group['section']]
    cfg=result['settings'];anchor=result['anchor_cache_key']
    if result.get('selected_iteration',0):anchor=digest([anchor,[(g['id'],g['section']) for g in groups]])
    compatible=[section_library_key(anchor,cfg,result['sites'],version=v)
                for v in ['library-1','library-2-portfolio']]
    key=result.get('selected_library_key',compatible[0])
    if key not in compatible:raise ValueError('Saved library provenance does not match the selected ownership.')
    library=json.loads((cache/f'routing-{key}.library.json').read_text('utf-8'))
    if set(library['sections'])!=set(parents):raise ValueError('Saved library has different work areas.')
    for section,variants in library['sections'].items():
        expected=sorted(g['id'] for g in groups if g['section']==section)
        if not all(sorted(v['groups'])==expected for stream in ['garbage','recycling'] for v in variants[stream]):
            raise ValueError('Saved library has different road passes.')
    return library,groups,anchors_record['anchors']
