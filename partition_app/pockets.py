"""Find sparse service pockets hidden inside otherwise useful planning areas.

Use existing finite municipal/physical footprints, never coordinate cuts or
example names. Empty land connecting polygons is not service continuity.
"""
from collections import Counter
from copy import deepcopy
from shapely import set_precision
from shapely.ops import unary_union
from shapely.strtree import STRtree
from .geography import polygon_parts,divider_line
from .continuity import assess


def separate_sparse_pockets(regions,points,buckets,parcels,geography,progress=lambda *a:None):
    result=deepcopy(regions);audit={'changes':[],'rejections':Counter()}
    parcel_values=list(parcels.values());parcel_tree=STRtree([p['geometry'] for p in parcel_values])
    def closest(a,b):
        tree=STRtree([points[i] for i in b]);other=[points[i] for i in b]
        return min(points[i].distance(other[int(tree.nearest(points[i]))]) for i in a)
    # A finite pass count prevents repeatedly exposing the same tiny seam.
    for _ in range(32):
        proposals=[]
        for index,region in enumerate(result):
            if len(region['members'])<100 or region['geometry'].geom_type!='Polygon':continue
            # A copied Shapely geometry loses its precision model. Restore the
            # existing City centimetre grid before clipping: otherwise shared
            # diagonal edges can create disconnected, sub-metre empty slivers.
            # Reject a material change rather than hiding it as numeric noise.
            boundary=set_precision(region['geometry'],.01)
            grid_change=boundary.symmetric_difference(region['geometry']).area
            if boundary.geom_type!='Polygon' or grid_change>.5:
                audit['rejections']['material grid normalization']+=1;continue
            for feature in geography.nearby_features(boundary,{'community','park','recreation','mapped_open_land','landuse'}):
                if feature['geometry'].geom_type not in {'Polygon','MultiPolygon'}:continue
                for pocket in polygon_parts(boundary.intersection(feature['geometry'])):
                    members={i for i in region['members'] if pocket.covers(points[i])}
                    if not 0<len(members)<100:continue
                    rest=region['members']-members
                    if not rest:continue
                    gap=closest(members,rest)
                    if gap<=500:continue
                    # The former owner may contain a long, empty tongue.
                    # Its neighbour can be operationally close even if the
                    # municipal pocket footprint stops short of that tongue.
                    # This is exposure only: merging still checks the actual
                    # pocket seam, service gap and important barriers below.
                    neighbours=[(closest(members,r['members']),j) for j,r in enumerate(result)
                        if j!=index and boundary.distance(r['geometry'])<=500]
                    if not neighbours:continue
                    nearest,neighbour=min(neighbours)
                    # Exposing a pocket is useful only when another serviced
                    # neighbour is closer than the population of its owner.
                    if nearest>=gap:continue
                    remainder=boundary.difference(pocket)
                    parts=polygon_parts(remainder)
                    populated=[p for p in parts if any(p.distance(points[i])<.02 for i in rest)]
                    if len(populated)!=1:
                        audit['rejections']['multiple populated remainder components']+=1;continue
                    # Retain real empty faces with the new pocket when the
                    # municipal split otherwise leaves an unserved island.
                    empty=[p for p in parts if not any(p.distance(points[i])<.02 for i in rest)]
                    if empty:pocket=unary_union([pocket,*empty])
                    remainder=populated[0]
                    if pocket.geom_type!='Polygon' or not pocket.is_valid or not remainder.is_valid:
                        audit['rejections']['disconnected pocket or invalid geometry']+=1;continue
                    ownership={i:int(i in members) for i in region['members']}
                    if any(len({ownership[i] for i in ids if i in ownership})>1 for ids in buckets.values()):
                        audit['rejections']['protected street or site']+=1;continue
                    seam=pocket.boundary.intersection(remainder.boundary)
                    if any(all(parcel_values[int(j)]['geometry'].intersection(p).area>max(4,parcel_values[int(j)]['geometry'].area*.02)
                        for p in [pocket,remainder]) for j in parcel_tree.query(seam,predicate='intersects')):
                        audit['rejections']['serviced parcel cut']+=1;continue
                    quality=assess(seam,ownership,points,buckets,geography)
                    if quality['street_breaks'] or quality['alley_side_splits']:
                        audit['rejections']['unsupported street or alley split']+=1;continue
                    proposals.append((-(gap-nearest),len(members),feature['id'],index,pocket,remainder,members,rest,gap,nearest,quality))
        if not proposals:break
        _,_,boundary_id,index,pocket,remainder,members,rest,gap,nearest,quality=min(proposals,key=lambda v:v[:4])
        region=result[index];common={k:deepcopy(v) for k,v in region.items() if k not in {'geometry','members','links'}}
        result[index]={**common,'geometry':remainder,'members':rest,'links':region.get('links',[])}
        result.append({**deepcopy(common),'geometry':pocket,'members':members,'links':[],
            'sparse_pocket':True,'boundaries':region.get('boundaries',[])+[boundary_id]})
        change={'addresses':len(members),'members':sorted(members),'boundary_id':boundary_id,
            'former_service_gap_m':round(gap,2),'nearest_other_service_gap_m':round(nearest,2),
            'reason':'Under-100 service pocket isolated by over 500 m of service-free land; separated on an existing finite boundary for compatible-neighbour consolidation.',
            'checks':quality}
        audit['changes'].append(change)
        progress(70,'Checking isolated small service pockets inside larger areas')
    audit['rejections']=dict(audit['rejections'])
    return result,audit


def consolidate_sparse_pockets(regions,points,geography):
    """Attach exposed pockets only across compatible seams; retain barriers."""
    from .balancing import hard_separator,footprint_between,boundary_merge_cost
    result=list(regions);audit=[]
    for pocket in [r for r in result if r.get('sparse_pocket')]:
        if not any(r is pocket for r in result):continue
        candidates=[];blocked=[]
        a=[points[i] for i in pocket['members']]
        for other in result:
            if other is pocket:continue
            union=pocket['geometry'].union(other['geometry'])
            if union.geom_type!='Polygon':continue
            seam=pocket['geometry'].boundary.intersection(other['geometry'].boundary)
            if seam.length<1:continue
            b=[points[i] for i in other['members']]
            tree=STRtree(b);distance=min(p.distance(b[int(tree.nearest(p))]) for p in a)
            if hard_separator(union,a+b,geography):
                blocked.append({'addresses':len(other['members']),'service_gap_m':round(distance,2),'reason':'rail, water or major highway'});continue
            if footprint_between(union,a,b,geography,{'park','recreation','mapped_open_land','landuse'}):continue
            # Rejoining the former remote owner defeats the pocket correction.
            if distance>500:continue
            candidates.append((distance+500*boundary_merge_cost(seam,geography),min(other['members']),other,union))
        if candidates:
            _,_,other,union=min(candidates,key=lambda v:v[:2])
            count=len(pocket['members']);other['geometry']=union;other['members']|=pocket['members']
            other['parents']|=pocket['parents'];other['boundaries']+=pocket['boundaries']
            result=[r for r in result if r is not pocket]
            audit.append({'addresses':count,'status':'MERGED_NEAREST_COMPATIBLE'})
        else:
            audit.append({'addresses':len(pocket['members']),'status':'IMPORTANT_BOUNDARY' if blocked else 'REMOTE',
                'blocked_neighbours':blocked})
    return result,audit
