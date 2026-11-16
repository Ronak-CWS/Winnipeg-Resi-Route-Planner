"""Finite connected road chains, with checked short endpoint completions."""
import hashlib,heapq,math
from collections import defaultdict
from shapely.geometry import Point,LineString
from shapely.ops import unary_union,nearest_points
from .geography import line_parts,canonical


def complete(line,parent,geography):
    """Close a source endpoint on mapped road space, never through property."""
    closures=[]
    if not hasattr(geography,'parcel_tree'):return line
    for part in line_parts(line):
        for xy in [part.coords[0],part.coords[-1]]:
            start=Point(xy);end=nearest_points(start,parent.boundary)[1];gap=start.distance(end)
            if not .001<gap<=8:continue
            path=LineString([start,end])
            if path.difference(parent.buffer(.02)).length>.1:continue
            # Both ends must have mapped roadway support. This also resolves
            # source-centreline endpoints a few centimetres short of a boundary.
            roads=[geography.roads[int(j)]['geometry'] for j in geography.road_tree.query(path.buffer(3),predicate='intersects')]
            if not roads or path.difference(unary_union(roads).buffer(3)).length>.1:continue
            parcels=[geography.parcels[int(j)]['geometry'] for j in geography.parcel_tree.query(path.buffer(.25),predicate='intersects')]
            if any(path.intersection(p.buffer(-.02)).length>1e-6 for p in parcels):continue
            service=getattr(geography,'boundary_service_tree',None)
            if service is not None and any(len(service.query(p,predicate='intersects')) and path.intersection(p.buffer(.25)).length>1 for p in parcels):continue
            closures.append(path)
    return unary_union([line,*closures]) if closures else line


def chains(parent,geography,limit=96):
    """Compare real road paths between separated footprint boundary junctions."""
    base=getattr(geography,'base_roads',geography.roads)
    roads=[r for r in base if r.get('name') and r.get('type')!='BRIDGE' and r['geometry'].intersects(parent)]
    graph=defaultdict(list);edges=[];boundary=parent.boundary
    for road in roads:
        for line in line_parts(complete(road['geometry'],parent,geography).intersection(parent)):
            if line.length<1:continue
            a,b=tuple(line.coords[0]),tuple(line.coords[-1]);index=len(edges);edges.append((line,road))
            graph[a].append((b,index));graph[b].append((a,index))
    ends=sorted([n for n in graph if Point(n).distance(boundary)<.03])
    if len(ends)>64:ends=[ends[round(i*(len(ends)-1)/63)] for i in range(64)]
    found={};minimum=max(250,math.sqrt(parent.area)*.45)
    for source in ends:
        best={(source,''):0.};queue=[(0.,source,'',())];finished=set()
        while queue:
            cost,node,name,path=heapq.heappop(queue)
            if cost!=best.get((node,name)):continue
            if node in ends and node!=source and node not in finished:
                finished.add(node)
                if math.dist(source,node)>=minimum and path:
                    line=unary_union([edges[i][0] for i in path]);key=canonical(line)
                    if line.length<=math.dist(source,node)*2.4 and line.difference(boundary.buffer(12)).length>line.length*.5:
                        sources=[edges[i][1] for i in path]
                        found[key]={'id':'road-chain-'+hashlib.sha256(key.encode()).hexdigest()[:16],
                            'name':' / '.join(dict.fromkeys(r['name'] for r in sources)), 'geometry':line,
                            'road_ids':sorted({r['id'] for r in sources}),'cost':cost,'composite':True}
                continue
            for other,index in graph[node]:
                if index in path:continue
                line,road=edges[index];following=road['name']
                penalty=100 if name and name!=following else 0
                new=cost+line.length+penalty;state=(other,following)
                if new<best.get(state,math.inf):best[state]=new;heapq.heappush(queue,(new,other,following,path+(index,)))
    return sorted(found.values(),key=lambda r:(r['cost'],r['id']))[:limit]
