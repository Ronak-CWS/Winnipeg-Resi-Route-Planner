"""Hand-drawn site-access cases, independent of Winnipeg example names."""
import pytest

from partition_app.geography import REVERSE
from routing_app.roads import make_groups
from routing_app.optimizer import fleet_cover,cohesive_candidates,reunion_exchanges


def xy(x, y):
    return list(REVERSE.transform(630000 + x, 5520000 + y))


def road(ident, points, nodes, name='', **tags):
    return {'id': ident, 'coords': [xy(*p) for p in points], 'nodes': nodes,
            'name': name, 'tags': {'highway': 'service', **tags}}


def point(ident, x, y):
    lon, lat = xy(x, y)
    return {'id': ident, 'address': '100 Example Street Unit ' + ident,
            'section': 'A', 'lon': lon, 'lat': lat}


def site():
    # Postal road east-west at y=0; an internal dead-end extends north.
    return {'roads': [
        road('main-west', [(-100, 0), (0, 0)], [1, 2], 'Example Street', highway='residential'),
        road('main-east', [(0, 0), (100, 0)], [2, 3], 'Example Street', highway='residential'),
        road('internal', [(0, 0), (0, 200)], [2, 4], service='driveway'),
    ]}


def test_internal_curbs_need_two_opposite_passes_and_preserve_unit_ids():
    points = [point('east', 15, 150), point('west', -15, 150), point('unit', 15, 150)]
    groups, anchors, reviews = make_groups({'points': points}, site())
    assert {a['road_id'] for a in anchors.values()} == {'internal'}
    assert anchors['east']['direction'] == 1  # northbound: east curb is right
    assert anchors['west']['direction'] == -1  # return southbound: west curb is right
    assert len(groups) == 2 and sum(g['count'] for g in groups) == 3
    assert anchors['east']['coordinate'] == anchors['unit']['coordinate']
    assert anchors['east']['original'] == xy(15, 150)
    assert all(a['setback_m'] == pytest.approx(15, abs=.02) for a in anchors.values())
    assert not reviews


@pytest.mark.parametrize('restriction', [
    {'access': 'private'}, {'access': 'no'}, {'motor_vehicle': 'private'},
    {'motor_vehicle': 'no'}, {'construction': 'yes'},
    {'service': 'alley'}, {'service': 'drive-through'},
])
def test_restricted_roads_and_alleys_are_not_invented_as_curb_access(restriction):
    inventory = site()
    inventory['roads'][-1]['tags'].update(restriction)
    _, anchors, _ = make_groups({'points': [point('east', 15, 150)]}, inventory)
    assert anchors['east']['road_id'].startswith('main-')
    assert 'property_setback_over_80m' in anchors['east']['review']


def test_geometric_crossing_without_shared_node_is_not_an_entrance():
    inventory = site()
    inventory['roads'][-1]['nodes'] = [99, 4]
    _, anchors, _ = make_groups({'points': [point('east', 15, 150)]}, inventory)
    assert anchors['east']['road_id'].startswith('main-')


def test_internal_path_can_cross_multiple_real_service_edges():
    inventory = site()
    inventory['roads'][-1] = road('entrance', [(0, 0), (0, 70)], [2, 5])
    inventory['roads'].append(road('internal', [(0, 70), (0, 200)], [5, 4], service='driveway'))
    _, anchors, _ = make_groups({'points': [point('east', 15, 150)]}, inventory)
    assert anchors['east']['road_id'] == 'internal'


def test_close_normal_frontage_keeps_its_named_street():
    _, anchors, _ = make_groups({'points': [point('corner', 5, 20)]}, site())
    assert anchors['corner']['road_id'].startswith('main-')


def test_two_interior_units_support_same_site_access_for_an_entrance_unit():
    points = [point('one', 15, 100), point('two', 15, 150), point('entrance', 23, 30)]
    _, anchors, _ = make_groups({'points': points}, site())
    assert {a['road_id'] for a in anchors.values()} == {'internal'}


def test_colocated_unit_ids_are_not_two_distinct_site_evidence_points():
    points = [point('one', 15, 100), point('two', 15, 100), point('entrance', 15, 35)]
    _, anchors, _ = make_groups({'points': points}, site())
    assert anchors['entrance']['road_id'].startswith('main-')


