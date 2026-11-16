from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, set_precision, union_all
from shapely.geometry import shape, Point, LineString
from shapely.ops import polygonize, transform, unary_union, nearest_points, substring
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
GEO_DIR = ROOT / "data/reference/partition_geography"
FORWARD = Transformer.from_crs(4326, 32614, always_xy=True)
REVERSE = Transformer.from_crs(32614, 4326, always_xy=True)


def project(geometry):
    # One-centimetre topology grid removes sub-millimetre projection noise in
    # shared official edges. It cannot invent material connections or road gaps.
    return set_precision(make_valid(transform(FORWARD.transform, geometry)), 0.01)


def unproject(geometry):
    return transform(REVERSE.transform, geometry)


def polygon_parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [part for g in getattr(geometry, "geoms", []) for part in polygon_parts(g)]


def canonical(geometry):
    return geometry.normalize().wkb_hex


def serviced_parcel_component(parcel, point):
    """A cadastral identifier can cover disconnected land on different banks.

    Protect the complete connected footprint containing this service point.
    Unoccupied remote pieces do not establish a shared collection site.
    """
    parts=sorted(polygon_parts(parcel['geometry']),key=canonical)
    index=next((i for i,g in enumerate(parts) if g.covers(point)),None)
    if index is None:return None
    return index,{**parcel,'geometry':parts[index],'component':index,
        'source_component_count':len(parts)}


def line_parts(geometry):
    if geometry.geom_type == "LineString":
        return [geometry]
    return [p for g in getattr(geometry, "geoms", []) for p in line_parts(g)]


def divider_line(feature):
    geometry = feature["geometry"]
    return geometry.boundary if geometry.geom_type in {"Polygon", "MultiPolygon"} else geometry


def internal_seams(geometries):
    """Only shared child edges, never numeric remnants of the outer boundary."""
    values=list(geometries);tree=STRtree(values)
    return unary_union([shared_boundary(g,values[int(j)])
        for i,g in enumerate(values) for j in tree.query(g,predicate='intersects') if int(j)>i])


def shared_boundary(left,right):
    # New intersections have full precision while frozen inputs carry a 1 cm
    # model. Remove metadata only; snapping an overlay again can collapse a
    # tiny line and cause a GEOS mixed-dimension assertion.
    shared=set_precision(left,0).boundary.intersection(set_precision(right,0).boundary)
    # A corner contact has zero shared length and is not a section divider.
    # Keeping isolated points in a line collection also triggers a GEOS
    # mixed-dimension overlay assertion when intersecting road buffers.
    return unary_union([line for line in line_parts(shared) if line.length>0])


def segment_roads_at_barriers(roads,features):
    """Stop frontage protection at finite strong physical-boundary crossings."""
    references=[f for f in features if f['category'] in {'railway','waterway','controlled_road','high_speed_road','wide_road'}]
    barriers=[divider_line(f) for f in references]
    tree=STRtree(barriers)
    result=[]
    def crossing_points(geometry):
        if geometry.is_empty:return []
        if geometry.geom_type=='Point':return [geometry]
        if geometry.geom_type=='LineString':return [Point(geometry.coords[0]),Point(geometry.coords[-1])]
        return [p for g in getattr(geometry,'geoms',[]) for p in crossing_points(g)]
    for road in roads:
        line=road['geometry'];cuts={0.,line.length}
        for j in tree.query(line,predicate='intersects'):
            for point in crossing_points(line.intersection(barriers[int(j)])):
                distance=line.project(point)
                if .05<distance<line.length-.05:cuts.add(distance)
        # Different references can put the same street centre a few metres
        # apart. Stop protection at the finite supported wide-road span, rather
        # than carrying an ordinary-street group through its divided portion.
        for j in tree.query(line.buffer(8),predicate='intersects'):
            f=references[int(j)]
            if f['category'] not in {'wide_road','controlled_road','high_speed_road'} or not f.get('name') or street_name(f['name'])!=street_name(road['name']):continue
            for point in crossing_points(line.intersection(barriers[int(j)].buffer(8))):
                distance=line.project(point)
                if .05<distance<line.length-.05:cuts.add(distance)
        positions=sorted(cuts)
        if len(positions)==2:result.append(road);continue
        for a,b in zip(positions,positions[1:]):
            if b-a<.05:continue
            part=substring(line,a,b)
            result.append({**road,'id':road['id']+':barrier:'+hashlib.sha256(part.wkb).hexdigest()[:12],'geometry':part})
    return result


