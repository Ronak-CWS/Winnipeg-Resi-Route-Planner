from types import SimpleNamespace
from shapely.geometry import Point,LineString,box
from shapely.strtree import STRtree
from partition_app.road_candidates import chains,complete


def test_multi_road_candidates_follow_the_complete_mapped_chain():
    lines=[LineString([(0,500),(300,500)]),LineString([(300,500),(300,700)]),
        LineString([(300,700),(1000,700)])]
    roads=[{'id':str(i),'name':f'Road {i}','geometry':line} for i,line in enumerate(lines)]
    geo=SimpleNamespace(roads=roads,base_roads=roads)
    candidates=chains(box(0,0,1000,1000),geo)
    assert candidates and any(len(c['road_ids'])==3 for c in candidates)
    assert all(c['geometry'].difference(lines[0].union(lines[1]).union(lines[2])).is_empty for c in candidates)


def test_endpoint_gap_completion_stays_in_mapped_road_space_outside_parcels():
    mapped=LineString([(0,50),(100,50)]);candidate=LineString([(.1,50),(100,50)])
    geo=SimpleNamespace(roads=[{'geometry':mapped}],road_tree=STRtree([mapped]),parcels=[],parcel_tree=STRtree([]))
    completed=complete(candidate,box(0,0,100,100),geo)
    assert completed.distance(Point(0,50))<1e-9
    parcel=box(.02,49,.08,51);geo.parcels=[{'geometry':parcel}];geo.parcel_tree=STRtree([parcel])
    assert complete(candidate,box(0,0,100,100),geo).distance(Point(0,50))==.1
