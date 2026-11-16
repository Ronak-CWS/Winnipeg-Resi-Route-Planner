"""Restore complete physical dividers after whole-parcel cell protection.

A parcel crossing a candidate line must not merge entire populated banks.
Retain its complete footprint locally, then check each serviced child again.
"""
from collections import Counter, defaultdict

from shapely import set_precision
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .geography import divider_line, polygon_parts, shared_boundary, subdivide


def separate(regions, points, buckets, parcels, geography):
    from .balancing import hard_separator
    output=[];audit={'splits':[], 'rejected':[]}
    categories={'railway','waterway','controlled_road','high_speed_road'}
    for region in regions:
        parent=region['geometry'];members=region['members']
        if parent.geom_type!='Polygon' or not hard_separator(parent,[points[i] for i in members],geography):
            output.append(region);continue
        features=geography.nearby_features(parent,categories)
        parts=subdivide(parent,[divider_line(f) for f in features])
        owners={};groups=defaultdict(set);tree=STRtree(parts)
        for i in sorted(members):
            hits=[int(j) for j in tree.query(points[i],predicate='intersects')]
            if not hits:hits=[j for j,g in enumerate(parts) if g.distance(points[i])<.02]
            if not hits:break
            owners[i]=min(hits);groups[min(hits)].add(i)
        reason=None
        if len(owners)!=len(members) or len(groups)<2:reason='No complete serviced division'
        if reason is None and any(len({owners[i] for i in group if i in owners})>1 for group in buckets.values()):
            reason='A mandatory service group spans the physical divider'
        if reason:
            audit['rejected'].append({'addresses':len(members),'reason':reason});output.append(region);continue
        children={k:parts[k] for k in groups}
        empty=set(range(len(parts)))-set(children)
        # Assign whole zero-service road-space faces; never draw connectors.
        for _ in range(len(empty)+1):
            changed=False
            for j in sorted(empty.copy()):
                options=sorted((-shared_boundary(parts[j],g).length,k) for k,g in children.items())
                length,k=options[0]
                if length>=-1e-7:continue
                joined=set_precision(children[k],0).union(set_precision(parts[j],0))
                if joined.geom_type=='Polygon':children[k]=joined;empty.remove(j);changed=True
            if not changed:break
        if empty:reason='Unassigned detached road-space face'
        adjustments=[]
        if reason is None:
            for parcel in parcels.values():
                g=set_precision(parcel['geometry'],0)
                parcel_members=[i for i in members if g.covers(points[i])]
                if not parcel_members:continue
                bank={owners[i] for i in parcel_members}
                if len(bank)>1:reason='A serviced parcel spans populated banks';break
                owner=next(iter(bank));footprint=g.intersection(set_precision(parent,0))
                cut=sum(footprint.intersection(v).area>max(4,g.area*.02) for v in children.values())>1
                if not cut:continue
                for k in children:
                    if k!=owner:children[k]=children[k].difference(footprint)
                children[owner]=children[owner].union(footprint)
                adjustments.append(parcel['id'])
            if reason is None:
                from .engine import assign_unserved_components
                assign_unserved_components(children,{k:[points[i] for i in group] for k,group in groups.items()},parcels,Counter())
            if reason is None and any(g.geom_type!='Polygon' or not g.is_valid for g in children.values()):
                reason='Whole-parcel correction is disconnected'
            if reason is None and unary_union(list(children.values())).symmetric_difference(parent).area>.5:
                reason='Physical division changed parent coverage'
            if reason is None and any(not children[owners[i]].covers(points[i]) for i in members):
                reason='Physical division changed source ownership'
            if reason is None and any(hard_separator(g,[points[i] for i in groups[k]],geography) for k,g in children.items()):
                reason='A child still spans populated physical banks'
        if reason:
            audit['rejected'].append({'addresses':len(members),'reason':reason,
                'whole_parcels_reallocated':adjustments,
                'child_geometry_types':{k:g.geom_type for k,g in children.items()},
                'child_components':{k:[{'area':p.area,'services':sum(p.covers(points[i]) for i in members)} for p in polygon_parts(g)] for k,g in children.items()}})
            output.append(region);continue
        audit['splits'].append({'addresses':len(members),'counts':[len(groups[k]) for k in sorted(children)],
            'source_ids':sorted(f['id'] for f in features),'whole_parcels_reallocated':adjustments})
        for k,g in sorted(children.items()):
            output.append({**region,'geometry':g,'members':groups[k],'links':[]})
    return output,audit
