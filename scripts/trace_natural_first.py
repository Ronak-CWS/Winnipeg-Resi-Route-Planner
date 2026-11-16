"""Local source-ID review of the preserved natural run; never changes delivery."""
import json
from pathlib import Path
from collections import Counter
from PIL import Image, ImageDraw, ImageFont
from shapely.geometry import shape, Point
from partition_app import engine
from partition_app.geography import project, polygon_parts

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'outputs/2026-11-04_monday_map/audit/partition_app'

def inspect(geography,dataset):
    ref=json.loads((AUDIT/'natural_first_review_reference.json').read_text())
    result=json.loads((AUDIT/(ref['key']+'.result.json')).read_text())
    rows=sorted(dataset.rows,key=lambda r:r['id'])
    identities={r['id']:i for i,r in enumerate(rows)}
    wanted={identities[i] for i in ref['examples']['MON-022']['address_ids']}
    original=engine.protect_cells
    def capture(cells,points,trusted,buckets,parcels,road_groups,roads):
        answer=original(cells,points,trusted,buckets,parcels,road_groups,roads)
        row_cell,dsu,reasons,_=answer
        trace={'reasons':dict(reasons),'cells':[], 'groups':[]}
        for i in sorted(wanted):
            cell=cells[row_cell[i]]
            trace['cells'].append({'id':rows[i]['id'],'address':rows[i]['address'],'cell':row_cell[i],
                'parent':cell['name'],'root':dsu.find(row_cell[i]),'area_m2':round(cell['geometry'].area,1)})
        for key,members in buckets.items():
            if len(members)>1 and wanted.intersection(members):
                trace['groups'].append({'key':key,'members':[{'id':rows[i]['id'],'address':rows[i]['address']} for i in members]})
        (AUDIT/'natural-first-protection-trace.json').write_text(json.dumps(trace,indent=2))
        print(json.dumps(trace),flush=True)
        return answer
    engine.protect_cells=capture
    try:
        fresh=engine.plan(dataset,geography,None,lambda p,m:print(p,m,flush=True))
    finally:engine.protect_cells=original
    (AUDIT/'natural-first-trace-result.json').write_text(json.dumps(fresh))
    geometries={f['id']:project(shape(f['geometry'])) for f in result['areas']['features']}
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',15)
    # Review labels belong here only, never in the algorithm.
    for ids,label in [(['MON-001','MON-023'],'whyte'),(['MON-005'],'north'),(['MON-022'],'small-corridor')]:
        bounds=geometries[ids[0]].bounds
        for sid in ids[1:]:
            b=geometries[sid].bounds;bounds=(min(bounds[0],b[0]),min(bounds[1],b[1]),max(bounds[2],b[2]),max(bounds[3],b[3]))
        x0,y0,x1,y1=bounds;pad=150;x0-=pad;y0-=pad;x1+=pad;y1+=pad
        scale=min(1100/(x1-x0),1100/(y1-y0));width=int((x1-x0)*scale)+50;height=int((y1-y0)*scale)+50
        canvas=Image.new('RGB',(width,height),'#f6f5ef');draw=ImageDraw.Draw(canvas)
        def xy(point):return (25+(point[0]-x0)*scale,25+(y1-point[1])*scale)
        for sid,g in geometries.items():
            for part in polygon_parts(g):
                draw.polygon([xy(p) for p in part.exterior.coords],fill='#e5ecdf' if sid in ids else '#eeeeea',outline='#637a6d',width=2)
        for road in geography.base_roads:
            if not (road['geometry'].bounds[2]<x0 or road['geometry'].bounds[0]>x1 or road['geometry'].bounds[3]<y0 or road['geometry'].bounds[1]>y1):
                draw.line([xy(p) for p in road['geometry'].coords],fill='#c3c5bf',width=1)
        box=__import__('shapely.geometry',fromlist=['box']).box(x0,y0,x1,y1)
        rail_ids=[]
        for feature in geography.nearby_features(box,{'railway'}):
            line=feature['geometry'];rail_ids.append({'id':feature['id'],'name':feature.get('name'),'geometry':__import__('shapely.geometry',fromlist=['mapping']).mapping(line)})
            for linepart in [line] if line.geom_type=='LineString' else line.geoms:
                draw.line([xy(p) for p in linepart.coords],fill='#151515',width=4)
        for point in result['points']:
            p=project(Point(point['lon'],point['lat']));x,y=xy((p.x,p.y))
            if 0<=x<width and 0<=y<height:
                colour='#ce315f' if point['section'] in ids else '#547ed3'
                draw.ellipse((x-2,y-2,x+2,y+2),fill=colour)
        draw.text((15,10),label+' / '+', '.join(ids),font=font,fill='#152f25')
        canvas.save(AUDIT/('natural-first-'+label+'.png'))
        (AUDIT/('natural-first-'+label+'-rails.json')).write_text(json.dumps(rail_ids))
    print('Saved local geometry plots and source protection trace.',flush=True)
