"""Prefer one driver across weak planning seams, subject to fleet constraints."""
from shapely.geometry import shape
from partition_app.geography import project,shared_boundary


def weights(partition,adjacency,parents):
    evidence={tuple(sorted(item['sections'])):item for item in partition.get('boundary_affinities',[])}
    if not evidence:return []
    polygons={f['id']:project(shape(f['geometry'])) for f in partition['areas']['features']}
    result=[]
    for a,neighbours in sorted(adjacency.items()):
        for b in sorted(neighbours):
            if b<=a or parents.get(a,a)==parents.get(b,b):continue
            item=evidence.get(tuple(sorted((parents.get(a,a),parents.get(b,b)))))
            if not item:continue
            shared=shared_boundary(polygons[a],polygons[b]).length
            if shared<20:continue
            # Long ordinary-street seams create stronger reunion preference;
            # protected major dividers do not earn this preference.
            value=round(shared*(1-item['strength'])**2/10)
            if value:result.append((a,b,value))
    return result


def separation_cost(members,edges):
    selected=set(members)
    return sum(weight for a,b,weight in edges if (a in selected)!=(b in selected))
