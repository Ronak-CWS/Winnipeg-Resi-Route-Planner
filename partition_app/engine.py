"""Deterministic geography-first adaptation of the reviewed CWS partition rules.

No geocoding, source discovery, basemap calls, route solving or street sequencing.
Official finite boundaries are the only polygon edges. Services remain individual.
"""
from __future__ import annotations

import csv
import hashlib
import io
import heapq
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from shapely import make_valid, set_precision, union_all
from shapely.geometry import Point, Polygon, MultiPolygon, LineString, mapping, shape
from shapely.ops import unary_union, polygonize, transform as transform_geometry, nearest_points
from shapely.strtree import STRtree
from shapely.prepared import prep

from .geography import FORWARD, canonical, divider_line, polygon_parts, unproject, subdivide
from .preferences import address_preferences
from .balancing import rebalance, linear_separator, hard_separator, footprint_between

ENGINE_VERSION = "winnipeg-geography-4.5"
COLOURS = ["#2563eb", "#0d9488", "#e08832", "#9b5de5", "#cf4d77", "#568438", "#1484a6", "#a76a40", "#5a65ab", "#ad7d13", "#247b64", "#b55440"]


class DisjointSet:
    def __init__(self, n):
        self.parent = list(range(n))

    def find(self, a):
        while a != self.parent[a]:
            self.parent[a] = self.parent[self.parent[a]]
            a = self.parent[a]
        return a

    def union(self, a, b):
        a, b = self.find(a), self.find(b)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def normalized(value):
    value = re.sub(r"[^A-Z0-9 ]", " ", value.upper())
    words = {"STREET": "ST", "AVENUE": "AVE", "BOULEVARD": "BLVD", "DRIVE": "DR", "ROAD": "RD", "PLACE": "PL", "CRESCENT": "CRES", "COURT": "CRT", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}
    return " ".join(words.get(word, word) for word in value.split())


def publication_geometry(geometry):
    """Keep polygonal area after inverse-projection noise; discard zero-area lines.

    A material split stays a MultiPolygon and fails the published-shape gate.
    This does not buffer, bridge or discard any polygonal component.
    """
    # Eight decimal places is approximately 1 mm here. It removes numerical
    # slits/holes introduced by the inverse transform, below the native 1 cm grid.
    wgs = set_precision(make_valid(unproject(geometry)), 1e-8)
    parts = polygon_parts(wgs)
    return parts[0] if len(parts) == 1 else MultiPolygon(parts)


def normalise_published_edges(sections):
    """Dissolve numeric inverse-projection overlaps using deterministic ownership.

    Repair is limited to <=1 m2 per section. Material overlaps are retained for
    the failure gate. No polygonal component or service record is discarded.
    """
    preceding, removed = [], 0.0
    for feature in sections:
        geometry = shape(feature["geometry"])
        if preceding:
            covered = unary_union(preceding)
            overlap = transform_geometry(FORWARD.transform, geometry.intersection(covered)).area
            if 0 < overlap <= 1:
                geometry = geometry.difference(covered)
                removed += overlap
        feature["geometry"] = mapping(geometry)
        preceding.append(geometry)
    return removed


def merge_geometry(cells, dsu):
    groups = defaultdict(list)
    for i, cell in enumerate(cells):
        groups[dsu.find(i)].append(cell["geometry"])
    return {key: unary_union(parts) for key, parts in sorted(groups.items())}


def assign_unserved_components(current, root_points, serviced_parcels, reasons, progress=lambda *_:None):
    """Give whole detached, zero-demand faces to a genuinely adjoining owner.

    Protecting a road or parcel can attach empty road-space pieces to its group.
    Those pieces are not service atoms. Transfer only a complete existing
    component, never cut a serviced parcel or invent connecting land.
    """
    parcels=list(serviced_parcels.values())
    parcel_tree=STRtree([p['geometry'] for p in parcels])
    moved=0
    while True:
        changed=False
        keys=sorted(k for k in current if root_points.get(k))
        tree=STRtree([current[k] for k in keys])
        for a in keys:
            parts=polygon_parts(current[a])
            if len(parts)<2:continue
            for index,part in enumerate(parts):
                if any(part.covers(p) for p in root_points[a]):continue
                remaining=unary_union(parts[:index]+parts[index+1:])
                material=False
                for j in parcel_tree.query(part):
                    parcel=parcels[int(j)]['geometry'];limit=max(4.,parcel.area*.02)
                    if parcel.intersection(part).area>limit and parcel.intersection(remaining).area>limit:
                        material=True;break
                if material:continue
                options=[]
                for j in tree.query(part,predicate='intersects'):
                    b=keys[int(j)]
                    if b==a:continue
                    shared=part.boundary.intersection(current[b].boundary).length
                    if shared<.1:continue
                    union=current[b].union(part)
                    if union.geom_type=='Polygon':options.append((-shared,b,union))
                if not options:continue
                _,b,union=min(options,key=lambda item:(item[0],item[1]))
                current[a],current[b]=remaining,union
                moved+=1;changed=True
                reasons['whole unserved component reassignment']+=1
                break
        if not changed:break
        progress(53,'Assigning whole detached road-space faces without moving service records')
    return moved


def shared_native_coverage(occupied):
    """Node all edges together; assign complete enclosed zero-service faces.

    This dissolves unused interior seams, not serviced enclaves. No convex hull,
    buffer or straight-line bridge is introduced. The independent final gates
    still reject any serviced hole or disconnected area.
    """
    keys = sorted(occupied)
    original = [occupied[k] for k in keys]
    tree = STRtree(original)
    exteriors = [unary_union([Polygon(p.exterior) for p in polygon_parts(g)]) for g in original]
    exterior_tree = STRtree(exteriors)
    network = union_all([g.boundary for g in original], grid_size=.01)
    groups = defaultdict(list)
    filled = []
    for face in sorted(polygonize(network), key=canonical):
        point = face.representative_point()
        owners = [int(i) for i in tree.query(point) if original[int(i)].covers(point)]
        if owners:
            owner = min(owners)
        else:
            enclosed = [int(i) for i in exterior_tree.query(point) if exteriors[int(i)].covers(point)]
            if not enclosed:
                continue
            owner = min(enclosed, key=lambda i:(exteriors[i].area,keys[i]))
            filled.append(face.area)
        groups[keys[owner]].append(face)
    result = {k:unary_union(parts) for k,parts in groups.items()}
    return result, {"enclosed_unserved_faces_assigned":len(filled), "enclosed_unserved_face_area_m2":sum(filled)}


def enclosed_owners(geometry, others, tree):
    """A hole is legitimate only when fully owned by other complete sections."""
    owners, gaps = set(), []
    for part in polygon_parts(geometry):
        for ring in part.interiors:
            hole = Polygon(ring)
            indices = [int(i) for i in tree.query(hole) if others[int(i)].intersection(hole).area > .01]
            coverage = unary_union([others[i] for i in indices])
            if hole.difference(coverage).area > 1:
                gaps.append(hole.area)
            owners.update(indices)
    return sorted(owners), gaps


def permitted_nearby_components(geometry,links,points):
    """Only recorded small-pocket groups may retain multiple serviced pieces."""
    parts=polygon_parts(geometry)
    if not links or not 1<len(parts)<=len(links)+1:return False
    if any(not any(p.distance(point)<.002 for point in points) for p in parts):return False
    reached={0}
    while True:
        extra={j for i in reached for j in range(len(parts)) if parts[i].distance(parts[j])<=500}
        if extra<=reached:break
        reached|=extra
    return len(reached)==len(parts)


def seam_dividers(shared,geography):
    """Match the seam itself, not a road/park merely near a tiny parcel corner."""
    categories={'waterway','railway','controlled_road','high_speed_road','wide_road','park','water_area','landuse','recreation','mapped_open_land','community'}
    dividers=getattr(geography,'nearby_dividers',geography.nearby_features)
    result=[]
    for feature in dividers(shared.buffer(.05),categories):
        overlap=shared.intersection(divider_line(feature).buffer(.05)).length
        category=feature['category']
        exact=shared.intersection(divider_line(feature)).length
        threshold=.1 if category in {'railway','waterway','water_area','controlled_road','high_speed_road'} else .5
        if exact>threshold or overlap>max(.5,min(20,shared.length*.7)):result.append(feature)
    return result


