"""Source-ID regression fixtures for illustrated boundaries, never solver inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
DELIVERY=ROOT/'outputs/2026-11-04_monday_map'
AUDIT=DELIVERY/'audit/partition_app'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--key',required=True)
    args=parser.parse_args()
    result=json.loads((AUDIT/(args.key+'.result.json')).read_text())
    diagnosis=json.loads((AUDIT/'queenston-boundary-reason-audit.json').read_text())
    old=json.loads((AUDIT/(diagnosis['partition_key']+'.result.json')).read_text())
    owner={p['id']:p['section'] for p in result['points']}
    fixtures=json.loads((AUDIT/'whyte-ridge-proposed-count-assignments.json').read_text())
    groups={n:{p['AddressId'] for p in fixtures if p['ProposedSection']==n and p['PlanningSection']!='MON-015'} for n in ['1','2']}
    assert sorted(map(len,groups.values()))==[946,1156]
    counts={}
    for n,ids in groups.items():
        assigned={owner[i] for i in ids}
        assert len(assigned)==1,(n,Counter(owner[i] for i in ids))
        section=next(iter(assigned))
        assert {i for i,s in owner.items() if s==section}==ids
        counts[n]={'area':section,'addresses':len(ids)}
    assert counts['1']['area']!=counts['2']['area']
    west_rail={p['id'] for p in old['points'] if p['section']=='MON-015'}
    assert len(west_rail)==283 and not ({owner[i] for i in west_rail}&{d['area'] for d in counts.values()})
    # Direct address identities on opposing sides of the former alley.
    alley=diagnosis['current_quality'][0]['alley_side_splits'][0]
    pair=[old['points'][side[0]]['id'] for side in alley['side_members']]
    assert len({owner[i] for i in pair})==1,pair
    corner=['193113','206887','37780','39479','196014']
    assert len({owner[i] for i in corner})==1,'Corner frontage must not be carved around an individual building'
    ref=json.loads((AUDIT/'street-alley-review-reference.json').read_text())
    cohort=set().union(*map(set,ref['source_cohorts'].values()))
    fleet=[p['id'] for p in old['points'] if p['id'] in cohort and p['address'].endswith(' FLEET AVE')]
    assert len(fleet)==144 and len({owner[i] for i in fleet})==1
    source_receipt=json.loads((AUDIT/'source-preservation-street-alley.json').read_text())
    for name,digest in source_receipt['coordinate_deliverables_unchanged'].items():
        assert hashlib.sha256((DELIVERY/name).read_bytes()).hexdigest()==digest,name
    code='\n'.join(p.read_text(encoding='utf-8') for folder in ['partition_app','routing_app'] for p in (ROOT/folder).glob('*.py'))
    for example in ['Queenston','Grosvenor','Scurfield','Fleetwood','MON-016','MON-018']:
        assert example not in code,example
    receipt={'key':args.key,'passed':True,'whyte_ridge_drawn_sections':counts,
        'railway_side_retained':283,'former_alley_pair_same_owner':pair,
        'illustrated_corner_ids_together':corner,
        'fleet_avenue_ids_kept_together':len(fleet),'source_coordinate_files_unchanged':True,
        'no_named_example_exceptions':True,'network_calls':0}
    (AUDIT/'boundary-hierarchy-example-validation.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':main()
