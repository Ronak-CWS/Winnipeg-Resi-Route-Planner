import math
from types import SimpleNamespace
from shapely.geometry import LineString,box
from partition_app.landuse_paths import frontage_groups


def test_park_lookup_retains_the_exact_rounded_buffer_corner():
    line=LineString([(0,0),(100,0),(100,100),(50,50)])
    road={'id':'road','geometry':LineString([(-60,80),(40,80)])}
    bucket={('ordinary segment','road'):[0,1]}
    for radius in (6,7.9,7.999,8.1):
        x=50-radius*math.cos(math.pi/64)
        y=50+radius*math.sin(math.pi/64)
        park={'id':'grounds','category':'park','geometry':box(x-100,y,x,y+100)}
        g=SimpleNamespace(roads=[road])
        g.nearby_features=lambda geometry,categories:[park] if park['geometry'].intersects(geometry) else []
        expected=set(bucket) if park['geometry'].intersects(line.buffer(8)) else set()
        assert frontage_groups([line],bucket,g)==expected
    assert not park['geometry'].intersects(line.buffer(8))


def test_cached_park_search_keeps_current_groups_and_changed_grounds():
    road={'id':'road','geometry':LineString([(0,0),(100,0)])}
    park={'id':'grounds','category':'park','geometry':box(0,0,100,100)}
    g=SimpleNamespace(roads=[road],nearby_features=lambda *args:[park])
    first={('ordinary segment','road'):[0,1]}
    assert frontage_groups([road['geometry']],first,g)==set(first)
    replacement={('ordinary segment','road','new-child'):[0]}
    assert frontage_groups([road['geometry']],replacement,g)==set(replacement)
    park['geometry']=box(1000,1000,1100,1100)
    assert not frontage_groups([road['geometry']],replacement,g)
