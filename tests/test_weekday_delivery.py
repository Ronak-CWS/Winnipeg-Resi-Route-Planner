import csv
import io
import json
from types import SimpleNamespace
import pytest

from routing_app import api
from partition_app import server


def test_saved_routing_day_is_never_inferred_from_the_open_partition(tmp_path):
    key='a'*64
    (tmp_path/'current-routing.json').write_text(json.dumps({'key':key,'partition_hash':'old'}))
    (tmp_path/f'routing-{key}.result.json').write_text(json.dumps({'day':'MONDAY'}))
    assert api.current(tmp_path,'MONDAY')['key']==key
    assert api.current(tmp_path,'TUESDAY') is None
    second='b'*64
    (tmp_path/'current-routing-tuesday.json').write_text(json.dumps({'key':second,'day':'TUESDAY'}))
    assert api.current(tmp_path,'TUESDAY')['key']==second
    assert api.current(tmp_path,'MONDAY')['key']==key


def test_tuesday_routing_exports_are_day_specific(monkeypatch):
    monkeypatch.setattr(api,'truck_map',lambda result:b'Tuesday review')
    route={'id':'G-01','stream':'garbage','equipment':'ASL','sections':['TUE-001'],
           'pickups':1,'load_count':1,'start':'06:15','return':'15:30','paid_seconds':33300,
           'overtime_seconds':4500,'km':50,'status':'PROVISIONAL','active_pickups_per_minute':3,
           'stops':[{'AddressId':'0001','Section':'TUE-001'}],
           'geometry':{'type':'FeatureCollection','features':[]}}
    result={'day':'TUESDAY','routes':[route],'access_reviews':[],'version':api.VERSION}
    files=api.export_files(result)
    assert len(files)==6 and all(n.startswith('Tuesday_') for n in files)
    for name in ['Tuesday_route_schedules.csv','Tuesday_route_pickup_order.csv']:
        rows=list(csv.DictReader(io.StringIO(files[name].decode('utf-8-sig'))))
        assert len(rows)==1 and rows[0]['CollectionDay']=='TUESDAY'
    assert json.loads(files['Tuesday_route_lines.geojson'])['day']=='TUESDAY'


def test_publishing_tuesday_preserves_the_previous_monday_route(tmp_path,monkeypatch):
    delivery=tmp_path/'delivery';delivery.mkdir()
    cache=tmp_path/'cache';cache.mkdir()
    accepted=delivery/'Monday_route_schedules.csv';accepted.write_bytes(b'accepted Monday')
    old={'key':'a'*64,'partition_hash':'monday-hash','day':'MONDAY'}
    (cache/'current-routing.json').write_text(json.dumps(old))
    monkeypatch.setattr(api,'export_files',lambda result:{'Tuesday_route_schedules.csv':b'Tuesday'})
    host=SimpleNamespace(CACHE=cache,DELIVERY=delivery,write_atomic=server.write_atomic)
    new={'key':'b'*64,'partition_hash':'tuesday-hash','day':'TUESDAY'}
    api.publish(host,new)
    assert accepted.read_bytes()==b'accepted Monday'
    assert api.current(cache,'MONDAY')==old and api.current(cache,'TUESDAY')==new


@pytest.mark.parametrize('elapsed',[0,601])
def test_publishing_tuesday_partition_preserves_the_accepted_monday(tmp_path,monkeypatch,elapsed):
    delivery=tmp_path/'delivery';delivery.mkdir()
    cache=tmp_path/'cache';cache.mkdir()
    old={'key':'a'*64,'day':'MONDAY'}
    new={'key':'b'*64,'day':'TUESDAY','status':'PROVISIONAL','summary':{'addresses':2}}
    for ext in ['areas.geojson','assignments.csv','review.json']:
        (delivery/f'Monday_partition_{ext}').write_bytes(b'accepted Monday')
        (cache/f"{new['key']}.{ext}").write_bytes(b'new Tuesday')
    (cache/f"{new['key']}.result.json").write_text(json.dumps(new))
    monkeypatch.setattr(server,'DELIVERY',delivery);monkeypatch.setattr(server,'CACHE',cache)
    monkeypatch.setattr(server,'STATE',{'current':old['key'],'day':'MONDAY','active':'job','active_kind':'partition'})
    monkeypatch.setattr(server,'JOBS',{'job':{'progress':0}})
    times=iter([0,elapsed,elapsed,elapsed])
    monkeypatch.setattr(server.time,'monotonic',lambda:next(times))
    server.run_job('job',None,None,new['key'])
    assert server.JOBS['job']['state']=='done'
    assert json.loads((cache/'current-monday.json').read_text())==old
    assert json.loads((cache/'current-tuesday.json').read_text())=={'key':new['key'],'day':'TUESDAY'}
    for ext in ['areas.geojson','assignments.csv','review.json']:
        assert (delivery/f'Monday_partition_{ext}').read_bytes()==b'accepted Monday'
        assert (delivery/f'Tuesday_partition_{ext}').read_bytes()==b'new Tuesday'


def test_partition_time_limit_preserves_previous_result(monkeypatch):
    monkeypatch.setattr(server,'STATE',{'current':'accepted','day':'MONDAY','active':'job','active_kind':'partition'})
    monkeypatch.setattr(server,'JOBS',{'job':{'progress':0}})
    times=iter([0,server.PARTITION_SECONDS+1])
    monkeypatch.setattr(server.time,'monotonic',lambda:next(times))
    server.run_job('job',None,None,'b'*64)
    assert server.JOBS['job']['state']=='error'
    assert '30-minute' in server.JOBS['job']['message']
    assert server.STATE['current']=='accepted' and server.STATE['day']=='MONDAY'
    assert server.STATE['active'] is None
