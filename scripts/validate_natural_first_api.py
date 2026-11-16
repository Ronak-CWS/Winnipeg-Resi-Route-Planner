"""Publish independently checked caches, then verify the real local app API."""
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from partition_app import server
from partition_app.inputs import parse_upload


def main():
    audit=server.CACHE
    natural_key=json.loads((audit/'range-natural-summary.json').read_text())['key']
    range_key=json.loads((audit/'range-900-1100-summary.json').read_text())['key']
    natural,balanced=(server.load_result(key) for key in [natural_key,range_key])
    for key,result in [(natural_key,natural),(range_key,balanced)]:
        assert result['engine']==server.ENGINE_VERSION and result['summary']['errors']==0
        assert json.loads((audit/(key+'.rail-validation.json')).read_text())['passed']
    assert balanced['summary']['natural_areas']==natural['summary']['areas']
    export=json.loads((audit/'export-validation.json').read_text())
    assert export['fresh_process_replay_identical'] and export['partition_hash']==balanced['partition_hash']
    source=server.DELIVERY/'Monday_addresses_lat_long.xlsx'
    dataset=parse_upload(source.read_bytes(),source.name)
    assert server.cache_key(dataset,None)==natural_key
    assert server.cache_key(dataset,None,minimum=900,maximum=1100)==range_key
    base='http://127.0.0.1:8765'
    def get(path):
        with urllib.request.urlopen(base+path,timeout=20) as response:return response.read()
    state=json.loads(get('/api/state'));assert state['version']==server.ENGINE_VERSION and not state['active']
    token=state['csrf']
    def post(path,data,headers=None):
        request=urllib.request.Request(base+path,data=data,headers={'X-CWS-Local':token,**(headers or {})},method='POST')
        with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
    uploaded=post('/api/upload',source.read_bytes(),{'X-Filename':source.name})
    assert uploaded['count']==21507
    def cached_run(preference,key):
        job=post('/api/run',json.dumps({'input_id':uploaded['input_id'],**preference}).encode())
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            status=json.loads(get('/api/job?id='+job['job_id']))
            if status['state']!='running':break
            time.sleep(.2)
        assert status['state']=='done' and status['cached'] and status['result']==key,status
        assert json.loads(get('/api/state'))['current']==key
        received=json.loads(get('/api/result?key='+key));assert received['partition_hash']==server.load_result(key)['partition_hash']
    cached_run({'target':None},natural_key)
    cached_run({'minimum':900,'maximum':1100},range_key)
    assert hashlib.sha256(get('/api/monday-workbook')).digest()==hashlib.sha256(source.read_bytes()).digest()
    for kind,suffix,name in [('assignments','assignments.csv','Monday_partition_assignments.csv'),
                              ('areas','areas.geojson','Monday_partition_areas.geojson'),
                              ('review','review.json','Monday_partition_review.json')]:
        expected=(audit/(range_key+'.'+suffix)).read_bytes()
        assert get('/api/download?key='+range_key+'&kind='+kind)==expected
        assert (server.DELIVERY/name).read_bytes()==expected
    with zipfile.ZipFile(io.BytesIO(get('/api/download?key='+range_key+'&kind=package'))) as archive:
        assert archive.testzip() is None and len(archive.namelist())==3
    for preference in [{'minimum':1100,'maximum':900},{'minimum':900,'maximum':1100,'use_mapped_alleys':True}]:
        try:post('/api/run',json.dumps({'input_id':uploaded['input_id'],**preference}).encode())
        except urllib.error.HTTPError as error:assert error.code==400
        else:raise AssertionError('Invalid preference accepted')
    assert post('/api/demo',b'{}')['count']==21507
    csv_key=json.loads((audit/'csv-replay-cache-validation.json').read_text())['key']
    assert server.load_result(csv_key)['partition_hash']==balanced['partition_hash']
    for name in ['index.html','app.js','app.css']:
        assert get('/' if name=='index.html' else '/'+name)==(server.ROOT/'web'/name).read_bytes()
    html=get('/').decode()
    assert 'expand-map-button' in html and 'settings-button' in html and 'id="minimum-input"' in html
    assert 'id="natural-mode"' not in html and 'id="target-mode"' not in html and 'id="preference-type"' not in html
    assert 'Hover or click' not in html and b'showAreaHover' not in get('/app.js')
    receipt={'engine':server.ENGINE_VERSION,'natural_key':natural_key,'range_key':range_key,
        'url':base,'pid':state['pid'],'both_modes_cached_and_published':True,'csv_demo_cached':True,
        'unchanged_excel_download':True,'published_exports_identical':True,'zip_valid':True,
        'invalid_preferences_rejected':True,'larger_map_assets_served':True,'click_only_area_details':True,
        'natural_summary':natural['summary'],'range_summary':balanced['summary'],
        'external_provider_calls':0,'chrome_visual_qa':'Not established by API checks'}
    (audit/'natural-first-api-validation.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
