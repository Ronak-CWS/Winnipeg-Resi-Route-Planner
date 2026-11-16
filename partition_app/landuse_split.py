"""Complete mapped land-use edges as internal section alternatives."""
import hashlib
from shapely.geometry import LineString,Point
from shapely.strtree import STRtree
from shapely.ops import unary_union
from .geography import canonical
from .boundary_evidence import land_features
from .landuse_candidates import road_space_completions


def between_completions(parent,left,right,geography):
    """Join mapped land-use vertices only across corroborated empty road space."""
    if not hasattr(geography,'parcel_tree') or left.distance(right)>45:return []
    from .geography import polygon_parts
    a=sorted({tuple(xy) for p in polygon_parts(left) for xy in p.exterior.coords})
    b=sorted({tuple(xy) for p in polygon_parts(right) for xy in p.exterior.coords})
    if not a or not b:return []
    tree=STRtree([Point(xy) for xy in b]);pairs=[]
    for xy in a:
        point=Point(xy)
        for j in tree.query(point,predicate='dwithin',distance=45):
            other=b[int(j)];length=point.distance(Point(other))
            if 3<=length<=45:pairs.append((length,xy,other))
    found=[]
    for _,a,b in sorted(pairs):
        line=LineString([a,b])
        if line.difference(parent.buffer(.02)).length>.1:continue
        roads=[geography.roads[int(j)] for j in geography.road_tree.query(line.buffer(2),predicate='intersects')]
        if not any(line.distance(r['geometry'])<2 for r in roads):continue
        parcels=[geography.parcels[int(j)]['geometry'] for j in geography.parcel_tree.query(line.buffer(.25),predicate='intersects')]
        if any(line.intersection(p.buffer(-.02)).length>.1 for p in parcels):continue
        services=getattr(geography,'boundary_service_tree',None)
        if services is not None and any(len(services.query(p,predicate='intersects')) and line.intersection(p.buffer(.25)).length>1 for p in parcels):continue
        if any(line.hausdorff_distance(f['geometry'])<3 for f in found):continue
        identity='landuse-road-space-'+hashlib.sha256(canonical(line).encode()).hexdigest()[:16]
        found.append({'id':identity,'category':'landuse_completion','geometry':line,
            'evidence':'Two mapped land-use vertices across checked public road space','length_m':round(line.length,3)})
        if len(found)>=3:break
    if not hasattr(geography,'boundary_land_completions'):geography.boundary_land_completions={}
    geography.boundary_land_completions.update({f['id']:f for f in found})
    return found


def corridors(parent, geography):
    features = land_features(parent, geography)
    features = [f for f in features if f['geometry'].intersection(parent).area>1]
    # A thin strip already following the outside of the parent cannot provide
    # a useful internal separator. Do not pull unrelated boundary road space
    # into a school/park chain merely because its corner is nearby.
    interior=parent.buffer(-45)
    features=[f for f in features if f['geometry'].intersection(interior).area>
        max(100,f['geometry'].intersection(parent).area*.1)]
    components = []
    pending = set(range(len(features)))
    while pending:
        seed = min(pending); pending.remove(seed)
        group = {seed}; todo = [seed]
        while todo:
            current = todo.pop()
            linked = {j for j in pending if features[current]['geometry'].intersects(features[j]['geometry'])}
            group.update(linked); pending.difference_update(linked); todo.extend(sorted(linked))
        components.append([features[j] for j in sorted(group)])
    groups=[(group,[]) for group in components]
    geometries=[unary_union([f['geometry'] for f in group]) for group in components]
    links={i:set() for i in range(len(components))};bridges={}
    for i,left in enumerate(geometries):
        for j,right in enumerate(geometries[i+1:],i+1):
            closures=between_completions(parent,left,right,geography)
            if closures:links[i].add(j);links[j].add(i);bridges[i,j]=closures
    pending=set(links)
    while pending:
        start=min(pending);joined={start};todo=[start];pending.remove(start)
        while todo:
            extra=links[todo.pop()]&pending;joined.update(extra);pending.difference_update(extra);todo.extend(sorted(extra))
        if len(joined)>1:
            group=[f for i in sorted(joined) for f in components[i]]
            closures=[f for (i,j),values in bridges.items() if i in joined and j in joined for f in values]
            groups.append((group,closures))
    result = []
    for group,bridges in groups:
        grounds = unary_union([f['geometry'] for f in group])
        # Public park outlines can overlap the edge of a residential lot.
        # Remove serviced property components rather than cutting through them
        # or expanding institutional grounds onto a neighbouring property.
        services=getattr(geography,'boundary_service_tree',None)
        if services is not None and hasattr(geography,'parcel_tree'):
            from .geography import polygon_parts
            occupied=[part for j in geography.parcel_tree.query(grounds,predicate='intersects')
                for part in polygon_parts(geography.parcels[int(j)]['geometry'])
                if len(services.query(part,predicate='intersects'))]
            if occupied:grounds=grounds.difference(unary_union(occupied))
        identity='landuse-union-'+hashlib.sha256('|'.join(sorted(f['id'] for f in group)).encode()).hexdigest()[:16]
        closures = road_space_completions(parent,[{'id':identity,'geometry':grounds}],geography)+bridges
        line = unary_union([grounds.boundary, *[f['geometry'] for f in closures]])
        if line.intersection(parent).length<100:
            continue
        sources = sorted(f['id'] for f in group)
        result.append({'id':'landuse-corridor-'+hashlib.sha256((canonical(line)+'|'.join(sources)).encode()).hexdigest()[:16],
            'name':' / '.join(sorted({f.get('name','') for f in group if f.get('name')})) or 'Mapped open-land corridor',
            'category':'landuse_corridor','rank':3,'geometry':line,'source_ids':sources,
            'evidence':'Complete connected mapped school/park/commercial edges with checked road-space completions',
            'road_space_completions':[f['id'] for f in closures]})
    return sorted(result,key=lambda f:f['id'])
