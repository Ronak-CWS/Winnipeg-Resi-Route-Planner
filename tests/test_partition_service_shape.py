from types import SimpleNamespace
from shapely.geometry import Point
from partition_app.service_shape import cost,enclosure


def test_equal_count_compact_territories_beat_a_wrapping_service_ribbon():
    points=[Point(x,y) for y in range(4) for x in range(4)]
    ribbon={0,1,2,3,4,7,8,11}
    left={i for i,p in enumerate(points) if p.x<2}
    all_ids=set(range(len(points)));geo=SimpleNamespace()
    bad=[{'members':ribbon},{'members':all_ids-ribbon}]
    good=[{'members':left},{'members':all_ids-left}]
    assert [len(r['members']) for r in bad]==[len(r['members']) for r in good]==[8,8]
    # Two interior addresses; points on the outer hull edge do not count.
    assert enclosure(ribbon,points,geo)['surrounded_other_addresses']==2
    assert cost(bad,points,geo)>cost(good,points,geo)==0


def test_a_curving_population_around_unserved_open_space_is_not_a_ribbon():
    points=[Point(0,0),Point(0,1),Point(0,2),Point(1,2),Point(2,2),Point(2,1),Point(2,0),Point(4,4)]
    assert enclosure(set(range(7)),points,SimpleNamespace())['penalty']==0
