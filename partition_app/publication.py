"""Keep shared metric edge vertices identical before inverse projection."""
from shapely import set_precision,make_valid
from shapely.geometry import LineString, Point, Polygon, MultiPolygon
from shapely.strtree import STRtree
from .geography import polygon_parts


def shared_edge_vertices(geometries):
    # Inverse projection is nonlinear. The same straight metric edge exported
    # with different intermediate vertices becomes two different WGS84 chords.
    # Insert existing, collinear mapped vertices on BOTH owners before export.
    coordinates = sorted({tuple(xy[:2]) for geometry in geometries.values()
        for part in polygon_parts(geometry) for ring in [part.exterior, *part.interiors]
        for xy in ring.coords})
    if not coordinates:
        return dict(geometries)
    points = [Point(xy) for xy in coordinates]
    tree = STRtree(points)
    tolerance = 1e-7  # Numerical equality in metres; never a road/site connector.

    def ring_vertices(ring):
        output = []
        values = list(ring.coords)
        for a, b in zip(values, values[1:]):
            output.append(tuple(a[:2]))
            dx, dy = b[0]-a[0], b[1]-a[1]
            length2 = dx*dx+dy*dy
            if not length2:
                continue
            segment = LineString([a,b])
            extra = []
            for index in tree.query(segment, predicate='dwithin', distance=tolerance):
                x,y = coordinates[int(index)]
                t = ((x-a[0])*dx+(y-a[1])*dy)/length2
                endpoint_clearance=tolerance/(length2**.5)
                if endpoint_clearance < t < 1-endpoint_clearance:
                    extra.append((t,(x,y)))
            for _,xy in sorted(extra):
                if Point(xy).distance(Point(output[-1]))>tolerance:
                    output.append(xy)
        output.append(output[0])
        return output

    result = {}
    for key, geometry in geometries.items():
        parts = [Polygon(ring_vertices(p.exterior),[ring_vertices(r) for r in p.interiors])
            for p in polygon_parts(geometry)]
        value = parts[0] if len(parts)==1 else MultiPolygon(parts)
        if not value.is_valid:
            # Removing native precision metadata can expose nanometre-scale
            # self-touches already present in a GEOS ring. Keep EVERY polygonal
            # component of the validity repair, as publication_geometry does.
            repaired=polygon_parts(make_valid(value))
            value=repaired[0] if len(repaired)==1 else MultiPolygon(repaired)
        # Compare at one precision model without snapping either operand.
        # Frozen cells carry a centimetre model; constructed rings do not.
        difference=value.symmetric_difference(set_precision(geometry,0)).area
        allowed=max(1e-5,geometry.length*tolerance)
        if not value.is_valid or difference > allowed:
            raise ValueError(f'Shared-edge vertex publication changed geometry {key}: valid={value.is_valid}, difference={difference:.9f} m2, numerical limit={allowed:.9f} m2.')
        result[key] = value
    return result
