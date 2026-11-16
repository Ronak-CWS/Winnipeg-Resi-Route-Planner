"""Local PBF road runs and auditable inferred right-curb pickup anchors.

Service IDs always come from the partition. The road inventory cannot add demand.
Split road geometry only at real shared OSM nodes, never a matrix-size threshold.
"""
import hashlib
import heapq
import itertools
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import LineString, Point
from shapely.strtree import STRtree
from partition_app.geography import FORWARD, REVERSE, GEO_DIR, street_name


def normalized(value):
    aliases = {"close": "cl", "court": "crt", "place": "pl", "lane": "ln", "bay": "bay",
               "terrace": "terr", "circle": "cir", "drive": "dr", "avenue": "ave",
               "saint": "st", "point": "pt", "northwest": "nw", "northeast": "ne"}
    return " ".join(aliases.get(w, w) for w in street_name(value.replace("'", "").replace("’", "")).split())


def address_street(value):
    # Number and optional unit/civic suffix, followed by the street name.
    value = re.sub(r"^\s*(?:\d+[A-Z]?\s*[-/]\s*)?\d+[A-Z]?\s+", "", value.upper())
    value = re.split(r"\s+(?:UNIT|APT|SUITE|STE)\s+|\s+#", value)[0]
    return normalized(value)


def bearing(a, b):
    # True-north geographic bearing, not UTM grid north.
    lon1, lat1, lon2, lat2 = map(math.radians, [a[0], a[1], b[0], b[1]])
    return math.degrees(math.atan2(math.sin(lon2-lon1)*math.cos(lat2),
        math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1))) % 360


def angle(a, b):
    return abs((a-b+180) % 360-180)


class SiteAccess:
    """Find nearby internal roads reached from an address's named street.

    Street names describe postal addresses, not necessarily the collection
    frontage. Follow real shared nodes through accessible service roads; never
    connect two roads just because their geometries cross or are close.
    """
    def __init__(self, roads, lines, names):
        self.roads, self.lines, self.names = roads, lines, names
        self.nodes = [r.get('nodes') or [tuple(r['coords'][0]), tuple(r['coords'][-1])]
                      for r in roads]
        self.internal = {i for i, r in enumerate(roads) if r['tags'].get('highway') == 'service'
                         and r['tags'].get('service') not in {'alley', 'drive-through'}}
        self.graph = defaultdict(list)
        for i in self.internal:
            a, b = self.nodes[i]
            self.graph[a].append((b, lines[i].length))
            self.graph[b].append((a, lines[i].length))
        self.distances = {}

    def from_street(self, street_names):
        key = tuple(sorted(street_names))
        if key not in self.distances:
            seeds = {node for name in key for i in self.names.get(name, []) for node in self.nodes[i]}
            distances = dict.fromkeys(seeds, 0.)
            serial = itertools.count()
            queue = [(0., next(serial), n) for n in seeds]
            heapq.heapify(queue)
            while queue:
                distance, _, node = heapq.heappop(queue)
                if distance != distances[node]:
                    continue
                for other, length in self.graph[node]:
                    value = distance + length
                    if value <= 800 and value < distances.get(other, math.inf):
                        distances[other] = value
                        heapq.heappush(queue, (value, next(serial), other))
            self.distances[key] = distances
        return self.distances[key]

    def candidates(self, loc, named, near, supported_site=False):
        if not named:
            return []
        named_distance = min(self.lines[i].distance(loc) for i in named)
        # Preserve normal street frontages and corner houses. A different
        # access needs a substantial, not centimetre-scale, improvement.
        if named_distance <= (20 if supported_site else 40):
            return []
        reachable = self.from_street({normalized(self.roads[i]['name']) for i in named})
        candidates = []
        for i in near:
            if i not in self.internal:
                continue
            line = self.lines[i]
            setback = line.distance(loc)
            ratio, improvement = (.9, 5) if supported_site else (.65, 20)
            if setback > 60 or setback > named_distance * ratio or named_distance - setback < improvement:
                continue
            position = line.project(loc)
            a, b = self.nodes[i]
            connection = min(reachable.get(a, math.inf) + position,
                             reachable.get(b, math.inf) + line.length - position)
            if connection > 800:
                continue
            # A nearby shopping aisle across another street is not the same
            # frontage, even if its network eventually joins the postal road.
            connector = LineString([loc, line.interpolate(position)])
            if any(self.roads[j]['tags'].get('highway') != 'service'
                   and connector.crosses(self.lines[j]) for j in near):
                continue
            candidates.append((i, connection))
        return candidates


