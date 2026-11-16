"""Geocode only the preserved Monday intake, using official Winnipeg points.

Public address records supply coordinates, never additional service records.
Building fallbacks and tightly grouped site centres are explicitly labelled.
"""

import argparse
import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook


SOURCE_FIELDS = [
    "AddressId", "CombinedAddress", "PostalCode", "GarbageCollectionDay",
    "RecyclingCollectionDay", "YardWasteCollectionCycle",
]
OUTPUT_FIELDS = SOURCE_FIELDS + [
    "Latitude", "Longitude", "CoordinateStatus", "MatchedCityAddress",
    "CoordinateNote", "CityReferenceRows", "SourceExcelRow",
]
SOURCE_URL = "https://data.winnipeg.ca/City-Planning/Addresses/cam2-ii3u"
SITE_SPREAD_LIMIT_M = 15.0


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.upper().replace("'", "").replace("\u2019", "")
    text = re.sub(r"[^A-Z0-9]+", " ", text).strip()
    # Keep civic suffixes, but accept the City's intervening space: 325A = 325 A.
    return re.sub(r"^(\d+)([A-Z]+) ", r"\1 \2 ", text)


def point(row):
    match = re.fullmatch(r"\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)", row["Geometry"])
    if not match:
        raise ValueError(f"Unsupported official geometry: {row['Geometry']!r}")
    lat, lon = map(float, match.groups())
    if not (49.5 < lat < 50.5 and -98 < lon < -96):
        raise ValueError(f"Official coordinate outside Winnipeg vicinity: {lat}, {lon}")
    return lat, lon


def distance(a, b):
    p, q = map(math.radians, (a[0], b[0]))
    dlon = math.radians(b[1] - a[1])
    h = math.sin((q - p) / 2) ** 2 + math.cos(p) * math.cos(q) * math.sin(dlon / 2) ** 2
    return 2 * 6371008.8 * math.asin(min(1, math.sqrt(h)))


def load_reference(path):
    full, street, parents = defaultdict(list), defaultdict(list), defaultdict(list)
    count = 0
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            count += 1
            if not row["Geometry"].strip():
                continue
            row["_point"] = point(row)
            full[normalize(row["Full Address"])].append(row)
            street[normalize(row["Street Address"])].append(row)
            # Used only for an unsuffixed source civic with no direct city record.
            parent = " ".join(filter(None, [row["Street Number"], row["Street Name"],
                                           row["Street Type"], row["Street Direction"]]))
            parents[normalize(parent)].append(row)
    return full, street, parents, count


def locate(address, full, street, parents):
    key = normalize(address)
    base, separator, unit = key.partition(" UNIT ")
    candidates = full.get(key, [])
    status, note = "Exact address", "Official property address point."
    if not candidates:
        candidates = street.get(base, [])
        if separator:
            units = [r for r in candidates if normalize(r["Unit Number"]) == unit]
            if units:
                candidates = units
                note = "Same official street address and unit number; unit label differs."
            else:
                status = "Building address"
                note = "Unit is absent from the city reference; uses its exact building address point."
                no_units = [r for r in candidates if not r["Unit Number"].strip()]
                candidates = no_units or candidates
        else:
            no_units = [r for r in candidates if not r["Unit Number"].strip()]
            candidates = no_units or candidates
        if not candidates and not separator:
            candidates = parents.get(base, [])

    if not candidates:
        return None, None, "Not found", "", "No exact address or building in the current city reference.", 0

    points = sorted(set(r["_point"] for r in candidates))
    names = "; ".join(sorted(set(r["Full Address"] for r in candidates)))
    if len(points) == 1:
        lat, lon = points[0]
        if not full.get(key) and not separator:
            status = "Building address"
            note = "Official subdivisions share one coordinate for this exact parent civic address."
    else:
        spread = max(distance(a, b) for i, a in enumerate(points) for b in points[i + 1:])
        if spread > SITE_SPREAD_LIMIT_M:
            return (None, None, "Not found", names,
                    f"Multiple official points span {spread:.1f} m; location needs review.", len(candidates))
        lat = sum(p[0] for p in points) / len(points)
        lon = sum(p[1] for p in points) / len(points)
        status = "Approximate site centre"
        note = (f"Mean of {len(points)} official unit/subdivision points for the exact parent civic; "
                f"maximum separation {spread:.1f} m. Review site position.")
    return lat, lon, status, names, note, len(candidates)