def load_noded_roads():
    """Canonical City baseline, independent of any prior review-worker state."""
    original=[{'id':str(r['segment_id']),'name':r.get('full_name',''),'type':r.get('type',''),
               'geometry':project(shape(r['the_geom']))} for r in json.loads((GEO_DIR/'roads.json').read_text())]
    tree=STRtree([r['geometry'] for r in original]);roads=[]
    for part in sorted(line_parts(unary_union([r['geometry'] for r in original])),key=canonical):
        middle=part.interpolate(.5,normalized=True)
        candidates=[int(i) for i in tree.query(middle.buffer(.02)) if original[int(i)]['geometry'].distance(middle)<.02]
        if candidates:
            road=min((original[i] for i in candidates),key=lambda r:r['id'])
            roads.append({**road,'id':road['id']+':'+hashlib.sha256(part.wkb).hexdigest()[:12],'geometry':part})
    return roads


def posted_speed_kmh(tags):
    """Explicit mapped limits only. Unknown or symbolic speeds stay unknown."""
    speeds=[]
    for key in ('maxspeed','maxspeed:forward','maxspeed:backward'):
        for value in str(tags.get(key,'')).split(';'):
            match=re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(km/h|kmh|kph|mph)?\s*',value,re.I)
            if match:speeds.append(float(match[1])*(1.609344 if (match[2] or '').lower()=='mph' else 1))
    return max(speeds) if speeds else None


def road_evidence(tags):
    """Physical road evidence; no street-name exceptions or speed-50 inference."""
    if tags.get("highway") in {"motorway", "trunk"}:
        return "Controlled highway"
    if (posted_speed_kmh(tags) or 0)>60:
        return "Mapped posted speed above 60 km/h"
    def number(key):
        match = re.match(r"^\s*(\d+(?:\.\d+)?)", tags.get(key, ""))
        return float(match[1]) if match else 0
    if number("lanes") >= 4:
        return "Mapped road with at least four traffic lanes"
    if number("width") >= 14:
        return "Mapped carriageway width of at least 14 m"
    if tags.get("divider") in {"median", "barrier", "grass", "raised"} or tags.get("dual_carriageway") == "yes":
        return "Mapped physical divider / dual carriageway"
    if (posted_speed_kmh(tags) or 0) >= 60 and tags.get("highway") in {"primary", "secondary", "tertiary"}:
        return "Mapped arterial at 60 km/h or above"
    return None


def major_speed_boundary(tags):
    """60 km/h needs arterial evidence; faster mapped roads are major dividers."""
    speed = posted_speed_kmh(tags)
    return speed is not None and (speed > 60 or
        speed >= 60 and tags.get('highway') in {'motorway', 'trunk', 'primary', 'secondary', 'tertiary'})


def street_name(value):
    words = {"street":"st", "avenue":"ave", "road":"rd", "boulevard":"blvd", "crescent":"cres", "drive":"dr", "highway":"hwy", "north":"n", "south":"s", "east":"e", "west":"w"}
    return " ".join(words.get(w,w) for w in re.sub(r"[^a-z0-9 ]", " ", (value or "").casefold()).split())


