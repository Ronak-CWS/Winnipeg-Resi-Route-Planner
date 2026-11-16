"""Isolated loopback UI fixture; never reads or writes the user's saved settings."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from partition_app import server

parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,required=True);parser.add_argument('--storage',type=Path,required=True)
args=parser.parse_args();args.storage.mkdir(parents=True,exist_ok=False)
server.DELIVERY=args.storage
server.CACHE=args.storage/'audit';server.CACHE.mkdir()
server.DEMO=args.storage/'not-an-example.csv'
server.STATE.update(current=None,day=None,active=None,active_kind=None)
sys.argv=['facility_test_server','--port',str(args.port)]
server.main()
