"""Routing jobs share the app's single worker and existing delivery/audit area."""
import csv
import hashlib
import io
import json
import re
import time
import traceback
import uuid
import zipfile
from pathlib import Path

from . import VERSION
from .engine import run, dump
from .settings import settings, DEFAULTS
from .maps import truck_map
from partition_app.inputs import InputError
from partition_app.days import day_label, normalize_day


def key_for(partition,cfg):
    code=b''.join(p.name.encode()+p.read_bytes() for p in sorted(Path(__file__).parent.glob('*.py')))
    code+=(Path(__file__).resolve().parents[1]/'web/truck-review.html').read_bytes()
    return hashlib.sha256(code+json.dumps([VERSION,partition.get('day','MONDAY'),partition['partition_hash'],cfg],sort_keys=True).encode()).hexdigest()


def current(cache, day=None):
    selected=normalize_day(day)
    if day and not selected:raise InputError('Choose a valid collection day.')
    paths=([cache/f'current-routing-{selected.lower()}.json'] if selected else [])+[cache/'current-routing.json']
    for path in paths:
        if not path.exists():continue
        saved=json.loads(path.read_text())
        saved_day=saved.get('day') or load(cache,saved['key']).get('day','MONDAY')
        if not selected or selected==saved_day:return {**saved,'day':saved_day}
    return None


def load(cache,key):
    if not re.fullmatch('[a-f0-9]{64}',key or ''):raise FileNotFoundError('Unknown routing result.')
    return json.loads((cache/f'routing-{key}.result.json').read_text(encoding='utf-8'))


def summary(result):
    return {**result,'routes':[{k:v for k,v in r.items() if k not in {'geometry','stops','events','legs'}} for r in result['routes']],
            'access_reviews':result['access_reviews'][:40],'access_review_count':len(result['access_reviews']),
            'current_engine_version':VERSION,'requires_recalculation':result['version']!=VERSION}


def csv_bytes(rows,fields=None):
    output=io.StringIO(newline='');fields=fields or list(rows[0])
    writer=csv.DictWriter(output,fieldnames=fields,extrasaction='ignore');writer.writeheader()
    for row in rows:
        safe={k:(json.dumps(v) if isinstance(v,(list,dict)) else v) for k,v in row.items()}
        # Spreadsheet consumers must not execute uploaded address strings.
        for k,v in safe.items():
            if isinstance(v,str) and v.startswith(('=','+','-','@')):safe[k]="'"+v
        writer.writerow(safe)
    return output.getvalue().encode('utf-8-sig')


def export_files(result):
    day=result.get('day','MONDAY');label=day_label(day)
    schedules=[];stops=[];features=[]
    for route in result['routes']:
        schedules.append({'CollectionDay':day,'Truck':route['id'],'Stream':route['stream'],'Equipment':route['equipment'],
            'Sections':' / '.join(route.get('planning_sections',route['sections'])),
            'WorkAreas':' / '.join(route['sections']),'Pickups':route['pickups'],'Loads':route['load_count'],
            'Start':route['start'],'Return':route['return'],'PaidHours':round(route['paid_seconds']/3600,3),
            'OvertimeMinutes':round(route['overtime_seconds']/60,1),'Kilometres':round(route['km'],2),
            'Status':route['status'],'ActivePickupsPerMinute':round(route['active_pickups_per_minute'],2)})
        stops.extend({'CollectionDay':day,**s} for s in route['stops']);features.extend(route['geometry']['features'])
    return {f'{label}_route_schedules.csv':csv_bytes(schedules),f'{label}_route_pickup_order.csv':csv_bytes(stops),
        f'{label}_route_lines.geojson':json.dumps({'type':'FeatureCollection','day':day,'features':features},separators=(',',':')).encode(),
        f'{label}_route_work_areas.geojson':json.dumps({**result.get('work_areas',{'type':'FeatureCollection','features':[]}),'day':day},separators=(',',':')).encode(),
        f'{label}_truck_route_maps.html':truck_map(result),
        f'{label}_routing_review.json':json.dumps(summary(result),ensure_ascii=False,indent=2).encode()}


def publish(host,result):
    for name,content in export_files(result).items():host.write_atomic(host.DELIVERY/name,content)
    previous=current(host.CACHE)
    if previous:dump(host.CACHE/f"current-routing-{previous['day'].lower()}.json",previous)
    saved={'key':result['key'],'partition_hash':result['partition_hash'],'day':result.get('day','MONDAY')}
    dump(host.CACHE/f"current-routing-{saved['day'].lower()}.json",saved)
    dump(host.CACHE/'current-routing.json',saved)


