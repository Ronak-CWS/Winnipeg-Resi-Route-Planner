from types import SimpleNamespace
from shapely.geometry import Point,box,LineString
from shapely.strtree import STRtree
from partition_app.pockets import separate_sparse_pockets,consolidate_sparse_pockets


def fixture(rail=False):
    points=[Point(100+i,900) for i in range(120)]+[Point(110,100),Point(120,100),Point(130,100),Point(110,-50)]
    regions=[{'geometry':box(0,0,500,1000),'members':set(range(123)),'parents':{'one'},'boundaries':[],'links':[]},
        {'geometry':box(0,-200,500,0),'members':{123},'parents':{'two'},'boundaries':[],'links':[]}]
    features=[{'id':'municipal-finite','name':'Test','category':'community','geometry':box(0,0,500,300)}]
    if rail:features.append({'id':'rail','category':'railway','geometry':LineString([(-10,0),(510,0)])})
    geo=SimpleNamespace(roads=[],base_roads=[],features=features,
        nearby_features=lambda g,c:[f for f in features if f['category'] in c and f['geometry'].intersects(g)])
    return points,regions,geo


def test_hidden_sparse_pocket_joins_nearer_compatible_neighbour():
    points,regions,geo=fixture()
    split,audit=separate_sparse_pockets(regions,points,{}, {},geo)
    assert len(audit['changes'])==1 and audit['changes'][0]['addresses']==3
    merged,review=consolidate_sparse_pockets(split,points,geo)
    assert sorted(len(r['members']) for r in merged)==[4,120]
    assert set.union(*(r['members'] for r in merged))==set(range(124))
    assert sum(r['geometry'].area for r in merged)==600000
    assert review[0]['status']=='MERGED_NEAREST_COMPATIBLE'


def test_sparse_pocket_never_overrides_rail_or_same_street_protection():
    points,regions,geo=fixture(True)
    split,_=separate_sparse_pockets(regions,points,{}, {},geo)
    kept,review=consolidate_sparse_pockets(split,points,geo)
    assert sorted(len(r['members']) for r in kept)==[1,3,120]
    assert review[0]['status']=='IMPORTANT_BOUNDARY'
    protected,audit=separate_sparse_pockets(regions,points,{('ordinary segment','same-road'):[0,120]}, {},geo)
    assert not audit['changes'] and len(protected)==2


def test_touching_empty_polygons_do_not_make_services_nearby():
    from partition_app.engine import small_area_exception
    points,regions,geo=fixture()
    occupied={i:r['geometry'] for i,r in enumerate(regions)}
    counts={0:120,1:3}
    remote={0:[Point(200,900)],1:[Point(200,-100)]}
    status,_=small_area_exception(1,occupied,counts,geo,1100,remote[1],remote)
    assert status=='REMOTE'
    near={0:[Point(200,100)],1:[Point(200,-100)]}
    status,_=small_area_exception(1,occupied,counts,geo,1100,near[1],near)
    assert status=='NEEDS_REVIEW'


def test_pocket_stays_with_owner_when_other_services_are_farther():
    points,regions,geo=fixture()
    points[-1]=Point(110,-1100)
    regions[-1]['geometry']=box(0,-1200,500,0)
    result,audit=separate_sparse_pockets(regions,points,{}, {},geo)
    assert not audit['changes'] and len(result)==2
