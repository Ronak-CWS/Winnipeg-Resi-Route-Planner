"""Local-only diagnostic of failed area connectivity; never changes geometry."""
import json
import sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shapely import make_valid,set_precision
from shapely.geometry import shape,Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from partition_app.geography import GEO_DIR,project,divider_line,polygon_parts,road_evidence,promote_divided_roads
from partition_app.geography import Geography
from partition_app.engine import seam_dividers,barrier_blocks_pocket

root=Path(__file__).resolve().parents[1]
audit=root/'outputs/2026-11-04_monday_map/audit/partition_app'
summary={'key':sys.argv[1]} if len(sys.argv)>1 else json.loads((audit/'range-900-summary.json').read_text())
result=json.loads((audit/(summary['key']+'.result.json')).read_text())
features=[]
for filename in ('physical_features.geojson','planning_features.geojson'):
    for f in json.loads((GEO_DIR/filename).read_text())['features']:
        feature={'id':f['id'],**f['properties'],'geometry':project(shape(f['geometry']))}
        if feature['category'] in {'major_road','collector','road_reference'} and road_evidence(feature.get('tags',{})):
            feature['category']='wide_road'
        features.append(feature)
roads=[{'id':str(r['segment_id']),'name':r.get('full_name',''),'type':r.get('type',''),'geometry':project(shape(r['the_geom']))} for r in json.loads((GEO_DIR/'roads.json').read_text())]
features.extend(promote_divided_roads(features,roads))
for r in json.loads((GEO_DIR/'parks.json').read_text()):
    features.append({'id':'park-'+str(r['park_id']),'category':'park','name':r.get('park_name',''),'geometry':project(shape(r['polygon']))})
strong_categories={'waterway','railway','controlled_road','wide_road','park','water_area','landuse','recreation','mapped_open_land'}
strong=[f for f in features if f['category'] in strong_categories]
lines=[divider_line(f) for f in strong];tree=STRtree(lines)
geo=Geography.__new__(Geography);geo.features=strong;geo.divider_indexes={}
geometries={f['id']:set_precision(make_valid(project(shape(f['geometry']))),.01) for f in result['areas']['features']}
properties={f['id']:f['properties'] for f in result['areas']['features']}
for a,g in geometries.items():
    if len(polygon_parts(g))==1 and properties[a].get('small_area_status')!='NEEDS_REVIEW':continue
    parts=polygon_parts(g)
    points=[Point(*project(Point(p['lon'],p['lat'])).coords[0]) for p in result['points'] if p['section']==a]
    print('\n',a,properties[a]['name'],properties[a]['addresses'],'parts',[(round(p.area,1),sum(p.buffer(.02).covers(x) for x in points)) for p in parts],flush=True)
    print('gaps',[round(parts[i].distance(parts[j]),3) for i in range(len(parts)) for j in range(i+1,len(parts))],flush=True)
    options=[]
    for b,h in geometries.items():
        if a==b or g.distance(h)>500:continue
        shared=g.boundary.intersection(h.boundary.buffer(.02))
        if shared.length<1 and properties[a].get('small_area_status')!='NEEDS_REVIEW':continue
        protected=[]
        for index in tree.query(shared.buffer(2),predicate='intersects'):
            overlap=lines[int(index)].intersection(shared.buffer(2)).length
            if overlap>shared.length*.4:
                f=strong[int(index)];protected.append((f['category'],f.get('name',''),f['id'],round(overlap/shared.length,2)))
        merged=g.union(h);new_parts=polygon_parts(merged)
        gaps=[p.distance(q) for i,p in enumerate(new_parts) for q in new_parts[i+1:]]
        actual=g.boundary.intersection(h.boundary)
        precise=seam_dividers(actual,geo) if actual.length else []
        if properties[b]['addresses']<100 and len(parts)==1:continue
        options.append((properties[b]['addresses'],b,len(new_parts),round(min(gaps),2) if gaps else 0,
                        round(g.distance(h),3),barrier_blocks_pocket(precise,points),[(f['category'],f['id']) for f in precise][:5],protected[:4]))
    for option in sorted(options):print(' neighbour count,id,parts,gap,barrier',option,flush=True)
print('\nBand counts',dict(Counter('below50' if p['addresses']<50 else '50-509' if p['addresses']<510 else 'inrange' for p in properties.values())))
