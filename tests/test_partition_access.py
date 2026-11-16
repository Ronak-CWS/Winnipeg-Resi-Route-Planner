from types import SimpleNamespace
from shapely.geometry import Point,LineString,box
from shapely.strtree import STRtree
from partition_app.geography import REVERSE
from partition_app.access import RoadAccess
from partition_app.access_refinement import trim_empty_major_lobes


def test_an_access_division_cannot_be_undone_by_later_neighbour_merges():
    from partition_app.access import respects_separations
    geo=SimpleNamespace(access_separations=[[{1,2},{3,4}]])
    assert respects_separations([{'members':{1,2,5}},{'members':{3,4,6}}],geo)
    assert not respects_separations([{'members':{1,2,3,4,5,6}}],geo)


def road(identity,nodes,coords,name='Test St',**tags):
    return {'id':identity,'nodes':nodes,'coords':[REVERSE.transform(*p) for p in coords],
        'name':name,'tags':{'highway':'residential',**tags}}


def test_touching_polygons_need_an_actual_shared_road_node():
    pts=[Point(10,20),Point(90,20)];rows=[{'address':'10 West St'},{'address':'90 East St'}]
    left={'geometry':box(0,0,50,40),'members':{0}};right={'geometry':box(50,0,100,40),'members':{1}}
    disconnected=RoadAccess([road(1,[1,2],[(0,20),(50,20)],'West St'),road(2,[3,4],[(50,20),(100,20)],'East St')])
    assert not disconnected.connected(left,right,pts,rows)
    connected=RoadAccess([road(1,[1,2],[(0,20),(50,20)],'West St'),road(2,[2,4],[(50,20),(100,20)],'East St')])
    assert connected.connected(left,right,pts,rows)


def test_long_road_is_clipped_without_losing_its_local_access():
    network=RoadAccess([road(1,[1,2],[(-500,20),(500,20)])])
    pts=[Point(20,20),Point(80,20)];rows=[{'address':'20 Test St'},{'address':'80 Test St'}]
    result=network.components(box(0,0,100,40),{0,1},pts,rows)
    assert result['groups']==[{0,1}] and not result['unknown']


def test_a_partial_shared_population_cannot_justify_merging_disconnected_groups():
    network=RoadAccess([road(1,[1,2],[(0,100),(1000,100)],'Common St'),
        road(2,[3,4],[(0,500),(400,500)],'West St'),road(3,[5,6],[(600,600),(1000,600)],'East St')])
    pts=[Point(x,100) for x in (100,200,300,700,800,900)]+[Point(100,500),Point(200,500),Point(800,600),Point(900,600)]
    rows=[{'address':f'{i+1} Common St'} for i in range(6)]+[{'address':'1 West St'},{'address':'2 West St'},{'address':'1 East St'},{'address':'2 East St'}]
    assert not network.connected({'geometry':box(0,0,500,1000),'members':{0,1,2,6,7}},
        {'geometry':box(500,0,1000,1000),'members':{3,4,5,8,9}},pts,rows)


def test_a_road_detour_outside_the_service_footprint_is_not_internal_access():
    network=RoadAccess([road(1,[1,2],[(10,20),(10,200)],'West St'),
        road(2,[2,3],[(10,200),(90,200)],'North St'),road(3,[3,4],[(90,200),(90,20)],'East St')])
    pts=[Point(10,20),Point(90,20)];rows=[{'address':'10 West St'},{'address':'90 East St'}]
    assert not network.connected({'geometry':box(0,0,50,40),'members':{0}},
        {'geometry':box(50,0,100,40),'members':{1}},pts,rows)


def test_intersection_connector_budget_applies_to_the_whole_path():
    def check(gap):
        inventory=[road(1,[1,2],[(10,0),(10,100)],'West St'),
            road(2,[3,4],[(10+gap,100),(10+gap,0)],'East St')]
        # Two real junction edges; neither edge alone exceeds the budget.
        inventory+=[road(3,[2,5],[(10,100),(10+gap/2,100)],'Cross St',highway='secondary',maxspeed='60'),
            road(4,[5,3],[(10+gap/2,100),(10+gap,100)],'Cross St',highway='secondary',maxspeed='60')]
        network=RoadAccess(inventory);pts=[Point(10,30),Point(10+gap,30)]
        rows=[{'address':'10 West St'},{'address':'10 East St'}]
        return network.connected({'geometry':box(0,0,10+gap/2,110),'members':{0}},
            {'geometry':box(10+gap/2,0,20+gap,110),'members':{1}},pts,rows)
    assert check(40)
    assert not check(90)


def test_crossing_geometries_and_prohibited_roads_do_not_invent_connections():
    network=RoadAccess([road(1,[1,2],[(0,50),(100,50)],'West St'),
        road(2,[3,4],[(50,0),(50,100)],'North St'),
        road(3,[2,4],[(100,50),(50,100)],'Private St',access='private')])
    pts=[Point(10,50),Point(50,90)];rows=[{'address':'10 West St'},{'address':'90 North St'}]
    result=network.components(box(-5,-5,105,105),{0,1},pts,rows)
    assert sorted(map(len,result['groups']))==[1,1]
    assert len(network.roads)==2


def test_only_large_empty_lobes_beyond_a_mapped_major_divider_are_removed():
    rail={'id':'rail','category':'railway','geometry':LineString([(0,300),(500,300)])}
    geo=SimpleNamespace(nearby_features=lambda g,c:[rail])
    region={'geometry':box(0,0,500,500),'members':{0}}
    result,audit=trim_empty_major_lobes([region],[Point(200,100)],{},geo)
    assert audit and result[0]['geometry'].equals(box(0,0,500,300))
    kept,audit=trim_empty_major_lobes([region],[Point(200,100)],{'p':{'geometry':box(100,200,200,400)}},geo)
    assert not audit and kept[0]['geometry'].equals(region['geometry'])


def test_final_empty_face_reconciliation_preserves_serviced_enclaves():
    from partition_app.engine import shared_native_coverage,enclosed_owners
    outer=box(0,0,1000,1000);enclave=box(200,200,400,400);gap=box(600,600,800,800)
    areas,notes=shared_native_coverage({0:outer.difference(enclave).difference(gap),1:enclave})
    assert notes['enclosed_unserved_faces_assigned']==1
    assert areas[0].equals(outer.difference(enclave)) and areas[1].equals(enclave)
    assert areas[0].intersection(areas[1]).area==0
    assert not enclosed_owners(areas[0],list(areas.values()),STRtree(list(areas.values())))[1]
