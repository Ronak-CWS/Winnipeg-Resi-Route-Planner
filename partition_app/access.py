"""Local collection connectivity on real mapped road nodes, never polygon touch."""
from collections import defaultdict
import heapq
import json
import math
from shapely.geometry import LineString
from shapely.strtree import STRtree
from .geography import FORWARD,ROOT,posted_speed_kmh,line_parts


class RoadAccess:
    def __init__(self,inventory):
        from routing_app.roads import normalized
        self.revision=2
        self.roads=[];self.lines=[];self.names=defaultdict(list)
        self.connectors=[];self.connector_lines=[]
        for r in inventory:
            t=r.get('tags',{});speed=posted_speed_kmh(t)
            if t.get('highway') in {'motorway','trunk','motorway_link','trunk_link'}:continue
            if t.get('construction') not in {None,'no'} or t.get('service') in {'alley','drive-through'}:continue
            if any(t.get(k) in {'no','private','agricultural','forestry','emergency'} for k in ['access','motor_vehicle','motorcar']):continue
            line=LineString([FORWARD.transform(*xy) for xy in r['coords']])
            if speed is not None and (speed>60 or speed>=60 and t.get('highway') in {'primary','secondary'}):
                if line.length<=60:self.connectors.append(r);self.connector_lines.append(line)
                continue
            i=len(self.roads);self.roads.append(r);self.lines.append(line)
            if r.get('name'):self.names[normalized(r['name'])].append(i)
        self.tree=STRtree(self.lines);self.matches={};self.cache={}
        self.connector_tree=STRtree(self.connector_lines)

    def match(self,point,address):
        from routing_app.roads import address_street
        key=(point.x,point.y,address)
        if key not in self.matches:
            named=self.names.get(address_street(address),[])
            nearby=[i for i in named if self.lines[i].distance(point)<=120]
            if not nearby:nearby=[int(i) for i in self.tree.query(point,predicate='dwithin',distance=45)]
            self.matches[key]=min(nearby,key=lambda i:(self.lines[i].distance(point),self.roads[i]['id'])) if nearby else None
        return self.matches[key]

    def components(self,geometry,indices,points,rows):
        key=(geometry.wkb,tuple(sorted(indices)))
        if key in self.cache:return self.cache[key]
        # Offset tolerance accommodates centreline/parcel publication precision;
        # a road leaving the footprint cannot join remote populations elsewhere.
        mask=geometry.buffer(12)
        edges={};parent={}
        def find(n):
            parent.setdefault(n,n)
            while parent[n]!=n:parent[n]=parent[parent[n]];n=parent[n]
            return n
        from shapely.geometry import Point
        for index in self.tree.query(mask,predicate='intersects'):
            i=int(index);line=self.lines[i];original=self.roads[i]['nodes']
            parts=line_parts(line.intersection(mask));edges[i]=[]
            for j,part in enumerate(parts):
                if part.length<.1:continue
                nodes=[]
                for side,xy in enumerate((part.coords[0],part.coords[-1])):
                    p=Point(xy)
                    node=(original[0] if p.distance(Point(line.coords[0]))<.02 else
                        original[1] if p.distance(Point(line.coords[-1]))<.02 else ('clip',i,j,side))
                    nodes.append(node)
                a,b=map(find,nodes)
                if a!=b:parent[b]=a
                edges[i].append((part,nodes[0]))
        groups=defaultdict(set);unknown=set()
        for i in indices:
            road=self.match(points[i],rows[i]['address'])
            if road is None or not edges.get(road):unknown.add(i);continue
            part,node=min(edges[road],key=lambda v:v[0].distance(points[i]))
            if part.distance(points[i])>120:unknown.add(i);continue
            groups[find(node)].add(i)
        value={'groups':sorted(groups.values(),key=lambda v:(-len(v),min(v))),'unknown':unknown,
            'root_members':dict(groups),'node_roots':{n:find(n) for n in parent}}
        self.cache[key]=value
        return value

    def connected(self,left,right,points,rows):
        found=self.components(left['geometry'].union(right['geometry']),left['members']|right['members'],points,rows)
        # Require the dominant populations to connect. A stray address at the
        # seam cannot justify combining two otherwise disconnected suburbs.
        known=(left['members']|right['members'])-found['unknown']
        minimum=lambda r:max(min(3,len(r['members'])),math.floor(len(r['members']&known)*.9))
        if any(len(g&left['members'])>=minimum(left) and len(g&right['members'])>=minimum(right) for g in found['groups']):return True
        # Keep local road populations separate for diagnosis, but permit a
        # real intersection crossing or short stagger between their entrances.
        # The TOTAL arterial travel is capped at 60 m, not each edge: a chain
        # of short source segments must never become a long arterial detour.
        # Rail/water/major-divider vetoes are still applied by every caller.
        starts={n for n,g in found['root_members'].items() if len(g&left['members'])>=minimum(left)}
        ends={n for n,g in found['root_members'].items() if len(g&right['members'])>=minimum(right)}
        if not starts or not ends:return False
        mask=left['geometry'].union(right['geometry']).buffer(12);graph=defaultdict(list)
        for index in self.connector_tree.query(mask,predicate='intersects'):
            i=int(index);line=self.connector_lines[i]
            if line.difference(mask).length>.1:continue
            a,b=[found['node_roots'].get(n,('arterial',n)) for n in self.connectors[i]['nodes']]
            graph[a].append((b,line.length));graph[b].append((a,line.length))
        serial=0;best={n:0. for n in starts};queue=[]
        for n in sorted(starts,key=str):serial+=1;heapq.heappush(queue,(0.,serial,n))
        while queue:
            distance,_,node=heapq.heappop(queue)
            if distance!=best[node]:continue
            if node in ends:return True
            for other,length in graph[node]:
                following=distance+length
                if following>60 or following>=best.get(other,float('inf')):continue
                best[other]=following;serial+=1;heapq.heappush(queue,(following,serial,other))
        return False


