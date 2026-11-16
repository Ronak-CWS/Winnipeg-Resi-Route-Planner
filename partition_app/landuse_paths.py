"""Complete finite paths combining mapped park edges and checked road space."""
import hashlib,heapq,math
from collections import defaultdict
from shapely.geometry import Point,LineString
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
    nearby=land_features(unary_union(lines).buffer(8),geography)
    if not nearby:return set()
    window=unary_union([f['geometry'] for f in nearby]).buffer(55)
    roads=geography.roads
    if getattr(geography,'land_frontage_roads',None) is not roads:
        geography.land_frontage_roads=roads
        geography.land_frontage_tree=STRtree([r['geometry'] for r in roads])
    eligible={roads[int(j)]['id'] for j in geography.land_frontage_tree.query(window,predicate='intersects')
        if roads[int(j)]['geometry'].intersection(window).length>50}
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
    bridge_lines=[f['geometry'] for f in bridges.values()]
    lines=line_parts(unary_union([road_union,land,*bridge_lines]).intersection(parent))
    mask=unary_union([land,*bridge_lines]).buffer(.1);graph=defaultdict(list);edges=[]
    for line in lines:
        if line.length<.1:continue
        a,b=tuple(line.coords[0]),tuple(line.coords[-1]);index=len(edges)
        support=line.intersection(mask).length/line.length
        weight=line.length*(1-.88*support);edges.append(line)
        graph[a].append((b,index,weight));graph[b].append((a,index,weight))
    ends=sorted(n for n in graph if Point(n).distance(parent.boundary)<.03)
    if len(ends)>80:ends=[ends[round(i*(len(ends)-1)/79)] for i in range(80)]
    found={};minimum=max(250,math.sqrt(parent.area)*.35)
    for source in ends:
        best={source:0.};queue=[(0.,source,())]
        while queue:
            weight,node,path=heapq.heappop(queue)
            if weight!=best.get(node):continue
            if node in ends and node!=source:
                if math.dist(source,node)>=minimum and path:
                    line=unary_union([edges[i] for i in path]);supported=line.intersection(mask).length
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
        used=[f for f in bridges.values() if f['geometry'].intersection(path_mask).length>1]
        geography.boundary_land_completions.update({f['id']:f for f in used})
        output.append({'id':'landuse-path-'+hashlib.sha256(canonical(line).encode()).hexdigest()[:16],
            'name':'Connected mapped park / road-space path','category':'landuse_corridor','rank':3,
            'geometry':line,'evidence':'Finite mapped land-use edges with checked public-road connections',
            'road_space_completions':[f['id'] for f in used]})
    geography.land_path_cache[key]=output
    return output
