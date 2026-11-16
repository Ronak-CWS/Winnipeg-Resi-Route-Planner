from shapely.geometry import Polygon, box, Point
from shapely.ops import transform
from partition_app.engine import publication_geometry
from partition_app.publication import shared_edge_vertices
from partition_app.geography import FORWARD


def overlap(left,right):
    return transform(FORWARD.transform,left.intersection(right)).area


def test_shared_collinear_vertex_survives_inverse_projection_on_both_owners():
    # One side has a midpoint on a long shared diagonal; the other does not.
    a=(630000,5530000); b=(632000,5532000); middle=(631000,5531000)
    left=Polygon([a,middle,b,(628000,5532000)])
    right=Polygon([a,(634000,5530000),b])
    original_union=publication_geometry(left.union(right))
    separate_union=publication_geometry(left).union(publication_geometry(right))
    before=transform(FORWARD.transform,original_union.symmetric_difference(separate_union)).area
    prepared=shared_edge_vertices({'left':left,'right':right})
    assert prepared['left'].equals(left) and prepared['right'].equals(right)
    assert middle in list(prepared['right'].exterior.coords)
    assert overlap(publication_geometry(prepared['left']),publication_geometry(prepared['right']))<.001
    after=publication_geometry(prepared['left']).union(publication_geometry(prepared['right']))
    assert transform(FORWARD.transform,original_union.symmetric_difference(after)).area<.001
    assert before>.001


def test_publication_never_resolves_a_real_overlap_or_connects_separate_polygons():
    source={'a':box(0,0,10,10),'b':box(9,0,19,10),'c':box(30,0,31,1)}
    result=shared_edge_vertices(source)
    assert result['a'].intersection(result['b']).area==10
    assert result['a'].distance(result['c'])==20
    assert all(result[k].equals(v) for k,v in source.items())
