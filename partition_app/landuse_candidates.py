"""Move complete frontage blocks onto nearby mapped school/land-use edges.

Only existing parcel/road faces and validated finite road-junction closures are
used. A minimum cut proposes alternatives; ordinary continuity, count, parcel,
ownership and major-barrier gates still decide whether one may be accepted.
"""
from collections import defaultdict
from ortools.graph.python import max_flow
import hashlib
from shapely.geometry import Point,LineString
from shapely.ops import unary_union,nearest_points
from shapely.strtree import STRtree
from .geography import canonical,divider_line,shared_boundary,internal_seams,polygon_parts
from .boundary_evidence import land_features,profile,prepare


def road_space_completions(parent,features,geography):
    """Close a mapped land-use edge across empty road space, never a property."""
    if not hasattr(geography,'parcel_tree'):return []
    results={}
    for f in features:
        for part in polygon_parts(f['geometry']):
            for xy in part.exterior.coords:
                start=Point(xy);end=nearest_points(start,parent.boundary)[1]
                if not 3<=start.distance(end)<=45:continue
                roads=[geography.roads[int(j)]['geometry'] for j in geography.road_tree.query(end.buffer(2),predicate='intersects')]
                if not roads:continue
                line=LineString([start,end])
                if line.difference(parent.buffer(.02)).length>.1:continue
                nearby=[geography.parcels[int(j)]['geometry'] for j in geography.parcel_tree.query(line.buffer(.25),predicate='intersects')]
                if any(line.intersection(p.buffer(-.02)).length>.1 for p in nearby):continue
                # A line between two property lots is not empty road space.
                # Do not turn a serviced parcel's side boundary into supporting
                # evidence for a mid-block cut simply because interiors miss it.
                service_tree=getattr(geography,'boundary_service_tree',None)
                if service_tree is not None and any(
                    len(service_tree.query(p,predicate='intersects')) and line.intersection(p.buffer(.25)).length>1
                    for p in nearby):continue
                identifier='landuse-road-space-'+hashlib.sha256(canonical(line).encode()).hexdigest()[:16]
                results[identifier]={'id':identifier,'category':'landuse_completion','geometry':line,
                    'source_ids':[f['id']],'evidence':'Finite mapped land-use corner to existing road boundary through empty road space',
                    'length_m':round(line.length,3)}
    if not hasattr(geography,'boundary_land_completions'):geography.boundary_land_completions={}
    geography.boundary_land_completions.update(results)
    return list(results.values())


