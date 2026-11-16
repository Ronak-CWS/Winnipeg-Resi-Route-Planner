"""Independent geometry/identity checks for the user's illustrated seam.

Road names and old MON labels are QA fixtures only, never engine inputs.
Uses saved City geometry and published exports, not the engine's cut routine.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from pyproj import Transformer
from shapely import make_valid, set_precision
from shapely.geometry import shape
from shapely.ops import transform, unary_union

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'outputs/2026-11-04_monday_map/audit/partition_app'
GEO=ROOT/'data/reference/partition_geography'
PROJECT=Transformer.from_crs(4326,32614,always_xy=True).transform


def metric(value):
    return set_precision(make_valid(transform(PROJECT,shape(value))),.01)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--key',required=True)
    args=parser.parse_args()
    reference=json.loads((AUDIT/'street-alley-review-reference.json').read_text())
    before=json.loads((AUDIT/(reference['previous_key']+'.result.json')).read_text())
    after=json.loads((AUDIT/(args.key+'.result.json')).read_text())
    cohort=set().union(*map(set,reference['source_cohorts'].values()))
    old_owner={p['id']:p['section'] for p in before['points']}
    new_owner={p['id']:p['section'] for p in after['points']}
    assert len(cohort)==2027 and set(new_owner)==set(old_owner)
    owners={new_owner[i] for i in cohort}
    assert len(owners)==2
    assert {i for i,sid in new_owner.items() if sid in owners}==cohort
    counts=Counter(new_owner[i] for i in cohort)
    assert sorted(counts.values())==[830,1197]
    old_geometries={f['id']:metric(f['geometry']) for f in before['areas']['features'] if f['id'] in reference['source_cohorts']}
    geometries={f['id']:metric(f['geometry']) for f in after['areas']['features'] if f['id'] in owners}
    unchanged_parent_m2=unary_union(list(old_geometries.values())).symmetric_difference(unary_union(list(geometries.values()))).area
    assert unchanged_parent_m2<1,unchanged_parent_m2
    a,b=geometries.values();seam=a.boundary.intersection(b.boundary)
    road_rows=[r for r in json.loads((GEO/'roads.json').read_text()) if r.get('full_name')=='Cambridge St']
    road=unary_union([metric(r['the_geom']) for r in road_rows])
    aligned=seam.intersection(road.buffer(.1)).length
    assert seam.length>700 and aligned/seam.length>.995,(seam.length,aligned)
    # The screenshot's Fleet Avenue cut must disappear, independently of
    # area numbering. All cohort addresses on that street now share an owner.
    fleet=[p['id'] for p in before['points'] if p['id'] in cohort and p['address'].endswith(' FLEET AVE')]
    assert len(fleet)>10 and len({old_owner[i] for i in fleet})==2
    assert len({new_owner[i] for i in fleet})==1
    changes=after['range_balancing']['continuity']['changes']
    assert len(changes)==len({c['candidate'] for c in changes})==2
    assert all(not c['quality_after']['street_breaks'] and not c['quality_after']['alley_side_splits'] for c in changes)
    assert all(c['quality_before']['alley_side_splits'] for c in changes)
    assert after['validation']['exactly_once'] and after['validation']['material_parcel_cuts']==0
    assert after['validation']['street_alley_continuity_review'], 'Remaining issues must stay visible'
    production='\n'.join(p.read_text(encoding='utf-8') for p in (ROOT/'partition_app').glob('*.py'))
    for text in ['Cambridge','Fleet Ave','MON-013','MON-018']:
        assert text not in production,text
    receipt={'passed':True,'before_key':before['key'],'key':args.key,'cohort_addresses':len(cohort),
        'new_counts':dict(counts),'no_outside_ids_taken':True,'parent_difference_m2':unchanged_parent_m2,
        'shared_seam_m':seam.length,'city_street_alignment_fraction':aligned/seam.length,
        'fleet_avenue_records':len(fleet),'fleet_avenue_whole':True,'continuity_corrections':len(changes),
        'remaining_review_seams':len(after['validation']['street_alley_continuity_review']),
        'no_named_example_in_production':True,'scope':'QA fixtures only; no live GIS or provider calls'}
    (AUDIT/'street-alley-example-validation.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
