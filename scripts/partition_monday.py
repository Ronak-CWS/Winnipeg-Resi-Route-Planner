"""Run the same offline engine used by the web app, without opening any maps."""
from pathlib import Path
import argparse
import json
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from partition_app.engine import assignments_csv, plan
from partition_app.geography import Geography
from partition_app.inputs import parse_upload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target", type=int)
    parser.add_argument("--tolerance", type=float, default=15)
    parser.add_argument("--minimum", type=int)
    parser.add_argument("--maximum", type=int)
    parser.add_argument("--confirm-monday", action="store_true")
    args = parser.parse_args()
    data = parse_upload(args.input.read_bytes(), args.input.name, confirm_monday=args.confirm_monday)
    print("Loading frozen geography", flush=True)
    geography = Geography()
    last_progress=[None,0.]
    def progress(pc,message):
        if pc!=last_progress[0] or time.monotonic()-last_progress[1]>15:
            print(f"{pc}% {message}",flush=True);last_progress[:]=[pc,time.monotonic()]
    result = plan(data, geography, args.target, progress, args.tolerance, args.minimum, args.maximum)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, payload in [("result.json", result), ("areas.geojson", result["areas"]),
                          ("review.json", {k: result[k] for k in ["status", "summary", "settings", "findings", "validation", "boundary_candidates", "partition_hash"]})]:
        (args.out / name).write_text(json.dumps(payload, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    (args.out / "assignments.csv").write_text(assignments_csv(data, result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "summary": result["summary"], "validation": result["validation"], "hash": result["partition_hash"]}, indent=2), flush=True)


if __name__ == "__main__":
    main()