def barrier_blocks_pocket(features,points):
    # A closed park/school/commercial footprint containing the small facility
    # is not a corridor between two residential populations. Attach that pocket
    # to one side, retaining the footprint's other edges as possible dividers.
    for feature in features:
        if feature['category']=='community':continue
        geometry=feature['geometry']
        enclosed=(feature['category'] in {'park','landuse','recreation','mapped_open_land'}
                  and feature.get('tags',{}).get('landuse')!='railway'
                  and geometry.geom_type in {'Polygon','MultiPolygon'} and points
                  and all(geometry.covers(point) for point in points))
        if not enclosed:return True
    return False


def railway_separates_services(geometry,points,geography):
    """A weak seam cannot join two populations separated by a finite railway.

    A railway can become a complete divider only after two polygons join;
    testing their old shared seam alone cannot detect that case.
    """
    return linear_separator(geometry,points,geography,{'railway'})


def nearby_gap_connector(a,b):
    # A nearest boundary pair can be the same railway corner even when both
    # serviced pieces are on the same bank. Probe from just inside each real
    # piece on the shared centimetre model; opposite-bank probes still cross
    # the actual railway. No probe geometry becomes part of an output area.
    interiors=[]
    for geometry in (a,b):
        inner=geometry.buffer(-.1)
        interiors.append(inner if not inner.is_empty else geometry.representative_point())
    return LineString(nearest_points(*interiors))


def nearby_gap_probes(a,b,points_a,points_b):
    yield nearby_gap_connector(a,b)
    # A closest corner can sit on an external road or railway. Also consider
    # a bounded set of actual service-to-service connections, rather than
    # deciding separation from that one arbitrary boundary corner. Every probe
    # must pass the same divider and third-party serviced-parcel checks.
    if not points_a or not points_b:return
    tree=STRtree(points_b);pairs={}
    for point in points_a:
        other=points_b[int(tree.nearest(point))]
        distance=point.distance(other)
        if .001<distance<=500:
            pairs[(point.x,point.y,other.x,other.y)]=(distance,point,other)
    for _,point,other in sorted(pairs.values(),key=lambda v:(v[0],v[1].x,v[1].y,v[2].x,v[2].y))[:8]:
        yield LineString([point,other])


def small_area_exception(root,occupied,area_counts,geography,ceiling,service_points,other_points=None):
    geometry=occupied[root]
    nearby=sorted((geometry.distance(g),other) for other,g in occupied.items()
                  if other!=root and area_counts[other]>0 and geometry.distance(g)<=500)
    if not nearby:return 'REMOTE','No other service area is adjacent or within 500 m.'
    remote_gap=None
    if service_points and other_points:
        neighbours=[p for other,points in other_points.items() if other!=root for p in points]
        if neighbours:
            tree=STRtree(neighbours)
            gap=min(p.distance(neighbours[int(tree.nearest(p))]) for p in service_points)
            if gap>500:remote_gap=gap
    dividers=getattr(geography,'nearby_dividers',geography.nearby_features)
    physical={'waterway','railway','controlled_road','high_speed_road','wide_road','park','water_area','landuse','recreation','mapped_open_land'}
    remote_neighbour=False
    for distance,other in nearby:
        g=occupied[other]
        shared=geometry.boundary.intersection(g.boundary) if distance<1 else None
        if shared is not None and shared.length>1:
            blocked=barrier_blocks_pocket(seam_dividers(shared,geography),service_points) if shared.length else True
        else:
            blocked=all(barrier_blocks_pocket(dividers(connector.buffer(.02),physical),service_points) or any(
                h.intersection(connector).length>1 for k,h in occupied.items() if k not in {root,other})
                for connector in nearby_gap_probes(geometry,g,service_points,(other_points or {}).get(other,[])))
        if blocked:continue
        if railway_separates_services(geometry.union(g),service_points+(other_points or {}).get(other,[]),geography):continue
        if remote_gap is not None:remote_neighbour=True;continue
        return 'NEEDS_REVIEW','A larger area is within 500 m without an inventoried important divider; a valid whole-block merge still needs correction.'
    if remote_neighbour:
        return 'REMOTE',f'The nearest other serviced address is {remote_gap:.0f} m away. Touching empty land does not provide nearby collection; truck ownership is evaluated with real road connections.'
    return 'IMPORTANT_BOUNDARY','An inventoried important boundary or intervening service area prevents the nearby larger-area merge.'


def owner_of(point, geometries, tree, allow_nearest=False):
    ids = tree.query(point, predicate="intersects")
    if len(ids):
        return min(int(i) for i in ids), False
    index = int(tree.nearest(point))
    if allow_nearest and geometries[index].distance(point) <= 200:
        return index, True
    raise ValueError("A reliable address is outside the selected geographic cells; no coordinate fallback boundary was used.")


def protect_cells(cells, points, trusted, buckets, parcels, road_groups, roads):
    geometries=[c['geometry'] for c in cells]
    tree=STRtree(geometries)
    row_cell={i:owner_of(points[i],geometries,tree)[0] for i in trusted}
    dsu=DisjointSet(len(cells))
    reasons=Counter()
    conflicts=[]
    road_by_id={r['id']:r for r in roads}
    cell_rows=defaultdict(set)
    for i,c in row_cell.items():cell_rows[c].add(i)
    for key,members in sorted(buckets.items(),key=lambda kv:str(kv[0])):
        parents=sorted({cells[row_cell[i]]['name'] for i in members})
        if key[0]=='ordinary segment' and len(parents)>1:
            road=road_by_id[key[1]]
            conflicts.append({'road':road['name'],'segment':key[1],'length_m':round(road['geometry'].length,1),'records':len(members),'parents':parents})
        first=row_cell[members[0]]
        for i in members[1:]:
            if dsu.find(first)!=dsu.find(row_cell[i]):
                dsu.union(first,row_cell[i]);reasons[key[0]]+=1
    # In a refined block the road-space faces connect each complete frontage
    # to its facing curb. Connectors stop these faces at mapped junctions.
    for key,members in sorted(road_groups.items()):
        road=set_precision(road_by_id[key]['geometry'],0);member_set=set(members)
        first=row_cell[members[0]]
        for j in tree.query(road.buffer(.02)):
            j=int(j)
            if not cells[j].get('frontage_refined') or cell_rows[j]-member_set:continue
            if road.intersection(geometries[j].boundary.buffer(.02)).length>1 and dsu.find(first)!=dsu.find(j):
                dsu.union(first,j);reasons['whole frontage road space']+=1
    for parcel in parcels.values():
        owners=[]
        for j in tree.query(parcel['geometry']):
            j=int(j)
            if parcel['geometry'].intersection(geometries[j]).area>max(4.,parcel['geometry'].area*.02):owners.append(j)
        for j in owners[1:]:
            if dsu.find(owners[0])!=dsu.find(j):
                dsu.union(owners[0],j);reasons['material parcel cut']+=1
    return row_cell,dsu,reasons,conflicts


