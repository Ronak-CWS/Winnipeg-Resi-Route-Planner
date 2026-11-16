"""Penalise split street runs and opposite sides of a mapped rear alley.

Mapped alley proximity is a conservative quality signal, never pickup evidence.
Continuous City street/division corridors can replace a worse last-resort seam.
"""
import hashlib
import math
from collections import defaultdict

from shapely.geometry import Point
from shapely.ops import linemerge, unary_union, substring
from shapely.strtree import STRtree

from .geography import canonical, divider_line, line_parts, street_name, subdivide, internal_seams, shared_boundary

BREAK_PENALTY = 1000.0


def neighbourhood_division_cost(seam,footprint):
    """Discourage long internal seams through an otherwise compact territory.

    This is a shape preference, not a street-cut violation. A finite supported
    replacement still has to preserve parcels and complete frontage groups.
    """
    ratio=seam.length/max(math.sqrt(footprint.area),1)
    return seam.length/1000+10*max(0,ratio-1.8)**2


def _points(geometry):
    if geometry.is_empty:return []
    if geometry.geom_type=='Point':return [geometry]
    if geometry.geom_type=='LineString':return [Point(geometry.coords[0]),Point(geometry.coords[-1])]
    return [p for part in getattr(geometry,'geoms',[]) for p in _points(part)]


def corridors(geography, geometry):
    named=defaultdict(list);search=geometry.buffer(100)
    base=getattr(geography,'base_roads',geography.roads)
    if getattr(geography,'continuity_road_source',None) is not base:
        geography.continuity_road_source=base
        geography.continuity_road_tree=STRtree([r['geometry'] for r in base])
    for j in geography.continuity_road_tree.query(search, predicate='intersects'):
        road=base[int(j)]
        if road.get('name') and road.get('type')!='BRIDGE' and road['geometry'].intersects(search):
            named[street_name(road['name'])].append(road)
    result=[]
    for name,roads in sorted(named.items()):
        network=unary_union([r['geometry'] for r in roads])
        joined=linemerge(network) if network.geom_type=='MultiLineString' else network
        for line in line_parts(joined):
            result.append({'name':roads[0]['name'],'key':name,'geometry':line,
                'id':'continuity-road-'+hashlib.sha256((name+canonical(line)).encode()).hexdigest()[:16],
                'road_ids':[r['id'] for r in roads if r['geometry'].intersection(line.buffer(.03)).length>1]})
    return result


def composite_corridors(roads,geometry,limit=48):
    """Two intersecting mapped street arms; no extended rays or invented links."""
    found={};tree=STRtree([r['geometry'] for r in roads])
    for i,a in enumerate(roads):
        for j in tree.query(a['geometry'],predicate='intersects'):
            j=int(j)
            if j<=i:continue
            b=roads[j];cross=a['geometry'].intersection(b['geometry'])
            if cross.geom_type not in {'Point','MultiPoint'}:continue
            for point in ([cross] if cross.geom_type=='Point' else cross.geoms):
                if not geometry.contains(point):continue
                arms=[]
                for road in (a,b):
                    line=road['geometry'];position=line.project(point)
                    arms.append([p for p in [substring(line,0,position),substring(line,position,line.length)]
                        if p.geom_type=='LineString' and p.length>20
                        and p.intersects(geometry.boundary)])
                for left in arms[0]:
                    for right in arms[1]:
                        line=unary_union([left,right]);inside=line.intersection(geometry)
                        if inside.length<250:continue
                        key=canonical(line)
                        found[key]={'id':'continuity-composite-'+hashlib.sha256(key.encode()).hexdigest()[:16],
                            'name':a['name']+' / '+b['name'],'key':a['key']+' / '+b['key'],'geometry':line,
                            'road_ids':sorted(set(a['road_ids']+b['road_ids'])),'composite':True,'inside_m':inside.length}
    return sorted(found.values(),key=lambda r:(r['inside_m'],r['id']))[:limit]


