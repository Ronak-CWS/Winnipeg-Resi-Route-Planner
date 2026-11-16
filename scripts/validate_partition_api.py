"""Publish a verified cached Monday run through the normal local app API."""
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
    key=json.loads((server.CACHE/'range-900-summary.json').read_text())['key']
    result=server.load_result(key)
    assert result['engine']==server.ENGINE_VERSION and result['status']!='FAILED' and result['summary']['errors']==0
    assert json.loads((server.CACHE/(key+'.rail-validation.json')).read_text())['passed']
    source=server.DELIVERY/'Monday_addresses_lat_long.xlsx'
    dataset=parse_upload(source.read_bytes(),source.name)
    assert server.cache_key(dataset,900,12)==key
    base='http://127.0.0.1:8765'
    def get(path):
        with urllib.request.urlopen(base+path,timeout=20) as response:return response.read()
    state=json.loads(get('/api/state'));assert state['version']==server.ENGINE_VERSION and not state['active']
    token=state['csrf']
    def post(path,data,headers=None):
        request=urllib.request.Request(base+path,data=data,headers={'X-CWS-Local':token,**(headers or {})},method='POST')
        with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
    uploaded=post('/api/upload',source.read_bytes(),{'X-Filename':source.name})
    assert uploaded['count']==21507 and uploaded['mapping']['day']=='Garbage day'
    job=post('/api/run',json.dumps({'input_id':uploaded['input_id'],'target':900,'tolerance':12}).encode())
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        status=json.loads(get('/api/job?id='+job['job_id']))
        if status['state']!='running':break
        time.sleep(.2)
    assert status['state']=='done' and status['cached'] and status['result']==key,status
    assert json.loads(get('/api/state'))['current']==key
    assert hashlib.sha256(get('/api/monday-workbook')).digest()==hashlib.sha256(source.read_bytes()).digest()
    for kind,suffix,delivery in [('assignments','assignments.csv','Monday_partition_assignments.csv'),
                                 ('areas','areas.geojson','Monday_partition_areas.geojson'),
                                 ('review','review.json','Monday_partition_review.json')]:
        expected=(server.CACHE/(key+'.'+suffix)).read_bytes()
        assert get('/api/download?key='+key+'&kind='+kind)==expected
        assert (server.DELIVERY/delivery).read_bytes()==expected
    with zipfile.ZipFile(io.BytesIO(get('/api/download?key='+key+'&kind=package'))) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist())==3
    for payload in [{'input_id':uploaded['input_id'],'target':900,'tolerance':12,'use_mapped_alleys':True},
                    {'input_id':uploaded['input_id'],'minimum':900,'maximum':800}]:
        try:post('/api/run',json.dumps(payload).encode())
        except urllib.error.HTTPError as error:assert error.code==400
        else:raise AssertionError('Invalid preferences accepted')
    demo=post('/api/demo',b'{}');assert demo['count']==21507
    assert json.loads(get('/api/state'))['current']==key
    html=get('/').decode();assert 'value="900"' in html and 'value="12"' in html
    receipt={'key':key,'engine':server.ENGINE_VERSION,'url':base,'pid':state['pid'],'cached_run':True,
             'xlsx_upload_and_csv_demo':True,'source_excel_download_identical':True,'published_exports_identical':True,
             'zip_valid':True,'invalid_preferences_rejected':True,'summary':result['summary'],
             'external_network_calls':0,'chrome_visual_qa':'Connector unavailable; API checks only'}
    (server.CACHE/'range-api-validation.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
