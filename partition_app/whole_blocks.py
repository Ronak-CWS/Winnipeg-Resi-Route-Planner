"""Last-resort graph regrouping of indivisible, mapped street-frontage blocks."""
import math
from collections import Counter,defaultdict

from shapely.ops import unary_union
from shapely.strtree import STRtree


def regroup(geometry,indices,points,buckets,parcels,geography,lower,upper,progress,diagnostics=None):
    from .engine import protect_cells,merge_geometry,merge_target_regions,assign_unserved_components
    from .balancing import count_cost
    diagnostics={} if diagnostics is None else diagnostics
    def fail(reason):diagnostics['rejected']=reason;return None
    if len(indices)<2*lower or not hasattr(geography,'refine_frontage_cells'):return fail('Not enough demand or mapped frontage geometry')
    root={'name':'Oversized natural area','source_id':'natural-frontage-root','geometry':geometry}
    def report(_pc,message):progress(69,message)
    cells,inventory,_=geography.refine_frontage_cells([root],{0},report)
    diagnostics['mapped_faces']=len(cells)
    selected=set(indices)
    groups={k:[i for i in v if i in selected] for k,v in buckets.items()}
    groups={k:v for k,v in groups.items() if v}
    road_groups={key[1]:v for key,v in groups.items() if key[0]=='ordinary segment'}
    parcel_ids={key[1] for key in groups if key[0]=='parcel'}
    local_parcels={key:p for key,p in parcels.items() if p['id'] in parcel_ids}
    try:row_cell,dsu,reasons,_=protect_cells(cells,points,indices,groups,local_parcels,road_groups,geography.roads)
    except ValueError:return fail('Mapped faces do not contain all reliable points')
    current=merge_geometry(cells,dsu);counts=Counter(dsu.find(row_cell[i]) for i in indices)
    # Attach complete zero-demand faces. Territory is never approximated with
    # hulls or buffers; every output is a union of the original mapped faces.
    for turn in range(len(current)):
        keys=sorted(current);tree=STRtree([current[k] for k in keys]);changed=False
        for empty in [k for k in keys if not counts[k]]:
            if empty not in current:continue
            options=[]
            for j in tree.query(current[empty],predicate='intersects'):
                other=dsu.find(keys[int(j)])
                if other==empty or other not in current or not counts[other]:continue
                shared=current[empty].boundary.intersection(current[other].boundary).length
                if shared>1e-7:options.append((-shared,other))
            if not options:continue
            _,other=min(options);union=current[empty].union(current[other])
            dsu.union(empty,other);owner=dsu.find(empty);total=counts[empty]+counts[other]
            del current[empty],current[other];current[owner]=union;counts[owner]=total;changed=True
        if not changed:break
        if turn%5==0:report(69,'Assigning real road-space faces to complete frontage blocks')
    diagnostics['protected_groups']=len(current)
    diagnostics['empty_faces']=sum(not counts[k] for k in current)
    if diagnostics['empty_faces']:
        diagnostics['unassigned_empty_faces']=[{'area_m2':g.area,'type':g.geom_type,
            'maximum_shared_edge_m':max((g.boundary.intersection(h.boundary).length for k,h in current.items() if k!=key),default=0),
            'nearest_owner_distance_m':min((g.distance(h) for k,h in current.items() if k!=key and counts[k]),default=None)}
            for key,g in current.items() if not counts[key]]
        return fail('Detached empty face remains')
    root_points=defaultdict(list)
    for i in indices:root_points[dsu.find(row_cell[i])].append(points[i])
    assign_unserved_components(current,root_points,local_parcels,reasons,report)
    merge_target_regions(current,counts,dsu,cells,geography,None,float('inf'),reasons,report,
        service_points=root_points,serviced_parcels=local_parcels,consolidate_small=False)
    unit_members=defaultdict(set)
    for i in indices:unit_members[dsu.find(row_cell[i])].add(i)
    root_points={k:[points[i] for i in sorted(v)] for k,v in unit_members.items()}
    assign_unserved_components(current,root_points,local_parcels,reasons,report)
    diagnostics['connected_groups']=len(current)
    diagnostics['group_geometry_types']=dict(Counter(g.geom_type for g in current.values()))
    if any(g.geom_type!='Polygon' for g in current.values()):return fail('A protected frontage is disconnected')
    if len(current)<2:return fail('All mapped faces belong to one protected group')
    diagnostics['coverage_difference_m2']=unary_union(list(current.values())).symmetric_difference(geometry).area
    if diagnostics['coverage_difference_m2']>.5:return fail('Mapped-face coverage changed')
    units={k:current[k] for k in current};unit_counts={k:len(unit_members[k]) for k in current}
    keys=sorted(units);tree=STRtree([units[k] for k in keys]);edges={k:{} for k in keys}
    for a in keys:
        for j in tree.query(units[a],predicate='intersects'):
            b=keys[int(j)]
            if a>=b:continue
            length=units[a].boundary.intersection(units[b].boundary).length
            if length>.1:edges[a][b]=edges[b][a]=length
    n=len(indices);maximum=min(len(units),max(2,int(n/min(400,lower*.5))))
    k=min(range(2,maximum+1),key=lambda count:(count*count_cost(n/count,lower,upper)+.4*(count-1),count))
    regions={u:{'geometry':g,'units':{u},'count':unit_counts[u]} for u,g in units.items()}
    adjacency={u:dict(v) for u,v in edges.items()}
    merges=0
    while len(regions)>k:
        options=[]
        for a,neighbours in adjacency.items():
            for b,length in neighbours.items():
                if a>=b:continue
                na,nb=regions[a]['count'],regions[b]['count'];total=na+nb
                delta=count_cost(total,lower,upper)-count_cost(na,lower,upper)-count_cost(nb,lower,upper)
                shape=length/(math.sqrt(regions[a]['geometry'].area)+math.sqrt(regions[b]['geometry'].area))
                options.append((total>upper,delta,-shape,a,b))
        chosen=None
        for _,_,_,a,b in sorted(options):
            union=regions[a]['geometry'].union(regions[b]['geometry'])
            if union.geom_type=='Polygon':chosen=(a,b,union);break
        if chosen is None:return fail('No contiguous whole-block merge remains')
        a,b,union=chosen;ra,rb=regions.pop(a),regions.pop(b)
        neighbours=(set(adjacency[a])|set(adjacency[b]))-{a,b}
        merged_edges={v:adjacency[a].get(v,0)+adjacency[b].get(v,0) for v in neighbours}
        del adjacency[a],adjacency[b]
        regions[a]={'geometry':union,'units':ra['units']|rb['units'],'count':ra['count']+rb['count']}
        adjacency[a]=merged_edges
        for v,length in merged_edges.items():
            adjacency[v].pop(a,None);adjacency[v].pop(b,None);adjacency[v][a]=length
        merges+=1
        if merges%20==0:report(69,'Grouping intact frontage blocks towards the requested range')
    # Transfer complete atomic blocks only within this one oversized natural
    # area. An existing satisfactory neighbouring natural area is never raided.
    moves=0
    for _ in range(32):
        owners={u:g for g,r in regions.items() for u in r['units']};options=[]
        for u,source in owners.items():
            if len(regions[source]['units'])==1:continue
            for destination in {owners[v] for v in edges[u]}-{source}:
                ns,nd=regions[source]['count'],regions[destination]['count'];weight=unit_counts[u]
                gain=count_cost(ns,lower,upper)+count_cost(nd,lower,upper)-count_cost(ns-weight,lower,upper)-count_cost(nd+weight,lower,upper)
                if gain>.005:options.append((-gain,u,source,destination))
        moved=False
        for _,u,source,destination in sorted(options)[:12]:
            left=regions[source]['units']-{u};right=regions[destination]['units']|{u}
            gs=unary_union([units[v] for v in sorted(left)]);gd=unary_union([units[v] for v in sorted(right)])
            if gs.geom_type!='Polygon' or gd.geom_type!='Polygon':continue
            old_length=regions[source]['geometry'].length+regions[destination]['geometry'].length
            if gs.length+gd.length>old_length+max(200,old_length*.1):continue
            regions[source]={'geometry':gs,'units':left,'count':regions[source]['count']-unit_counts[u]}
            regions[destination]={'geometry':gd,'units':right,'count':regions[destination]['count']+unit_counts[u]}
            moves+=1;moved=True;report(69,'Balancing complete frontage blocks without splitting their streets');break
        if not moved:break
    result=[]
    for _,region in sorted(regions.items()):
        members=set().union(*(unit_members[u] for u in region['units']))
        if len(members)<min(400,lower*.5):return fail('Regrouping leaves a small remnant')
        result.append({'geometry':region['geometry'],'members':members})
    after=sum(count_cost(len(r['members']),lower,upper) for r in result)+.4*(len(result)-1)
    if count_cost(n,lower,upper)-after<.4:return fail('Regrouping does not improve range sufficiently')
    from .geography import internal_seams
    cut=internal_seams(r['geometry'] for r in result)
    parcel_ids=[p['id'] for p in local_parcels.values() if p['geometry'].boundary.intersection(cut).length>1]
    alley_lines=[f['geometry'] for f in geography.nearby_features(cut.buffer(2),{'alley'})]
    alley_length=cut.intersection(unary_union(alley_lines).buffer(2)).length if alley_lines else 0
    return {'regions':result,'cut':cut,'score':after,'parcel_ids':sorted(parcel_ids),
        'mapped_alley_boundary_m':round(alley_length,2),'units':len(units),'moves':moves,
        'inventory':inventory,'protection_reasons':dict(reasons)}
