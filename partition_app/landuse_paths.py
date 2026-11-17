"""Complete finite paths combining mapped park edges and checked road space."""
import hashlib,heapq,math
from collections import defaultdict
from shapely.geometry import Point,LineString,MultiPolygon
from shapely.ops import unary_union,nearest_points
from shapely.strtree import STRtree
from .geography import line_parts,polygon_parts,canonical
from .boundary_evidence import land_features
from .landuse_split import corridors
from .road_candidates import complete


def frontage_groups(lines,buckets,geography):
    """Allow actual park-gap checks to decide over-broad ordinary road groups.

    This only proposes ordinary-frontage exceptions. Every coordinate/site/
    parcel group remains protected, and assess() must still reject every real
    unsupported street or opposing-alley cut before accepting the alternative.
    """
    if not hasattr(geography,'nearby_features'):return set()
    line=unary_union(lines)
    # Most candidates lie on the grounds themselves. Avoid buffering a large
    # branching outline merely to establish that zero-distance intersection.
    # Seven metres is strictly inside the existing rounded eight-metre mask;
    # the narrow outer band still uses that exact mask, including its corners.
    nearby=[];mask=None
    for feature in land_features(line.envelope.buffer(8),geography):
        distance=feature['geometry'].distance(line)
        if distance>8:continue
        if distance>=7:
            if mask is None:mask=line.buffer(8)
            if not feature['geometry'].intersects(mask):continue
        nearby.append(feature)
    if not nearby:return set()
    roads=geography.roads
    services=getattr(geography,'boundary_service_tree',None)
    if (getattr(geography,'land_frontage_roads',None) is not roads
            or getattr(geography,'land_frontage_services',None) is not services):
        geography.land_frontage_roads=roads
        geography.land_frontage_services=services
        geography.land_frontage_tree=STRtree([r['geometry'] for r in roads])
        geography.land_frontage_cache={}
    key=tuple(sorted((f['id'],f['geometry'].wkb) for f in nearby))
    if key not in geography.land_frontage_cache:
        window=unary_union([f['geometry'] for f in nearby]).buffer(55)
        geography.land_frontage_cache[key]={roads[int(j)]['id']
            for j in geography.land_frontage_tree.query(window,predicate='intersects')
            if roads[int(j)]['geometry'].intersection(window).length>50}
    eligible=geography.land_frontage_cache[key]
    return {key for key in buckets if key[0]=='ordinary segment' and key[1] in eligible}


def candidates(parent,geography,limit=160):
    """Generate mapped park/road paths, never extend a user-drawn separator."""
    if not hasattr(geography,'parcel_tree'):return []
    service_tree=getattr(geography,'boundary_service_tree',None)
    if getattr(geography,'land_path_services',None) is not service_tree:
        geography.land_path_services=service_tree;geography.land_path_cache={}
    if not hasattr(geography,'land_path_cache'):geography.land_path_cache={}
    key=parent.wkb
    if key in geography.land_path_cache:return geography.land_path_cache[key]
    parks=corridors(parent,geography)
    roads=[complete(r['geometry'],parent,geography) for r in getattr(geography,'base_roads',geography.roads)
        if r.get('type')!='BRIDGE' and r['geometry'].intersects(parent)]
    if not parks or not roads:return []
    land=unary_union([f['geometry'] for f in parks]);road_union=unary_union(roads)
    bridges={}
    for feature in land_features(parent,geography):
        for part in polygon_parts(feature['geometry']):
            for xy in part.exterior.coords:
                start=Point(xy);end=nearest_points(start,road_union)[1]
                if not 3<=start.distance(end)<=45:continue
                path=LineString([start,end])
                if path.difference(parent.buffer(.02)).length>.1:continue
                nearby=[geography.parcels[int(j)]['geometry'] for j in geography.parcel_tree.query(path.buffer(.25),predicate='intersects')]
                if any(path.intersection(p.buffer(-.02)).length>1e-6 for p in nearby):continue
                if service_tree is not None and any(len(service_tree.query(p,predicate='intersects'))
                    and path.intersection(p.buffer(.25)).length>1 for p in nearby):continue
                identity='landuse-road-space-'+hashlib.sha256(canonical(path).encode()).hexdigest()[:16]
                bridges[identity]={'id':identity,'category':'landuse_completion','geometry':path,
                    'source_ids':[feature['id']],'length_m':round(path.length,3),
                    'evidence':'Mapped land-use vertex to mapped road through checked empty road space'}
    bridge_values=list(bridges.values())
    bridge_lines=[f['geometry'] for f in bridge_values]
    bridge_tree=STRtree(bridge_lines)
    lines=line_parts(unary_union([road_union,land,*bridge_lines]).intersection(parent))
    mask=unary_union([land,*bridge_lines]).buffer(.1);graph=defaultdict(list);edges=[]
    mask_parts=polygon_parts(mask);mask_tree=STRtree(mask_parts)
    def supported_length(line):
        # Preserve the exact existing mask and component order. Disjoint mask
        # components cannot contribute to this intersection and need not be
        # rebuilt by GEOS for every road segment in the graph.
        hits=sorted(int(i) for i in mask_tree.query(line,predicate='intersects'))
        if not hits:return 0.
        local=mask_parts[hits[0]] if len(hits)==1 else MultiPolygon([mask_parts[i] for i in hits])
        return line.intersection(local).length
    for line in lines:
        if line.length<.1:continue
        a,b=tuple(line.coords[0]),tuple(line.coords[-1]);index=len(edges)
        support=supported_length(line)/line.length
        weight=line.length*(1-.88*support);edges.append(line)
        graph[a].append((b,index,weight));graph[b].append((a,index,weight))
    boundary=parent.boundary
    ends=sorted(n for n in graph if Point(n).distance(boundary)<.03)
    if len(ends)>80:ends=[ends[round(i*(len(ends)-1)/79)] for i in range(80)]
    end_nodes=set(ends)
    found={};minimum=max(250,math.sqrt(parent.area)*.35)
    for source in ends:
        best={source:0.};queue=[(0.,source,())]
        while queue:
            weight,node,path=heapq.heappop(queue)
            if weight!=best.get(node):continue
            if node in end_nodes and node!=source:
                if math.dist(source,node)>=minimum and path:
                    line=unary_union([edges[i] for i in path]);supported=supported_length(line)
                    if line.length<3*math.dist(source,node) and supported>250 and supported>line.length*.35:
                        found[canonical(line)]=(weight,line)
                continue
            for other,index,cost in graph[node]:
                following=weight+cost
                if following<best.get(other,math.inf):
                    best[other]=following;heapq.heappush(queue,(following,other,path+(index,)))
    if not hasattr(geography,'boundary_land_completions'):geography.boundary_land_completions={}
    output=[]
    for _,line in sorted(found.values(),key=lambda v:(v[0],canonical(v[1])))[:limit]:
        path_mask=line.buffer(.1)
        used=[bridge_values[int(i)] for i in sorted(bridge_tree.query(path_mask,predicate='intersects'))
            if bridge_lines[int(i)].intersection(path_mask).length>1]
        geography.boundary_land_completions.update({f['id']:f for f in used})
        output.append({'id':'landuse-path-'+hashlib.sha256(canonical(line).encode()).hexdigest()[:16],
            'name':'Connected mapped park / road-space path','category':'landuse_corridor','rank':3,
            'geometry':line,'evidence':'Finite mapped land-use edges with checked public-road connections',
            'road_space_completions':[f['id'] for f in used]})
    geography.land_path_cache[key]=output
    return output
