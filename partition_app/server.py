"""Loopback-only web UI. One local worker, frozen GIS, no automatic network calls."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import traceback
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .engine import ENGINE_VERSION, assignments_csv, plan
from .geography import GEO_DIR, ROOT, Geography
from .inputs import MAX_BYTES, InputError, parse_upload
from .days import DAYS, day_label
from .preferences import address_preferences
from routing_app import api as routing_api

DELIVERY = ROOT / "outputs/2026-11-04_monday_map"
CACHE = DELIVERY / "audit/partition_app"
ASSETS = DELIVERY / "audit/assets"
WEB = ROOT / "web"
DEMO = DELIVERY / "Monday_addresses_lat_long.csv"
CSRF = secrets.token_urlsafe(32)
PARTITION_SECONDS = 30 * 60
POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Service-area-partition")
LOCK = threading.RLock()
DATASETS = {}
JOBS = {}
STATE = {"active": None, "active_kind": None, "current": None, "day": None, "geography": None, "context": None}


def example_path(day="MONDAY", extension="csv"):
    return DELIVERY / f"{day_label(day)}_addresses_lat_long.{extension}"


def write_atomic(path, content):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    temporary.replace(path)


def json_text(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def get_geography():
    if STATE["geography"] is None:
        STATE["geography"] = Geography()
    return STATE["geography"]


def cache_key(dataset, target, tolerance=15, minimum=None, maximum=None, use_mapped_alleys=False):
    manifest = (GEO_DIR / "manifest.json").read_bytes()
    code = b"".join(path.name.encode()+path.read_bytes() for path in sorted((ROOT/'partition_app').glob('*.py')))
    settings = address_preferences(target, tolerance, minimum, maximum)
    settings["use_mapped_alley_evidence"] = use_mapped_alleys
    return hashlib.sha256((ENGINE_VERSION + dataset.digest + json.dumps(settings, sort_keys=True)).encode() + manifest + code).hexdigest()


def load_result(key):
    if not re.fullmatch(r"[a-f0-9]{64}", key):
        raise FileNotFoundError("Unknown result.")
    return json.loads((CACHE / f"{key}.result.json").read_text(encoding="utf-8"))


def run_job(job_id, dataset, target, key, tolerance=15, minimum=None, maximum=None, use_mapped_alleys=False):
    started_at = time.monotonic()
    def progress(percent, message):
        with LOCK:
            if JOBS[job_id].get("cancelled"):
                raise InterruptedError("Partition cancelled. The previous result is preserved.")
            elapsed = time.monotonic() - started_at
            if elapsed > PARTITION_SECONDS:
                raise TimeoutError("The 30-minute local partition budget was reached. The previous result is preserved.")
            JOBS[job_id].update(progress=max(percent,JOBS[job_id].get('progress',0)), message=message,
                               elapsed_seconds=round(elapsed), calculation_limit_seconds=PARTITION_SECONDS)
    try:
        progress(5, "Loading frozen local geography")
        cached = CACHE / f"{key}.result.json"
        reused = cached.exists()
        if reused:
            result = load_result(key)
            progress(96, "Reusing the identical input and settings; no solve or map reload")
        else:
            result = plan(dataset, get_geography(), target, progress, tolerance, minimum, maximum, use_mapped_alleys)
            result["key"] = key
            CACHE.mkdir(parents=True, exist_ok=True)
            write_atomic(CACHE / f"{key}.result.json", json_text(result))
            write_atomic(CACHE / f"{key}.assignments.csv", assignments_csv(dataset, result))
            write_atomic(CACHE / f"{key}.areas.geojson", json_text(result["areas"]))
            review = {k: v for k, v in result.items() if k not in {"points", "areas"}}
            write_atomic(CACHE / f"{key}.review.json", json_text(review))
        label = day_label(result["day"])
        progress(99, f"Updating the {label} delivery")
        with LOCK:
            # No accepted file is replaced by a failed geometry run.
            if result["status"] != "FAILED":
                if STATE["current"] and STATE.get("day"):
                    write_atomic(CACHE / f"current-{STATE['day'].lower()}.json", json_text({"key": STATE["current"], "day": STATE["day"]}))
                STATE["current"] = key
                STATE["day"] = result["day"]
                pointer = json_text({"key": key, "day": result["day"]})
                write_atomic(CACHE / "current.json", pointer)
                write_atomic(CACHE / f"current-{result['day'].lower()}.json", pointer)
                for extension, name in [("areas.geojson", f"{label}_partition_areas.geojson"),
                                        ("assignments.csv", f"{label}_partition_assignments.csv"),
                                        ("review.json", f"{label}_partition_review.json")]:
                    write_atomic(DELIVERY / name, (CACHE / f"{key}.{extension}").read_bytes())
            JOBS[job_id].update(state="done", progress=100, message="Partition ready for review", result=key,
                                cached=reused, summary=result["summary"], status=result["status"])
    except InterruptedError as exc:
        with LOCK:
            JOBS[job_id].update(state="cancelled", message=str(exc))
    except Exception as exc:
        traceback.print_exc()
        with LOCK:
            JOBS[job_id].update(state="error", message=str(exc))
    finally:
        with LOCK:
            STATE["active"] = None
            STATE["active_kind"] = None


def context_data():
    if STATE["context"] is None:
        roads = json.loads((GEO_DIR / "roads.json").read_text())
        physical = json.loads((GEO_DIR / "physical_features.geojson").read_text())
        features = [{"type": "Feature", "properties": {"name": row.get("full_name", ""), "kind": "road"}, "geometry": row["the_geom"]} for row in roads]
        features.extend({"type": "Feature", "properties": {"name": row["properties"]["name"], "kind": row["properties"]["category"]}, "geometry": row["geometry"]}
                        for row in physical["features"] if row["properties"]["category"] in {"waterway", "water_area", "railway", "landuse"})
        features.extend({"type":"Feature","properties":{"name":row.get('park_name',''),'kind':'park'},'geometry':row['polygon']}
                        for row in json.loads((GEO_DIR/'parks.json').read_text()))
        features.extend({"type":"Feature","properties":{"name":row['name'],'kind':'community'},'geometry':row['location']}
                        for row in json.loads((GEO_DIR/'neighbourhoods.json').read_text()))
        STATE["context"] = json_text({"type": "FeatureCollection", "features": features}).encode()
    return STATE["context"]


class Handler(BaseHTTPRequestHandler):
    server_version = "CWSServiceAreas/1.1"

    def log_message(self, fmt, *args):
        print(f"{self.log_date_time_string()} {fmt % args}", flush=True)

    def headers_safe(self):
        port = self.server.server_address[1]
        host = self.headers.get("Host", "")
        if host not in {f"127.0.0.1:{port}", f"localhost:{port}"}:
            return False
        origin = self.headers.get("Origin")
        return not origin or origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def reply(self, data, code=200, content_type="application/json; charset=utf-8", filename=None, offline_document=False):
        if isinstance(data, (dict, list)):
            data = json_text(data)
        if isinstance(data, str):
            data = data.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        policy=("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; connect-src 'none'; base-uri 'none'; frame-ancestors 'none'"
            if offline_document else "default-src 'self'; script-src 'self' blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self' https://tiles.openfreemap.org; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.send_header("Content-Security-Policy",policy)
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        if len(data) > 4096 and "gzip" in self.headers.get("Accept-Encoding", ""):
            data = gzip.compress(data, compresslevel=4)
            self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if not self.headers_safe():
            return self.reply({"error": "Localhost requests only."}, 403)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path
        try:
            if path == "/api/state":
                index = ASSETS / "openfreemap_qa_cache.json"
                return self.reply({"csrf": CSRF, "pid": os.getpid(), "day": STATE.get("day"), "demo_available": DEMO.exists(),
                                   "demo_days": [day for day in DAYS if example_path(day).exists()],
                                   "current": STATE["current"], "active": STATE["active"], "active_kind": STATE["active_kind"],
                                   "routing_current": routing_api.current(CACHE, STATE.get("day")),
                                   "geography_prepared": (GEO_DIR / "manifest.json").exists(),
                                   "basemap_cached_urls": list(json.loads(index.read_text())) if index.exists() else [],
                                   "storage": str(DELIVERY), "version": ENGINE_VERSION})
            if path == "/api/context":
                return self.reply(context_data())
            if path == '/truck-maps.html':
                day = query.get("day", [STATE.get("day") or "MONDAY"])[0]
                return self.reply((DELIVERY/f'{day_label(day)}_truck_route_maps.html').read_bytes(),content_type='text/html; charset=utf-8',offline_document=True)
            if path.startswith('/api/routing/'):
                return routing_api.get(self, sys.modules[__name__], path, query)
            if path in {"/api/monday-workbook", "/api/workbook"}:
                day = "MONDAY" if path == "/api/monday-workbook" else query.get("day", [STATE.get("day") or "MONDAY"])[0]
                workbook = example_path(day, "xlsx")
                return self.reply(workbook.read_bytes(), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", filename=workbook.name)
            if path == "/api/job":
                with LOCK:
                    job = JOBS.get(query.get("id", [""])[0])
                    if job is None:
                        raise FileNotFoundError("Unknown job.")
                    return self.reply(dict(job))
            if path == "/api/result":
                return self.reply(load_result(query.get("key", [STATE["current"] or ""])[0]))
            if path == "/api/basemap-cache":
                url = query.get("url", [""])[0]
                index = json.loads((ASSETS / "openfreemap_qa_cache.json").read_text())
                resource = index.get(url)
                if not resource or Path(resource["file"]).name != resource["file"]:
                    raise FileNotFoundError("Resource is not in the frozen overview cache. No upstream request was made.")
                return self.reply((ASSETS / resource["file"]).read_bytes(), content_type=resource.get("content_type", "application/octet-stream"))
            if path == "/api/download":
                key = query.get("key", [STATE["current"] or ""])[0]
                result = load_result(key)
                label = day_label(result["day"])
                kind = query.get("kind", ["assignments"])[0]
                names = {"assignments": ("assignments.csv", "text/csv; charset=utf-8"), "areas": ("areas.geojson", "application/geo+json"), "review": ("review.json", "application/json")}
                if kind == "package":
                    buffer = io.BytesIO()
                    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                        for extension, _ in names.values():
                            archive.write(CACHE / f"{key}.{extension}", f"{label}_partition_{extension}")
                    return self.reply(buffer.getvalue(), content_type="application/zip", filename=f"{label}_partition.zip")
                if kind not in names:
                    raise FileNotFoundError("Unknown export.")
                extension, mime = names[kind]
                return self.reply((CACHE / f"{key}.{extension}").read_bytes(), content_type=mime, filename=f"{label}_partition_{extension}")
            static = {"/": (WEB / "index.html", "text/html; charset=utf-8"), "/app.css": (WEB / "app.css", "text/css"),
                      "/app.js": (WEB / "app.js", "text/javascript"), "/routing.js": (WEB / "routing.js", "text/javascript"),
                      "/routing.css": (WEB / "routing.css", "text/css"), "/basemap-policy.js": (ROOT / "scripts/basemap_request_policy.js", "text/javascript")}
            for name in ("leaflet.js", "leaflet.css", "maplibre-gl.js", "maplibre-gl.css", "leaflet-maplibre-gl.js"):
                static[f"/vendor/{name}"] = (ASSETS / name, "text/css" if name.endswith("css") else "text/javascript")
            if path not in static:
                raise FileNotFoundError("Page not found.")
            file, mime = static[path]
            return self.reply(file.read_bytes(), content_type=mime)
        except (FileNotFoundError, KeyError, ValueError) as exc:
            return self.reply({"error": str(exc)}, 404)
        except Exception:
            traceback.print_exc()
            return self.reply({"error": "The local server could not read this resource. Check its log."}, 500)

    def do_POST(self):
        if not self.headers_safe() or self.headers.get("X-CWS-Local") != CSRF:
            return self.reply({"error": "Local session check failed. Reload the app."}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 <= length <= MAX_BYTES:
                return self.reply({"error": "Upload exceeds the 30 MiB limit."}, 413)
            content = self.rfile.read(length)
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            if parsed.path in {"/api/upload", "/api/demo"}:
                if parsed.path == "/api/demo":
                    day = query.get("day", ["MONDAY"])[0]
                    file = example_path(day)
                    name, content = file.name, file.read_bytes()
                    options = {"collection_day": day}
                else:
                    name = unquote(self.headers.get("X-Filename", "upload.csv"))
                    options = {"sheet": query.get("sheet", [""])[0], "collection_day": query.get("day", [""])[0],
                               "confirm_monday": query.get("monday", [""])[0] == "true"}
                    if self.headers.get("X-Column-Mapping"):
                        options["mapping"] = json.loads(self.headers["X-Column-Mapping"])
                dataset = parse_upload(content, name, **options)
                identity = uuid.uuid4().hex
                with LOCK:
                    # Prevent an unbounded upload collection. Results stay on disk.
                    if len(DATASETS) >= 4:
                        DATASETS.pop(next(iter(DATASETS)))
                    DATASETS[identity] = dataset
                return self.reply({"input_id": identity, **dataset.preview()})
            payload = json.loads(content or b"{}")
            if parsed.path == '/api/routing/settings':
                cfg = routing_api.settings(payload.get('settings'))
                routing_api.dump(CACHE / 'routing-settings.json', cfg)
                return self.reply({'settings': cfg})
            if parsed.path == '/api/routing/run':
                return routing_api.start(self, sys.modules[__name__], payload)
            if parsed.path == "/api/run":
                identity = payload.get("input_id", "")
                with LOCK:
                    if STATE["active"]:
                        return self.reply({"error": "A partition job is already running.", "job_id": STATE["active"]}, 409)
                    if identity not in DATASETS:
                        raise InputError("Load or upload the service addresses first.")
                    target = payload.get("target")
                    tolerance = payload.get("tolerance", 15)
                    minimum, maximum = payload.get("minimum"), payload.get("maximum")
                    address_preferences(target, tolerance, minimum, maximum)
                    use_mapped_alleys = payload.get("use_mapped_alleys", False)
                    if not isinstance(use_mapped_alleys,bool):
                        raise InputError("Mapped-alley evidence option must be true or false.")
                    if use_mapped_alleys:
                        raise InputError("Mapped alleys alone cannot enable street boundaries. Both curbs stay together until pickups are confirmed.")
                    dataset = DATASETS[identity]
                    key = cache_key(dataset, target, tolerance, minimum, maximum, use_mapped_alleys)
                    job_id = uuid.uuid4().hex
                    JOBS[job_id] = {"id": job_id, "state": "running", "progress": 0, "message": "Starting one local worker", "cancelled": False}
                    STATE["active"] = job_id
                    STATE["active_kind"] = 'partition'
                    POOL.submit(run_job, job_id, dataset, target, key, tolerance, minimum, maximum, use_mapped_alleys)
                    return self.reply({"job_id": job_id}, 202)
            if parsed.path == "/api/cancel":
                with LOCK:
                    job_id = STATE["active"]
                    if job_id:
                        JOBS[job_id]["cancelled"] = True
                return self.reply({"message": "Cancellation requested; stops at the next processing checkpoint."})
            raise FileNotFoundError("Unknown operation.")
        except InputError as exc:
            return self.reply({"error": str(exc), "errors": exc.errors, "available_days": exc.available_days,
                               "available_sheets": exc.available_sheets}, 400)
        except (ValueError, KeyError, TypeError) as exc:
            return self.reply({"error": str(exc)}, 400)
        except FileNotFoundError as exc:
            return self.reply({"error": str(exc)}, 404)
        except Exception:
            traceback.print_exc()
            return self.reply({"error": "Local operation failed. Check the server log."}, 500)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    CACHE.mkdir(parents=True, exist_ok=True)
    current = CACHE / "current.json"
    if current.exists():
        key = json.loads(current.read_text())["key"]
        result = load_result(key)
        if result.get("engine") == ENGINE_VERSION and not result['settings'].get('use_mapped_alley_evidence'):
            STATE["current"] = key
            STATE["day"] = result["day"]
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Service-area app: http://127.0.0.1:{args.port}", flush=True)
    print(f"Local delivery: {DELIVERY}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        with LOCK:
            if STATE["active"]:
                JOBS[STATE["active"]]["cancelled"] = True
        server.server_close()
        POOL.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
