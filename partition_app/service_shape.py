"""Score interleaved service populations without penalising unserved park space."""
from shapely.geometry import MultiPoint
from shapely.strtree import STRtree


def enclosure(members,points,geography):
    """Measure other service addresses surrounded by this population's hull.

    This is a soft comparison between otherwise valid mapped divisions. The
    hull is never used as an output boundary or as proof of road access. Empty
    parks, rivers and industrial land add no penalty; other service owners do.
    """
    if getattr(geography,'shape_points',None) is not points:
        geography.shape_points=points
        geography.shape_tree=STRtree(points)
        geography.shape_cache={}
    key=frozenset(members)
    if key not in geography.shape_cache:
        hull=MultiPoint([points[i] for i in sorted(key)]).convex_hull
        others={int(i) for i in geography.shape_tree.query(hull,predicate='contains')}-key
        geography.shape_cache[key]={'surrounded_other_addresses':len(others),
            'penalty':4*len(others)/max(1,len(key))}
    return geography.shape_cache[key]


def cost(regions,points,geography):
    return sum(enclosure(r['members'],points,geography)['penalty'] for r in regions)
