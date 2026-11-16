"""Cache a freshly replayed CSV artifact only after cross-format verification."""
import json
import argparse
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from partition_app import server,engine
from partition_app.inputs import parse_upload

parser=argparse.ArgumentParser();parser.add_argument('--minimum',type=int,default=900);parser.add_argument('--maximum',type=int,default=1100);args=parser.parse_args()
audit=server.CACHE
validated=json.loads((audit/'export-validation.json').read_text())
assert validated['fresh_process_replay_identical']
result=json.loads((audit/'result.json').read_text())
assert result['partition_hash']==validated['partition_hash'] and result['summary']['errors']==0
source=server.DEMO;dataset=parse_upload(source.read_bytes(),source.name)
assert result['input_hash']==dataset.digest and result['engine']==engine.ENGINE_VERSION
assert result['settings']['preferred_minimum']==args.minimum and result['settings']['maximum_addresses']==args.maximum
key=server.cache_key(dataset,None,minimum=args.minimum,maximum=args.maximum);result['key']=key
for suffix,payload in [('result.json',server.json_text(result)),('areas.geojson',server.json_text(result['areas'])),
                       ('assignments.csv',engine.assignments_csv(dataset,result)),
                       ('review.json',server.json_text({k:v for k,v in result.items() if k not in {'areas','points'}}))]:
    server.write_atomic(audit/(key+'.'+suffix),payload)
receipt={'key':key,'partition_hash':result['partition_hash'],'source':dataset.source,'csv_and_xlsx_geometry_identical':True}
(audit/'csv-replay-cache-validation.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps(receipt,indent=2))
