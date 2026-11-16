"""Validate complete mapped-divider alternatives without count-specific waivers."""
from collections import defaultdict
from shapely import set_precision
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .geography import subdivide,shared_boundary,internal_seams
from .continuity import assess


def divide(parent,members,lines,points,buckets,parcels,geography,minimum=1):
    try:parts=subdivide(parent,lines)
    except ValueError:return None,{'reason':'subdivision coverage'}
    if len(parts)<2:return None,{'reason':'no useful serviced division','counts':[len(members)]}
    groups=defaultdict(set);owners={}
    if getattr(geography,'alternative_points',None) is not points:
        geography.alternative_points=points;geography.alternative_point_tree=STRtree(points)
    for k,part in enumerate(parts):
        for index in geography.alternative_point_tree.query(part,predicate='intersects'):
            i=int(index)
            if i in members and i not in owners:owners[i]=k;groups[k].add(i)
    for i in members-set(owners):
        hits=[j for j,p in enumerate(parts) if p.distance(points[i])<.02]
        if not hits:return None,{'reason':'point containment'}
        owners[i]=min(hits);groups[min(hits)].add(i)
    counts=[len(g) for g in groups.values()]
    if len(counts)<2 or min(counts)<minimum:return None,{'reason':'no useful serviced division','counts':counts}
    road_by_id={r['id']:r for r in geography.roads};mask=unary_union(lines).buffer(8);allowed=set()
    from .landuse_paths import frontage_groups
    flexible=frontage_groups(lines,buckets,geography)
    for key,indices in buckets.items():
        if len({owners[i] for i in indices if i in owners})<2:continue
        road=road_by_id.get(key[1]) if key[0]=='ordinary segment' else None
        if road and (key in flexible or road['geometry'].intersection(mask).length>road['geometry'].length*.7):allowed.add(key)
        else:return None,{'reason':'protected group','group':list(key),'counts':counts}
    populated={k:set_precision(parts[k],0) for k in groups};empty=set(range(len(parts)))-set(groups)
    for _ in range(len(empty)+1):
        changed=False
        for j in sorted(empty.copy()):
            options=sorted((-shared_boundary(parts[j],g).length,k) for k,g in populated.items())
            length,k=options[0]
            if length>=-.001:continue
            joined=populated[k].union(set_precision(parts[j],0))
            if joined.geom_type=='Polygon':populated[k]=joined;empty.remove(j);changed=True
        if not changed:break
    if empty:return None,{'reason':'detached empty face','counts':counts}
    cut=internal_seams(populated.values())
    if getattr(geography,'alternative_parcels',None) is not parcels:
        geography.alternative_parcels=parcels
        geography.alternative_parcel_values=list(parcels.values())
        geography.alternative_parcel_tree=STRtree([p['geometry'] for p in geography.alternative_parcel_values])
    for index in geography.alternative_parcel_tree.query(cut,predicate='intersects'):
        parcel=geography.alternative_parcel_values[int(index)]
        p=parcel['geometry']
        if sum(p.intersection(g).area>max(4,p.area*.02) for g in populated.values())>1:
            return None,{'reason':'serviced parcel cut','parcel':parcel['id'],'counts':counts}
    quality=assess(cut,owners,points,buckets,geography)
    if quality['street_breaks'] or quality['alley_side_splits']:return None,{'reason':'street or alley split','quality':quality,'counts':counts}
    if any(g.geom_type!='Polygon' or not g.is_valid for g in populated.values()):return None,{'reason':'noncontiguous child','counts':counts}
    return {'children':[{'geometry':g,'members':groups[k]} for k,g in sorted(populated.items())],
        'cut':cut,'allowed':allowed,'owners':owners,'quality':quality},{'reason':'valid','counts':counts}
