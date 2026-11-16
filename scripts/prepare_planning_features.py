"""One-time, local-only enrichment. Never called from uploads or partition runs."""
import hashlib
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from partition_app.geography import GEO_DIR


def main():
    import osmium
    from shapely.geometry import LineString, Polygon, box, mapping
    meta = json.loads((GEO_DIR / "physical_features.source.json").read_text())
    source = Path(meta["source"])
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--greenways',action='store_true')
    args=parser.parse_args()
    stem='greenway_features' if args.greenways else 'planning_features'
    dest = GEO_DIR / (stem+".geojson")
    receipt = GEO_DIR / (stem+".source.json")
    if dest.exists() and receipt.exists():
        assert hashlib.sha256(dest.read_bytes()).hexdigest() == json.loads(receipt.read_text())["sha256"]
        print("Reusing existing planning-feature cache", flush=True)
        return
    assert hashlib.sha256(source.read_bytes()).hexdigest() == meta["source_sha256"]
    extent = box(*meta["bbox"])
    features = []

    class Handler(osmium.SimpleHandler):
        def way(self, way):
            tags = dict(way.tags)
            category = None
            if args.greenways:
                if tags.get('highway') in {'path','footway','cycleway','pedestrian'} and tags.get('footway') not in {'sidewalk','crossing'} and tags.get('indoor')!='yes':
                    category='greenway'
            elif tags.get("highway") in {"tertiary", "secondary", "primary", "residential", "unclassified", "living_street", "service"}:
                category = "alley" if tags.get("service") == "alley" else "road_reference"
            elif tags.get("amenity") == "school" or tags.get("leisure") in {"park", "recreation_ground", "pitch", "sports_centre", "golf_course"}:
                category = "recreation"
            elif tags.get("landuse") in {"brownfield", "greenfield", "grass", "meadow", "recreation_ground", "forest"}:
                category = "mapped_open_land"
            if category is None:
                return
            try:
                coords = [(n.lon, n.lat) for n in way.nodes]
                if len(coords) < 2:
                    return
                geometry = LineString(coords)
                if not geometry.intersects(extent):
                    return
                if category in {"recreation", "mapped_open_land"}:
                    if len(coords) < 4 or coords[0] != coords[-1]:
                        return
                    geometry = Polygon(coords)
                    if not geometry.is_valid:
                        return
                features.append({"type": "Feature", "id": f"planning-way-{way.id}",
                    "properties": {"category": category, "name": tags.get("name", ""), "rank": 3, "tags": tags},
                    "geometry": mapping(geometry.intersection(extent))})
            except (osmium.InvalidLocationError, ValueError):
                pass
    Handler().apply_file(str(source), locations=True, idx="flex_mem")
    features.sort(key=lambda f: f["id"])
    dest.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    new_meta = {"file": dest.name, "name": "Mapped path/greenway corridor candidates" if args.greenways else "Local road, alley, recreation and open-land evidence", "source": str(source),
        "source_sha256": meta["source_sha256"], "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(), "features": len(features),
        "license": "OpenStreetMap contributors, ODbL", "source_kind": "existing local PBF; zero network requests",
        "limitations": "Mapped physical features do not establish actual collection access. Way-only inventory; relation completeness unverified.",
        "automatic_refresh": False}
    receipt.write_text(json.dumps(new_meta, indent=2), encoding="utf-8")
    manifest_path = GEO_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sources"].append(new_meta)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"features": len(features), "bytes": dest.stat().st_size, "network_requests": 0}), flush=True)


if __name__ == "__main__":
    main()
