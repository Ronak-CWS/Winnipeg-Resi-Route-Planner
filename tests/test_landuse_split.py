from types import SimpleNamespace
from shapely.geometry import box,Point,LineString
from shapely.strtree import STRtree
from partition_app.landuse_split import between_completions
from partition_app.balancing import rebalance
from partition_app.alternatives import divide


def geography(features=(),parcels=(),roads=()):
    g=SimpleNamespace(features=list(features),parcels=list(parcels),roads=list(roads))
    g.base_roads=g.roads;g.road_tree=STRtree([r['geometry'] for r in roads])
    g.parcel_tree=STRtree([p['geometry'] for p in parcels])
    g.nearby_features=lambda geometry,categories:[f for f in g.features if f['category'] in categories and f['geometry'].intersects(geometry)]
    return g


def test_complete_park_corridor_can_split_1400_into_600_and_800_below_a_soft_900_minimum():
    points=[Point(100+(i%30)*20,100+(i//30)*20) for i in range(600)]
    points += [Point(1100+(i%40)*20,50+(i//40)*40) for i in range(800)]
    park={'id':'mapped-grounds','category':'park','name':'Grounds','geometry':box(980,0,1020,1000)}
    g=geography([park]);g.boundary_service_tree=STRtree(points)
    preferences={'preferred_minimum':900,'maximum_addresses':1100}
    result,audit=rebalance({0:box(0,0,2000,1000)},{0:set(range(1400))},{},points,{}, {},g,
        preferences,[],lambda *args:None,{})
    assert sorted(len(r['members']) for r in result)==[600,800]
    assert set().union(*(r['members'] for r in result))==set(range(1400))
    assert sum(r['geometry'].area for r in result)==2_000_000
    assert audit['splits']==1


def test_an_empty_road_gap_can_join_mapped_vertices_but_a_property_interior_cannot():
    parent=box(0,0,200,200);left=box(10,0,80,40);right=box(10,60,80,110)
    road={'id':'public-road','name':'Road','type':'STREET','geometry':LineString([(0,50),(200,50)])}
    assert between_completions(parent,left,right,geography(roads=[road]))
    parcel={'id':'property','geometry':box(0,40,90,60)}
    assert not between_completions(parent,left,right,geography(parcels=[parcel],roads=[road]))


def test_public_park_outline_cannot_slice_a_serviced_residential_property():
    points=[Point(100+(i%30)*20,100+(i//30)*20) for i in range(600)]
    points += [Point(1100+(i%40)*20,50+(i//40)*40) for i in range(800)]
    points.append(Point(1030,420))
    parcel={'id':'residential','geometry':box(1010,400,1050,440)}
    park={'id':'imprecise-public-park','category':'park','name':'Grounds','geometry':box(980,0,1020,1000)}
    g=geography([park],[parcel]);g.boundary_service_tree=STRtree(points)
    result,audit=rebalance({0:box(0,0,2000,1000)},{0:set(range(len(points)))},{},points,{},
        {'residential':parcel},g,{'preferred_minimum':900,'maximum_addresses':1100},[],lambda *a:None,{})
    assert sorted(len(r['members']) for r in result)==[600,801]
    assert sum(parcel['geometry'].intersection(r['geometry']).area>4 for r in result)==1
    assert audit['splits']==1


def test_a_supported_park_gap_can_split_an_over_broad_road_group_without_a_street_cut():
    road={'id':'street','name':'Example St','type':'STREET','geometry':LineString([(0,500),(1000,500)])}
    park={'id':'greenway','category':'park','geometry':box(480,0,520,1000)}
    points=[Point(100,480),Point(200,520),Point(800,480),Point(900,520)]
    g=geography([park],roads=[road]);g.boundary_service_tree=STRtree(points)
    buckets={('ordinary segment','street'):[0,1,2,3]}
    option,report=divide(box(0,0,1000,1000),set(range(4)),[LineString([(480,0),(480,1000)])],points,buckets,{},g)
    assert option is not None,report
    assert not option['quality']['street_breaks'] and not option['quality']['alley_side_splits']
    assert sorted(len(c['members']) for c in option['children'])==[2,2]
    blocked=dict(buckets);blocked['site','shared']=[0,2]
    assert divide(box(0,0,1000,1000),set(range(4)),[LineString([(480,0),(480,1000)])],points,blocked,{},g)[0] is None


def test_a_long_stepped_road_is_not_worth_splitting_only_to_hit_the_count_target():
    points=[Point(100+(i%30)*10,100+(i//30)*100) for i in range(600)]
    points += [Point(1600+(i%20)*10,100+(i//20)*80) for i in range(800)]
    road={'id':'stepped','name':'Winding St','type':'STREET',
        'geometry':LineString([(1000,0),(1000,800),(1400,800),(1400,1600),(600,1600),(600,2400),(1000,2400),(1000,4000)])}
    g=geography(roads=[road]);g.boundary_service_tree=STRtree(points)
    result,audit=rebalance({0:box(0,0,2000,4000)},{0:set(range(1400))},{},points,{}, {},g,
        {'preferred_minimum':900,'maximum_addresses':1100},[],lambda *a:None,{})
    assert [len(r['members']) for r in result]==[1400]
    assert audit['splits']==0


def test_a_park_split_cannot_strand_a_population_that_needs_the_other_childs_roads():
    from partition_app.access import RoadAccess,prepare
    from partition_app.geography import REVERSE
    points=[Point(100+(i%35)*20,200+i//35) for i in range(350)]
    points += [Point(100+(i%35)*20,800+i//35) for i in range(350)]
    points += [Point(1500+(i%7-3)*2,220+(i//7)*5) for i in range(700)]
    lines=[LineString([(100,200),(1500,200)]),LineString([(100,800),(1500,800)]),LineString([(1500,200),(1500,800)])]
    names=['North St','South St','East St'];nodes=[(1,2),(3,4),(2,4)]
    roads=[{'id':str(i),'name':names[i],'type':'STREET','geometry':line} for i,line in enumerate(lines)]
    park={'id':'park','category':'park','geometry':box(980,0,1020,1000)}
    g=geography([park],roads=roads);g.boundary_service_tree=STRtree(points)
    g.access_network=RoadAccess([{'id':i,'name':names[i],'nodes':nodes[i],
        'coords':[REVERSE.transform(*xy) for xy in line.coords],'tags':{'highway':'residential'}} for i,line in enumerate(lines)])
    rows=[{'address':f'{i+1} '+names[0 if i<350 else 1 if i<700 else 2]} for i in range(1400)]
    prepare(g,rows)
    result,audit=rebalance({0:box(0,0,2000,1000)},{0:set(range(1400))},{},points,{}, {},g,
        {'preferred_minimum':900,'maximum_addresses':1100},[],lambda *a:None,{})
    assert [len(r['members']) for r in result]==[1400]
    assert audit['rejections']['would strand a service population outside its internal road network']>0
