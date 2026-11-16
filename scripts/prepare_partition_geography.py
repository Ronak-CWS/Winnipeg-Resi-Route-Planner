"""Freeze Winnipeg reference geometry once. Never called by the web application.

Uses four bounded, cached City bulk downloads and an existing local Manitoba PBF.
No map tiles, geocoding, Overpass, OSRM or retry loops are used here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "data/reference/partition_geography"
UA = "CWS-Winnipeg-Monday-Partitioner/1.0 (one-time cached reference preparation)"
BBOX = (-97.55, 49.68, -96.9, 50.08)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_city(name: str, dataset: str, geometry: str, fields: str, limit: int, where: str = "", max_mib=30) -> dict:
    path = DEST / f"{name}.json"
    meta_path = DEST / f"{name}.source.json"
    if path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if digest(path) != meta["sha256"]:
            raise RuntimeError(f"Cached {name} hash changed; inspect before replacing it.")
        print(f"Cached {name}: {meta['rows']:,} rows", flush=True)
        return meta
    if path.exists() or meta_path.exists():
        raise RuntimeError(f"Incomplete {name} cache; inspect before retrying preparation.")
    session = requests.Session()
    session.headers["User-Agent"] = UA
    schema = session.get(f"https://data.winnipeg.ca/api/views/{dataset}.json", timeout=25)
    schema.raise_for_status()
    metadata = schema.json()
    params = {"$select": fields, "$limit": limit, "$order": ":id"}
    if name == "parcels":
        params.update({"$select": "min(gisid) as gisid,geometry", "$group": "geometry", "$order": "gisid"})
    if where:
        params["$where"] = where
    url = f"https://data.winnipeg.ca/resource/{dataset}.json"
    temporary = path.with_suffix(".download")
    try:
        with session.get(url, params=params, timeout=(15, 120), stream=True) as response:
            response.raise_for_status()
            size = 0
            with temporary.open("wb") as stream:
                for chunk in response.iter_content(1024 * 1024):
                    size += len(chunk)
                    if size > max_mib * 1024 * 1024:
                        failure = {"name": name, "url": response.url, "bytes_received": size,
                                   "stopped": "preparation size guard", "automatic_retry": False}
                        (DEST / f"{name}.stopped.json").write_text(json.dumps(failure, indent=2))
                        raise RuntimeError(f"Reference download exceeded its {max_mib} MiB preparation limit.")
                    stream.write(chunk)
            rows = json.loads(temporary.read_bytes())
            if not rows or len(rows) >= limit:
                raise RuntimeError(f"{name} may be empty or truncated; refusing this cache.")
            if any(geometry not in row for row in rows):
                rows = [row for row in rows if row.get(geometry)]
                temporary.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
            temporary.replace(path)
            meta = {
                "dataset": dataset, "name": metadata["name"], "geometry_field": geometry,
                "url": response.url, "catalog_url": f"https://data.winnipeg.ca/d/{dataset}",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "source_updated_at": metadata.get("rowsUpdatedAt"), "rows": len(rows),
                "bytes": path.stat().st_size, "sha256": digest(path),
                "license": "Open Government Licence - Winnipeg", "crs": "EPSG:4326",
                "filter": where or "entire published dataset", "automatic_refresh": False,
            }
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            print(f"Frozen {name}: {len(rows):,} rows; {path.stat().st_size:,} bytes", flush=True)
            return meta
    finally:
        if temporary.exists():
            temporary.unlink()


def extract_osm(pbf: Path) -> dict:
    import osmium
    from shapely.geometry import LineString, Polygon, box, mapping

    path = DEST / "physical_features.geojson"
    meta_path = DEST / "physical_features.source.json"
    if path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text())
        if digest(path) != meta["sha256"]:
            raise RuntimeError("Physical feature cache hash changed.")
        print(f"Cached physical features: {meta['features']:,}", flush=True)
        return meta
    extent = box(*BBOX)
    features = []

    class Handler(osmium.SimpleHandler):
        def way(self, way):
            tags = dict(way.tags)
            category = None
            rank = 8
            if tags.get("waterway") in {"river", "canal", "stream"}:
                category, rank = "waterway", 0
            elif tags.get("railway") == "rail" and not tags.get("service"):
                category, rank = "railway", 1
            elif tags.get("highway") in {"motorway", "trunk"}:
                category, rank = "controlled_road", 2
            elif tags.get("highway") == "primary":
                category, rank = "major_road", 4
            elif tags.get("highway") == "secondary":
                category, rank = "collector", 5
            elif tags.get("natural") == "water" or tags.get("waterway") == "riverbank":
                category, rank = "water_area", 0
            elif tags.get("landuse") in {"industrial", "commercial", "railway"}:
                category, rank = "landuse", 3
            if category is None:
                return
            try:
                coords = [(node.lon, node.lat) for node in way.nodes]
                if len(coords) < 2:
                    return
                geometry = LineString(coords)
                if not geometry.intersects(extent):
                    return
                if category in {"water_area", "landuse"}:
                    if len(coords) < 4 or coords[0] != coords[-1]:
                        return
                    geometry = Polygon(coords)
                    if not geometry.is_valid:
                        return
                features.append({"type": "Feature", "id": f"osm-way-{way.id}",
                    "properties": {"osm_id": str(way.id), "name": tags.get("name", ""),
                        "category": category, "rank": rank, "tags": tags},
                    "geometry": mapping(geometry.intersection(extent))})
            except (osmium.InvalidLocationError, ValueError):
                return

    print("Extracting Winnipeg physical features from the existing local Manitoba PBF...", flush=True)
    Handler().apply_file(str(pbf), locations=True, idx="flex_mem")
    features.sort(key=lambda feature: feature["id"])
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    meta = {"source": str(pbf.resolve()), "source_sha256": digest(pbf),
        "source_file_modified": datetime.fromtimestamp(pbf.stat().st_mtime, timezone.utc).isoformat(),
        "retrieved_at": datetime.now(timezone.utc).isoformat(), "sha256": digest(path),
        "features": len(features), "bbox": BBOX, "crs": "EPSG:4326",
        "license": "OpenStreetMap contributors, ODbL", "source_kind": "local cached PBF; no network",
        "limitations": "Way geometry only; no complete relation water/landuse inventory or legal crossing proof.",
        "automatic_refresh": False}
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"Frozen physical features: {len(features):,}", flush=True)
    return meta


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pbf", type=Path, required=True)
    args = parser.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    sources = []
    sources.append(fetch_city("neighbourhoods", "8k6x-xxsy", "location", "id,name,location", 2000))
    sources.append(fetch_city("roads", "ngsx-caav", "the_geom", "segment_id,full_name,type,the_geom", 50000))
    sources.append(fetch_city("parks", "tx3d-pfxq", "polygon", "park_id,park_name,classification_type,polygon", 10000))
    # The survey export includes extremely detailed road parcels and exceeded the
    # size guard. Use a bounded geometry-only assessment extract. Primary accounts
    # avoid unit/condo duplicates; any unmatched serviced sites remain explicit QA.
    west, south, east, north = -97.34, 49.75, -97.09, 49.99
    sources.append(fetch_city("parcels", "d4mq-wa44", "geometry", "gisid,geometry", 250000,
                              f"centroid_lat between {south} and {north} and centroid_lon between {west} and {east} and unit_number is null", max_mib=60))
    sources.append(extract_osm(args.pbf))
    (DEST / "manifest.json").write_text(json.dumps({"prepared_at": datetime.now(timezone.utc).isoformat(),
        "sources": sources, "parcel_coverage": [west, south, east, north],
        "policy": "Frozen local data; no per-upload retrieval or automatic refresh."}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
