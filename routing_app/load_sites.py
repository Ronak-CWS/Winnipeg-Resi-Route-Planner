"""Keep truck territories whole while allowing a real RF trip during a road pass."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import json


def endpoint_key(point):
    return (*point['coordinate'],point.get('bearing'))


def expand_passes(groups,anchors,core,cfg):
    atoms=[];paths={};edges={};expansion={}
    for group in groups:
        sites=[]
        for ident in group['members']:
            anchor=anchors[ident]
            if sites and endpoint_key(sites[-1]['end'])==endpoint_key(anchor):
                sites[-1]['members'].append(ident);sites[-1]['count']+=1
            else:
                sites.append({**group,'id':group['id']+':p'+str(len(sites)+1),
                    'road_pass':group['id'],'members':[ident],'count':1,'start':anchor,'end':anchor})
        if len(core[group['id']]['legs'])!=max(0,len(sites)-1):
            raise ValueError('Pickup sites do not match the directed road replay.')
        joins=[]
        for a,b,path in zip(sites,sites[1:],core[group['id']]['legs']):
            edges[endpoint_key(a['end']),endpoint_key(b['start'])]=path
            joins.append(path['seconds']/cfg['active_speed_factor']+path['reversals']*cfg['reversal_seconds'])
        for site in sites:
            paths[site['id']]={'seconds':0.,'meters':0.,'reversals':0,'geometry':[]}
        atoms.extend(sites);expansion[group['id']]=([s['id'] for s in sites],joins)
    return atoms,paths,edges,expansion


def expand_library(library,atoms,expansion,road,sites,cache,progress):
    key=hashlib.sha256(json.dumps([[a['id'],endpoint_key(a['start'])] for a in atoms]).encode()).hexdigest()
    key=hashlib.sha256((key+json.dumps(sites,sort_keys=True)).encode()).hexdigest()
    path=cache/f'routing-{key}.site-gateways.json'
    if path.exists():
        gateways=json.loads(path.read_text())
    else:
        progress(None,'Calculating receiver access at physical pickup sites; street ownership stays intact')
        enter,_=road.table([sites['yard'],sites['garbage'],sites['recycling']],[a['start'] for a in atoms])
        leave,_=road.table([a['end'] for a in atoms],[sites['garbage'],sites['recycling']])
        gateways={'dispatch':{a['id']:float(enter[0,i]) for i,a in enumerate(atoms)},'from_rf':{},'to_rf':{}}
        for s,stream in enumerate(['garbage','recycling']):
            gateways['from_rf'][stream]={a['id']:float(enter[s+1,i]) for i,a in enumerate(atoms)}
            gateways['to_rf'][stream]={a['id']:float(leave[i,s]) for i,a in enumerate(atoms)}
        from .engine import dump
        dump(path,gateways)
    result={**library,**gateways,'sections':deepcopy(library['sections'])}
    for section in result['sections'].values():
        for variants in section.values():
            for variant in variants:
                ids=[];joins=[]
                for i,g in enumerate(variant['groups']):
                    if i:joins.append(variant['joins'][i-1])
                    children,within=expansion[g]
                    ids.extend(children);joins.extend(within)
                variant.update(groups=ids,joins=joins)
    return result
