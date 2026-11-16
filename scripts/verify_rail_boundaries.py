"""Independent, finite railway-separator check against saved area exports."""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shapely.geometry import Point,LineString,shape
from shapely.ops import nearest_points
from shapely.ops import split,unary_union
from shapely.strtree import STRtree
from partition_app.geography import GEO_DIR,FORWARD,project,polygon_parts

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--key',required=True);args=parser.parse_args()
    audit=Path(__file__).resolve().parents[1]/'outputs/2026-11-04_monday_map/audit/partition_app'
    result=json.loads((audit/(args.key+'.result.json')).read_text())
    rails=[{'id':f['id'],'geometry':project(shape(f['geometry']))} for f in json.loads((GEO_DIR/'physical_features.geojson').read_text())['features'] if f['properties']['category']=='railway']
    tree=STRtree([r['geometry'] for r in rails]);failures=[]
    for feature in result['areas']['features']:
        sid=feature['id'];geometry=project(shape(feature['geometry']));parts=polygon_parts(geometry)
        points=[Point(*FORWARD.transform(p['lon'],p['lat'])) for p in result['points'] if p['section']==sid and p['trusted']]
        candidates=[rails[int(i)] for i in tree.query(geometry,predicate='intersects')]
        for component in parts:
            # Independent library split of the complete finite rail network.
            # Do not call the engine's polygoniser or pre-clip rail endpoints.
            pieces=list(split(component,unary_union([r['geometry'] for r in candidates])).geoms) if candidates else [component]
            counts=Counter()
            for point in points:
                owners=[i for i,p in enumerate(pieces) if p.distance(point)<.03]
                if owners:counts[min(owners)]+=1
            if len(counts)>1:
                failures.append({'section':sid,'name':feature['properties']['name'],'serviced_sides':dict(counts),
                                 'rail_ids':[r['id'] for r in candidates]})
        if len(parts)>1 and feature['properties'].get('nearby_small_area_group'):
            recorded=feature['properties'].get('nearby_merge_links',[])
            probes=[project(shape(link['probe'])) for link in recorded if link.get('probe')]
            checked=[]
            for probe in probes:
                if any(rails[int(n)]['geometry'].intersects(probe.buffer(.01)) for n in tree.query(probe.buffer(.01))):
                    failures.append({'section':sid,'reason':'Recorded nearby connection crosses a railway'})
                    continue
                ends=[Point(probe.coords[0]),Point(probe.coords[-1])]
                owners=[[i for i,part in enumerate(parts) if part.distance(end)<.04] for end in ends]
                checked.extend((a,b) for a in owners[0] for b in owners[1] if parts[a].distance(parts[b])<=500)
            reached={0}
            while True:
                extra=set()
                if probes:
                    extra.update(b for a,b in checked if a in reached)
                    extra.update(a for a,b in checked if b in reached)
                for i in reached:
                    if probes:continue
                    for j in range(len(parts)):
                        if i==j or parts[i].distance(parts[j])>500:continue
                        # Probe inside each real piece, independently of the
                        # engine. A degenerate boundary-corner probe can touch
                        # an unrelated rail on the outside of both pieces.
                        a,b=(part.buffer(-.1) for part in (parts[i],parts[j]))
                        if a.is_empty:a=parts[i].representative_point()
                        if b.is_empty:b=parts[j].representative_point()
                        gap=LineString(nearest_points(a,b))
                        if not any(rails[int(n)]['geometry'].intersects(gap) for n in tree.query(gap)):extra.add(j)
                if extra<=reached:break
                reached|=extra
            if len(reached)<len(parts):failures.append({'section':sid,'reason':'Nearby pieces separated by railway'})
    receipt={'key':args.key,'rail_features':len(rails),'areas_checked':len(result['areas']['features']),
             'rail_crossing_sections':failures,'network_calls':0,'passed':not failures}
    (audit/(args.key+'.rail-validation.json')).write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))
    return 0 if not failures else 1

if __name__=='__main__':raise SystemExit(main())