def split_frontage_buckets(buckets, allowed, ownership):
    """Scope a permitted longitudinal exception to its actual child frontages.

    Deleting the entire road group also removed protection from houses outside
    the chosen pair. Keep every unmodified group and each resulting curb group.
    """
    for key in allowed:
        if key not in buckets:
            continue
        members=buckets.pop(key)
        groups=defaultdict(list)
        for i in members:
            groups[ownership.get(i, 'outside')].append(i)
        for group in groups.values():
            suffix=hashlib.sha256(','.join(map(str, sorted(group))).encode()).hexdigest()[:16]
            buckets[(key[0], key[1], suffix)]=group


def assess(seam, ownership, points, buckets, geography, supported=None):
    """A single unjustified street/alley split outweighs small count gains."""
    if seam.is_empty:return {'penalty':0.,'street_breaks':[],'alley_side_splits':[],'unsupported_metres':0.}
    indices=sorted(ownership);tree=STRtree([points[i] for i in indices])
    buffers={distance:seam.buffer(distance) for distance in (2,3,4,8,16)}
    nearby=geography.nearby_features(buffers[8],{'railway','waterway','controlled_road','high_speed_road','wide_road','municipal_corridor','broad_corridor','park','recreation','mapped_open_land','landuse'})
    from .boundary_evidence import land_features
    nearby+=land_features(buffers[8],geography)
    nearby.extend(f for f in getattr(geography,'boundary_land_completions',{}).values() if f['geometry'].intersects(buffers[8]))
    support=[supported] if supported is not None else []
    for f in nearby:
        if f['category']=='landuse' and f.get('tags',{}).get('landuse') not in {'commercial','retail','industrial','railway'}:continue
        line=divider_line(f)
        if line.intersection(buffers[2]).length>20:support.append(line)
    # Only evidence within eight metres can affect this seam. Clip to a
    # sixteen-metre search window before buffering: repeatedly buffering
    # entire municipal/park perimeters dominated neighbour comparisons.
    search=buffers[16]
    support_line=unary_union([g.intersection(search) for g in support]);support_mask=support_line.buffer(8)
    streets=corridors(geography,seam.envelope.buffer(120))
    # A boundary following another mapped street through an intersection is
    # valid. A coincident intersection alone is insufficient: require actual
    # alignment of the boundary with that street on either side of the node.
    aligned_streets=[(r,r['geometry'].intersection(buffers[2])) for r in streets]
    aligned_streets=[(r,g) for r,g in aligned_streets if g.length>20]
    road_support=unary_union([g for _,g in aligned_streets]).buffer(8)
    municipal=unary_union([divider_line(f).intersection(search)
        for f in geography.nearby_features(buffers[8],{'community'})]).buffer(8)
    # Administrative evidence can support shape, but cannot excuse a street cut.
    unsupported=seam.difference(support_mask.union(road_support).union(municipal)).length
    by_name=defaultdict(set);road_by_id={r['id']:r for r in geography.roads}
    for key,members in buckets.items():
        if key[0]=='ordinary segment' and key[1] in road_by_id:
            by_name[street_name(road_by_id[key[1]]['name'])].update(i for i in members if i in ownership)
    street_breaks=[];road_following_intersections=[]
    for road in streets:
        line=road['geometry'];members=by_name[road['key']]
        if len({ownership[i] for i in members})<2:continue
        seen=[]
        # Projection/overlay round trips can leave a shared-edge endpoint a few
        # nanometres short of the road. A 3 cm topological tolerance must not
        # make that real transverse frontage cut disappear from assessment.
        for cross in _points(line.intersection(seam.buffer(.03))):
            if support_mask.covers(cross) or any(cross.distance(p)<10 for p in seen):continue
            d=line.project(cross)
            if d<15 or line.length-d<15:continue
            # Overlay noding returns endpoints along coincident line pieces.
            # Continuing along this same street is not a transverse cut.
            # Require alignment on both sides so a mid-block departure from
            # the road still reaches the protection checks below.
            local=substring(line,max(0,d-12),min(line.length,d+12))
            alignment=local.intersection(buffers[2]).length/max(local.length,1e-6)
            if alignment>=.8:
                continue
            before=[];after=[]
            for i in members:
                if points[i].distance(cross)>120:continue
                along=line.project(points[i])-d
                if along < -8:before.append((points[i].distance(cross),i))
                if along > 8:after.append((points[i].distance(cross),i))
            pairs=[(min(before)[1],min(after)[1])] if before and after else []
            if alignment>=.4:
                # At a three-area junction a shared road-following edge ends
                # on one side of the node. Comparing its opposite curbs invents
                # a transverse cut. Only a change along the same curb is a
                # break here; a genuinely transverse edge keeps the usual test.
                def curb(i):
                    p=points[i];position=line.project(p);on=line.interpolate(position)
                    if p.distance(line)<1:return 0
                    u=line.interpolate(max(0,position-2));v=line.interpolate(min(line.length,position+2))
                    return 1 if (v.x-u.x)*(p.y-on.y)-(v.y-u.y)*(p.x-on.x)>0 else -1
                sides={i:curb(i) for _,i in before+after};pairs=[]
                for side in (-1,1):
                    aa=[item for item in before if sides[item[1]] in {0,side}]
                    bb=[item for item in after if sides[item[1]] in {0,side}]
                    if aa and bb:pairs.append((min(aa)[1],min(bb)[1]))
            for a,b in pairs:
                if ownership[a]!=ownership[b]:
                    followed=[r['name'] for r,g in aligned_streets if r['key']!=road['key'] and g.distance(cross)<8]
                    if followed:
                        road_following_intersections.append({'road':road['name'],'boundary_roads':sorted(set(followed)),
                            'crossing':[round(cross.x,2),round(cross.y,2)],'members':[a,b]})
                        seen.append(cross);break
                    others=[r['name'] for r in getattr(geography,'base_roads',geography.roads)
                        if r.get('name') and street_name(r['name'])!=road['key'] and r['geometry'].distance(cross)<.05]
                    street_breaks.append({'road':road['name'],'road_id':road['id'],'members':[a,b],
                        'crossing_type':'mapped_intersection' if others else 'between_intersections',
                        'crossing_roads':sorted(set(others)),
                        'crossing':[round(cross.x,2),round(cross.y,2)]});seen.append(cross);break
    alley_splits=[]
    for feature in geography.nearby_features(buffers[4],{'alley'}):
        for line in line_parts(feature['geometry']):
            overlap=seam.intersection(line.buffer(3)).length
            if overlap<max(10,min(25,line.length*.3)):continue
            # A long lane can extend beyond the boundary and have mixed owners
            # on both sides globally. Compare opposing houses locally along
            # the actual aligned portion instead of cancelling those splits.
            split=None
            for matched in line_parts(line.intersection(buffers[3])):
                if matched.length<10:continue
                samples=max(1,math.ceil(matched.length/40))
                for sample in range(samples):
                    centre=matched.interpolate((sample+.5)/samples,normalized=True);position=line.project(centre)
                    sides={-1:[],1:[]}
                    for j in tree.query(centre.buffer(61),predicate='intersects'):
                        i=indices[int(j)];point=points[i];d=line.project(point);distance=point.distance(line)
                        if abs(d-position)>35 or not .5<d<line.length-.5 or not 1<=distance<=50:continue
                        p=line.interpolate(d);a,b=line.interpolate(max(0,d-2)),line.interpolate(min(line.length,d+2))
                        sign=(b.x-a.x)*(point.y-p.y)-(b.y-a.y)*(point.x-p.x)
                        sides[1 if sign>0 else -1].append((point.distance(centre),i))
                    if sides[-1] and sides[1]:
                        left,right=min(sides[-1])[1],min(sides[1])[1]
                        if ownership[left]!=ownership[right]:
                            split={'alley_id':feature['id'],'aligned_metres':round(overlap,2),
                                'side_members':[[left],[right]],'sample':[round(centre.x,2),round(centre.y,2)]};break
                if split:break
            if split:alley_splits.append(split)
    penalty=BREAK_PENALTY*(len(street_breaks)+len(alley_splits))+unsupported*.05
    return {'penalty':round(penalty,5),'street_breaks':street_breaks,'alley_side_splits':alley_splits,
        'road_following_intersections':road_following_intersections,
        'unsupported_metres':round(unsupported,2)}


