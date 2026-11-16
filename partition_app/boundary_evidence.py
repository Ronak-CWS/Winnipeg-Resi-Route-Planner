"""Physical boundary preferences shared by partitioning and truck affinity."""
from shapely.ops import unary_union
from .geography import divider_line,polygon_parts

MAJOR={'railway','waterway','water_area','controlled_road','high_speed_road'}
LAND={'park','recreation','mapped_open_land','landuse'}


def register_services(geography,points):
    from shapely.strtree import STRtree
    geography.boundary_service_tree=STRtree(points)
    geography.boundary_land_parcels=None
    geography.boundary_land_completions={}


def land_features(geometry,geography):
    """Use corroborated, unserviced cadastral grounds around mapped land use."""
    result=[f for f in geography.nearby_features(geometry,LAND) if land_gap(f)]
    if not hasattr(geography,'boundary_service_tree') or not hasattr(geography,'parcel_tree'):return result
    if getattr(geography,'boundary_land_parcels',None) is None:
        derived={}
        for f in getattr(geography,'features',[]):
            if not land_gap(f):continue
            tags=f.get('tags',{})
            if tags.get('amenity') not in {'school','college','university'} and tags.get('landuse') not in {'commercial','retail','industrial','education','institutional'}:continue
            for j in geography.parcel_tree.query(f['geometry'],predicate='intersects'):
                parcel=geography.parcels[int(j)]
                for component,g in enumerate(polygon_parts(parcel['geometry'])):
                    overlap=g.intersection(f['geometry']).area
                    if overlap<f['geometry'].area*.8 or overlap<g.area*.25:continue
                    if len(geography.boundary_service_tree.query(g,predicate='intersects')):continue
                    key=(parcel['id'],component)
                    derived[key]={'id':'landuse-parcel-'+parcel['id']+'-'+str(component),'category':f['category'],
                        'name':f.get('name',''),'geometry':g,'tags':tags,'source_ids':[f['id'],parcel['id']],
                        'evidence':'Mapped non-residential use corroborates the complete unserviced City parcel component'}
        geography.boundary_land_parcels=list(derived.values())
    result.extend(f for f in geography.boundary_land_parcels if f['geometry'].intersects(geometry))
    return result


def land_gap(feature):
    if feature['category'] not in LAND or feature['geometry'].geom_type not in {'Polygon','MultiPolygon'}:
        return False
    if feature['geometry'].area<1000:return False
    tags=feature.get('tags',{})
    if feature['category']=='landuse':
        return tags.get('landuse') in {'commercial','retail','industrial','education','institutional'} or tags.get('amenity') in {'school','college','university'}
    return True


def prepare(geometry,geography):
    """Build local masks once when scoring many edges in the same footprint."""
    search=geometry.buffer(16)
    features=geography.nearby_features(search,MAJOR|LAND|{'wide_road','municipal_corridor','broad_corridor','community'})
    features+=land_features(search,geography)
    features.extend(f for f in getattr(geography,'boundary_land_completions',{}).values() if f['geometry'].intersects(search))
    tiers=[('major',1.,[f for f in features if f['category'] in MAJOR]),
           ('landuse',.85,[f for f in features if land_gap(f) or f['category']=='landuse_completion']),
           ('wide_road',.55,[f for f in features if f['category']=='wide_road']),
           ('supported_corridor',.45,[f for f in features if f['category'] in {'municipal_corridor','broad_corridor'}]),
           ('municipal',.25,[f for f in features if f['category']=='community'])]
    base=getattr(geography,'base_roads',geography.roads)
    from shapely.strtree import STRtree
    if getattr(geography,'boundary_road_source',None) is not base:
        geography.boundary_road_source=base;geography.boundary_road_tree=STRtree([r['geometry'] for r in base])
    roads=[base[int(j)]['geometry'].intersection(search) for j in geography.boundary_road_tree.query(search,predicate='intersects')]
    road_mask=unary_union(roads).buffer(8)
    prepared=[]
    for label,strength,items in tiers:
        sources=[dict(f,_boundary_line=divider_line(f)) for f in items]
        mask=unary_union([f['_boundary_line'].intersection(search) for f in sources]).buffer(8)
        prepared.append((label,strength,mask,sources))
    return prepared+[('ordinary_road',.2,road_mask,[])]


def profile(seam,geography,prepared=None):
    """Measure the strongest mapped support at each point without double count."""
    if seam.is_empty or seam.length<1e-6:
        return {'strength':0.,'preference_cost':0.,'major_m':0.,'landuse_m':0.,'ordinary_road_m':0.}
    remaining=seam;weighted=0.;lengths={};support_ids=set()
    for label,strength,mask,items in (prepared if prepared is not None else prepare(seam,geography)):
        supported=remaining.intersection(mask);lengths[label+'_m']=round(supported.length,3)
        if supported.length:
            weighted+=strength*supported.length
            support_ids.update(f['id'] for f in items
                if (f['_boundary_line'] if '_boundary_line' in f else divider_line(f)).distance(supported)<8.01)
            remaining=remaining.difference(mask)
    return {**lengths,'strength':round(weighted/seam.length,6),
        'preference_cost':round(12*(seam.length-weighted)/1000,6),
        'source_ids':sorted(support_ids)}