def promote_divided_roads(features, roads):
    """Recognise paired carriageways even when each direction has two lanes."""
    road_categories = {"major_road", "collector", "road_reference", "wide_road", "high_speed_road", "controlled_road"}
    references = [f for f in features if f["category"] in road_categories]
    candidates = [f for f in references if f.get("tags", {}).get("oneway") in {"yes", "1", "-1"}
                  and f.get("tags", {}).get("highway") in {"primary", "secondary", "tertiary"}
                  and f["geometry"].geom_type == "LineString" and f["geometry"].length > 20]
    tree = STRtree([f["geometry"] for f in candidates])
    def direction(f):
        a, b = (f["geometry"].interpolate(p, normalized=True) for p in (.4, .6))
        dx, dy = b.x-a.x, b.y-a.y
        length = max((dx*dx+dy*dy)**.5, .001)
        sign = -1 if f["tags"].get("oneway") == "-1" else 1
        return sign*dx/length, sign*dy/length
    for f in candidates:
        if f.get("eligible"):
            continue
        dx, dy = direction(f)
        for j in tree.query(f["geometry"].buffer(40)):
            other = candidates[int(j)]
            if not f.get("name") or f["name"].casefold() != other.get("name", "").casefold():
                continue
            if f["id"].split('-')[-1] == other["id"].split('-')[-1]:
                continue
            distance = f["geometry"].distance(other["geometry"])
            ox, oy = direction(other)
            if 3 <= distance <= 40 and dx*ox+dy*oy < -.85 and f["geometry"].intersection(other["geometry"].buffer(40)).length > f["geometry"].length*.6:
                f.update(category="wide_road", eligible=True, evidence="Opposing, parallel mapped arterial carriageways, 3–40 m apart", paired_with=other["id"])
                break
    wide = [f for f in references if f.get("eligible") or f['category']=='controlled_road']
    tree = STRtree([f["geometry"] for f in wide])
    additions = []
    for road in roads:
        nearby = [wide[int(j)] for j in tree.query(road["geometry"].buffer(25))
                  if street_name(wide[int(j)].get("name")) == street_name(road["name"])]
        if not nearby:
            continue
        supported = unary_union([road["geometry"].intersection(f["geometry"].buffer(25)) for f in nearby])
        if supported.length >= road["geometry"].length*.7:
            fast=unary_union([f['geometry'] for f in nearby if f['category']=='high_speed_road'])
            high_speed=not fast.is_empty and road['geometry'].intersection(fast.buffer(25)).length>=road['geometry'].length*.7
            controlled=unary_union([f['geometry'] for f in nearby if f['category']=='controlled_road'])
            highway=not controlled.is_empty and road['geometry'].intersection(controlled.buffer(25)).length>=road['geometry'].length*.7
            additions.append({**road, "id": "city-wide-"+road["id"], "category": "controlled_road" if highway else "high_speed_road" if high_speed else "wide_road", "rank": 2 if high_speed or highway else 3, "eligible": True,
                              "evidence": "Finite official road segment supported by wide/divided-road mapping", "evidence_ids": sorted(f["id"] for f in nearby)})
    return additions


def alley_frontage_candidates(features, roads):
    """Physical rear-alley evidence only; does not classify actual collection."""
    alleys=[f for f in features if f["category"]=="alley" and f["geometry"].geom_type=="LineString"]
    tree=STRtree([f["geometry"] for f in alleys])
    candidates=[]
    for road in roads:
        line=road["geometry"]
        if line.length<40 or road["type"]=="BRIDGE":continue
        middle=line.interpolate(.5,normalized=True)
        a,b=(line.interpolate(p,normalized=True) for p in (.4,.6))
        dx,dy=b.x-a.x,b.y-a.y
        length=max((dx*dx+dy*dy)**.5,.001)
        sides={}
        for j in tree.query(line.buffer(85)):
            alley=alleys[int(j)];g=alley["geometry"]
            if not 12<=g.distance(middle)<=85:continue
            p,q=(g.interpolate(v,normalized=True) for v in (.4,.6))
            ex,ey=q.x-p.x,q.y-p.y;other=max((ex*ex+ey*ey)**.5,.001)
            if abs((dx*ex+dy*ey)/(length*other))<.85:continue
            nearest=g.interpolate(g.project(middle));side=dx*(nearest.y-middle.y)-dy*(nearest.x-middle.x)
            supported=line.intersection(g.buffer(85)).length
            if supported<line.length*.7:continue
            sides[side>0]=alley["id"]
        if len(sides)==2:
            candidates.append({**road,"id":"alley-frontage-"+road["id"],"road_id":road["id"],"category":"alley_supported_road","rank":6,
                "evidence":"Parallel mapped rear alleys on both sides; actual pickup access remains UNKNOWN and needs confirmation",
                "evidence_ids":sorted(sides.values()),"pickup_access_confirmed":False})
    return candidates


def subdivide(parent, lines):
    """Exact finite feature geometry only. No extended rays or point-shaped polygons."""
    if not lines:
        return [parent]
    # Source vertices are on the centimetre grid. New intersections on a
    # diagonal must stay on that exact edge: re-rounding them to centimetres
    # shifts the outer coverage. Remove precision metadata, not coordinates.
    parent = set_precision(parent, 0)
    # Node complete finite source lines together. Pre-clipping a diagonal can
    # leave its computed endpoint a floating-point step off the parent edge;
    # polygonize then silently misses a genuine through-divider. The original
    # line already continues outside the parent, so no extension is necessary.
    boundary = unary_union([parent.boundary, *(set_precision(line, 0) for line in lines)])
    parts = [p for p in polygonize(boundary) if parent.covers(p.representative_point()) and p.area > 0]
    # The partition must cover its original geometry, including source polygon holes.
    if not parts or unary_union(parts).symmetric_difference(parent).area > 0.5:
        raise ValueError(f"Geographic subdivision did not preserve the parent area ({unary_union(parts).symmetric_difference(parent).area:.3f} m2).")
    return sorted(parts, key=canonical)


