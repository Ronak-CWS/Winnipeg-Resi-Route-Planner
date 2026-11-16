"""Build a portable Monday-only map; all address data and Leaflet are local."""
import argparse
import json
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    run = args.run
    rows = json.loads((run / "audit/monday_data.json").read_text(encoding="utf-8"))
    fields = ["AddressId", "CombinedAddress", "PostalCode", "YardWasteCollectionCycle",
              "Latitude", "Longitude", "CoordinateStatus", "MatchedCityAddress", "CoordinateNote"]
    compact = [[row[k] for k in fields] for row in rows]
    assets = run / "audit/assets"
    assets.mkdir(parents=True, exist_ok=True)
    urls = {
        "leaflet.js": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js",
        "leaflet.css": "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css",
        "maplibre-gl.js": "https://unpkg.com/maplibre-gl@5.7.1/dist/maplibre-gl.js",
        "maplibre-gl.css": "https://unpkg.com/maplibre-gl@5.7.1/dist/maplibre-gl.css",
        "leaflet-maplibre-gl.js": "https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.1.3/leaflet-maplibre-gl.js",
    }
    for name, url in urls.items():
        target = assets / name
        if not target.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "CWS-Winnipeg-Monday-Map/1.0"})
            # One attempt per missing, version-pinned library; never a render loop.
            with urllib.request.urlopen(request, timeout=30) as response:
                target.write_bytes(response.read())
    template = Path(__file__).with_name("monday_map_template.html").read_text(encoding="utf-8")
    html = (template.replace("__LEAFLET_CSS__", (assets / "leaflet.css").read_text(encoding="utf-8"))
            .replace("__MAPLIBRE_CSS__", (assets / "maplibre-gl.css").read_text(encoding="utf-8"))
            .replace("__LEAFLET_JS__", (assets / "leaflet.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))
            .replace("__MAPLIBRE_JS__", (assets / "maplibre-gl.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))
            .replace("__MAPLIBRE_LEAFLET_JS__", (assets / "leaflet-maplibre-gl.js").read_text(encoding="utf-8").replace("</script", "<\\/script"))
            .replace("__BASEMAP_POLICY_JS__", Path(__file__).with_name("basemap_request_policy.js").read_text(encoding="utf-8"))
            .replace("__MONDAY_DATA__", json.dumps(compact, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")))
    if "tile.openstreetmap.org" in html or "basemaps.cartocdn.com" in html:
        raise ValueError("A blocked raster tile provider remains in the generated map")
    target = run / "Monday_address_map.html"
    target.write_text(html, encoding="utf-8")
    print(json.dumps({"map": str(target.resolve()), "bytes": target.stat().st_size, "records": len(rows)}))


if __name__ == "__main__":
    main()