def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def apply_coordinate_overrides(rows, path):
    """Apply explicit, provenance-labelled coordinates to existing IDs only."""
    overrides = json.loads(Path(path).read_text(encoding="utf-8"))
    index = {str(row["AddressId"]): row for row in rows}
    for address_id, item in overrides.items():
        if address_id not in index:
            raise ValueError(f"Override is outside this intake: {address_id}")
        row = index[address_id]
        if row["CombinedAddress"] != item["CombinedAddress"]:
            raise ValueError(f"Override address disagrees with AddressId {address_id}")
        lat, lon = item["Latitude"], item["Longitude"]
        if not (math.isfinite(lat) and math.isfinite(lon) and 49.5 < lat < 50.5 and -98 < lon < -96):
            raise ValueError(f"Invalid Winnipeg override coordinate: {address_id}")
        row.update(Latitude=lat, Longitude=lon, CoordinateStatus="User supplied",
                   MatchedCityAddress="", CityReferenceRows=0,
                   CoordinateNote=f"User supplied {item['provided_on']}: {item['source_dms']} (WGS 84 decimal conversion).")
    return overrides


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--overrides", type=Path)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("Use a new output directory; accepted runs are preserved.")
    before = sha256(args.source)
    book = load_workbook(args.source, read_only=True, data_only=True)
    values = book["Monday"].iter_rows(values_only=True)
    if list(next(values)) != SOURCE_FIELDS:
        raise ValueError("Unexpected Monday source headers")
    rows = [dict(zip(SOURCE_FIELDS, values), SourceExcelRow=i)
            for i, values in enumerate(values, 2) if any(v is not None for v in values)]
    book.close()
    ids = [r["AddressId"] for r in rows]
    if not rows or len(ids) != len(set(ids)):
        raise ValueError("Blank intake or repeated Monday AddressId")
    if any(r["GarbageCollectionDay"] != "MONDAY" for r in rows):
        raise ValueError("Non-Monday record in Monday intake")

    full, street, parents, ref_count = load_reference(args.reference)
    for row in rows:
        location = locate(row["CombinedAddress"], full, street, parents)
        row.update(dict(zip(OUTPUT_FIELDS[6:-1], location)))
    if args.overrides:
        apply_coordinate_overrides(rows, args.overrides)
    mapped = [r for r in rows if r["Latitude"] is not None]
    review = [r for r in rows if r["CoordinateStatus"] != "Exact address"]
    summary = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_path": str(args.source.resolve()), "source_sheet": "Monday",
        "source_sha256": before, "source_rows": len(rows), "distinct_address_ids": len(set(ids)),
        "reference_path": str(args.reference.resolve()), "reference_sha256": sha256(args.reference),
        "reference_url": SOURCE_URL, "reference_rows": ref_count,
        "mapped_rows": len(mapped), "unlocated_rows": len(rows) - len(mapped),
        "status_counts": dict(Counter(r["CoordinateStatus"] for r in rows)),
        "unique_mapped_coordinates": len(set((r["Latitude"], r["Longitude"]) for r in mapped)),
        "repeated_address_string_extra_rows": len(rows) - len(set(r["CombinedAddress"] for r in rows)),
        "coordinate_reference_system": "WGS 84 / EPSG:4326; latitude then longitude in CSV",
        "site_centre_spread_limit_m": SITE_SPREAD_LIMIT_M,
        "coordinate_scope": "Property/building locations; actual curbside/alley pickup locations are unknown.",
        "normalization": "Case, spacing, punctuation, accents and spacing before civic suffix only; retains civic suffix and street direction.",
        "source_hash_after": sha256(args.source),
        "unlocated": [{k: r[k] for k in ["AddressId", "CombinedAddress", "CoordinateNote"]}
                      for r in rows if r["Latitude"] is None],
    }
    if args.overrides:
        summary["coordinate_overrides_path"] = str(args.overrides.resolve())
    assert summary["source_sha256"] == summary["source_hash_after"]
    args.out.mkdir(parents=True)
    (args.out / "audit").mkdir()
    write_csv(args.out / "Monday_addresses_lat_long.csv", rows)
    write_csv(args.out / "Monday_location_review.csv", review)
    (args.out / "audit" / "monday_data.json").write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    (args.out / "audit" / "geocoding_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    features = [{"type": "Feature", "id": r["AddressId"],
                 "geometry": {"type": "Point", "coordinates": [r["Longitude"], r["Latitude"]]}
                             if r["Latitude"] is not None else None,
                 "properties": {k: v for k, v in r.items() if k not in ["Latitude", "Longitude"]}}
                for r in rows]
    (args.out / "Monday_addresses.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
