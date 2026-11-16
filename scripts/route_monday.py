"""Run or resume a cached Monday routing scenario in the existing delivery."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from routing_app.engine import run, dump, prepare
from routing_app.settings import settings

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--seconds',type=int,default=5)
    args=parser.parse_args()
    cache=Path('outputs/2026-11-04_monday_map/audit/partition_app')
    key=json.loads((cache/'current.json').read_text())['key']
    partition=json.loads((cache/f'{key}.result.json').read_text(encoding='utf-8'))
    cfg=settings({'search_seconds_per_section':args.seconds})
    import time
    last=[0]
    def progress(percent,message):
        if time.monotonic()-last[0]>3:
            print(f'{percent if percent is not None else "..."} {message}',flush=True);last[0]=time.monotonic()
    if args.prepare_only:
        road,groups,anchors,reviews,core,sites,ak=prepare(partition,cfg,cache,progress)
        dump(cache/'routing-preparation-validation.json',{'groups':len(groups),'anchors':len(anchors),'reviews':reviews,'sites':sites,'cache_key':ak})
        road.close()
        print('PREPARATION COMPLETE',len(groups),len(anchors),len(reviews),flush=True)
    else:
        result=run(partition,cfg,cache,progress)
        dump(cache/'routing-first-result.json',result)
        print(json.dumps({'trucks':result['total_trucks'],'streams':result['streams'],'status':result['status']}),flush=True)

if __name__=='__main__':main()