def improve(regions,points,buckets,parcels,geography,lower,upper,ledger,evidence,progress):
    """Repair bad seams and excessive weak divisions using finite City streets."""
    from .balancing import count_cost
    audit={'changes':[],'candidates':0,'remaining':[],'candidate_decisions':[]}
    road_by_id={r['id']:r for r in geography.roads}
    hood_values=getattr(geography,'neighbourhoods',[])
    broad_names={street_name(f.get('name')) for f in getattr(geography,'features',[])
        if f.get('name') and f['category'] in {'wide_road','high_speed_road','controlled_road','municipal_corridor','broad_corridor'}}
    quality_cache={}
    def pair_score(left,right):
        key=tuple(sorted((canonical(left['geometry']),canonical(right['geometry']))))
        if key in quality_cache:return quality_cache[key]
        seam=shared_boundary(left['geometry'],right['geometry'])
        if seam.length<1:return 0.
        ownership={i:0 for i in left['members']}|{i:1 for i in right['members']}
        quality=assess(seam,ownership,points,buckets,geography)
        from .boundary_evidence import profile
        value=quality['penalty']+neighbourhood_division_cost(seam,left['geometry'].union(right['geometry']))+profile(seam,geography)['preference_cost']
        quality_cache[key]=value
        return value
    def affected_score(a,b,left,right):
        from .service_shape import cost as shape_cost
        return (count_cost(len(left['members']),lower,upper)+count_cost(len(right['members']),lower,upper)
            +shape_cost([left,right],points,geography)
            +pair_score(left,right)+sum(pair_score(r,left)+pair_score(r,right)
                for k,r in enumerate(regions) if k not in {a,b}))
    seen={tuple(sorted(canonical(r['geometry']) for r in regions))}
    for _ in range(min(64,max(8,len(regions)*2))):
        options=[]
        for a,ra in enumerate(regions):
            for b in range(a+1,len(regions)):
                rb=regions[b]
                seam=shared_boundary(ra['geometry'],rb['geometry'])
                if seam.length<20:continue
                union=ra['geometry'].union(rb['geometry'])
                if union.geom_type!='Polygon':continue
                # Major barriers remain outside the replaceable footprint.
                from .balancing import hard_separator
                if hard_separator(union,[points[i] for i in ra['members']|rb['members']],geography):continue
                ownership={i:a for i in ra['members']}|{i:b for i in rb['members']}
                current_support=ra.get('continuity_support') if ra.get('continuity_corridor')==rb.get('continuity_corridor') else None
                before=assess(seam,ownership,points,buckets,geography,current_support)
                conflicts=len(before['street_breaks'])+len(before['alley_side_splits'])
                from .boundary_evidence import profile
                physical=profile(seam,geography)
                excessive_weak_seam=seam.length>1.8*math.sqrt(union.area) and physical.get('landuse_m',0)<seam.length*.5
                # Valid street-following seams can still be weaker than an
                # available broad corridor. Compare their evidence separately
                # instead of inventing a mid-block-cut violation.
                broad_here=geography.nearby_features(seam.buffer(8),{'wide_road','municipal_corridor','broad_corridor'})
                broad_mask=unary_union([divider_line(f) for f in broad_here]).buffer(8)
                weak_road_seam=physical.get('ordinary_road_m',0)>250 and seam.intersection(broad_mask).length<seam.length*.5
                if not conflicts and not excessive_weak_seam and not weak_road_seam:continue
                old_cost=affected_score(a,b,ra,rb)
                hood_edges=unary_union([h['geometry'].boundary for h in hood_values if h['geometry'].intersects(union)])
                hood_mask=hood_edges.buffer(8)
                streets=corridors(geography,union)
                for road in streets+composite_corridors(streets,union):
                    from .road_candidates import complete
                    line=complete(road['geometry'],union,geography);inside=line.intersection(union)
                    if inside.length<250:continue
                    alignment=inside.intersection(hood_mask).length/max(inside.length,1)
                    audit['candidates']+=1
                    decision={'road':road['name'],'municipal_alignment':round(alignment,4),
                        'parent_counts':[len(ra['members']),len(rb['members'])],'state':'REJECTED','reason':'No eligible complete division'}
                    audit['candidate_decisions'].append(decision)
                    try:parts=subdivide(union,[line])
                    except ValueError:continue
                    part_members=defaultdict(set);owners={};tree=STRtree(parts)
                    for i in ownership:
                        hits=[int(j) for j in tree.query(points[i],predicate='intersects')]
                        if not hits:hits=[j for j,p in enumerate(parts) if p.distance(points[i])<.02]
                        if not hits:break
                        owners[i]=min(hits);part_members[min(hits)].add(i)
                    if len(owners)!=len(ownership) or len(part_members)!=2:continue
                    minimum_child=min(400,lower*.5)
                    if conflicts:minimum_child=min(minimum_child,len(ra['members']),len(rb['members']))
                    if min(map(len,part_members.values()))<minimum_child:continue
                    # Optional quality repair must preserve every previously
                    # satisfactory population in a satisfactory new owner.
                    if any(lower<=len(old['members'])<=upper and any(
                        not lower<=len(group)<=upper for group in part_members.values() if group&old['members'])
                        for old in (ra,rb)):
                        decision['reason']='A satisfactory neighbour would leave its requested range';continue
                    allowed=set();bad=False
                    line_mask=line.buffer(8)
                    for key,members in buckets.items():
                        if len({owners[i] for i in members if i in owners})<2:continue
                        road_group=road_by_id.get(key[1]) if key[0]=='ordinary segment' else None
                        if road_group and road_group['geometry'].intersection(line_mask).length>road_group['geometry'].length*.7:
                            allowed.add(key)
                        else:bad=True;break
                    if bad:continue
                    populated={j:parts[j] for j in part_members}
                    empty=set(range(len(parts)))-set(populated)
                    for _turn in range(len(empty)+1):
                        changed=False
                        for j in sorted(empty.copy()):
                            choices=[(-parts[j].boundary.intersection(g.boundary).length,k) for k,g in populated.items()]
                            length,k=min(choices)
                            if length>=-.1:continue
                            joined=populated[k].union(parts[j])
                            if joined.geom_type=='Polygon':populated[k]=joined;empty.remove(j);changed=True
                        if not changed:break
                    if empty:continue
                    cut=internal_seams(populated.values())
                    if cut.hausdorff_distance(seam)<.05 and abs(cut.length-seam.length)<1:continue
                    if any(sum(p['geometry'].intersection(g).area>max(4,p['geometry'].area*.02) for g in populated.values())>1
                           for p in parcels.values() if p['geometry'].intersects(cut)):continue
                    after=assess(cut,owners,points,buckets,geography,line)
                    if after['street_breaks'] or after['alley_side_splits']:continue
                    # A continuous broad street is preferable to an ordinary
                    # residential street. Municipal alignment is a score, not
                    # a veto that leaves an even worse alley seam untouched.
                    children=[{'geometry':g,'members':part_members[j]} for j,g in sorted(populated.items())]
                    from .access import disconnected_count,respects_separations
                    if not respects_separations(children,geography):
                        decision['reason']='Would undo an access-based natural division';continue
                    if disconnected_count(children,points,geography)>disconnected_count([ra,rb],points,geography)+5:
                        decision['reason']='Would combine disconnected road populations';continue
                    new_cost=affected_score(a,b,*children)
                    state=tuple(sorted(canonical(r['geometry']) for k,r in enumerate(regions) if k not in {a,b})+sorted(canonical(r['geometry']) for r in children))
                    state=tuple(sorted(state))
                    if state in seen:
                        decision['reason']='Previously evaluated complete partition';continue
                    decision.update(counts=[len(v) for v in part_members.values()],score_before=round(old_cost,5),
                        score_after=round(new_cost,5),quality_after=after)
                    if old_cost-new_cost<(.2 if not conflicts else 100):
                        decision['reason']='No sufficient improvement in continuity and neighbourhood cohesion';continue
                    decision.update(state='ELIGIBLE',reason='Cleaner continuous mapped division; municipal alignment is supporting evidence, not an eligibility gate')
                    options.append((new_cost-old_cost,road['id'],a,b,road,populated,part_members,allowed,before,after,cut,decision))
        if not options:break
        _,_,a,b,road,geometries,members,allowed,before,after,cut,decision=min(options,key=lambda x:x[:4])
        decision['state']='CHOSEN'
        old_a,old_b=regions[a],regions[b]
        split_frontage_buckets(buckets,allowed,{i:j for j,group in members.items() for i in group})
        identifier=road['id']+'-'+hashlib.sha256(canonical(cut).encode()).hexdigest()[:12]
        evidence[identifier]={'geometry':cut}
        ledger.append({'id':identifier,'name':road['name'],'category':'natural_area_split','rank':6,
            'stage':'street and alley continuity','state':'CHOSEN','chosen_for_split':True,'source_ids':road['road_ids'],
            'longitudinal_street_exception':True,'waived_ordinary_segments':sorted(k[1] for k in allowed),
            'reason':'Finite continuous City street boundary improves street/alley continuity or avoids an excessive division through a coherent neighbourhood. Municipal alignment is supporting evidence only.',
            'quality_before':before,'quality_after':after,'counts':[len(v) for v in members.values()]})
        for target,(j,g) in zip([a,b],sorted(geometries.items())):
            regions[target]={'geometry':g,'members':members[j],'links':[],
                'parents':old_a['parents']|old_b['parents'],'boundaries':old_a['boundaries']+old_b['boundaries']+[identifier],
                'last_resort':old_a.get('last_resort',False) or old_b.get('last_resort',False),
                'continuity_corridor':road['name'],'continuity_support':road['geometry'],'boundary_quality':after}
        audit['changes'].append({'candidate':identifier,'quality_before':before,'quality_after':after,
            'road':road['name'],'municipal_alignment':decision['municipal_alignment'],
            'affected_score_before':decision['score_before'],'affected_score_after':decision['score_after'],
            'previous_counts':[len(old_a['members']),len(old_b['members'])],
            'counts':[len(v) for v in members.values()]})
        seen.add(tuple(sorted(canonical(r['geometry']) for r in regions)))
        progress(70,'Replacing fragmented seams with continuous City street boundaries')
    audit['remaining']=audit_boundaries(regions,points,buckets,geography)
    return regions,audit


