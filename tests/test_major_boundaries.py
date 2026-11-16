from shapely.geometry import LineString, MultiPolygon, Point, box
from shapely.ops import unary_union

from partition_app.geography import serviced_parcel_component
from partition_app.major_boundaries import separate


class PhysicalGeography:
    features=[{'id':'mapped-arterial','category':'high_speed_road',
        'geometry':LineString([(50,-10),(50,110)])}]

    def nearby_features(self,geometry,categories):
        return [f for f in self.features if f['category'] in categories and f['geometry'].intersects(geometry)]


def test_disconnected_cadastral_land_does_not_join_service_banks():
    parcel={'id':'cadastre','geometry':MultiPolygon([box(5,5,20,20),box(70,70,90,90)])}
    first,left=serviced_parcel_component(parcel,Point(10,10))
    second,right=serviced_parcel_component(parcel,Point(80,80))
    assert first!=second
    assert left['geometry'].equals(box(5,5,20,20))
    assert right['geometry'].equals(box(70,70,90,90))
    assert left['id']==right['id']=='cadastre'
    assert left['source_component_count']==2


def test_major_divider_separates_populated_banks_with_complete_coverage():
    parent=box(0,0,100,100);points=[Point(20,20),Point(80,20)]
    regions,audit=separate([{'geometry':parent,'members':{0,1},'links':[]}],points,{}, {},PhysicalGeography())
    assert audit['splits'][0]['counts']==[1,1] and not audit['rejected']
    assert unary_union([r['geometry'] for r in regions]).equals(parent)
    assert regions[0]['geometry'].intersection(regions[1]['geometry']).area==0
    assert all(r['geometry'].covers(points[next(iter(r['members']))]) for r in regions)


def test_real_shared_site_cannot_be_silently_split_for_major_road():
    parent=box(0,0,100,100)
    regions,audit=separate([{'geometry':parent,'members':{0,1},'links':[]}],
        [Point(20,20),Point(80,20)],{('site','shared'):[0,1]}, {},PhysicalGeography())
    assert len(regions)==1 and not audit['splits']
    assert 'mandatory service group' in audit['rejected'][0]['reason']


def test_whole_local_parcel_is_kept_without_merging_populated_banks():
    parent=box(0,0,100,100);points=[Point(45,45),Point(80,80)]
    parcel={'id':'local-parcel','geometry':box(40,40,60,60)}
    regions,audit=separate([{'geometry':parent,'members':{0,1},'links':[]}],
        points,{}, {0:parcel},PhysicalGeography())
    assert len(regions)==2 and not audit['rejected']
    owner=next(r for r in regions if 0 in r['members'])
    assert owner['geometry'].covers(parcel['geometry'])
    assert unary_union([r['geometry'] for r in regions]).equals(parent)