def merge_target_regions(current, counts, dsu, cells, geography, target, ceiling, reasons, progress, parent_votes=None,service_points=None,existing_nearby_links=None,serviced_parcels=None,consolidate_small=True):
    """Merge a sparse shared-edge graph; score each original seam once.

    Combined edges retain every strong barrier. Boundary ranking cannot be
    diluted by joining a longer weak seam later. Geometry union happens only
    for the selected candidate, not every possible neighbour on every step.
    """
    parents=defaultdict(set)
    for i,cell in enumerate(cells):parents[dsu.find(i)].add(cell['source_id'])
    if parent_votes:
        # A protected frontage spanning a City line must join one side as a
        # complete block. It must not force both entire neighbourhoods together.
        for root,votes in parent_votes.items():
            parents[root]={min(votes,key=lambda name:(-votes[name],name))}
    keys=sorted(k for k in current if counts[k])
    tree=STRtree([current[k] for k in keys])
    adjacent={k:{} for k in keys}
    versions=Counter()
    queue=[]
    serial=0
    nearby_links={k:list(v) for k,v in (existing_nearby_links or {}).items()}
    dividers=getattr(geography,'nearby_dividers',geography.nearby_features)
    votes={k:Counter((parent_votes or {}).get(k,{})) for k in keys}
    service_points={k:list((service_points or {}).get(k,[])) for k in keys}
    parcels=list((serviced_parcels or {}).values())
    parcel_tree=STRtree([p['geometry'] for p in parcels])
    service_trees={}
    source_features={f['id']:f for f in geography.features}
    def service_distance(a,b):
        if not service_points[a] or not service_points[b]:return current[a].distance(current[b])
        if b not in service_trees:service_trees[b]=STRtree(service_points[b])
        distances=sorted(p.distance(service_points[b][int(service_trees[b].nearest(p))]) for p in service_points[a])
        return distances[len(distances)//2]
    def urban_highway_penalty(a,b):
        # Prefer the local neighbourhood side of a major urban highway when
        # several neighbours are available. This is a boundary-strength score,
        # not a named-road veto or a claim about driving time.
        for feature in adjacent[a][b]['physical_features'].values():
            sources=[feature]+[source_features[k] for k in feature.get('evidence_ids',[]) if k in source_features]
            if any(f.get('tags',{}).get('highway')=='primary' for f in sources):return 200
        return 0
    def small_blocked(a,b):
        union=current[a].union(current[b]);points=service_points[a]+service_points[b]
        # A park outline or an urban arterial is a useful candidate, not proof
        # that a small pocket is isolated. Keep a complete corridor only when
        # removing its footprint really separates two serviced populations.
        return service_distance(a,b)>500 and footprint_between(union,service_points[a],service_points[b],geography,{'park','recreation','mapped_open_land','landuse'})
    def rail_safe(a,b,union):
        if railway_separates_services(union,service_points[a]+service_points[b],geography):
            reasons['railway separation veto']+=1;return False
        if hard_separator(union,service_points[a]+service_points[b],geography):
            reasons['important physical separation veto']+=1;return False
        return True
    def push(a,b):
        nonlocal serial
        if target is None:return
        a,b=sorted((a,b))
        edge=adjacent[a][b]
        if edge['strong'] or parents[a]!=parents[b] or counts[a]+counts[b]>ceiling:return
        serial+=1
        heapq.heappush(queue,(-edge['rank'],abs(target-counts[a]-counts[b]),-edge['length'],a,b,versions[a],versions[b],serial))
    for position,a in enumerate(keys):
        for j in tree.query(current[a],predicate='intersects'):
            b=keys[int(j)]
            if a>=b:continue
            shared=current[a].boundary.intersection(current[b].boundary)
            if shared.length<1:continue
            protected=seam_dividers(shared,geography)
            evidence=dividers(shared.buffer(4),{'alley','greenway'})
            edge={'length':shared.length,'strong':bool(protected),
                  'physical':any(f['category']!='community' for f in protected),
                  'physical_features':{f['id']:f for f in protected if f['category']!='community'},
                  'rank':min([f['rank'] for f in evidence] or [7])}
            adjacent[a][b]=adjacent[b][a]=edge
        if position%100==0:progress(57,'Grouping whole neighbouring blocks within the address upper bound')
    def join(a,b,union):
        neighbours=(set(adjacent[a])|set(adjacent[b]))-{a,b}
        edges={}
        for n in neighbours:
            pieces=[edge for edge in (adjacent[a].get(n),adjacent[b].get(n)) if edge]
            edges[n]={'length':sum(e['length'] for e in pieces),'strong':any(e['strong'] for e in pieces),
                      'physical':any(e['physical'] for e in pieces),'rank':min(e['rank'] for e in pieces),
                      'physical_features':{identity:f for e in pieces for identity,f in e['physical_features'].items()}}
        count=counts[a]+counts[b]
        source_parents=parents[a]|parents[b]
        combined_votes=votes[a]+votes[b]
        combined_links=nearby_links.pop(a,[])+nearby_links.pop(b,[])
        combined_points=service_points.pop(a)+service_points.pop(b)
        service_trees.pop(a,None);service_trees.pop(b,None)
        if combined_votes:source_parents={min(combined_votes,key=lambda name:(-combined_votes[name],name))}
        dsu.union(a,b);root=dsu.find(a)
        version=max(versions[a],versions[b])+1
        del current[a],current[b],counts[a],counts[b],parents[a],parents[b],adjacent[a],adjacent[b],votes[a],votes[b]
        current[root],counts[root],parents[root],versions[root]=union,count,source_parents,version
        votes[root]=combined_votes
        service_points[root]=combined_points
        if combined_links:nearby_links[root]=combined_links
        adjacent[root]={n:edges[n] for n in neighbours if n in current}
        for n in sorted(adjacent[root]):
            adjacent[n].pop(a,None);adjacent[n].pop(b,None);adjacent[n][root]=edges[n]
        return root

    def separation(parts):
        # Total minimum-spanning-tree gap. A whole neighbouring face may bridge
        # the curbs in two steps; each step must reduce their actual separation.
        remaining=set(range(1,len(parts)))
        distances={i:parts[0].distance(parts[i]) for i in remaining}
        total=0.
        while remaining:
            i=min(remaining,key=lambda n:(distances[n],n));remaining.remove(i)
            total+=distances[i]
            for j in remaining:distances[j]=min(distances[j],parts[i].distance(parts[j]))
        return total

    # Whole-curb/site protection can unite two serviced sides before their road
    # space is assigned. Connect those groups first, using existing whole faces,
    # so size balancing cannot consume their only connecting neighbour. A City
    # administrative line can yield to mandatory frontage protection; physical
    # barriers and the address upper bound cannot.
    repaired=0
    for original in keys:
        a=dsu.find(original)
        while a in adjacent:
            parts=polygon_parts(current[a])
            if len(parts)<2:break
            if permitted_nearby_components(current[a],nearby_links.get(a),service_points[a]):break
            gap=separation(parts)
            options=[]
            for b,edge in sorted(adjacent[a].items()):
                # A mandatory site/parcel/frontage group can already span a park
                # edge. It may take a real neighbouring whole block to connect
                # that group. This exception never crosses rail, water or a
                # controlled/wide road, and never applies to count balancing.
                if any(f['category'] in {'railway','waterway','water_area','controlled_road','high_speed_road','wide_road'}
                       or f.get('tags',{}).get('landuse')=='railway' for f in edge['physical_features'].values()):continue
                union=current[a].union(current[b]);joined_parts=polygon_parts(union)
                if len(joined_parts)>len(parts):continue
                if not rail_safe(a,b,union):continue
                new_gap=separation(joined_parts)
                if len(joined_parts)==len(parts) and gap-new_gap<=.01:continue
                options.append(((len(joined_parts),counts[b],new_gap,-edge['length'],b),b,union))
            if not options:break
            _,b,union=min(options,key=lambda item:item[0])
            crossed_city=parents[a]!=parents[b] or adjacent[a][b]['strong']
            yielded_areal=adjacent[a][b]['physical']
            a=join(a,b,union);repaired+=1
            reasons['whole-frontage connectivity']+=1
            if yielded_areal:reasons['park/land-use edge yields to whole-group connectivity']+=1
            if crossed_city:reasons['City line yields to protected frontage']+=1
            if repaired%5==0:progress(59,'Connecting protected frontages through whole neighbouring blocks')
    if not consolidate_small:return nearby_links
    # Consolidate small service pockets before larger regions consume their
    # available count allowance. A City line alone does not isolate <100 rows;
    # an actual physical barrier does. Whole cells and the upper bound remain.
    threshold=100
    consolidated=0
    for original in keys:
        a=dsu.find(original)
        while a in adjacent and counts[a]<threshold:
            options=[]
            for b,edge in adjacent[a].items():
                if small_blocked(a,b):continue
                total=counts[a]+counts[b]
                score=(total>ceiling,total<threshold,service_distance(a,b)+urban_highway_penalty(a,b),-edge['length'],-counts[b],b)
                options.append((score,b))
            candidate=None
            for _,b in sorted(options):
                union=current[a].union(current[b])
                if union.geom_type=='Polygon' and rail_safe(a,b,union):candidate=(b,union);break
            if candidate is None:break
            b,union=candidate
            crossed_city=parents[a]!=parents[b] or adjacent[a][b]['strong']
            a=join(a,b,union);consolidated+=1
            reasons['under-100 adjacent consolidation']+=1
            if crossed_city:reasons['City line yields to small area']+=1
            if consolidated%20==0:progress(59,'Consolidating small areas without crossing important boundaries')
    # A nearby address-list group may retain distinct real polygon pieces.
    # Never fill the gap with a buffer, hull or a strip through another area.
    # Only a <100 pocket can initiate this explicit <=500 m exception.
    proximity_keys=sorted(adjacent)
    proximity_tree=STRtree([current[k] for k in proximity_keys])
    physical_categories={'waterway','railway','controlled_road','high_speed_road','wide_road','park','water_area','landuse','recreation','mapped_open_land'}
    def nearby_component_links(a,b):
        # A source-protected pocket or the larger address list may already have
        # several real pieces. Check every small piece, not only its closest
        # component. Another area's empty road space is not a physical barrier;
        # an important divider or somebody else's serviced parcel is.
        if current[b].geom_type!='Polygon' and not permitted_nearby_components(current[b],nearby_links.get(b),service_points[b]):return None
        if not rail_safe(a,b,current[a].union(current[b])):return None
        remaining=polygon_parts(current[a]);reached=polygon_parts(current[b]);links=[]
        owners=current[a].union(current[b]);accumulated=counts[b]
        while remaining:
            options=[]
            for index,part in enumerate(remaining):
                members=[p for p in service_points[a] if part.distance(p)<.002]
                if not members or len(members)>=100:continue
                for n,other in enumerate(reached):
                    distance=part.distance(other)
                    if distance>500:continue
                    other_members=[p for p in service_points[a]+service_points[b] if other.distance(p)<.002]
                    for connector in nearby_gap_probes(part,other,members,other_members):
                        if barrier_blocks_pocket(dividers(connector.buffer(.02),physical_categories),members):continue
                        blocked=False
                        for j in parcel_tree.query(connector,predicate='intersects'):
                            parcel=parcels[int(j)]['geometry']
                            if parcel.intersection(connector).length>.1 and parcel.intersection(owners).area<parcel.area*.98:
                                blocked=True;break
                        if not blocked:
                            options.append((distance,index,n,len(members),connector));break
            if not options:return None
            distance,index,_,members,connector=min(options,key=lambda option:option[:3])
            links.append({'distance_m':round(distance,2),'smaller_addresses':members,'larger_addresses':accumulated,
                'probe':mapping(unproject(connector)),'probe_length_m':round(connector.length,3),
                'basis':'Under-100 pocket within 500 m, checked component by component. No important divider or other serviced parcel crosses the gap. Real pieces retained; road access unverified.'})
            accumulated+=members;reached.append(remaining.pop(index))
        return links
    for original in proximity_keys:
        a=dsu.find(original)
        if a not in adjacent or counts[a]>=threshold:continue
        candidates={dsu.find(proximity_keys[int(j)]) for j in proximity_tree.query(current[a].buffer(500))}-{a}
        for b in sorted(candidates,key=lambda b:(current[a].distance(current[b]),b)):
            # "Larger neighbour" is relative: a 1-address pocket may join a
            # nearby 30-address area even when neither side reaches 100 yet.
            if b not in adjacent or counts[b]<counts[a]:continue
            links=nearby_component_links(a,b)
            if links is None:continue
            a=join(a,b,current[a].union(current[b]));nearby_links.setdefault(a,[]).extend(links)
            reasons['under-100 nearby address-list grouping']+=1
            break
    for a in sorted(adjacent):
        for b in sorted(adjacent[a]):
            if a<b:push(a,b)
    joined=0
    while queue:
        _,_,_,a,b,va,vb,_=heapq.heappop(queue)
        if a not in current or b not in current or versions[a]!=va or versions[b]!=vb:continue
        union=current[a].union(current[b])
        if union.geom_type!='Polygon':continue
        if not rail_safe(a,b,union):continue
        root=join(a,b,union)
        for n in sorted(adjacent[root]):
            push(root,n)
        reasons['soft target merge']+=1;joined+=1
        if joined%20==0:progress(60,f'Shaping {len(adjacent):,} tentative areas toward the preferred range')
    return nearby_links


def plan(dataset, geography, target=None, progress=lambda *_: None, tolerance=15, minimum=None, maximum=None, use_mapped_alleys=False):
    preferences = address_preferences(target, tolerance, minimum, maximum)
    planning_target=preferences["target_addresses"]
    planning_ceiling=preferences["maximum_addresses"]
    # Both modes first produce exactly the same natural partition. Address
    # preferences never introduce an alley, parcel mesh or street-junction cut.
    target=ceiling=None
    if not isinstance(use_mapped_alleys, bool):
        raise ValueError("Mapped-alley boundary option must be true or false.")
    if use_mapped_alleys:
        raise ValueError("Both curbs stay together until pickups are confirmed. Mapped alleys alone cannot enable a street boundary; supply confirmed CollectionAccess per address.")
    preferences["use_mapped_alley_evidence"] = use_mapped_alleys
    if hasattr(geography, "refresh_dividers") and getattr(geography, "prepared_road_revision", 0) < 10:
        geography.refresh_dividers()
    rows = sorted(dataset.rows, key=lambda row: row["id"])
    xs, ys = FORWARD.transform([r["lon"] for r in rows], [r["lat"] for r in rows])
    points = [Point(x, y) for x, y in zip(xs, ys)]
    trusted = [i for i, r in enumerate(rows) if r["trusted"]]
    from .boundary_evidence import register_services
    register_services(geography,[points[i] for i in trusted])
    findings = [{"code": "INPUT_NOTICE", "severity": "warning", "message": message} for message in dataset.warnings]
    progress(15, "Matching actual intersection-bounded street frontages")
    snapped = {}
    for i in trusted:
        point, row = points[i], rows[i]
        candidates = []
        address = normalized(row["address"])
        for idx in geography.road_tree.query(point.buffer(80)):
            road = geography.roads[int(idx)]
            if normalized(road["name"]) and address.endswith(" " + normalized(road["name"])):
                distance = point.distance(road["geometry"])
                if distance <= 80:
                    candidates.append((distance, road["id"], int(idx)))
        if candidates:
            snapped[i] = min(candidates)[2]
    members_by_road = defaultdict(list)
    for i, road_index in snapped.items():
        members_by_road[road_index].append(i)
    alley_roads = []
    for road_index, members in sorted(members_by_road.items()):
        # Nearby alleys alone never establish collection access.
        if all(rows[i].get("access") == "alley" and any(f["geometry"].distance(points[i]) < 80
               for f in geography.nearby_features(points[i].buffer(80), {"alley"})) for i in members):
            alley_roads.append(geography.roads[road_index])
    known_curb_ids={geography.roads[index]["id"] for index,members in members_by_road.items() if any(rows[i].get("access")=="curbside" for i in members)}
    mapped_alley_roads=[f for f in geography.features if f["category"]=="alley_supported_road" and f["road_id"] not in known_curb_ids] if target and use_mapped_alleys else []
    progress(22, "Inventorying City divisions, water, rail, roads and open-space boundaries")
    cells, ledger = geography.geography_cells([points[i] for i in trusted], None)
    geometries = [c["geometry"] for c in cells]
    tree = STRtree(geometries)
    row_cell = {}
    for i in trusted:
        row_cell[i], _ = owner_of(points[i], geometries, tree)
    row_parent={i:cells[row_cell[i]]['name'] for i in trusted}
    dsu = DisjointSet(len(cells))
    atomic = DisjointSet(len(rows))
    buckets = defaultdict(list)
    for i in trusted:
        r = rows[i]
        buckets[("coordinate", round(r["lat"], 8), round(r["lon"], 8))].append(i)
        if r["site"]:
            buckets[("site", r["site"])].append(i)
        # A repeated address string alone is not proof of one physical site.
        # Only supplied site IDs, shared coordinates and reference parcels link it.
    progress(28, "Protecting shared sites, points and ordinary street segments")
    road_groups = defaultdict(list)
    snap_misses = len(trusted) - len(snapped)
    selected_categories = {"waterway", "railway", "controlled_road", "high_speed_road", "wide_road"}
    alley_ids = set()
    for i in trusted:
        if i not in snapped:
            continue
        road = geography.roads[snapped[i]]
        if road["type"] == "BRIDGE" or road["id"] in alley_ids:
            continue
        # A selected divider is allowed two sides; bridges are never inferred as doors.
        nearby = geography.nearby_features(road["geometry"].buffer(8), selected_categories)
        if any(road["geometry"].intersection(divider_line(feature).buffer(8)).length > road["geometry"].length * 0.7
               for feature in nearby):
            continue
        road_groups[road["id"]].append(i)
    for key, members in road_groups.items():
        buckets[("ordinary segment", key)] = members
    serviced_parcels = {}
    for i in trusted:
        matches = geography.parcel_tree.query(points[i], predicate="intersects")
        if len(matches):
            p = min((int(j) for j in matches), key=lambda j: (geography.parcels[j]["geometry"].area, geography.parcels[j]["id"]))
            from .geography import serviced_parcel_component
            component,parcel=serviced_parcel_component(geography.parcels[p],points[i])
            buckets[("parcel", parcel["id"],component)].append(i)
            serviced_parcels[p,component] = parcel
    for members in buckets.values():
        for i in members[1:]:atomic.union(members[0],i)
    atomic_counts=Counter(atomic.find(i) for i in trusted)
    row_cell,dsu,merge_reasons,boundary_conflicts=protect_cells(cells,points,trusted,buckets,serviced_parcels,road_groups,geography.roads)
    refinement_evidence={}
    progress(48, "Dissolving weak seams and evaluating planning size")
    counts = Counter(dsu.find(row_cell[i]) for i in trusted)
    current = merge_geometry(cells, dsu)
    # A divider with service only on one side has no subdivision purpose. Assign
    # empty child pieces through the weakest finite seam, retaining the real edges.
    while True:
        changed = False
        keys = sorted(current)
        empty_tree = STRtree([current[k] for k in keys])
        for empty in sorted(key for key in current if not counts[key]):
            if empty not in current:
                continue
            options = []
            for other_index in empty_tree.query(current[empty]):
                other = dsu.find(keys[int(other_index)])
                if other == empty or other not in current or not counts[other]:
                    continue
                shared = current[empty].boundary.intersection(current[other].boundary).length
                if shared > 0.1:
                    union = current[empty].union(current[other])
                    if union.geom_type in {'Polygon','MultiPolygon'} and len(polygon_parts(union))<=len(polygon_parts(current[other])):
                        options.append((-shared, other, union))
            if options:
                _, other, union = min(options, key=lambda x: (x[0], x[1]))
                dsu.union(empty, other)
                root = dsu.find(empty)
                count = counts[empty] + counts[other]
                del current[empty], current[other]
                current[root], counts[root] = union, count
                merge_reasons["unserved candidate child"] += 1
                changed = True
        if not changed:
            break
        progress(51, "Assigning whole unserved faces without leaving internal gaps")
    root_points=defaultdict(list)
    for i in trusted:root_points[dsu.find(row_cell[i])].append(points[i])
    assign_unserved_components(current,root_points,serviced_parcels,merge_reasons,progress)
    # Target mode joins small neighbouring candidate cells inside the same parent
    # before considering any seam between neighbourhoods. Strong natural boundaries
    # are never crossed merely to balance counts. Target is deliberately soft.
    parent_votes=defaultdict(Counter)
    for i in trusted:parent_votes[dsu.find(row_cell[i])][cells[row_cell[i]]['source_id']]+=1
    nearby_links=merge_target_regions(current,counts,dsu,cells,geography,target,ceiling or float('inf'),merge_reasons,progress,parent_votes,root_points,serviced_parcels=serviced_parcels)
    root_points=defaultdict(list)
    for i in trusted:root_points[dsu.find(row_cell[i])].append(points[i])
    assign_unserved_components(current,root_points,serviced_parcels,merge_reasons,progress)
    # Keep explicit zero-demand face ownership. Reconstructing from the earlier
    # protection DSU would incorrectly attach those empty components again.
    counts = Counter(dsu.find(row_cell[i]) for i in trusted)
    empty_face_count = sum(1 for root in current if not counts[root])
    empty_face_area = sum(g.area for root,g in current.items() if not counts[root])
    numeric_holes = []
    occupied = {}
    for root, geometry in current.items():
        if not counts[root]:
            continue
        cleaned = []
        for part in polygon_parts(geometry):
            holes = []
            for ring in part.interiors:
                area = Polygon(ring).area
                if area <= 1:
                    numeric_holes.append(area)
                else:
                    holes.append(ring)
            cleaned.append(Polygon(part.exterior, holes))
        occupied[root] = cleaned[0] if len(cleaned) == 1 else MultiPolygon(cleaned)
    occupied, coverage_notes = shared_native_coverage(occupied)
    assign_unserved_components(occupied,root_points,serviced_parcels,merge_reasons,progress)
    # Face ownership and shared-edge noding can expose a new legitimate neighbour.
    # Re-evaluate actual final seams until no whole-area join or empty-face
    # ownership change remains. A soft count preference cannot strand a pocket.
    for cycle in range(12):
        before=len(occupied)
        counts=Counter(dsu.find(row_cell[i]) for i in trusted)
        root_points=defaultdict(list);parent_votes=defaultdict(Counter)
        for i in trusted:
            root=dsu.find(row_cell[i]);root_points[root].append(points[i])
            parent_votes[root][cells[row_cell[i]]['source_id']]+=1
        nearby_links=merge_target_regions(occupied,counts,dsu,cells,geography,target,ceiling or float('inf'),merge_reasons,
            lambda _pc,message:progress(65,message),parent_votes,root_points,nearby_links,serviced_parcels)
        root_points=defaultdict(list)
        for i in trusted:root_points[dsu.find(row_cell[i])].append(points[i])
        moved=assign_unserved_components(occupied,root_points,serviced_parcels,merge_reasons,lambda _pc,message:progress(66,message))
        occupied,notes=shared_native_coverage(occupied)
        for name,value in notes.items():coverage_notes[name]+=value
        moved+=assign_unserved_components(occupied,root_points,serviced_parcels,merge_reasons,lambda _pc,message:progress(66,message))
        if before==len(occupied) and not moved:break
    else:
        findings.append({'code':'CONSOLIDATION_STABILITY','severity':'error','message':'Final whole-area ownership did not stabilise within the bounded review passes.'})
    # Protecting a parcel can join entire candidate cells on opposite banks.
    # Reapply strong physical dividers to the service groups, assigning the
    # complete parcel locally instead of dragging both populated banks with it.
    from .major_boundaries import separate
    physical_regions=[{'geometry':g,'members':{i for i in trusted if dsu.find(row_cell[i])==k},
        'links':nearby_links.get(k,[])} for k,g in occupied.items()]
    physical_regions,physical_corrections=separate(physical_regions,points,buckets,serviced_parcels,geography)
    if physical_corrections['splits']:
        occupied={k:r['geometry'] for k,r in enumerate(physical_regions)}
        row_cell={i:k for k,r in enumerate(physical_regions) for i in r['members']}
        dsu=DisjointSet(len(physical_regions))
        nearby_links={k:r['links'] for k,r in enumerate(physical_regions) if r['links']}
        root_points={k:[points[i] for i in r['members']] for k,r in enumerate(physical_regions)}
    natural_count=len(occupied);balance_report=None;planning_metadata={};natural_corrections=None
    if any(f['category']=='municipal_corridor' for f in geography.features):
        members=defaultdict(list)
        for i in trusted:members[dsu.find(row_cell[i])].append(i)
        corrected,natural_corrections=rebalance(occupied,members,nearby_links,points,buckets,serviced_parcels,geography,preferences,ledger,progress,refinement_evidence,natural_only=True)
        occupied={k:r['geometry'] for k,r in enumerate(corrected)}
        row_cell={i:k for k,r in enumerate(corrected) for i in r['members']};dsu=DisjointSet(len(corrected))
        nearby_links={k:r['links'] for k,r in enumerate(corrected) if r['links']}
        root_points={k:[points[i] for i in sorted(r['members'])] for k,r in enumerate(corrected)}
        planning_metadata={k:{'natural_boundary_ids':r['boundaries']} for k,r in enumerate(corrected)}
        natural_count=len(occupied)
    target,ceiling=planning_target,planning_ceiling
    if target:
        members=defaultdict(list)
        for i in trusted:members[dsu.find(row_cell[i])].append(i)
        planned,balance_report=rebalance(occupied,members,nearby_links,points,buckets,serviced_parcels,geography,preferences,ledger,progress,refinement_evidence)
        occupied={k:r['geometry'] for k,r in enumerate(planned)}
        row_cell={i:k for k,r in enumerate(planned) for i in r['members']}
        dsu=DisjointSet(len(planned));nearby_links={k:r['links'] for k,r in enumerate(planned) if r['links']}
        planning_metadata={k:{'planning_reason':r['reason'],'planning_score':round(r['score'],6),
            'natural_parent_ids':sorted(r['parents']),'chosen_boundary_ids':r['boundaries'],
            'last_resort_boundary_review':r.get('last_resort',False),
            'continuity_street_boundary':r.get('continuity_corridor'),
            'boundary_quality':r.get('boundary_quality')} for k,r in enumerate(planned)}
        root_points={k:[points[i] for i in sorted(r['members'])] for k,r in enumerate(planned)}
        atomic=DisjointSet(len(rows))
        for group in buckets.values():
            for i in group[1:]:atomic.union(group[0],i)
        atomic_counts=Counter(atomic.find(i) for i in trusted)
    # Stable numbering depends on geometry/identity, never hash iteration or row order.
    roots = sorted(occupied, key=lambda root: (min(rows[i]["id"] for i in trusted if dsu.find(row_cell[i]) == root), canonical(occupied[root])))
    section_id = {root: f"{dataset.day[:3]}-{number:03d}" for number, root in enumerate(roots, 1)}
    root_geometries = [occupied[root] for root in roots]
    final_tree = STRtree(root_geometries)
    assignment = {i: section_id[dsu.find(row_cell[i])] for i in trusted}
    estimated_nearest = []
    trusted_sites = {rows[i]["site"]: assignment[i] for i in trusted if rows[i]["site"]}
    trusted_coordinates = {(rows[i]["lat"], rows[i]["lon"]): assignment[i] for i in trusted}
    estimated_sites = {}
    for i, row in enumerate(rows):
        if row["trusted"]:
            continue
        fixed_owner = trusted_sites.get(row["site"]) or trusted_coordinates.get((row["lat"], row["lon"])) or estimated_sites.get(row["site"])
        if fixed_owner:
            assignment[i], nearest = fixed_owner, False
        else:
            owner, nearest = owner_of(points[i], root_geometries, final_tree, allow_nearest=True)
            assignment[i] = section_id[roots[owner]]
        if row["site"]:
            estimated_sites[row["site"]] = assignment[i]
            buckets[("site", row["site"])].append(i)
        buckets[("coordinate", round(row["lat"], 8), round(row["lon"], 8))].append(i)
        if nearest:
            estimated_nearest.append(row["id"])
    progress(72, "Checking exported ownership, containment, parcels and topology")
    sections = []
    for root in roots:
        sid = section_id[root]
        member_indices = [i for i in range(len(rows)) if assignment[i] == sid]
        parent_counts=Counter(row_parent[i] for i in member_indices if rows[i]['trusted'])
        parent_names=sorted(parent_counts,key=lambda name:(-parent_counts[name],name))
        geometry = occupied[root]
        parts = polygon_parts(geometry)
        holes = sum(len(p.interiors) for p in parts)
        enclave_indices, unowned_holes = enclosed_owners(geometry, root_geometries, final_tree)
        enclave_ids = [section_id[roots[j]] for j in enclave_indices if roots[j]!=root]
        nearby_allowed=permitted_nearby_components(geometry,nearby_links.get(root),[points[i] for i in member_indices if rows[i]['trusted']])
        if (len(parts) != 1 and not nearby_allowed) or unowned_holes:
            findings.append({"code": "TOPOLOGY", "severity": "error", "section": sid,
                             "message": f"{len(parts)} polygon components and {len(unowned_holes)} unassigned interior gaps; this section needs correction before acceptance."})
        if nearby_allowed:
            findings.append({'code':'NEARBY_SMALL_AREA_GROUP','severity':'warning','section':sid,
                'message':'A pocket under 100 addresses shares this address list with a larger area within 500 m. Each real polygon piece is checked. No inventoried important boundary or other serviced parcel crossed the grouping check; road access remains unverified.'})
        narrow = polygon_parts(geometry.buffer(-40))
        populated_lobes = sum(any(r["trusted"] and p.covers(points[i]) for i, r in enumerate(rows) if assignment[i] == sid) for p in narrow)
        if populated_lobes > 1:
            findings.append({"code": "NARROW_CONNECTION", "severity": "warning", "section": sid,
                             "message": "A 40 m geometry erosion separates serviced lobes. Review the connection; road access is not proven."})
        count = len(member_indices)
        oversize_reason = None
        if target and count > ceiling:
            protected_count = max([atomic_counts[atomic.find(i)] for i in member_indices if rows[i]['trusted']] or [0])
            oversize_reason = (f"One linked, indivisible site/coordinate/parcel/ordinary frontage group contains {protected_count:,} records."
                               if protected_count > ceiling else
                               planning_metadata.get(root,{}).get('planning_reason',
                               "The available mapped dividers do not yield another useful split after site, parcel and ordinary-frontage protection."))
            findings.append({"code": "ABOVE_TARGET", "severity": "warning", "section": sid,
                             "message": f"Larger planning exception: {count:,} is above the {ceiling:,} preferred upper value. The address preference is soft; whole groups, small-pocket consolidation and important boundaries take priority. {oversize_reason}"})
        sections.append({"type": "Feature", "id": sid, "properties": {"id": sid,
            "name": " / ".join(parent_names), "addresses": count, "trusted": sum(rows[i]["trusted"] for i in member_indices),
            "estimated": sum(not rows[i]["trusted"] for i in member_indices), "area_km2": round(geometry.area / 1e6, 4),
            "colour": COLOURS[(len(sections)) % len(COLOURS)], "components": len(parts), "holes": holes,
            "enclave_areas": enclave_ids,
            "nearby_small_area_group":nearby_allowed,"nearby_merge_links":nearby_links.get(root,[]),
            "boundary_basis": "Natural areas first; range mode scores whole-area merges and supported finite municipal/broad-road splits. Last-resort whole-frontage regrouping is separately flagged for pickup-access review.",
            **planning_metadata.get(root,{}),
            "city_neighbourhood_counts":dict(parent_counts),
            "size_status": "ABOVE_LIMIT" if oversize_reason else "SMALL_NATURAL_AREA" if target and count < preferences["preferred_minimum"] else "IN_RANGE" if target else "NATURAL",
            "oversize_reason": oversize_reason,
            "status": "PROVISIONAL"}, "geometry": mapping(publication_geometry(geometry))})
        if planning_metadata.get(root,{}).get('last_resort_boundary_review'):
            findings.append({'code':'LAST_RESORT_BOUNDARY','severity':'warning','section':sid,
                'message':('A continuous City street/municipal boundary replaced fragmented cuts. Recorded opposite-curb exceptions apply along that street; shared sites, coordinates and parcels remain whole. Review actual pickup access.'
                    if planning_metadata.get(root,{}).get('continuity_street_boundary') else
                    'An oversized natural area needed whole-frontage regrouping after supported broad/municipal dividers failed. Shared sites, coordinates and parcels remain whole. Review street continuity and rear-property/alley sides against actual pickup access.')})
    area_counts=Counter(dsu.find(row_cell[i]) for i in trusted)
    # Include estimates in the address-list count, after boundaries are fixed.
    root_by_section={section_id[root]:root for root in roots}
    for i in range(len(rows)):
        if not rows[i]['trusted']:area_counts[root_by_section[assignment[i]]]+=1
    for feature in sections:
        p=feature['properties'];p['small_area_status']=None;p['small_area_reason']=None
        if p['addresses']>=100:continue
        status,reason=small_area_exception(root_by_section[feature['id']],occupied,area_counts,geography,ceiling,root_points[root_by_section[feature['id']]],root_points)
        p['small_area_status'],p['small_area_reason']=status,reason
        findings.append({'code':'SMALL_AREA_EXCEPTION','severity':'error' if status=='NEEDS_REVIEW' else 'warning',
                         'section':feature['id'],'message':f"{p['addresses']} addresses retained below 100: {reason}"})
    exported_points = [{"id": row["id"], "address": row["address"], "lat": row["lat"], "lon": row["lon"],
                        "quality": row["quality"], "section": assignment[i], "source_row": row["source_row"],
                        "trusted": row["trusted"]} for i, row in enumerate(rows)]
    validation = verify(rows, points, assignment, sections, occupied, roots, section_id, buckets, serviced_parcels)
    findings.extend(validation.pop("findings"))
    validation["published_numeric_overlap_removed_m2"] = normalise_published_edges(sections)
    published = {f["id"]: shape(f["geometry"]) for f in sections}
    published_projected = [transform_geometry(FORWARD.transform,g) for g in published.values()]
    published_projected_tree = STRtree(published_projected)
    invalid_published = [sid for (sid, g), metric,root in zip(published.items(),published_projected,roots)
                         if not g.is_valid or (g.geom_type != "Polygon" and not permitted_nearby_components(metric,nearby_links.get(root),
                             [points[i] for i in trusted if assignment[i]==sid])) or enclosed_owners(metric,published_projected,published_projected_tree)[1]]
    outside_published = [rows[i]["id"] for i in trusted if not published[assignment[i]].covers(Point(rows[i]["lon"], rows[i]["lat"]))]
    validation["published_geometries_valid"] = not invalid_published
    railway_crossings=[sid for (sid,_g),metric in zip(published.items(),published_projected)
        if railway_separates_services(metric,[points[i] for i in trusted if assignment[i]==sid],geography)]
    validation['railway_separation_preserved']=not railway_crossings
    validation['railway_crossing_areas']=railway_crossings
    if railway_crossings:
        findings.append({'code':'RAILWAY_BOUNDARY','severity':'error','message':'Published areas contain serviced populations on both sides of a complete finite railway divider.','sections':railway_crossings})
    major_crossings=[sid for (sid,_g),metric in zip(published.items(),published_projected)
        if linear_separator(metric,[points[i] for i in trusted if assignment[i]==sid],geography,
            {'controlled_road','high_speed_road'})]
    validation['major_road_separation_preserved']=not major_crossings
    validation['major_road_crossing_areas']=major_crossings
    if major_crossings:
        findings.append({'code':'MAJOR_ROAD_BOUNDARY','severity':'error',
            'message':'Published areas contain serviced populations across a complete mapped major-road divider.',
            'sections':major_crossings})
    validation['nearby_small_area_groups']=[f['id'] for f in sections if f['properties']['nearby_small_area_group']]
    validation['small_area_exceptions']={f['id']:f['properties']['small_area_status'] for f in sections if f['properties']['small_area_status']}
    validation["published_reliable_points_outside"] = len(outside_published)
    validation["published_precision_degrees"] = 1e-8
    published_list = list(published.values())
    published_tree = STRtree(published_list)
    published_overlap = 0.0
    for i, geometry in enumerate(published_list):
        for j in published_tree.query(geometry):
            if int(j) > i:
                published_overlap += transform_geometry(FORWARD.transform, geometry.intersection(published_list[int(j)])).area
    validation["published_overlap_m2"] = published_overlap
    if published_overlap > 1:
        findings.append({"code": "PUBLISHED_OVERLAP", "severity": "error", "message": f"Exported polygons overlap by {published_overlap:.3f} m2."})
    if invalid_published:
        findings.append({"code": "PUBLISHED_GEOMETRY", "severity": "error", "message": "Exported WGS 84 polygons fail validity or topology.", "sections": invalid_published})
    if outside_published:
        findings.append({"code": "PUBLISHED_CONTAINMENT", "severity": "error", "message": f"{len(outside_published)} reliable points fall outside the exported WGS 84 geometry.", "ids": outside_published[:40]})
    validation["numeric_holes_removed"] = len(numeric_holes)
    validation["numeric_hole_area_m2"] = sum(numeric_holes)
    validation["geometry_precision_m"] = 0.01
    validation.update(coverage_notes)
    validation["street_boundary_conflicts"] = boundary_conflicts
    validation["unassigned_unserved_faces"] = empty_face_count
    validation["unassigned_unserved_area_m2"] = empty_face_area
    parcel_covered = {i for key, indices in buckets.items() if key[0] == "parcel" for i in indices}
    validation["reliable_points_with_parcel"] = len(parcel_covered)
    validation["reliable_points_without_parcel"] = len(trusted) - len(parcel_covered)
    if len(parcel_covered) < len(trusted):
        findings.append({"code": "PARCEL_COVERAGE", "severity": "warning",
                         "message": f"{len(trusted) - len(parcel_covered):,} reliable records have no containing parcel in the bounded reference. Full parcel validation is not claimed for those records."})
    if target:
        protected_excess = {tuple(sorted(indices)) for indices in buckets.values() if len(indices) > target}
        if protected_excess:
            findings.append({"code": "PROTECTED_GROUP_ABOVE_TARGET", "severity": "warning",
                             "message": f"{len(protected_excess)} protected group(s) exceed the planning target. They remain intact; no capacity-driven site split was applied."})
    if snap_misses:
        findings.append({"code": "ROAD_SNAP_REVIEW", "severity": "warning", "message": f"{snap_misses:,} records have no same-name official segment within 80 m. They retain site/point/parcel protection; complete frontage QA remains open."})
    if merge_reasons['park/land-use edge yields to whole-group connectivity']:
        findings.append({'code':'WHOLE_GROUP_CONNECTIVITY','severity':'warning','message':
            f"{merge_reasons['park/land-use edge yields to whole-group connectivity']} real whole-block joins preserve mandatory site, parcel or paired-curb connectivity across weaker park/land-use seams. Railway, water and controlled/wide-road boundaries were not waived for this repair. Review the candidate ledger and actual pickup access."})
    if estimated_nearest:
        findings.append({"code": "ESTIMATE_NEAREST", "severity": "warning", "message": f"Estimated points assigned to the nearest fixed section (within 200 m): {', '.join(estimated_nearest)}."})
    findings.append({"code": "ROAD_QA_PENDING", "severity": "warning", "message": "Road reachability, legal barrier crossings, complete areal-gap discovery and actual pickup positions are not verified. These are provisional planning sections, not routes or fleet requirements."})
    if use_mapped_alleys:
        findings.append({"code":"ALLEY_ACCESS_UNCONFIRMED","severity":"warning","message":"Mapped parallel rear alleys may support provisional road boundaries. They do not establish actual alley collection. Explicit curbside inputs veto this exception; confirm pickup access before acceptance."})
    # Selection is measured on final *shared* seams, not merely because a candidate was tried.
    shared_seams = []
    for a, ga in enumerate(root_geometries):
        for b_idx in final_tree.query(ga):
            b = int(b_idx)
            if b <= a:
                continue
            seam = ga.boundary.intersection(root_geometries[b].boundary)
            if seam.length > 1:
                shared_seams.append(seam)
    seam = unary_union(shared_seams) if shared_seams else None
    seam_buffer = seam.buffer(2) if seam is not None else None
    prepared_seam = prep(seam_buffer) if seam_buffer is not None else None
    by_id = {feature["id"]: feature for feature in geography.features}
    by_id.update({r["id"]: r for r in alley_roads})
    by_id.update(refinement_evidence)
    progress(88, "Auditing selected boundary evidence")
    for number, item in enumerate(ledger):
        if item.get('category')=='natural_area_split':
            item['decision']=item['state'];item['decision_reason']=item['reason']
            feature=by_id.get(item['id'])
            selected=bool(item.get('chosen_for_split') and feature and prepared_seam is not None
                and prepared_seam.intersects(feature['geometry']) and feature['geometry'].intersection(seam_buffer).length>1)
            item['state']='SELECTED' if selected else 'REVIEWED_UNUSED'
            continue
        feature = by_id[item["id"]]
        line = divider_line(feature)
        selected = (prepared_seam is not None and prepared_seam.intersects(line)
                    and line.intersection(seam_buffer).length > 20)
        item["state"] = "SELECTED" if selected else "REVIEWED_UNUSED"
        item["reason"] = "Feature supports a final shared section edge." if selected else "Inventoried; no material final shared edge uses this feature."
        if number % 250 == 0:
            progress(89, "Checking boundary evidence against final shared edges")
    continuity_review=[]
    for quality in (balance_report or {}).get('continuity',{}).get('remaining',[]):
        members=[i for item in quality['street_breaks'] for i in item['members']]
        members.extend(i for item in quality['alley_side_splits'] for side in item['side_members'] for i in side)
        affected=sorted({assignment[i] for i in members})
        review={'sections':affected,'street_breaks':len(quality['street_breaks']),
            'alley_side_splits':len(quality['alley_side_splits']),'penalty':quality['penalty'],
            'roads':sorted({item['road'] for item in quality['street_breaks']}),
            'alley_ids':sorted({item['alley_id'] for item in quality['alley_side_splits']})}
        continuity_review.append(review)
        for sid in affected:
            findings.append({'code':'STREET_ALLEY_CONTINUITY_REVIEW','severity':'warning','section':sid,
                'message':f"The shared boundary retains {review['street_breaks']} street-run cut(s) and {review['alley_side_splits']} opposite-alley-side split(s). Both carry the same large penalty. No eligible continuous replacement was found; review this boundary before accepting it."})
    validation['street_alley_continuity_review']=continuity_review
    validation['street_alley_boundary_score_passed']=not continuity_review
    errors = [f for f in findings if f["severity"] == "error"]
    above_limit = [f["id"] for f in sections if f["properties"]["size_status"] == "ABOVE_LIMIT"]
    below_range=[f['id'] for f in sections if target and f['properties']['addresses']<preferences['preferred_minimum']]
    validation["address_limit_met"] = not above_limit if target else None
    validation["areas_above_limit"] = above_limit
    validation["maximum_addresses"] = ceiling
    validation['below_preferred_range']=below_range
    validation['preferred_range_met']=not above_limit and not below_range if target else None
    validation['last_resort_boundary_review']=[f['id'] for f in sections if f['properties'].get('last_resort_boundary_review')]
    validation['longitudinal_street_boundary_exceptions']=[{'candidate':r['id'],'road':r['name'],
        'ordinary_segment_ids':r['waived_ordinary_segments']} for r in ledger if r.get('longitudinal_street_exception')]
    status = "FAILED" if errors else "PROVISIONAL"
    for section in sections:
        sid = section["id"]
        section["properties"]["status"] = "FAILED" if any(f.get("section") == sid and f["severity"] == "error" for f in findings) else status
        section["properties"]["review_count"] = sum(f.get("section") == sid for f in findings)
    from .boundary_evidence import profile as boundary_profile
    from .geography import shared_boundary
    affinities=[]
    for a,root in enumerate(roots):
        for other in roots[a+1:]:
            edge=shared_boundary(occupied[root],occupied[other])
            if edge.length>=20:
                affinities.append({'sections':[section_id[root],section_id[other]],'shared_m':round(edge.length,3),**boundary_profile(edge,geography)})
    result = {"engine": ENGINE_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
        "status": status, "source": dataset.source, "sheet": dataset.sheet, "day": dataset.day,
        "day_source": dataset.day_source, "available_days": dataset.available_days,
        "input_hash": dataset.digest, "geography_hash": geography.digest,
        "settings": {**preferences,
                     "small_area_merge_threshold":100,"nearby_small_area_metres":500,"larger_areas_require_review":True,
                     "target_is_hard_capacity": False, "coordinate_crs": "EPSG:4326", "geometry_crs": "EPSG:32614"},
        "summary": {"addresses": len(rows), "areas": len(sections), "natural_areas":natural_count,"assigned": len(assignment),
                    "estimated": len(rows) - len(trusted), "excluded_other_days": dataset.excluded,
                    "smallest": min(f["properties"]["addresses"] for f in sections),
                    "largest": max(f["properties"]["addresses"] for f in sections),
                    "areas_above_limit": len(above_limit), "areas_below_range":len(below_range),
                    "target_met": not above_limit and not below_range if target else None,
                    "within_preferred_range":sum(preferences['preferred_minimum']<=f['properties']['addresses']<=ceiling for f in sections) if target else None,
                    "within_preferred_upper_percent":round((len(sections)-len(above_limit))*100/len(sections),1) if target else None,
                    "errors": len(errors), "warnings": sum(f["severity"] == "warning" for f in findings)},
        "areas": {"type": "FeatureCollection", "day": dataset.day, "features": sections}, "points": exported_points,
        "findings": findings, "validation": validation, "boundary_candidates": ledger,
        "range_balancing":balance_report,
        "boundary_affinities":affinities,
        "natural_corrections":natural_corrections,
        "physical_boundary_corrections":physical_corrections,
        "corridor_evidence":getattr(geography,'corridor_review',[]),
        "merge_reasons": dict(merge_reasons), "geography_sources": geography.manifest,
        "assignment_columns": assignment_columns(dataset.columns),
        "limitations": "Property coordinates only. No truck, load, duration, pickup-access or legal road-connectivity conclusions."}
    # Deterministic content excludes timestamps. Used by independent process replay.
    result["partition_hash"] = hashlib.sha256(json.dumps({"areas": result["areas"], "assignments": [(p["id"], p["section"]) for p in exported_points], "ledger": ledger}, sort_keys=True).encode()).hexdigest()
    progress(96, "Saving one local result package")
    return result


def verify(rows, points, assignment, sections, occupied, roots, section_ids, buckets, parcels):
    """Independent gates over the final result; repeats ownership/geometry checks."""
    findings = []
    counts = Counter(p["id"] for p in rows)
    exactly_once = len(assignment) == len(rows) and len(counts) == len(rows) and set(assignment) == set(range(len(rows)))
    if not exactly_once:
        findings.append({"code": "COVERAGE", "severity": "error", "message": "Address identity coverage failed."})
    by_id = {section_ids[r]: occupied[r] for r in roots}
    containment = [rows[i]["id"] for i in range(len(rows)) if rows[i]["trusted"] and not by_id[assignment[i]].covers(points[i])]
    split_atoms = [str(key) for key, indices in buckets.items() if len({assignment[i] for i in indices}) > 1]
    if containment:
        findings.append({"code": "CONTAINMENT", "severity": "error", "message": f"{len(containment)} reliable points lie outside their assigned polygon.", "ids": containment[:40]})
    if split_atoms:
        findings.append({"code": "SPLIT_ATOM", "severity": "error", "message": f"{len(split_atoms)} protected groups cross sections.", "groups": split_atoms[:40]})
    polygons = list(by_id.values())
    tree = STRtree(polygons)
    overlap = 0.0
    for i, geometry in enumerate(polygons):
        if not geometry.is_valid:
            findings.append({"code": "INVALID_POLYGON", "severity": "error", "section": list(by_id)[i], "message": "Invalid final polygon."})
        for j in tree.query(geometry):
            if int(j) > i:
                overlap += geometry.intersection(polygons[int(j)]).area
    if overlap > 1:
        findings.append({"code": "OVERLAP", "severity": "error", "message": f"Final polygons overlap by {overlap:.2f} square metres."})
    cut_parcels = []
    for parcel in parcels.values():
        pieces = [parcel["geometry"].intersection(polygons[int(i)]).area for i in tree.query(parcel["geometry"])]
        if sum(a > max(4.0, parcel["geometry"].area * .02) for a in pieces) > 1:
            cut_parcels.append(parcel["id"])
    if cut_parcels:
        findings.append({"code": "PARCEL_CUT", "severity": "error", "message": f"{len(cut_parcels)} serviced parcels materially cross final sections.", "parcels": cut_parcels[:40]})
    return {"exactly_once": exactly_once, "source_ids": len(counts), "assigned": len(assignment),
            "reliable_points_outside": len(containment), "split_protected_groups": len(split_atoms),
            "overlap_m2": round(overlap, 6), "serviced_parcels_checked": len(parcels),
            "material_parcel_cuts": len(cut_parcels), "estimated_points_drive_boundaries": False,
            "road_connectivity": "NOT_VERIFIED", "findings": findings}


def assignment_columns(source_columns):
    names = {}
    used = set(source_columns)
    for name in ["PartitionAddressId", "PartitionAreaId", "PartitionStatus", "PartitionSourceRow", "PartitionCollectionDay"]:
        candidate, suffix = name, 2
        while candidate in used:
            candidate = f"{name}_{suffix}"
            suffix += 1
        names[name] = candidate
        used.add(candidate)
    return names


def assignments_csv(dataset, result):
    by_id = {point["id"]: point for point in result["points"]}
    output = io.StringIO(newline="")
    names = assignment_columns(dataset.columns)
    columns = dataset.columns + list(names.values())
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for row in dataset.rows:
        data = dict(row["raw"])
        data.update({names["PartitionAddressId"]: row["id"], names["PartitionAreaId"]: by_id[row["id"]]["section"], names["PartitionStatus"]: result["status"], names["PartitionSourceRow"]: row["source_row"], names["PartitionCollectionDay"]: dataset.day})
        writer.writerow(data)
    return "\ufeff" + output.getvalue()