def worker(host,job_id,partition,cfg,key):
    started=time.monotonic()
    def progress(percent,message):
        with host.LOCK:
            job=host.JOBS[job_id]
            if job.get('cancelled'):raise InterruptedError('Routing cancelled. Completed road calculations remain cached; the previous result is preserved.')
            if time.monotonic()-started>7200:raise TimeoutError('The two-hour local calculation budget was reached. Cached work is preserved.')
            if percent is not None:job['progress']=max(job['progress'],round(percent))
            job.update(message=message,elapsed_seconds=round(time.monotonic()-started))
    try:
        path=host.CACHE/f'routing-{key}.result.json'
        cached=path.exists()
        if cached:
            result=load(host.CACHE,key);progress(97,'Reusing this complete routing scenario')
        else:
            result=run(partition,cfg,host.CACHE,progress);result['key']=key
            dump(path,result)
        progress(99,'Saving route schedules, pickup orders and road lines')
        publish(host,result)
        with host.LOCK:host.JOBS[job_id].update(state='done',progress=100,message=f"{day_label(result.get('day','MONDAY'))} routes ready",result=key,cached=cached)
    except InterruptedError as exc:
        with host.LOCK:host.JOBS[job_id].update(state='cancelled',message=str(exc))
    except Exception as exc:
        traceback.print_exc()
        with host.LOCK:host.JOBS[job_id].update(state='error',message=str(exc))
    finally:
        with host.LOCK:host.STATE['active']=None;host.STATE['active_kind']=None


def get(handler,host,path,query):
    if path=='/api/routing/settings':
        saved=current(host.CACHE,query.get('day',[host.STATE.get('day')])[0])
        config_path=host.CACHE/'routing-settings.json'
        cfg=settings(json.loads(config_path.read_text(encoding='utf-8'))) if config_path.exists() else settings(load(host.CACHE,saved['key'])['settings']) if saved else settings()
        return handler.reply({'settings':cfg,'current':saved,'version':VERSION})
    key=query.get('key',[(current(host.CACHE,host.STATE.get('day')) or {}).get('key','')])[0]
    result=load(host.CACHE,key)
    if path=='/api/routing/result':return handler.reply(summary(result))
    if path=='/api/routing/route':
        ident=query.get('id',[''])[0]
        route=next((r for r in result['routes'] if r['id']==ident),None)
        if route is None:raise FileNotFoundError('Unknown truck route.')
        return handler.reply(route)
    if path=='/api/routing/download':
        kind=query.get('kind',['package'])[0]
        files=export_files(result)
        label=day_label(result.get('day','MONDAY'))
        names={'schedules':f'{label}_route_schedules.csv','pickups':f'{label}_route_pickup_order.csv',
               'roads':f'{label}_route_lines.geojson','areas':f'{label}_route_work_areas.geojson','review':f'{label}_routing_review.json','maps':f'{label}_truck_route_maps.html'}
        if kind=='package':
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,'w',zipfile.ZIP_DEFLATED) as archive:
                for name,content in files.items():archive.writestr(name,content)
            return handler.reply(buffer.getvalue(),content_type='application/zip',filename=f'{label}_routing.zip')
        if kind not in names:raise FileNotFoundError('Unknown routing export.')
        name=names[kind]
        return handler.reply(files[name],content_type='text/html; charset=utf-8' if name.endswith('.html') else 'text/csv; charset=utf-8' if name.endswith('csv') else 'application/json',filename=name)
    raise FileNotFoundError('Unknown routing operation.')


def start(handler,host,payload):
    with host.LOCK:
        if host.STATE['active']:return handler.reply({'error':'A local calculation is already running.','job_id':host.STATE['active']},409)
        partition=host.load_result(payload.get('partition_key') or host.STATE['current'] or '')
        cfg=settings(payload.get('settings'))
        dump(host.CACHE/'routing-settings.json',cfg)
        key=key_for(partition,cfg);job_id=uuid.uuid4().hex
        host.JOBS[job_id]={'id':job_id,'kind':'routing','state':'running','progress':0,
                         'message':'Preparing complete sections and operating inputs','cancelled':False}
        host.STATE['active']=job_id;host.STATE['active_kind']='routing'
        host.POOL.submit(worker,host,job_id,partition,cfg,key)
        return handler.reply({'job_id':job_id},202)