def candidates(left,right,points,buckets,parcels,geography):
    if not hasattr(geography,'refine_frontage_cells'):return []
    parent=left['geometry'].union(right['geometry']);seam=shared_boundary(left['geometry'],right['geometry'])
    nearby=land_features(seam.buffer(140),geography)
    if not nearby or sum(divider_line(f).intersection(seam.buffer(140)).length for f in nearby)<150:return []
    from .engine import protect_cells,merge_geometry
    members=left['members']|right['members']
    root={'name':'Mapped land-use boundary comparison','source_id':'landuse-frontages','geometry':parent}
    completions=road_space_completions(parent,nearby,geography)
    cells,inventory,_=geography.refine_frontage_cells([root],{0},extra_lines=[f['geometry'] for f in completions])
    local_buckets={k:[i for i in v if i in members] for k,v in buckets.items()}
    local_buckets={k:v for k,v in local_buckets.items() if v}
    # A long street segment can span a genuine school/park gap. Let proposals
    # consider its complete parcels independently near such evidence; the
    # original full groups still feed the street/alley acceptance check.
    road_by_id={r['id']:r for r in geography.roads}
    gap_window=unary_union([f['geometry'] for f in nearby]).buffer(55)
    flexible={key for key in local_buckets if key[0]=='ordinary segment' and key[1] in road_by_id
        and road_by_id[key[1]]['geometry'].intersection(gap_window).length>50}
    protected={key:v for key,v in local_buckets.items() if key not in flexible}
    local_parcels={k:p for k,p in parcels.items() if any(key[:2]==('parcel',p['id']) for key in local_buckets)}
    try:row_cell,dsu,_,_=protect_cells(cells,points,sorted(members),protected,local_parcels,{},geography.roads)
    except ValueError:return []
    units=merge_geometry(cells,dsu);keys=sorted(units);indices={k:i for i,k in enumerate(keys)}
    unit_members=defaultdict(set)
    for i in members:unit_members[dsu.find(row_cell[i])].add(i)
    masks=prepare(parent,geography);old_profile=profile(seam,geography,masks)
    tree=STRtree([units[k] for k in keys]);edges=[]
    for a in keys:
        for j in tree.query(units[a],predicate='intersects'):
            b=keys[int(j)]
            if b<=a:continue
            edge=shared_boundary(units[a],units[b])
            if edge.length<.05:continue
            strength=profile(edge,geography,masks)['strength']
            edges.append((indices[a],indices[b],max(1,round(100*edge.length*((1-strength)**2+.02)))))
    old={k:(0 if units[k].intersection(left['geometry']).area>=units[k].intersection(right['geometry']).area else 1) for k in keys}
    anchors={k:old[k] for k in keys if units[k].distance(seam)>140}
    # Keep a deep original service group on each bank even in narrow parents.
    for side,region in enumerate((left,right)):
        options=[k for k in keys if unit_members[k] and unit_members[k]<=region['members']]
        if not options:return []
        best=max(options,key=lambda k:min(points[i].distance(seam) for i in unit_members[k]))
        anchors[best]=side
    outputs=[];seen=set();source=len(keys);sink=source+1
    for movement in (.01,.1,.5,2.):
        flow=max_flow.SimpleMaxFlow()
        for a,b,cost in edges:
            flow.add_arc_with_capacity(a,b,cost);flow.add_arc_with_capacity(b,a,cost)
        for k in keys:
            index=indices[k];cost=max(1,round(100*movement*(units[k].area/100+10*len(unit_members[k]))))
            costs=[cost if old[k]!=side else 0 for side in (0,1)]
            if k in anchors:costs[1-anchors[k]]=10**12
            flow.add_arc_with_capacity(source,index,costs[1]);flow.add_arc_with_capacity(index,sink,costs[0])
        if flow.solve(source,sink)!=flow.OPTIMAL:continue
        side=set(flow.get_source_side_min_cut());groups=[[k for k in keys if (indices[k] in side)==(s==0)] for s in (0,1)]
        if not all(groups):continue
        children=[{'geometry':unary_union([units[k] for k in group]),
            'members':set().union(*(unit_members[k] for k in group))} for group in groups]
        # Keep the original edge wherever no service ownership changes. Empty
        # road-space slivers must not introduce unrelated intersection detours.
        for side,original in enumerate((left,right)):
            removed=original['members']-children[side]['members']
            patches=[p for p in polygon_parts(original['geometry'].difference(children[side]['geometry']))
                if any(p.covers(points[i]) for i in removed)]
            transfer=unary_union(patches)
            if side==0:new_left=left['geometry'].difference(transfer);new_right=right['geometry'].union(transfer)
            else:new_right=new_right.difference(transfer);new_left=new_left.union(transfer)
        children[0]['geometry'],children[1]['geometry']=new_left,new_right
        if any(c['geometry'].geom_type!='Polygon' or not c['geometry'].is_valid or not c['members'] for c in children):continue
        cut=internal_seams(c['geometry'] for c in children);key=canonical(cut)
        if key in seen or cut.hausdorff_distance(seam)<.1:continue
        seen.add(key)
        if unary_union([c['geometry'] for c in children]).symmetric_difference(parent).area>.5:continue
        if any(not c['geometry'].covers(points[i]) for c in children for i in c['members']):continue
        if any(sum(p['geometry'].intersection(c['geometry']).area>max(4,p['geometry'].area*.02) for c in children)>1 for p in local_parcels.values()):continue
        strength=profile(cut,geography,masks)
        if strength['landuse_m']<old_profile['landuse_m']+50:continue
        outputs.append({'children':children,'geometry':cut,'source_ids':strength['source_ids'],
            'strength':strength,'mapped_faces':len(cells),'movement_weight':movement,
            'flexible_groups':flexible,
            'road_space_completions':[{'id':f['id'],'length_m':f['length_m'],'source_ids':f['source_ids']} for f in completions if f['geometry'].intersection(cut.buffer(.1)).length>1],
            'junction_connectors':sum(len(v.get('junction_connectors',[])) for v in inventory)})
    return outputs