def inventory(cache, progress):
    path = cache / "routing-road-inventory.json"
    meta = json.loads((GEO_DIR / "physical_features.source.json").read_text())
    fingerprint = meta["source_sha256"]
    if path.exists():
        saved = json.loads(path.read_text())
        if saved["source_hash"] == fingerprint and saved.get("version") == 1:
            return saved
    import osmium
    bbox = meta["bbox"]
    ways, node_uses = [], Counter()
    class Reader(osmium.SimpleHandler):
        def way(self, w):
            t = dict(w.tags)
            if t.get("highway") not in {"motorway", "trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service", "motorway_link", "trunk_link", "primary_link", "secondary_link", "tertiary_link"}:
                return
            if t.get("area") == "yes" or t.get("motor_vehicle") == "no" or t.get("access") == "no":
                return
            try:
                coords = [(n.lon, n.lat) for n in w.nodes]
                if not any(bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3] for x,y in coords):
                    return
                ids = [n.ref for n in w.nodes]
                if len(ids) < 2:
                    return
                ways.append((str(w.id), ids, coords, t))
                node_uses.update(set(ids))
            except osmium.InvalidLocationError:
                return
    source = Path(meta["source"])
    if hashlib.sha256(source.read_bytes()).hexdigest() != fingerprint:
        raise ValueError("Local road source changed; prepare and review the reference again.")
    progress(3, "Reading the existing Manitoba roads; no downloads")
    Reader().apply_file(str(source), locations=True, idx="flex_mem")
    roads = []
    for way, ids, coords, tags in ways:
        begin = 0
        for end in range(1, len(ids)):
            if node_uses[ids[end]] > 1 or end == len(ids)-1:
                part = coords[begin:end+1]
                if len(set(part)) > 1:
                    roads.append({"id": f"{way}:{begin}:{end}", "nodes": [ids[begin], ids[end]],
                                  "coords": part, "tags": tags, "name": tags.get("name", "")})
                begin = end
    result = {"version": 1, "source_hash": fingerprint, "roads": roads,
              "source": str(source), "network_requests": 0}
    path.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    return result


