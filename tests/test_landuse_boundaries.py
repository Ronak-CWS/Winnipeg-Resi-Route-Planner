from types import SimpleNamespace
from shapely.geometry import box,LineString,Point
from shapely.strtree import STRtree
from shapely.ops import unary_union
from partition_app.boundary_evidence import profile,register_services,land_features
from partition_app.landuse_candidates import candidates,road_space_completions
from partition_app.geography import Geography
from routing_app.boundary_affinity import separation_cost,weights
from routing_app.optimizer import fleet_cover
import pytest


def geography(features=(),parcels=(),roads=()):
    g=SimpleNamespace(features=list(features),parcels=list(parcels),roads=list(roads))
    g.base_roads=g.roads;g.parcel_tree=STRtree([p['geometry'] for p in parcels]);g.road_tree=STRtree([r['geometry'] for r in roads])
    g.nearby_features=lambda shape,categories:[f for f in g.features if f['category'] in categories and f['geometry'].intersects(shape)]
    g.refine_frontage_cells=Geography.refine_frontage_cells.__get__(g)
    return g


def test_school_and_commercial_edges_outrank_ordinary_roads_below_major_barriers():
    road=LineString([(0,0),(0,200)])
    g=geography(roads=[{'id':'road','geometry':road,'name':'Local','type':'STREET'}])
    ordinary=profile(road,g)['preference_cost']
    for category,tags in [('recreation',{'amenity':'school'}),('landuse',{'landuse':'retail'})]:
        g.features=[{'id':'grounds','category':category,'tags':tags,'geometry':box(-80,0,0,200)}]
        grounds=profile(road,g)['preference_cost']
        assert grounds<ordinary/3
        g.features.append({'id':'major','category':'high_speed_road','geometry':road})
        assert profile(road,g)['preference_cost']<grounds


def test_school_parcel_extension_requires_no_service_points():
    school={'id':'school','category':'recreation','tags':{'amenity':'school'},'geometry':box(0,0,50,50)}
    parcel={'id':'land','geometry':box(0,0,60,60)};g=geography([school],[parcel])
    register_services(g,[Point(100,100)])
    assert any(f['id'].startswith('landuse-parcel-') for f in land_features(box(-1,-1,61,61),g))
    register_services(g,[Point(55,55)])
    assert not any(f['id'].startswith('landuse-parcel-') for f in land_features(box(-1,-1,61,61),g))


def test_road_space_completion_cannot_cross_a_private_property():
    grounds={'id':'park','category':'park','geometry':box(50,20,100,70)}
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(0,0),(200,0)])}
    g=geography([grounds],[],[road]);parent=box(0,0,200,200)
    assert road_space_completions(parent,[grounds],g)
    g.parcels=[{'id':'private','geometry':box(0,1,200,19)}];g.parcel_tree=STRtree([g.parcels[0]['geometry']])
    assert not road_space_completions(parent,[grounds],g)


def test_road_space_completion_cannot_follow_a_serviced_property_side():
    grounds={'id':'park','category':'park','geometry':box(50,20,100,70)}
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(0,0),(200,0)])}
    # Both geometrically empty side lines border occupied parcels. They are
    # not evidence for a safe road-space connection between neighbouring homes.
    parcels=[{'id':'a','geometry':box(50.01,1,75,19)}, {'id':'b','geometry':box(75,1,99.99,19)}]
    g=geography([grounds],parcels,[road]);register_services(g,[Point(60,10),Point(90,10)])
    assert not road_space_completions(box(0,0,200,200),[grounds],g)


def test_street_cut_at_nearly_coincident_endpoint_is_not_lost():
    from partition_app.continuity import assess,BREAK_PENALTY
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(-100,0),(100,0)])}
    g=geography(roads=[road]);points=[Point(-20,20),Point(20,20)]
    q=assess(LineString([(0,.00000001),(0,100)]),{0:0,1:1},points,{('ordinary segment','road'):[0,1]},g)
    assert len(q['street_breaks'])==1 and q['penalty']>=BREAK_PENALTY


def test_road_following_junction_does_not_compare_opposite_curbs():
    from partition_app.continuity import assess,BREAK_PENALTY
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(-150,0),(150,0)])}
    g=geography(roads=[road]);seam=LineString([(-100,0),(0,0)])
    points=[Point(-20,20),Point(20,-20),Point(30,20),Point(-30,-20)]
    buckets={('ordinary segment','road'):[0,1,2,3]}
    clean=assess(seam,{0:1,1:0,2:1,3:0},points,buckets,g)
    assert not clean['street_breaks']
    broken=assess(seam,{0:1,1:0,2:0,3:0},points,buckets,g)
    assert len(broken['street_breaks'])==1 and broken['penalty']>=BREAK_PENALTY