def audit_boundaries(regions,points,buckets,geography):
    """Inspect every final shared edge, including inherited natural seams."""
    remaining=[]
    qualities={k:[] for k in range(len(regions))}
    for a,ra in enumerate(regions):
        for b in range(a+1,len(regions)):
            rb=regions[b]
            seam=shared_boundary(ra['geometry'],rb['geometry'])
            if seam.length<20:continue
            ownership={i:a for i in ra['members']}|{i:b for i in rb['members']}
            supported=None
            if ra.get('continuity_corridor')==rb.get('continuity_corridor') and ra.get('continuity_corridor'):
                supported=ra.get('continuity_support')
            quality=assess(seam,ownership,points,buckets,geography,supported)
            qualities[a].append(quality);qualities[b].append(quality)
            if quality['street_breaks'] or quality['alley_side_splits']:
                remaining.append({'area_members':[len(ra['members']),len(rb['members'])],**quality})
    for k,region in enumerate(regions):
        region['boundary_quality']={'penalty':round(sum(q['penalty'] for q in qualities[k]),5),
            'street_breaks':[v for q in qualities[k] for v in q['street_breaks']],
            'alley_side_splits':[v for q in qualities[k] for v in q['alley_side_splits']],
            'shared_edges_checked':len(qualities[k]),'scope':'all final shared boundaries'}
    return remaining