def make_groups(partition, road_inventory):
    unavailable=[r for r in road_inventory['roads'] if r['tags'].get('construction') not in {None,'no'}]
    unavailable_lines=[LineString([FORWARD.transform(x,y) for x,y in r['coords']]) for r in unavailable]
    unavailable_tree=STRtree(unavailable_lines)
    roads = [r for r in road_inventory["roads"] if r["tags"].get("service") != "alley"
             and r['tags'].get('service') != 'drive-through'
             and r["tags"].get("highway") not in {"motorway", "motorway_link", "trunk_link"}
             and r['tags'].get('construction') in {None,'no'}
             and r['tags'].get('access') not in {'private','agricultural','forestry','emergency','no'}
             and r['tags'].get('motor_vehicle') not in {'private','agricultural','forestry','emergency','no'}]
    lines = [LineString([FORWARD.transform(x,y) for x,y in r["coords"]]) for r in roads]
    tree = STRtree(lines)
    names = defaultdict(list)
    for i, r in enumerate(roads):
        if r["name"]:
            names[normalized(r["name"])].append(i)
    access = SiteAccess(roads, lines, names)
    grouped, reviews, anchors = defaultdict(list), [], {}
    def local_tangent(line,loc):
        pos=max(.15,min(line.length-.15,line.project(loc))) if line.length>.3 else line.length/2
        # A sharp polyline vertex has two real road headings, not their mean.
        # Move a few centimetres along the same mapped road to select one edge.
        vertices=list(line.coords);distance=0
        for x,y in zip(vertices,vertices[1:]):
            distance+=math.dist(x,y)
            if abs(pos-distance)<.12 and .15<distance<line.length-.15:
                pos=distance-.15;break
        q=line.interpolate(pos)
        a,b=[line.interpolate(max(0,min(line.length,pos+d))) for d in [-.05,.05]]
        return pos,q,a,b
    def locate(p, supported_site=False):
        loc = Point(*FORWARD.transform(p["lon"], p["lat"]))
        street = address_street(p["address"])
        choices = names.get(street, [])
        if not choices:
            # Generic directional suffix disagreement is reported, never a named-road exception.
            choices = names.get(re.sub(r" (n|s|e|w)$", "", street), [])
        near = [int(i) for i in tree.query(loc.buffer(200))]
        named = [i for i in choices if lines[i].distance(loc) <= 250]
        if not named:
            from difflib import SequenceMatcher
            close_names = [j for j in near if roads[j]['name'] and SequenceMatcher(None,street,normalized(roads[j]['name'])).ratio() >= .9]
            if close_names:
                named = close_names
        def match_cost(j):
            ln=lines[j]; tags=roads[j]['tags']; t,q,a,b=local_tangent(ln,loc)
            side=(b.x-a.x)*(loc.y-q.y)-(b.y-a.y)*(loc.x-q.x)
            allowed=-1 if tags.get('oneway')=='-1' else 1 if tags.get('oneway') in {'yes','1','true'} or tags.get('junction')=='roundabout' else 0
            return (ln.distance(loc)+(40 if allowed and allowed != (1 if side<0 else -1) else 0),roads[j]['id'])
        i = min(named or near or [int(tree.nearest(loc))], key=match_cost)
        named_setback = lines[i].distance(loc) if named else None
        method, connection = 'named_street' if named else 'nearest_mapped_road', None
        candidates = access.candidates(loc, named, near, supported_site)
        if candidates:
            # Network distance favours the site's own entrance over an equally
            # close road in a neighbouring complex reached by a long detour.
            candidate, distance = min(candidates, key=lambda c:
                (match_cost(c[0])[0] + .15*c[1], roads[c[0]]['id']))
            if match_cost(candidate)[0] + .15*distance < match_cost(i)[0]:
                i, connection, method = candidate, distance, 'connected_site_access'
        road, line = roads[i], lines[i]
        pos,q,a,b = local_tangent(line,loc)
        dx,dy = b.x-a.x,b.y-a.y
        side = dx*(loc.y-q.y)-dy*(loc.x-q.x)
        direction = 1 if side < 0 else -1
        oneway = road["tags"].get("oneway")
        allowed = -1 if oneway == "-1" else 1 if oneway in {"yes","1","true"} or road["tags"].get("junction") == "roundabout" else 0
        issues = []
        if any(normalized(unavailable[int(j)]['name'])==street and unavailable_lines[int(j)].distance(loc)<line.distance(loc)
               for j in unavailable_tree.query(loc.buffer(250))):
            issues.append('construction_tagged_street_access_proxy')
        if not named:
            issues.append("street_name_unmatched")
        if line.distance(loc) > 80:
            issues.append("property_setback_over_80m")
        if abs(side)/max(math.hypot(dx,dy),.001) < 1.5:
            issues.append("ambiguous_property_side")
        if allowed and allowed != direction:
            # Explicit unresolved access: use legal road direction, do not claim right-side proof.
            direction = allowed
            issues.append("oneway_opposite_curb_requires_review")
        if not p.get("trusted", True):
            issues.append("estimated_property_location")
        heading = bearing(REVERSE.transform(a.x,a.y),REVERSE.transform(b.x,b.y))
        if direction == -1:
            heading = (heading+180)%360
        coords = list(REVERSE.transform(q.x, q.y))
        anchor = {"id": p["id"], "section": p["section"], "address": p["address"],
                  "original": [p["lon"],p["lat"]], "coordinate": coords,
                  "bearing": round(heading), "road_id": road["id"], "road_name": road["name"],
                  "position_m": pos, "direction": direction, "setback_m": round(line.distance(loc),2),
                  "match_method": method, "postal_street_setback_m": round(named_setback,2) if named_setback is not None else None,
                  "access_connection_m": round(connection,2) if connection is not None else None,
                  "snap_radius_m": 8 if method == 'connected_site_access' else 35,
                  "review": issues, "inferred": True}
        return anchor
    def unit_site(address):
        parts = re.split(r"\s+(?:UNIT|APT|SUITE|STE)\s+|\s+#", address.upper())
        if len(parts) > 1:
            return parts[0].strip()
        prefix = re.match(r"^\s*\d+[A-Z]?\s*[-/]\s*(\d+[A-Z]?\s+.+)$", address.upper())
        return prefix.group(1).strip() if prefix else None
    support = defaultdict(set)
    for p in partition['points']:
        a = anchors[p['id']] = locate(p)
        site = unit_site(p['address'])
        if site and a['match_method'] == 'connected_site_access':
            support[site].add(tuple(a['original']))
    # Two distinct interior unit locations establish a same-civic site cohort.
    # Its near-entrance units can use that access without changing ordinary
    # nearby houses or treating repeated co-located IDs as spatial evidence.
    for p in partition['points']:
        a = anchors[p['id']]
        if len(support.get(unit_site(p['address']), ())) >= 2 and a['match_method'] != 'connected_site_access':
            a = anchors[p['id']] = locate(p, supported_site=True)
        grouped[(p['section'],a['road_id'],a['direction'])].append(a)
        if a['review']:
            reviews.append({'id':p['id'], 'section':p['section'], 'issues':a['review']})
    groups = []
    for key, members in sorted(grouped.items()):
        members.sort(key=lambda a:(a["position_m"]*key[2],a["id"]))
        groups.append({"id": f"{key[0]}:{key[1]}:{key[2]}", "section":key[0], "road_id":key[1],
                       "road_name":members[0]["road_name"], "direction":key[2], "count":len(members),
                       "members":[a["id"] for a in members], "start":members[0], "end":members[-1]})
    return groups, anchors, reviews