def test_internal_access_does_not_jump_across_a_public_street():
    inventory = site()
    inventory['roads'].append(road('divider', [(7, 50), (7, 200)], [50, 51],
                                   'Other Street', highway='residential'))
    _, anchors, _ = make_groups({'points': [point('east', 15, 150)]}, inventory)
    assert anchors['east']['road_id'].startswith('main-')


def test_oneway_access_never_claims_the_opposite_curb_is_proven():
    inventory = site()
    inventory['roads'][-1]['tags']['oneway'] = 'yes'
    _, anchors, _ = make_groups({'points': [point('west', -15, 150)]}, inventory)
    assert anchors['west']['road_id'] == 'internal'
    assert anchors['west']['direction'] == 1
    assert 'oneway_opposite_curb_requires_review' in anchors['west']['review']


def test_whole_parent_exchange_beats_a_slightly_shorter_split_with_same_trucks():
    def candidate(sections, seconds, late=0):
        return {'sections':sections,'plan':{'late_seconds':late,'early_seconds':0,
            'overtime_seconds':0,'paid_seconds':seconds,'seconds':seconds}}
    split=[candidate(['north','south-a'],100), candidate(['south-b','pocket'],100)]
    whole=[candidate(['north','pocket'],110), candidate(['south-a','south-b'],110)]
    ids=['north','south-a','south-b','pocket']
    parents={'north':'N','south-a':'S','south-b':'S','pocket':'P'}
    chosen,_=fleet_cover(ids,split+whole,5,parent_sections=parents)
    assert chosen==whole
    # Whole-section preference cannot justify violating the return deadline.
    whole[0]['plan']['late_seconds']=1
    chosen,_=fleet_cover(ids,split+whole,5,parent_sections=parents)
    assert chosen==split


def test_preserving_a_parent_does_not_purchase_an_additional_truck():
    def candidate(sections):
        return {'sections':sections,'plan':{'late_seconds':0,'early_seconds':0,
            'overtime_seconds':0,'paid_seconds':100,'seconds':100}}
    two=[candidate(['a1','b']),candidate(['a2','c'])]
    three=[candidate(['a1','a2']),candidate(['b']),candidate(['c'])]
    chosen,_=fleet_cover(['a1','a2','b','c'],two+three,5,
        parent_sections={'a1':'a','a2':'a','b':'b','c':'c'})
    assert chosen==two


def test_whole_parent_plus_neighbour_is_explicitly_retained():
    graph={'a1':{'a2'},'a2':{'a1','b'},'b':{'a2'}}
    options=cohesive_candidates(list(graph),graph,{'a1':'a','a2':'a','b':'b'},dict.fromkeys(graph,100),350)
    assert frozenset({'a1','a2','b'}) in options


def test_reunion_exchange_checks_both_resulting_territories():
    graph={'a1':{'a2','c'},'a2':{'a1','b'},'b':{'a2','c'},'c':{'a1','b'}}
    parents={'a1':'a','a2':'a','b':'b','c':'c'};counts=dict.fromkeys(graph,100)
    chosen=[{'sections':['a1','c']},{'sections':['a2','b']}]
    proposed=reunion_exchanges(chosen,graph,parents,counts,250)
    assert frozenset({'a1','a2'}) in proposed and frozenset({'b','c'}) in proposed
    graph['b'].remove('c');graph['c'].remove('b')
    assert not reunion_exchanges(chosen,graph,parents,counts,250)


def test_unmet_return_window_does_not_reward_a_longer_unproductive_trip():
    def candidate(seconds,early):
        return {'sections':['a'],'plan':{'late_seconds':0,'early_seconds':early,
            'overtime_seconds':0,'paid_seconds':seconds,'seconds':seconds}}
    short=candidate(100,20);longer=candidate(110,10)
    chosen,stages=fleet_cover(['a'],[short,longer],5)
    assert chosen==[short] and stages[0]=='RETURN_WINDOW_INFEASIBLE'
    meets=candidate(120,0)
    chosen,_=fleet_cover(['a'],[short,longer,meets],5)
    assert chosen==[meets]
