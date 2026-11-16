"""Keep road-isolated populations separate using existing mapped dividers."""
import hashlib
from shapely.ops import unary_union
from .geography import canonical,divider_line,subdivide,internal_seams
from .alternatives import divide
from .road_candidates import complete


def separate(regions,points,buckets,parcels,geography,ledger,evidence):
    network=getattr(geography,'access_network',None)
    audit={'changes':[],'unresolved':[],'available':network is not None}
    if network is None:return regions,audit
    from .continuity import corridors,split_frontage_buckets
    output=[]
    for region in regions:
        parent=region['geometry'];members=region['members']
        found=network.components(parent,members,points,geography.access_rows)
        groups=[g for g in found['groups'] if len(g)>=max(10,len(members)*.01)]
        if len(groups)<2 or parent.geom_type!='Polygon':output.append(region);continue
        features=geography.nearby_features(parent,{'community','wide_road','broad_corridor','municipal_corridor','park','recreation','mapped_open_land'})
        features+=corridors(geography,parent)
        best=None
        for f in features:
            line=complete(divider_line(f),parent,geography)
            option,report=divide(parent,members,[line],points,buckets,parcels,geography,minimum=10)
            if option is None:continue
            children=option['children']
            # A physical group may have a few ambiguous frontage matches, but
            # its main population must not be scattered just to improve counts.
            matches=[[len(g&c['members']) for c in children] for g in groups]
            if any(max(v)<len(g)*.95 for v,g in zip(matches,groups)):continue
            owners=[max(range(len(v)),key=lambda j:v[j]) for v in matches]
            if len(set(owners))<2:continue
            score=(len(groups)-len(set(owners)),len(children),option['cut'].length,canonical(option['cut']))
            if best is None or score<best[0]:best=(score,f,option)
        if best is None:
            audit['unresolved'].append({'source_member':min(members),'addresses':len(members),'road_components':[len(g) for g in groups],
                'unknown_addresses':len(found['unknown']),'reason':'No complete mapped division passes site, parcel and frontage checks'})
            output.append(region);continue
        _,f,option=best
        identifier='access-division-'+hashlib.sha256(canonical(option['cut']).encode()).hexdigest()[:16]
        split_frontage_buckets(buckets,option['allowed'],option['owners'])
        evidence[identifier]={'geometry':option['cut']}
        counts=[len(c['members']) for c in option['children']]
        if not hasattr(geography,'access_separations'):geography.access_separations=[]
        geography.access_separations.append([set(c['members']) for c in option['children']])
        ledger.append({'id':identifier,'name':f.get('name','Mapped access division'),'category':'natural_area_split','rank':4,
            'state':'CHOSEN','stage':'road connectivity','chosen_for_split':True,'source_ids':[f['id']],'counts':counts,
            'reason':'Separate mapped road populations; preferred minimum does not justify joining disconnected service areas.'})
        audit['changes'].append({'source_member':min(members),'addresses':len(members),'counts':counts,'boundary':f.get('name',''),'source_id':f['id']})
        output.extend({**region,**c,'links':[],'boundaries':region.get('boundaries',[])+[identifier],
            'access_separated':True} for c in option['children'])
    return output,audit


def trim_empty_major_lobes(regions,points,parcels,geography):
    """Remove substantial unserved tails beyond a complete major divider.

    The service universe is unchanged. No hull, parcel mesh or fabricated edge
    is used; unrelated small road-space slivers are deliberately retained.
    """
    output=[];audit=[]
    for region in regions:
        geometry=region['geometry'];members=region['members']
        if geometry.geom_type!='Polygon':output.append(region);continue
        removed=[]
        features=geography.nearby_features(geometry,{'railway','waterway','controlled_road','high_speed_road'})
        for f in sorted(features,key=lambda v:v['id']):
            try:parts=subdivide(geometry,[complete(divider_line(f),geometry,geography)])
            except ValueError:continue
            empty=[p for p in parts if p.area>=10000 and min(p.distance(points[i]) for i in members)>40]
            if not empty:continue
            removed_geometry=unary_union(empty)
            if any(removed_geometry.intersection(p['geometry']).area>1 for p in parcels.values() if p['geometry'].intersects(removed_geometry)):continue
            kept=geometry.difference(removed_geometry)
            if kept.geom_type!='Polygon' or not kept.is_valid or any(kept.distance(points[i])>.002 for i in members):continue
            removed.append({'source_id':f['id'],'category':f['category'],'area_m2':round(removed_geometry.area,2)})
            geometry=kept
        if removed:audit.append({'source_member':min(members),'addresses':len(members),'removed':removed})
        output.append({**region,'geometry':geometry})
    return output,audit
