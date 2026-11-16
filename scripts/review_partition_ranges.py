"""Offline full-data review; reuses one frozen GIS in a retained stdin session."""
import importlib
import json
import sys
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from partition_app.geography import Geography
from partition_app.inputs import parse_upload
from partition_app import engine, server

print("Loading frozen local geometry", flush=True)
server.write_atomic(server.CACHE/'offline-review-process.json',server.json_text({'pid':os.getpid(),'workspace':str(server.ROOT)}))
geography = Geography()
source = server.DELIVERY / "Monday_addresses_lat_long.xlsx"
dataset = parse_upload(source.read_bytes(), source.name)
print("Ready: send a target number, natural, or quit", flush=True)
for line in sys.stdin:
    command = line.strip()
    if command == "quit":
        break
    try:
        for module in ('partition_app.geography','partition_app.corridors','partition_app.whole_blocks','partition_app.continuity','partition_app.balancing'):
            if module in sys.modules:importlib.reload(sys.modules[module])
        importlib.reload(engine)
        importlib.reload(server)
        server.ENGINE_VERSION=engine.ENGINE_VERSION
        # Refresh methods without rebuilding the large, unchanged spatial cache.
        geography.__class__ = sys.modules["partition_app.geography"].Geography
        if command == "refresh":
            geography.refresh_dividers()
            print("Refreshed road evidence; Ready", flush=True)
            continue
        if command == "trace-natural":
            from trace_natural_first import inspect
            inspect(geography,dataset)
            print("Ready after trace",flush=True)
            continue
        if command == "trace-streets":
            import trace_street_continuity
            importlib.reload(trace_street_continuity)
            trace_street_continuity.inspect(geography,dataset)
            print('Ready after street trace',flush=True)
            continue
        options = json.loads(command) if command.startswith('{') else {"target":None if command=="natural" else int(command)}
        target = options.pop("target",None)
        started = time.monotonic()
        last_progress=[None,0.]
        def progress(percent,message):
            if (server.CACHE/'review.cancel').exists():
                raise InterruptedError('Offline review cancelled at checkpoint')
            if time.monotonic()-started>600:
                raise TimeoutError('Ten-minute offline processing budget reached')
            if percent!=last_progress[0] or time.monotonic()-last_progress[1]>15:
                print(f'{percent}% {message}',flush=True)
                last_progress[:]=[percent,time.monotonic()]
        result = engine.plan(dataset, geography, target, progress, **options)
        key = server.cache_key(dataset, target, **options)
        result["key"] = key
        for suffix, content in [("result.json", server.json_text(result)), ("areas.geojson", server.json_text(result["areas"])),
                                ("assignments.csv", engine.assignments_csv(dataset, result)),
                                ("review.json", server.json_text({k: v for k, v in result.items() if k not in {"areas", "points"}}))]:
            server.write_atomic(server.CACHE / f"{key}.{suffix}", content)
        label=(str(options['minimum'])+'-'+str(options['maximum']) if 'minimum' in options else str(target or 'natural'))+('-alleys' if options.get('use_mapped_alleys') else '')
        server.write_atomic(server.CACHE / f"range-{label}-summary.json", server.json_text({"key": key, "summary": result["summary"], "validation": result["validation"], "settings": result["settings"],
            "areas": [{k: f["properties"][k] for k in ["id", "name", "addresses", "size_status", "oversize_reason"]} for f in result["areas"]["features"]]}))
        print(json.dumps({"key": key, "seconds": round(time.monotonic()-started, 2), "summary": result["summary"],
                          "errors": [f for f in result["findings"] if f["severity"] == "error"], "merge_reasons": result["merge_reasons"]}), flush=True)
        print("Ready", flush=True)
    except Exception:
        import traceback
        traceback.print_exc()
        print("Ready after error", flush=True)