@pytest.mark.parametrize('road_category',['ordinary','wide_road'])
def test_school_frontage_proposal_preserves_complete_parcels_and_source_coverage(road_category):
    park={'id':'park','category':'park','geometry':box(0,0,60,200)}
    parcels=[{'id':str(i),'geometry':g} for i,g in enumerate([box(0,0,60,200),box(60,0,100,200),box(100,0,140,200),box(140,0,200,200),box(0,200,100,400),box(100,200,200,400)])]
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(100,0),(100,400)])}
    g=geography([park],parcels,[road]);points=[Point(10,300),Point(80,100),Point(120,100),Point(180,300)]
    if road_category!='ordinary':g.features.append({**road,'category':road_category})
    left={'geometry':box(0,0,100,400),'members':{0,1}};right={'geometry':box(100,0,200,400),'members':{2,3}}
    buckets={('parcel','1'):[1],('parcel','2'):[2],('parcel','4'):[0],('parcel','5'):[3]}
    choices=candidates(left,right,points,buckets,{i:parcels[i] for i in [1,2,4,5]},g)
    assert any(1 in c['children'][1]['members'] for c in choices)
    for c in choices:
        assert unary_union([v['geometry'] for v in c['children']]).equals(box(0,0,200,400))
        assert set.union(*(v['members'] for v in c['children']))=={0,1,2,3}
        assert c['children'][0]['geometry'].intersection(c['children'][1]['geometry']).area==0


def test_weak_seams_prefer_adjacent_joint_work_without_buying_more_trucks():
    edges=[('a','b',100),('c','d',100)]
    def option(members,cost=100):
        return {'sections':members,'weak_boundary_separation_cost':separation_cost(members,edges),
            'plan':{'late_seconds':0,'early_seconds':0,'overtime_seconds':0,'paid_seconds':cost,'seconds':cost}}
    crossed=[option(['a','c']),option(['b','d'])]
    joined=[option(['a','b'],110),option(['c','d'],110)]
    chosen,_=fleet_cover(['a','b','c','d'],crossed+joined,4)
    assert chosen==joined
    single=option(['a','b','c','d'],500)
    assert fleet_cover(['a','b','c','d'],crossed+joined+[single],4)[0]==[single]
    joined[0]['plan']['late_seconds']=1
    assert fleet_cover(['a','b','c','d'],crossed+joined,4)[0]==crossed
    assert weights({'areas':{'features':[]}}, {}, {})==[]


def test_optional_landuse_repair_preserves_satisfactory_neighbours(monkeypatch):
    from partition_app.landuse_repair import improve
    import partition_app.landuse_candidates as proposals
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(100,0),(100,200)])}
    grounds=[{'id':'school','category':'park','geometry':box(0,0,60,200)},
             {'id':'open-ground','category':'park','geometry':box(60,0,80,200)}]
    g=geography(grounds,roads=[road]);g.neighbourhoods=[]
    points=[Point(20,50)]*800+[Point(70,50)]*200+[Point(90,50)]*20+[Point(150,50)]*903
    regions=[{'geometry':box(0,0,100,200),'members':set(range(1020)),'parents':{'left'},'boundaries':[]},
             {'geometry':box(100,0,200,200),'members':set(range(1020,1923)),'parents':{'right'},'boundaries':[]}]
    def choices(left,right,*_):
        if len(left['members'])!=1020:return []
        result=[]
        for x,n in [(60,800),(80,1000)]:
            result.append({'children':[{'geometry':box(0,0,x,200),'members':set(range(n))},
                {'geometry':box(x,0,200,200),'members':set(range(n,1923))}],
                'geometry':LineString([(x,0),(x,200)]),'flexible_groups':set(),
                'source_ids':['school'],'strength':{},'road_space_completions':[]})
        return result
    monkeypatch.setattr(proposals,'candidates',choices)
    revised,audit=improve(regions,points,{}, {},g,900,1100,[],{},lambda *_:None)
    assert [len(r['members']) for r in revised]==[1000,923]
    assert any(r['counts']==[800,1123] and 'satisfactory' in r['reason'] for r in audit['rejections'])


@pytest.mark.parametrize('coverage_failure',[True,False])
def test_optional_comparison_keeps_valid_areas_when_subdivision_loses_coverage(monkeypatch,coverage_failure):
    from partition_app.landuse_repair import improve
    from partition_app.geography import SubdivisionCoverageError
    import partition_app.landuse_candidates as proposals
    road={'id':'road','name':'Local','type':'STREET','geometry':LineString([(100,0),(100,200)])}
    park={'id':'park','category':'park','geometry':box(0,0,60,200)}
    g=geography([park],roads=[road]);g.neighbourhoods=[]
    regions=[{'geometry':box(0,0,100,200),'members':{0}},
             {'geometry':box(100,0,200,200),'members':{1}}]
    def invalid_proposal(*args):
        if coverage_failure:raise SubdivisionCoverageError('18.373 m2 lost')
        raise ValueError('Unrelated invalid input')
    monkeypatch.setattr(proposals,'candidates',invalid_proposal)
    if not coverage_failure:
        with pytest.raises(ValueError,match='Unrelated invalid input'):
            improve(regions,[Point(20,50),Point(150,50)],{},{},g,900,1100,[],{},lambda *_:None)
        return
    revised,audit=improve(regions,[Point(20,50),Point(150,50)],{},{},g,900,1100,[],{},lambda *_:None)
    assert revised==regions
    assert audit['changes']==[]
    assert audit['rejections']==[{'reason':'Candidate subdivision does not preserve coverage',
                                 'detail':'18.373 m2 lost','counts':[1,1]}]
    assert unary_union([r['geometry'] for r in revised]).equals(box(0,0,200,200))
