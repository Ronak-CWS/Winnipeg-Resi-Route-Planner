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


def test_balanced_counts_do_not_buy_a_population_wrapping_its_neighbour():
    from partition_app.balancing import count_cost
    points=[Point(x,y) for x in range(40) for y in range(40)]
    all_ids=set(range(len(points)))
    wrapping={i for i,p in enumerate(points) if p.x<8 or p.x>=32 or p.y>=32}
    straight={i for i,p in enumerate(points) if p.x<20}
    geo=SimpleNamespace()
    def score(groups):
        return sum(count_cost(len(g),900,1100) for g in groups)+cost([{'members':g} for g in groups],points,geo)
    # A useful straight division improves the oversized parent, while two
    # similar counts cannot justify one service population surrounding another.
    assert score([straight,all_ids-straight])<score([all_ids])<score([wrapping,all_ids-wrapping])