class Geography:
    def __init__(self):
        manifest = GEO_DIR / "manifest.json"
        if not manifest.exists():
            raise RuntimeError("Frozen geography is not prepared. Run scripts/prepare_partition_geography.py once.")
        self.manifest = json.loads(manifest.read_text())
        # Fail closed on cache drift instead of silently mixing reference versions.
        for path in sorted(GEO_DIR.glob("*.source.json")):
            meta = json.loads(path.read_text())
            data = path.with_name(meta.get("file") or path.name.replace(".source.json", ".geojson" if path.name.startswith("physical_features") else ".json"))
            if hashlib.sha256(data.read_bytes()).hexdigest() != meta["sha256"]:
                raise RuntimeError(f"Frozen reference hash mismatch: {data.name}")
        self.digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        self.neighbourhoods = []
        for row in json.loads((GEO_DIR / "neighbourhoods.json").read_text()):
            for part in polygon_parts(make_valid(project(shape(row["location"])))):
                self.neighbourhoods.append({"id": str(row["id"]), "name": row["name"], "geometry": part})
        self.neighbourhoods.sort(key=lambda r: (r["id"], canonical(r["geometry"])))
        self.neighbourhood_tree = STRtree([r["geometry"] for r in self.neighbourhoods])
        self.city = unary_union([r["geometry"] for r in self.neighbourhoods])
        self.roads = []
        for row in json.loads((GEO_DIR / "roads.json").read_text()):
            self.roads.append({"id": str(row["segment_id"]), "name": row.get("full_name", ""),
                               "type": row.get("type", ""), "geometry": project(shape(row["the_geom"]))})
        # A City segment ID can span several intersections. Protection must stop
        # at actual mapped intersections rather than join entire neighbourhoods.
        original_roads = self.roads
        original_tree = STRtree([r["geometry"] for r in original_roads])
        self.roads = []
        for part in sorted(line_parts(unary_union([r["geometry"] for r in original_roads])), key=canonical):
            middle = part.interpolate(.5, normalized=True)
            candidates = [int(i) for i in original_tree.query(middle.buffer(.02))
                          if original_roads[int(i)]["geometry"].distance(middle) < .02]
            if candidates:
                road = min((original_roads[i] for i in candidates), key=lambda r: r["id"])
                self.roads.append({**road, "id": road["id"] + ":" + hashlib.sha256(part.wkb).hexdigest()[:12], "geometry": part})
        self.base_roads=list(self.roads)
        self.road_tree = STRtree([r["geometry"] for r in self.roads])
        self.features = []
        feature_rows = json.loads((GEO_DIR / "physical_features.geojson").read_text())["features"]
        for filename in ('planning_features.geojson','greenway_features.geojson'):
            planning = GEO_DIR / filename
            if planning.exists():
                feature_rows += json.loads(planning.read_text())["features"]
        for row in feature_rows:
            geometry = project(shape(row["geometry"]))
            if geometry.is_empty:
                continue
            feature = {"id": row["id"], **row["properties"], "geometry": geometry}
            category = feature["category"]
            if category=='greenway':
                # A sidewalk or cycle lane running alongside an ordinary road
                # is not an independent residential divider.
                nearby=[self.roads[int(j)]['geometry'].buffer(15) for j in self.road_tree.query(geometry.buffer(15))]
                if nearby and geometry.intersection(unary_union(nearby)).length>geometry.length*.35:
                    continue
                feature['rank']=6
                feature['evidence']='Mapped path/greenway away from street centrelines; finite corridor candidate, not proof of road or pickup access'
            if feature.get('tags',{}).get('highway') and major_speed_boundary(feature['tags']):
                feature.update(category='high_speed_road',rank=2,eligible=True,
                    evidence='Mapped speed above 60 km/h, or 60 km/h with arterial evidence; important physical boundary')
            elif category in {"major_road", "collector", "road_reference"}:
                evidence = road_evidence(feature.get("tags", {}))
                feature["eligible"] = bool(evidence)
                feature["evidence"] = evidence or "Road class alone does not prove a wide/divided road; ordinary curbs remain protected."
                if evidence:
                    feature["category"] = "wide_road"
            self.features.append(feature)
        self.parcels = []
        for row in json.loads((GEO_DIR / "parcels.json").read_text()):
            geometry = make_valid(project(shape(row.get("location") or row["geometry"])))
            if not geometry.is_empty:
                self.parcels.append({"id": str(row.get("id") or row["gisid"]), "geometry": geometry})
        self.parcel_tree = STRtree([p["geometry"] for p in self.parcels])
        self.parks = [{"id": str(p["park_id"]), "name": p.get("park_name", ""),
                       "geometry": make_valid(project(shape(p["polygon"])))}
                      for p in json.loads((GEO_DIR / "parks.json").read_text())]
        self.park_tree = STRtree([p["geometry"] for p in self.parks])
        self.features.extend({**p, "id": "city-park-" + p["id"], "category": "park", "rank": 3,
                              "evidence": "Official City park/open-space boundary"} for p in self.parks)
        self.features.extend({**p, "id": "city-area-" + p["id"], "category": "community", "rank": 2,
                              "evidence": "Official City neighbourhood division"} for p in self.neighbourhoods)
        self.refresh_dividers()

    def refresh_dividers(self):
        if not hasattr(self,'base_roads'):
            self.base_roads=load_noded_roads() if self.manifest.get('sources') else list(self.roads)
        self.roads=list(self.base_roads)
        for feature in self.features:
            if major_speed_boundary(feature.get('tags', {})):
                feature.update(category='high_speed_road', rank=2, eligible=True,
                    evidence='Mapped speed above 60 km/h, or 60 km/h with arterial evidence; important physical boundary')
        self.features = [f for f in self.features if not f["id"].startswith(("city-wide-","corridor-"))]
        self.features.extend(promote_divided_roads(self.features, self.roads))
        if self.manifest.get('sources'):
            from .corridors import discover_corridors
            self.features.extend(discover_corridors(self))
        self.roads=segment_roads_at_barriers(self.roads,self.features)
        self.road_tree=STRtree([r['geometry'] for r in self.roads])
        for name in ('junctions','junction_tree'):
            if hasattr(self,name):delattr(self,name)
        self.features = [f for f in self.features if f["category"]!="alley_supported_road"]
        self.features.extend(alley_frontage_candidates(self.features, self.roads))
        self.features.sort(key=lambda f: f["id"])
        self.feature_tree = STRtree([f["geometry"] for f in self.features])
        self.prepared_road_revision = 11
        if hasattr(self,'divider_tree'):del self.divider_tree
        self.divider_indexes={}

    def nearby_features(self, geometry, categories):
        return [self.features[int(i)] for i in self.feature_tree.query(geometry)
                if self.features[int(i)]["category"] in categories
                and self.features[int(i)]["geometry"].intersects(geometry)]

    def nearby_dividers(self,geometry,categories):
        # Polygon interiors are not divider edges. Index the actual linework
        # so a small shared seam does not repeatedly test entire neighbourhoods.
        if not hasattr(self,'divider_indexes'):self.divider_indexes={}
        key=tuple(sorted(categories))
        if key not in self.divider_indexes:
            features=[f for f in self.features if f['category'] in categories]
            self.divider_indexes[key]=(features,STRtree([divider_line(f) for f in features]))
        features,tree=self.divider_indexes[key]
        return [features[int(i)] for i in tree.query(geometry,predicate='intersects')]

    def refine_frontage_cells(self, cells, selected, progress=lambda *_:None, extra_lines=()):
        """Refine only oversized regions with whole mapped street-frontage blocks.

        New connectors are finite junction-to-parcel-edge segments inside the
        road space. No marker-derived cut, extended ray or point hull is used.
        """
        if not hasattr(self,'junction_tree'):
            endpoints=defaultdict(int)
            for road in self.roads:
                if road['type']=='BRIDGE':continue
                for xy in (road['geometry'].coords[0],road['geometry'].coords[-1]):
                    endpoints[(round(xy[0],2),round(xy[1],2))]+=1
            self.junctions=[Point(xy) for xy,n in sorted(endpoints.items()) if n>=3]
            self.junction_tree=STRtree(self.junctions)
        refined,ledger,evidence=[],[],{}
        for number,cell in enumerate(cells):
            if number not in selected:
                refined.append(cell)
                continue
            parent=cell['geometry']
            parcels=[self.parcels[int(j)] for j in self.parcel_tree.query(parent) if self.parcels[int(j)]['geometry'].intersects(parent)]
            roads=[self.roads[int(j)] for j in self.road_tree.query(parent) if self.roads[int(j)]['geometry'].intersects(parent)]
            connectors=[]
            junction_ids=[]
            for j in self.junction_tree.query(parent):
                junction=self.junctions[int(j)]
                if not parent.covers(junction):continue
                near=[self.parcels[int(k)] for k in self.parcel_tree.query(junction.buffer(45))]
                if any(p['geometry'].contains(junction) for p in near):continue
                for parcel in near:
                    end=nearest_points(junction,parcel['geometry'])[1]
                    length=junction.distance(end)
                    if not 3<=length<=45:continue
                    connector=LineString([junction,end])
                    if any(connector.crosses(p['geometry']) or p['geometry'].contains(connector.interpolate(.5,normalized=True)) for p in near):continue
                    connectors.append(connector)
                    junction_ids.append({'junction':[round(junction.x,2),round(junction.y,2)],'parcel':parcel['id'],
                                         'end':[round(end.x,3),round(end.y,3)]})
            lines=[part.boundary for p in parcels for part in polygon_parts(p['geometry'])]+[r['geometry'] for r in roads]+connectors+list(extra_lines)
            parts=subdivide(parent,lines)
            for part in parts:
                refined.append({**cell,'geometry':part,'frontage_refined':True,
                                'basis':'Whole street frontages; City parcel edges and finite mapped-junction connectors'})
            identifier='frontage-blocks-'+cell['source_id']+'-'+hashlib.sha256(parent.wkb).hexdigest()[:12]
            ledger.append({'id':identifier,'name':cell['name']+' frontage blocks','category':'frontage_blocks','rank':7,
                'parent':cell['name'],'state':'CANDIDATE','evidence':'Official parcel and street geometry; finite junction-to-parcel-edge connectors. Ordinary street frontages and serviced parcels stay whole.',
                'parcel_ids':sorted(p['id'] for p in parcels),'road_segment_ids':sorted(r['id'] for r in roads),
                'junction_connectors':junction_ids,'reason':'Additional mapped block geometry is considered only inside an oversized region.'})
            evidence[identifier]={'geometry':unary_union(lines)}
            progress(35,'Preparing whole frontages in '+cell['name'])
        refined.sort(key=lambda c:(c['source_id'],canonical(c['geometry'])))
        return refined,ledger,evidence

    def geography_cells(self, points, target=None, alley_roads=(), mapped_alley_roads=()):
        """Official neighbourhood references, subdivided by credible finite separators.

        Counts never move a boundary. Weak neighbourhood seams are subsequently
        dissolved wherever they divide an ordinary segment/site/serviced parcel.
        """
        owners = set()
        for point in points:
            ids = self.neighbourhood_tree.query(point, predicate="intersects")
            if not len(ids):
                raise ValueError("An address is outside the frozen Winnipeg neighbourhood boundary.")
            owners.add(min(int(i) for i in ids))
        cells, ledger = [], []
        for owner in sorted(owners):
            area = self.neighbourhoods[owner]
            categories = {"waterway", "railway", "controlled_road", "high_speed_road", "wide_road", "water_area", "landuse", "park", "recreation", "mapped_open_land"}
            features = self.nearby_features(area["geometry"], categories)
            # Every line is actual finite mapped geometry. A closed park island
            # alone cannot become an invented boundary-to-boundary separator.
            lines = [divider_line(f) for f in features]
            try:
                parts = subdivide(area["geometry"], lines)
            except ValueError as exc:
                raise ValueError(f"{area['name']}: {exc}") from exc
            for part in parts:
                cells.append({"name": area["name"], "source_id": area["id"], "geometry": part,
                              "basis": "Official neighbourhood + finite mapped physical and land-use boundaries"})
            for feature in features + [{"id": "city-area-" + area["id"], "name": area["name"], "category": "community", "rank": 2,
                                        "evidence": "Official City neighbourhood division"}]:
                ledger.append({"id": feature["id"], "name": feature["name"], "category": feature["category"],
                               "rank": feature["rank"], "parent": area["name"], "state": "CANDIDATE",
                               "evidence": feature.get("evidence", "Mapped finite physical feature"),
                               "reason": "Finite reference feature inventoried; selection checked against final shared boundaries."})
        cells.sort(key=lambda c: (c["source_id"], canonical(c["geometry"])))
        return cells, ledger
