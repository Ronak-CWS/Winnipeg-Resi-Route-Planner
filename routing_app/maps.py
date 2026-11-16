"""One self-contained HTML review map; zero external requests or tile providers."""
import json
import hashlib
from pathlib import Path
from partition_app.days import day_label

ROOT=Path(__file__).resolve().parents[1]


def truck_map(result):
    assets=ROOT/'outputs/2026-11-04_monday_map/audit/assets'
    template=(ROOT/'web/truck-review.html').read_text(encoding='utf-8')
    key=hashlib.sha256((result['key']+template).encode()+Path(__file__).read_bytes()).hexdigest()
    cached=assets.parent/'partition_app'/f'routing-{key}.review.html'
    if cached.exists():return cached.read_bytes()
    geography=ROOT/'data/reference/partition_geography'
    roads=json.loads((geography/'roads.json').read_text())
    context=[{'type':'Feature','geometry':r['the_geom'],'properties':{'name':r.get('full_name',''),'kind':'road'}} for r in roads]
    for f in json.loads((geography/'physical_features.geojson').read_text())['features']:
        if f['properties']['category'] in {'waterway','water_area','railway','landuse'}:
            context.append({'type':'Feature','geometry':f['geometry'],'properties':{'name':f['properties'].get('name',''),'kind':f['properties']['category']}})
    for p in json.loads((geography/'parks.json').read_text()):
        context.append({'type':'Feature','geometry':p['polygon'],'properties':{'name':p.get('park_name',''),'kind':'park'}})
    routes=[]
    for r in result['routes']:
        routes.append({**{k:v for k,v in r.items() if k not in {'legs','events','stops'}},
            'stops':[{**{k:s[k] for k in ['AddressId','Address','Section','WorkArea','Load','Sequence','Latitude','Longitude',
                'PickupLatitude','PickupLongitude','TravelBearing','EstimatedServiceTime','AccessIssues']},
                **{k:s.get(k) for k in ['PickupRoad','PickupOffsetM','AccessBasis']}} for s in r['stops']]})
    payload={'key':result['key'],'day':result.get('day','MONDAY'),'created':result['created_at'],'version':result['version'],'settings':result['settings'],
        'status':result['status'],'streams':result['streams'],'routes':routes,'areas':result['work_areas'],
        'sites':result['sites'],'context':{'type':'FeatureCollection','features':context}}
    document=template.replace('COLLECTION_DAY',day_label(result.get('day','MONDAY')))
    document=document.replace('/* LEAFLET_CSS */',(assets/'leaflet.css').read_text(encoding='utf-8'))
    leaflet=(assets/'leaflet.js').read_text(encoding='utf-8').replace('//# sourceMappingURL=leaflet.js.map','')
    document=document.replace('/* LEAFLET_JS */',leaflet)
    # Uploaded strings never become executable markup or close this data block.
    document=document.replace('"ROUTING_DATA"',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c'))
    content=document.encode('utf-8')
    temporary=cached.with_suffix('.html.tmp');temporary.write_bytes(content);temporary.replace(cached)
    return content
