"""Source-ID regression references supplied by the user, separate from the engine."""
import argparse
import json
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shapely.geometry import Point
from shapely.strtree import STRtree
from partition_app.geography import FORWARD,street_name

AUDIT=Path(__file__).resolve().parents[1]/'outputs/2026-11-04_monday_map/audit/partition_app'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--range-key');args=parser.parse_args()
    ref=json.loads((AUDIT/'natural_first_review_reference.json').read_text())
    expected=json.loads((AUDIT/'natural-first-expectations.json').read_text())
    key=json.loads((AUDIT/'range-natural-summary.json').read_text())['key']
    natural=json.loads((AUDIT/(key+'.result.json')).read_text())
    before=json.loads((AUDIT/(ref['key']+'.result.json')).read_text())
    before_points={v['id']:Point(*FORWARD.transform(v['lon'],v['lat'])) for v in before['points']}
    lookup={v['id']:v['section'] for v in natural['points']}
    props={f['id']:f['properties'] for f in natural['areas']['features']}
    groups={g:set(v['address_ids']) for g,v in ref['examples'].items()}
    after_groups={g:Counter(lookup[i] for i in ids) for g,ids in groups.items()}
    range_result=json.loads((AUDIT/(args.range_key+'.result.json')).read_text()) if args.range_key else None
    rail=json.loads((AUDIT/(key+'.rail-validation.json')).read_text())
    results=[]
    for case in expected['checks']:
        kind=case['type'];details={};passed=False
        if kind=='same_area':
            ids=set().union(*(groups[g] for g in case['groups']));owners={lookup[i] for i in ids}
            passed=len(owners)==1;details={'areas':{s:props[s]['addresses'] for s in sorted(owners)}}
        elif kind=='share_dominant_area':
            a,b=case['groups'];dominant=after_groups[a].most_common(1)[0][0]
            passed=set(after_groups[b])=={dominant};details={'receiving_area':dominant}
        elif kind=='rail_split':
            sizes=list(after_groups[case['group']].values())
            passed=sum(n>=case['main_population_minimum'] for n in sizes)==2 and rail['passed']
            details={'source_populations':dict(after_groups[case['group']]),'independent_railway_audit':rail['passed']}
        elif kind=='source_road_split':
            sources={f['id'] for f in natural['boundary_candidates'] if street_name(f.get('name',''))==street_name(case['road']) and f['state']=='SELECTED'}
            areas=set(after_groups[case['group']])
            passed=len(areas)>1 and any(set(props[s].get('natural_boundary_ids',[]))&sources for s in areas)
            details={'areas':dict(after_groups[case['group']]),'supported_source_ids':sorted(sources)}
        elif kind=='nearest_pocket':
            target_points={g:sorted(groups[g]) for g in case['targets']}
            trees={g:STRtree([before_points[i] for i in ids]) for g,ids in target_points.items()}
            counts=Counter();matches=[]
            for identity in sorted(groups[case['group']]):
                candidates=[]
                for g,tree in trees.items():
                    closest=target_points[g][int(tree.nearest(before_points[identity]))]
                    candidates.append((before_points[identity].distance(before_points[closest]),g,closest))
                _,g,closest=min(candidates);counts[g]+=1;matches.append(lookup[identity]==lookup[closest])
            passed=all(matches) and dict(counts)==case['expected_counts'];details={'nearby_source_group_counts':dict(counts)}
        elif kind=='preserve_satisfactory_neighbours':
            all_groups=[case['group'],*case['neighbours']]
            passed=all(len(after_groups[g])==1 and props[next(iter(after_groups[g]))]['addresses']==len(groups[g]) for g in all_groups)
            if range_result:
                owners={v['id']:v['section'] for v in range_result['points']}
                own={owners[i] for i in groups[case['group']]}
                other={owners[i] for g in case['neighbours'] for i in groups[g]}
                passed=passed and len(own)==1 and not own.intersection(other)
            details={'natural_counts':{g:len(groups[g]) for g in all_groups},'range_checked':bool(range_result)}
        results.append({'label':case['label'],'passed':passed,**details})
    receipt={'reference_key':ref['key'],'natural_key':key,'range_key':args.range_key,'checks':results,
        'passed':all(v['passed'] for v in results),'scope':'Regression references only; not read by the partition algorithm.'}
    (AUDIT/'natural-first-example-validation.json').write_text(json.dumps(receipt,indent=2))
    print(json.dumps(receipt,indent=2));return 0 if receipt['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