def prepare(geography,rows):
    geography.access_rows=rows
    geography.access_point_indices=None
    geography.access_points=None
    geography.access_separations=[]
    # Synthetic/offline geographies can supply an explicit network. Never
    # inject a machine's private city cache into an unrelated fixture.
    if not getattr(geography,'manifest',{}).get('sources') and not hasattr(geography,'access_network'):return
    if getattr(getattr(geography,'access_network',None),'revision',0)<2:
        path=ROOT/'outputs/2026-11-04_monday_map/audit/partition_app/routing-road-inventory.json'
        if path.exists():
            inventory=json.loads(path.read_text(encoding='utf-8'));geography.access_network=RoadAccess(inventory['roads'])
        else:geography.access_network=None
    if geography.access_network:geography.access_network.cache.clear()


def connected(left,right,points,geography):
    if not respects_separations([{'members':left['members']|right['members']}],geography):return False
    network=getattr(geography,'access_network',None)
    if network is None:return None
    return network.connected(left,right,points,geography.access_rows)


def respects_separations(regions,geography):
    """A count reshuffle cannot undo a demonstrated access-based division."""
    for separated in getattr(geography,'access_separations',[]):
        for region in regions:
            if sum(bool(group&region['members']) for group in separated)>1:return False
    return True


def disconnected_count(regions,points,geography):
    network=getattr(geography,'access_network',None)
    if network is None:return 0
    count=0
    for r in regions:
        groups=network.components(r['geometry'],r['members'],points,geography.access_rows)['groups']
        count+=sum(len(g) for g in groups[1:] if len(g)>=max(10,len(r['members'])*.01))
    return count


def review_region(region,points,geography):
    """Report remaining local-road access uncertainty on a final planning area."""
    network=getattr(geography,'access_network',None)
    if network is None:return {'available':False}
    members=region['members'];geometry=region['geometry'];rows=geography.access_rows
    found=network.components(geometry,members,points,rows)
    groups=[g for g in found['groups'] if len(g)>=max(10,len(members)*.01)]
    disconnected=[]
    for group in groups[1:]:
        if not network.connected({'geometry':geometry,'members':groups[0]},
                                 {'geometry':geometry,'members':group},points,rows):
            disconnected.append(len(group))
    return {'available':True,'known_addresses':len(members)-len(found['unknown']),
            'unknown_addresses':len(found['unknown']),
            'significant_component_sizes':[len(g) for g in groups],
            'unconnected_component_sizes':disconnected}


def connected_points(left,right,a,b,geography):
    """Connectivity gate for the initial whole-cell consolidation stage."""
    network=getattr(geography,'access_network',None)
    if network is None:return None
    rows=geography.access_rows
    lookup=getattr(geography,'access_point_indices',None)
    if lookup is None:
        lookup={FORWARD.transform(r['lon'],r['lat']):i for i,r in enumerate(rows)}
        geography.access_point_indices=lookup
    indices_a={lookup[(p.x,p.y)] for p in a if (p.x,p.y) in lookup}
    indices_b={lookup[(p.x,p.y)] for p in b if (p.x,p.y) in lookup}
    if not indices_a or not indices_b:return False
    points=getattr(geography,'access_points',None)
    if points is None:
        from shapely.geometry import Point
        points=[Point(*FORWARD.transform(r['lon'],r['lat'])) for r in rows]
        geography.access_points=points
    return network.connected({'geometry':left,'members':indices_a},{'geometry':right,'members':indices_b},points,rows)
