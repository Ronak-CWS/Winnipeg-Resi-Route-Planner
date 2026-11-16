"""Independent Monday source/CSV/GeoJSON verification and fresh-process replay check."""
from collections import Counter, defaultdict
import argparse
import csv
import hashlib
import json
from pathlib import Path

import openpyxl
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely import make_valid
from shapely.ops import transform
from shapely.strtree import STRtree

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"outputs/2026-11-04_monday_map"
AUDIT=OUT/"audit/partition_app"
SOURCE=ROOT/"data/source/Winnipeg - Area 1 addresses.xlsx"
SOURCE_HASH="fbff92cbe50d4a56aa39883a8fafbe0de97ac3a542c47df2f02a8e106c18d5a2"


def string(value):
    return "" if value is None else str(int(value)) if isinstance(value,float) and value.is_integer() else str(value)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--key')
    parser.add_argument('--replay',type=Path)
    args=parser.parse_args()
    source_hash=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    assert source_hash==SOURCE_HASH
    workbook=openpyxl.load_workbook(SOURCE,read_only=True,data_only=True)
    values=workbook["Monday"].iter_rows(values_only=True)
    header=[string(v).strip() for v in next(values)]
    source={string(row[0]):{key:string(row[i]) for i,key in enumerate(header[:6])} for row in values if row[0] is not None}
    workbook.close()
    reference=list(csv.DictReader((OUT/"Monday_addresses_lat_long.csv").open(encoding="utf-8-sig",newline="")))
    reference_by_id={r["AddressId"]:r for r in reference}
    target={'key':args.key} if args.key else json.loads((AUDIT/"ui-validation-target.json").read_text())["result"]
    cached=json.loads((AUDIT/f"{target['key']}.result.json").read_text())
    replay=json.loads((args.replay or AUDIT/'result.json').read_text()) if args.replay or not args.key else None
    if replay:
        assert cached["partition_hash"]==replay["partition_hash"]
        assert cached["areas"]==replay["areas"]
    points={p["id"]:p for p in cached["points"]}
    assignments=list(csv.DictReader((AUDIT/f"{target['key']}.assignments.csv").open(encoding="utf-8-sig",newline="")))
    upload_names={'CombinedAddress':'Address','PostalCode':'Postal code','GarbageCollectionDay':'Garbage day',
                  'RecyclingCollectionDay':'Recycling day','YardWasteCollectionCycle':'Yard waste cycle',
                  'CoordinateStatus':'Coordinate status','MatchedCityAddress':'City address matched',
                  'CoordinateNote':'Coordinate note','CityReferenceRows':'City rows','SourceExcelRow':'Source Excel row'}
    def exported(row,field):
        return row[field] if field in row else row[upload_names[field]]
    assert len(assignments)==len(source)==21507
    assert set(points)==set(source)=={r["AddressId"] for r in assignments}
    assert len({r["AddressId"] for r in assignments})==21507
    for row in assignments:
        identity=row["AddressId"]
        for field,value in source[identity].items():assert exported(row,field)==value,(identity,field)
        for field,value in reference_by_id[identity].items():assert exported(row,field)==value,(identity,field)
        assert row[cached["assignment_columns"]["PartitionAreaId"]]==points[identity]["section"]
        assert abs(float(row["Latitude"])-points[identity]["lat"])<1e-11
        assert abs(float(row["Longitude"])-points[identity]["lon"])<1e-11
    projected=Transformer.from_crs(4326,32614,always_xy=True)
    wgs={f["id"]:shape(f["geometry"]) for f in cached["areas"]["features"]}
    properties={f['id']:f['properties'] for f in cached['areas']['features']}
    assert all(g.is_valid and g.geom_type in {'Polygon','MultiPolygon'} for g in wgs.values())
    # Published WGS validity was checked strictly above. The independent metric
    # projection may introduce floating-point zero-area lines; normalise those
    # for area operations without weakening the published-geometry gate.
    geometries={sid:make_valid(transform(projected.transform,g)) for sid,g in wgs.items()}
    for sid,g in geometries.items():
        if g.geom_type=='Polygon':continue
        p=properties[sid];parts=list(g.geoms)
        assert p['nearby_small_area_group'] and len(parts)<=len(p['nearby_merge_links'])+1
        assert all(link['smaller_addresses']<100 and link['distance_m']<=500 for link in p['nearby_merge_links'])
        assigned=[Point(*projected.transform(point['lon'],point['lat'])) for point in points.values() if point['section']==sid and point['trusted']]
        assert all(any(part.distance(point)<.002 for point in assigned) for part in parts)
        reached={0}
        while True:
            extra={j for i in reached for j in range(len(parts)) if parts[i].distance(parts[j])<=500}
            if extra<=reached:break
            reached|=extra
        assert len(reached)==len(parts),(sid,'nearby-group gap')
    # An intentional serviced enclave is complementary ownership, not an
    # unassigned hole. Independently require every ring to be fully covered.
    from shapely.geometry import Polygon
    from shapely.ops import unary_union
    for sid,g in wgs.items():
        for ring in [r for part in ([g] if g.geom_type=='Polygon' else g.geoms) for r in part.interiors]:
            hole=Polygon(ring)
            others=unary_union([p for other,p in wgs.items() if other!=sid and p.intersects(hole)])
            assert transform(projected.transform,hole.difference(others)).area<=1,(sid,'unassigned hole')
    for p in points.values():
        if p["trusted"]:
            assert geometries[p["section"]].buffer(.000001).covers(Point(*projected.transform(p["lon"],p["lat"]))),p["id"]
    coordinate_groups=defaultdict(set)
    for p in points.values():coordinate_groups[(p["lat"],p["lon"])].add(p["section"])
    assert all(len(owners)==1 for owners in coordinate_groups.values())
    polygons=list(wgs.values());tree=STRtree(polygons);overlap=0
    for i,geometry in enumerate(polygons):
        for j in tree.query(geometry):
            if int(j)>i:overlap+=transform(projected.transform,geometry.intersection(polygons[int(j)])).area
    assert overlap<=1
    assert cached["validation"]["material_parcel_cuts"]==0
    assert cached["validation"]["split_protected_groups"]==0
    settings=cached['settings']
    above=[]
    if settings['mode']=='target':
        assert settings['tolerance_percent']>=10
        above=[f['id'] for f in cached['areas']['features'] if f['properties']['addresses']>settings['maximum_addresses']]
        assert above==cached['validation']['areas_above_limit']
        below=[f['id'] for f in cached['areas']['features'] if f['properties']['addresses']<settings['preferred_minimum']]
        assert cached['summary']['target_met']==(not above and not below)
        assert below==cached['validation']['below_preferred_range']
        assert all(f['properties']['oversize_reason'] for f in cached['areas']['features'] if f['id'] in above)
    user=points["49738"]
    assert user["quality"]=="User supplied"
    assert abs(user["lat"]-(49+51/60+.3/3600))<1e-11
    assert abs(user["lon"]+97+13/60+29.8/3600)<1e-11
    report={"source_sha256":source_hash,"source_rows":len(source),"assignment_rows":len(assignments),
            "original_six_source_values_and_all_coordinate_values_unchanged":True,
            "exactly_once":True,"shared_coordinate_groups":len(coordinate_groups),"shared_coordinates_split":0,
            "reliable_points_outside":0,"valid_single_polygons":sum(g.geom_type=='Polygon' for g in geometries.values()),
            "valid_nearby_multi_piece_groups":sum(g.geom_type=='MultiPolygon' for g in geometries.values()),"unassigned_holes":0,
            "overlap_m2":overlap,"user_supplied_49738_preserved":True,
            "fresh_process_replay_identical":bool(replay),"partition_hash":cached["partition_hash"],
            "areas_above_limit":len(above),'address_limit_met':not above if settings['mode']=='target' else None,
            "network_calls":0,"status":cached["status"]}
    (AUDIT/"export-validation.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))


if __name__=="__main__":main()
