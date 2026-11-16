"""Operational truck territories inside preserved planning-section geometry.

Only finite, mapped division lines are candidates. No point sorting, road-name
exceptions, coordinate bisectors or independently routed arbitrary chunks.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from shapely.geometry import Point, shape, mapping
from shapely.ops import unary_union,substring
from shapely.strtree import STRtree

from partition_app.geography import Geography, project, unproject, subdivide, divider_line
from partition_app.continuity import corridors, assess


def best_split(feature,groups,anchors,geography):
    parent=project(shape(feature['geometry']))
    points={ident:project(Point(anchors[ident]['original'])) for g in groups for ident in g['members']}
    candidates=[]
    categories={'community','wide_road','municipal_corridor','broad_corridor','railway','waterway','controlled_road','high_speed_road','park','recreation','mapped_open_land'}
    for f in geography.nearby_features(parent,categories):
        candidates.append({'id':f['id'],'name':f.get('name',f['category']),
            'line':divider_line(f),'kind':f['category'],'rank':0 if f['category']!='community' else 1})
    streets=corridors(geography,parent)
    for road in streets:
        candidates.append({'id':road['id'],'name':road['name'],'line':road['geometry'],
                           'kind':'continuous_city_street','rank':2})
    occupied_parcels=set()
    for point in points.values():
        occupied_parcels.update(int(j) for j in geography.parcel_tree.query(point,predicate='intersects'))
    best=None;counts=Counter()
    def combinations():
        tree=STRtree([r['geometry'] for r in streets])
        for i,a in enumerate(streets):
            for j in tree.query(a['geometry'],predicate='intersects'):
                j=int(j)
                if j<=i:continue
                b=streets[j];cross=a['geometry'].intersection(b['geometry'])
                points_cross=[cross] if cross.geom_type=='Point' else list(cross.geoms) if cross.geom_type=='MultiPoint' else []
                for point in points_cross[:4]:
                    if not parent.covers(point):continue
                    arms=[]
                    for street in [a,b]:
                        line=street['geometry'];distance=line.project(point)
                        arms.append([part for part in [substring(line,0,distance),substring(line,distance,line.length)] if part.geom_type=='LineString' and part.length>10])
                    for left in arms[0]:
                        for right in arms[1]:
                            yield {'id':a['id']+'+'+b['id'],'name':a['name']+' / '+b['name'],
                                'line':unary_union([left,right]),'kind':'connected_city_streets','rank':2.5}
        # Finite park edge plus an intersecting mapped street can form a clean
        # composite divider. No unbounded extension or off-road ray is used.
        for park in geography.nearby_features(parent,{'park','recreation','mapped_open_land'}):
            edge=divider_line(park)
            for road in streets:
                if edge.intersects(road['geometry']):
                    yield {'id':park['id']+'+'+road['id'],'name':park.get('name','Open space')+' / '+road['name'],
                        'line':unary_union([edge,road['geometry']]),'kind':'park_and_city_street','rank':1.5}
    def options():
        yield from candidates
        if best is None:yield from combinations()
    for candidate in options():
        counts['tested']+=1
        try:parts=subdivide(parent,[candidate['line']])
        except ValueError:continue
        if len(parts)<2:continue
        tree=STRtree(parts);owners={}
        for ident,point in points.items():
            hits=tree.query(point,predicate='intersects')
            if not len(hits):
                hits=[i for i,p in enumerate(parts) if p.distance(point)<.03]
            if not len(hits):break
            owners[ident]=min(map(int,hits))
        if len(owners)!=len(points):counts['outside']+=1;continue
        sizes=Counter(owners.values())
        if len(sizes)!=2 or min(sizes.values())<min(100,max(50,len(points)*.1)):continue
        # Empty park interiors or microscopic road-edge slivers must not make
        # a useful two-sided divider fail. Assign them by real shared edge.
        populated=sorted(sizes);combined={i:parts[i] for i in populated}
        pending=[part for i,part in enumerate(parts) if i not in sizes]
        while pending:
            remaining=[];changed=False
            for part in pending:
                share=[(part.boundary.intersection(poly.boundary).length,i) for i,poly in combined.items()]
                length,owner=max(share)
                if length>.01:combined[owner]=combined[owner].union(part);changed=True
                else:remaining.append(part)
            pending=remaining
            if not changed:break
        if pending or any(p.geom_type!='Polygon' for p in combined.values()):continue
        remap={old:new for new,old in enumerate(populated)}
        parts=[combined[i] for i in populated]
        owners={ident:remap[owner] for ident,owner in owners.items()}
        sizes=Counter(owners.values())
        # Every directed road pass stays with one truck work area. A receiver
        # visit can interrupt that pass later, without changing its owner.
        if any(len({owners[x] for x in g['members']})>1 for g in groups):
            counts['street_pass_cut']+=1;continue
        seam=parts[0].boundary.intersection(parts[1].boundary)
        # Do not trade the time target for a boundary through occupied parcels.
        if any(all(geography.parcels[j]['geometry'].intersection(p).area>1 for p in parts)
               for j in occupied_parcels if geography.parcels[j]['geometry'].intersects(seam)):
            counts['occupied_parcel_cut']+=1;continue
        # Alley opposition is checked on the actual local seam, independently
        # of street naming and without assuming collection happens in alleys.
        ids=sorted(points);indexed=[points[x] for x in ids]
        check=assess(seam,{i:owners[x] for i,x in enumerate(ids)},indexed,{},geography)
        if check['alley_side_splits']:
            counts['opposite_alley_sides']+=1;continue
        counts['eligible']+=1
        balance=abs(sizes[0]-sizes[1])/len(points)
        score=candidate['rank']*.12+balance
        if best is None or score<best['score']:
            best={'score':score,'parts':parts,'owners':owners,'sizes':dict(sizes),
                'boundary':{k:v for k,v in candidate.items() if k!='line'},
                'seam':mapping(unproject(seam)),'checks':{'whole_road_passes':True,'occupied_parcels_intact':True,
                                                       'opposite_alley_sides_intact':True}}
    return best,dict(counts)


def subdivide_overlong(partition,groups,anchors,overlong,progress,geography=None):
    if not overlong:return partition,groups,[]
    geography=geography or Geography()
    result=deepcopy(partition);new_groups=deepcopy(groups);features=[];audit=[]
    by_section=defaultdict(list)
    for g in new_groups:
        g.setdefault('parent_section',g['section']);by_section[g['section']].append(g)
    for feature in partition['areas']['features']:
        section=feature['id']
        if section not in overlong:features.append(deepcopy(feature));continue
        progress(None,f"Finding a clean mapped boundary to rebalance work in {section}")
        best,counts=best_split(feature,by_section[section],anchors,geography)
        if best is None:
            features.append(deepcopy(feature));audit.append({'parent':section,'status':'NO_CLEAN_BOUNDARY','candidates':counts});continue
        children=[]
        for i,part in enumerate(best['parts']):
            ident=section+'-'+chr(65+i);children.append(ident)
            child=deepcopy(feature);child['id']=ident
            child['properties'].update(id=ident,parent_section=by_section[section][0]['parent_section'],
                count=best['sizes'][i],address_count=best['sizes'][i],name=feature['properties'].get('name',section)+' / '+chr(65+i),
                routing_boundary=best['boundary']['name'])
            child['geometry']=mapping(unproject(part));features.append(child)
        for g in by_section[section]:g['section']=children[best['owners'][g['members'][0]]]
        audit.append({'parent':section,'status':'SHARED_BY_CLEAN_WORK_AREAS','children':children,
            'counts':[best['sizes'][i] for i in range(2)],'boundary':best['boundary'],
            'seam':best['seam'],'checks':best['checks'],'candidates':counts})
    result['areas']={'type':'FeatureCollection','features':features}
    owner={ident:g['section'] for g in new_groups for ident in g['members']}
    for point in result['points']:point['section']=owner[point['id']]
    return result,new_groups,audit
