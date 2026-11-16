"""QA source-ID cohorts only: user's two illustrated last-resort neighbours."""
import json
from pathlib import Path
from shapely.geometry import shape,Point
from shapely.ops import unary_union
from partition_app.geography import project,FORWARD,subdivide
from partition_app.continuity import corridors,assess

AUDIT=Path(__file__).resolve().parents[1]/'outputs/2026-11-04_monday_map/audit/partition_app'

def inspect(geography,dataset):
    old=json.loads((AUDIT/'eb12342296c010957cd5b07ac5fdf4d4439aec3ac9319d139c42e5fede483dfa.result.json').read_text())
    rows=sorted(dataset.rows,key=lambda r:r['id']);identities={r['id']:i for i,r in enumerate(rows)}
    points=[Point(*FORWARD.transform(r['lon'],r['lat'])) for r in rows]
    wanted=['MON-013','MON-018'];features={f['id']:f for f in old['areas']['features']}
    geometry=unary_union([project(shape(features[s]['geometry'])) for s in wanted])
    owners={identities[p['id']]:wanted.index(p['section']) for p in old['points'] if p['section'] in wanted and p['trusted']}
    hood_edges=unary_union([h['geometry'].boundary for h in geography.neighbourhoods if h['geometry'].intersects(geometry)])
    found=[]
    for road in corridors(geography,geometry):
        inside=road['geometry'].intersection(geometry)
        alignment=inside.intersection(hood_edges.buffer(8)).length/max(inside.length,1)
        if inside.length<250 or alignment<.6:continue
        parts=subdivide(geometry,[road['geometry']]);counts=[sum(p.distance(points[i])<.02 for i in owners) for p in parts]
        found.append({'name':road['name'],'id':road['id'],'inside_m':inside.length,'municipal_alignment':alignment,'counts':counts})
    report={'previous_key':old['key'],'source_cohorts':{s:[p['id'] for p in old['points'] if p['section']==s] for s in wanted},'corridors':found}
    (AUDIT/'street-alley-review-reference.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(found,indent=2),flush=True)
