"""Independent replay check for locally recorded screenshot regression cohorts.

Reads the existing audit fixture; no road requests and no routing assignments.
Checks real path segments near each derived pickup, their heading and the
property's side. Merely visiting the outside postal road cannot pass this check.
"""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from pyproj import Transformer
from shapely.geometry import LineString, Point
from shapely.strtree import STRtree


def verify():
    cache=Path('outputs/2026-11-04_monday_map/audit/partition_app')
    fixture=json.loads((cache/'internal-access-anchor-validation.json').read_text())
    current=json.loads((cache/'current-routing.json').read_text())
    result=json.loads((cache/f"routing-{current['key']}.result.json").read_text(encoding='utf-8'))
    # A corrected planning partition changes the cache key even when physical
    # access is identical. Verify the actual cohort anchors, not key equality.
    anchors=json.loads((cache/f"routing-{result['anchor_cache_key']}.anchors.json").read_text(encoding='utf-8'))['anchors']
    reference=json.loads((cache/f"routing-{fixture['anchor_key']}.anchors.json").read_text(encoding='utf-8'))['anchors']
    for case in fixture['cases']:
        for ident in case['source_ids']:
            for field in ['original','coordinate','road_id','direction']:
                assert anchors[ident][field]==reference[ident][field], (ident,field,'pickup access changed')
    project=Transformer.from_crs(4326,32614,always_xy=True).transform
    rows=[];failures=[]
    for stream in ['garbage','recycling']:
        routes=[r for r in result['routes'] if r['stream']==stream]
        owner={s['AddressId']:(r,s) for r in routes for s in r['stops']}
        indexes={}
        for route in routes:
            for load in route['loads']:
                segments=[];headings=[]
                for feature in route['geometry']['features']:
                    if feature['properties']['load']!=load['load']:continue
                    coords=feature['geometry']['coordinates']
                    for a,b in zip(coords,coords[1:]):
                        pa,pb=project(*a),project(*b)
                        if math.dist(pa,pb)<.05:continue
                        segments.append(LineString([pa,pb]))
                        # Geographic heading, independently derived from the replay.
                        headings.append(math.degrees(math.atan2((b[0]-a[0])*math.cos(math.radians((a[1]+b[1])/2)),b[1]-a[1]))%360)
                indexes[route['id'],load['load']]=(segments,headings,STRtree(segments))
        for case in fixture['cases']:
            details=[];directions=defaultdict(set)
            for ident in case['source_ids']:
                route,stop=owner[ident];anchor=anchors[ident]
                segments,headings,tree=indexes[route['id'],stop['Load']]
                point=Point(*project(stop['PickupLongitude'],stop['PickupLatitude']))
                prop=Point(*project(stop['Longitude'],stop['Latitude']))
                nearby=tree.query(point,predicate='dwithin',distance=8.5)
                matches=[]
                for index in nearby:
                    line=segments[index];delta=abs((headings[index]-stop['TravelBearing']+180)%360-180)
                    a,b=line.coords;at=line.interpolate(line.project(point))
                    cross=(b[0]-a[0])*(prop.y-at.y)-(b[1]-a[1])*(prop.x-at.x)
                    if delta<=35 and cross<0:matches.append(point.distance(line))
                valid=bool(matches)
                if not valid:failures.append({'stream':stream,'id':ident,'route':route['id'],'nearby_segments':len(nearby)})
                directions[anchor['road_id']].add(anchor['direction'])
                details.append({'id':ident,'route':route['id'],'load':stop['Load'],
                    'sequence':stop['Sequence'],'property_offset_m':round(point.distance(prop),2),
                    'access_issues':stop['AccessIssues'],
                    'right_side_path_distance_m':round(min(matches),3) if matches else None})
            rows.append({'stream':stream,'example':case['example'],'pickups':len(details),
                'truck_owners':dict(Counter(d['route'] for d in details)),
                'max_property_offset_m':max(d['property_offset_m'] for d in details),
                'internal_road_segments_served_in_both_directions':sum(len(d)==2 for d in directions.values()),
                'correct_direction_and_property_side':all(d['right_side_path_distance_m'] is not None for d in details),
                'pickup_diagnostic_count':sum(bool(d['access_issues']) for d in details),
                'details':details})
    receipt={'result_key':result['key'],'anchor_key':result['anchor_cache_key'],
        'reference_anchor_key':fixture['anchor_key'],'cohort_physical_anchors_unchanged':True,
        'cases':rows,'failures':failures,'no_network_requests':True,
        'meaning':'Actual replay has nearby correctly directed segments with the source property to the right. This does not certify truck dimensions or field access.'}
    (cache/'internal-access-replay-validation.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print(json.dumps({**receipt,'cases':[{k:v for k,v in r.items() if k!='details'} for r in rows]},indent=2))
    assert not failures, failures[:8]


if __name__=='__main__':verify()
