"""Evidence for finite broad road corridors, without named-road exceptions."""
import hashlib
import math
import statistics
from collections import defaultdict

from shapely.geometry import LineString
from shapely.ops import unary_union
from shapely.strtree import STRtree


def discover_corridors(geography):
    from .geography import street_name, line_parts, canonical
    references=defaultdict(list);city=defaultdict(list)
    for f in geography.features:
        if f['category'] in {'wide_road','high_speed_road','major_road','collector','road_reference'} and f.get('name'):
            references[street_name(f['name'])].append(f)
    for road in geography.roads:
        if road.get('name'):city[street_name(road['name'])].append(road)
    result=[];review=[]
    for name,refs in sorted(references.items()):
        arterial=[f for f in refs if f.get('tags',{}).get('highway') in {'primary','secondary','tertiary'}]
        if not arterial or name not in city:continue
        mask=unary_union([f['geometry'] for f in arterial]).buffer(12)
        roads=[r for r in city[name] if r['geometry'].intersection(mask).length>r['geometry'].length*.7]
        if not roads:continue
        tree=STRtree([r['geometry'] for r in roads]);remaining=set(range(len(roads)));components=[]
        while remaining:
            todo=[min(remaining)];component=[]
            while todo:
                i=todo.pop()
                if i not in remaining:continue
                remaining.remove(i);component.append(i)
                todo.extend(int(j) for j in tree.query(roads[i]['geometry'].buffer(.03)) if int(j) in remaining)
            components.append(component)
        strong=unary_union([f['geometry'] for f in refs if f['category'] in {'wide_road','high_speed_road'}])
        for component in components:
            geometry=unary_union([roads[i]['geometry'] for i in component])
            if geometry.length<250:continue
            supported=geometry.intersection(strong.buffer(12)).length if not strong.is_empty else 0
            widths=[]
            for line in sorted(line_parts(geometry),key=lambda g:-g.length):
                if len(widths)>=40:break
                for n in range(1,max(2,math.ceil(line.length/80))):
                    d=line.length*n/max(2,math.ceil(line.length/80));p=line.interpolate(d)
                    a,b=line.interpolate(max(0,d-5)),line.interpolate(min(line.length,d+5));dx,dy=b.x-a.x,b.y-a.y;length=math.hypot(dx,dy)
                    if length<1:continue
                    nearby=[geography.parcels[int(j)]['geometry'] for j in geography.parcel_tree.query(p.buffer(45))]
                    if any(g.contains(p) for g in nearby):continue
                    distances=[]
                    for sign in (-1,1):
                        ray=LineString([p,(p.x-sign*dy/length*45,p.y+sign*dx/length*45)])
                        hits=[p.distance(g.intersection(ray)) for g in nearby if g.intersects(ray)]
                        distances.append(min(hits,default=100))
                    if all(5<=d<=40 for d in distances):widths.append(sum(distances))
                    if len(widths)>=40:break
            median=statistics.median(widths) if len(widths)>=4 else None
            areas=[geography.neighbourhoods[int(j)]['geometry'].boundary for j in geography.neighbourhood_tree.query(geometry)]
            municipal=geometry.intersection(unary_union(areas).buffer(8)).length/geometry.length if areas else 0
            fraction=supported/geometry.length
            # Complete a municipal arterial only with corroborating width and
            # multi-lane evidence. Weaker broad corridors are target candidates,
            # not mandatory natural cuts through every neighbourhood.
            natural=municipal>=.4 and supported>=250 and median is not None and median>=18
            candidate=natural or fraction>=.15 and supported>=250 or median is not None and median>=26
            review.append({'name':roads[component[0]]['name'],'length_m':round(geometry.length,1),
                'multi_lane_or_arterial_support_m':round(supported,1),'support_fraction':round(fraction,4),
                'municipal_alignment':round(municipal,4),'median_public_right_of_way_m':round(median,2) if median is not None else None,
                'width_samples':len(widths),'natural_divider':natural,'range_candidate':candidate})
            if not candidate:continue
            identifier='corridor-'+hashlib.sha256((name+canonical(geometry)).encode()).hexdigest()[:16]
            result.append({'id':identifier,'name':roads[component[0]]['name'],'geometry':geometry,
                'category':'municipal_corridor' if natural else 'broad_corridor','rank':3 if natural else 4,
                'tags':{},'supported_road_ids':sorted(roads[i]['id'] for i in component),
                'evidence_ids':sorted(f['id'] for f in refs if f['geometry'].intersects(geometry.buffer(12))),
                'strong_support_fraction':round(fraction,4),'municipal_alignment':round(municipal,4),
                'median_right_of_way_m':round(median,2) if median is not None else None,'width_samples':len(widths),
                'evidence':'Connected finite City road geometry with arterial/multi-lane source evidence and measured City-parcel right-of-way support; no name exceptions or inferred pickup access.'})
    # Short wide-road source fragments are evidence for a finite continuous
    # City street candidate, not proof that the fragment alone closes an area.
    # Keep these as optional range candidates; do not promote the whole road
    # to a mandatory natural barrier or require a municipal boundary match.
    from .continuity import corridors
    existing={canonical(f['geometry']) for f in result}
    extent=getattr(geography,'city',unary_union([r['geometry'] for r in geography.roads]).envelope)
    for road in corridors(geography,extent):
        refs=references.get(road['key'],[])
        strong=[f for f in refs if f['category'] in {'wide_road','high_speed_road'}]
        if not strong or road['geometry'].length<250:continue
        support=road['geometry'].intersection(unary_union([f['geometry'] for f in strong]).buffer(12)).length
        if support<250 or support/road['geometry'].length<.15:continue
        if canonical(road['geometry']) in existing:continue
        identifier='corridor-complete-'+hashlib.sha256(canonical(road['geometry']).encode()).hexdigest()[:16]
        result.append({'id':identifier,'name':road['name'],'geometry':road['geometry'],
            'category':'broad_corridor','rank':4,'tags':{},'supported_road_ids':road['road_ids'],
            'evidence_ids':sorted(f['id'] for f in strong),'strong_support_fraction':round(support/road['geometry'].length,4),
            'municipal_alignment':None,'finite_street_completion':True,
            'evidence':'Complete finite City street with at least 250 m and 15% mapped broad-road support; optional division, not a municipal-alignment gate.'})
        existing.add(canonical(road['geometry']))
    geography.corridor_review=review
    return result
