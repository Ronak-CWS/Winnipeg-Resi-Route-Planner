"""Range scoring over intact natural areas and a bounded set of real dividers."""
import hashlib
import math
from collections import defaultdict
from itertools import combinations

from shapely import make_valid, set_precision
from shapely.geometry import Point
from shapely.ops import unary_union
from shapely.strtree import STRtree

from .geography import canonical, divider_line, polygon_parts, subdivide, internal_seams, shared_boundary


def count_cost(count, lower, upper):
    """Penalise overload and fragmentation, with an explicit tiny-area cost."""
    deficit=max(0,lower-count)/lower
    excess=max(0,count-upper)/lower
    floor=min(400,lower*.5)
    return .35+deficit**2+(2 if excess else 0)+8*excess+12*excess**2+2*(max(0,floor-count)/floor)**2


def populated_parts(parts, points):
    owners=set()
    for point in points:
        hits=[i for i,part in enumerate(parts) if part.distance(point)<.03]
        if hits:owners.add(min(hits))
        if len(owners)>1:return True
    return False


def linear_separator(geometry, points, geography, categories):
    features=geography.nearby_features(geometry,categories)
    if not features:return False
    for part in polygon_parts(geometry):
        part=set_precision(make_valid(part),.01)
        lines=[set_precision(divider_line(f),.01) for f in features if divider_line(f).intersects(part)]
        if lines and populated_parts(subdivide(part,lines),points):return True
    return False


def footprint_separator(geometry, points, geography, categories):
    for feature in geography.nearby_features(geometry,categories):
        footprint=set_precision(make_valid(feature['geometry']),.01)
        if footprint.geom_type not in {'Polygon','MultiPolygon'}:continue
        for part in polygon_parts(geometry):
            part=set_precision(make_valid(part),.01)
            if footprint.intersects(part) and populated_parts(polygon_parts(part.difference(footprint)),points):return True
    return False


def footprint_between(geometry, points_a, points_b, geography, categories):
    """A footprint must separate the two groups, not already-split lobes of one."""
    for feature in geography.nearby_features(geometry,categories):
        footprint=set_precision(make_valid(feature['geometry']),.01)
        if footprint.geom_type not in {'Polygon','MultiPolygon'}:continue
        for part in polygon_parts(geometry):
            part=set_precision(make_valid(part),.01)
            pieces=polygon_parts(part.difference(footprint))
            a={i for i,p in enumerate(pieces) if any(p.distance(q)<.03 for q in points_a)}
            b={i for i,p in enumerate(pieces) if any(p.distance(q)<.03 for q in points_b)}
            if a and b and a.isdisjoint(b):return True
    return False


def hard_separator(geometry, points, geography):
    if linear_separator(geometry,points,geography,{'railway','waterway','controlled_road','high_speed_road'}):return True
    if footprint_separator(geometry,points,geography,{'water_area'}):return True
    return False


def boundary_merge_cost(shared,geography):
    """Prefer erasing weak seams; major barriers are vetoed separately."""
    weights={'wide_road':.8,'municipal_corridor':.6,'broad_corridor':.5,'community':.25}
    costs=[]
    for category,weight in weights.items():
        lines=[divider_line(f) for f in geography.nearby_features(shared.buffer(8),{category})]
        fraction=shared.intersection(unary_union(lines).buffer(8)).length/max(shared.length,1) if lines else 0
        costs.append(weight*fraction)
    return max(costs,default=0)


def rebalance(occupied, members, nearby_links, points, buckets, parcels, geography, preferences, ledger, progress, boundary_evidence, natural_only=False):
    # Derived urban-corridor corrections need two useful natural children. They
    # must not carve an 80-house remnant out of an otherwise useful community.
    lower,upper=(400,799) if natural_only else (preferences['preferred_minimum'],preferences['maximum_addresses'])
    natural_count=len(occupied)
    regions={k:{'geometry':g,'members':set(members[k]),'links':list(nearby_links.get(k,[])),
        'parents':{hashlib.sha256(g.normalize().wkb).hexdigest()[:16]},'boundaries':[]} for k,g in occupied.items()}
    parcel_values=list(parcels.values());parcel_tree=STRtree([p['geometry'] for p in parcel_values])
    road_values=list(geography.roads);road_tree=STRtree([r['geometry'] for r in road_values])
    next_key=max(regions,default=-1)+1
    audit={'natural_areas':natural_count,'merges':0,'splits':0,'candidates':0,'rejections':defaultdict(int),
           'ordinary_or_alley_dividers':0,'stage':'natural corrections' if natural_only else 'range',
           'score_before':None if natural_only else sum(count_cost(len(v['members']),lower,upper) for v in regions.values())}
    if not natural_only:
        from .access_refinement import separate,trim_empty_major_lobes
        revised,audit['road_connectivity']=separate(list(regions.values()),points,buckets,parcels,geography,ledger,boundary_evidence)
        revised,audit['empty_major_lobes']=trim_empty_major_lobes(revised,points,parcels,geography)
        regions=dict(enumerate(revised));next_key=len(regions)
    def service(region):return [points[i] for i in sorted(region['members'])]
    from .service_shape import cost as shape_cost
    def score(region):
        return count_cost(len(region['members']),lower,upper)+(0 if natural_only else shape_cost([region],points,geography))
    def coalesce():
        for _ in range(natural_count*2):
            keys=sorted(regions);tree=STRtree([regions[k]['geometry'] for k in keys]);options=[]
            for a in keys:
                ra=regions[a];na=len(ra['members'])
                for j in tree.query(ra['geometry'],predicate='intersects'):
                    b=keys[int(j)]
                    if a>=b:continue
                    rb=regions[b];nb=len(rb['members']);total=na+nb
                    if lower<=na<=upper and total>upper or lower<=nb<=upper and total>upper:
                        audit['rejections']['satisfactory neighbour would leave range']+=1;continue
                    gain=score(ra)+score(rb)-score({'members':ra['members']|rb['members']})
                    if gain<=.02:continue
                    shared=shared_boundary(ra['geometry'],rb['geometry'])
                    if shared.length<1:continue
                    gain-=boundary_merge_cost(shared,geography)
                    if gain<=.02:continue
                    union=ra['geometry'].union(rb['geometry'])
                    if union.geom_type!='Polygon':continue
                    combined_points=service(ra)+service(rb)
                    if hard_separator(union,combined_points,geography):
                        audit['rejections']['important physical divider']+=1;continue
                    if footprint_between(union,service(ra),service(rb),geography,{'park','recreation','mapped_open_land','landuse'}):
                        audit['rejections']['complete park or land-use corridor']+=1;continue
                    from .access import connected
                    if hasattr(geography,'access_network') and connected(ra,rb,points,geography) is not True:
                        audit['rejections']['no demonstrated internal road connection']+=1;continue
                    options.append((-gain,-shared.length,a,b,union))
            if not options:break
            _,_,a,b,union=min(options,key=lambda v:v[:4]);ra,rb=regions.pop(a),regions.pop(b)
            regions[a]={'geometry':union,'members':ra['members']|rb['members'],'links':ra['links']+rb['links'],
                        'parents':ra['parents']|rb['parents'],'boundaries':ra['boundaries']+rb['boundaries'],
                        'last_resort':ra.get('last_resort',False) or rb.get('last_resort',False)}
            audit['merges']+=1
    if not natural_only:coalesce()
    blocked=set()
    for turn in range(64):
        oversized=sorted((k for k,v in regions.items() if len(v['members'])>upper and k not in blocked),key=lambda k:(-len(regions[k]['members']),k))
        if not oversized:break
        key=oversized[0];region=regions[key];geometry=region['geometry'];indices=sorted(region['members'])
        if geometry.geom_type!='Polygon':blocked.add(key);continue
        features=geography.nearby_features(geometry,{'community','wide_road','municipal_corridor','broad_corridor','park','recreation','mapped_open_land'})
        types={'municipal_corridor'} if natural_only else {'community','wide_road','municipal_corridor','broad_corridor'}
        base=[f for f in features if f['category'] in types]
        # No ordinary road, alley, parcel edge or artificial connector is a
        # splitter. Parks can close a finite municipal/large-road corridor.
        parks=sorted((f for f in features if f['category'] in {'park','recreation','mapped_open_land'}),
                     key=lambda f:(-divider_line(f).intersection(geometry).length,f['id']))[:24]
        base=sorted(base,key=lambda f:(f['category']!='community',-divider_line(f).intersection(geometry).length,f['id']))[:24]
        recorded={item['id'] for item in ledger}
        for f in base:
            if f['id'] not in recorded:
                boundary_evidence.setdefault(f['id'],f)
                ledger.append({key:f[key] for key in ['id','name','category','rank','evidence','evidence_ids',
                    'strong_support_fraction','municipal_alignment','median_right_of_way_m','width_samples','supported_road_ids'] if key in f}
                    |{'state':'CANDIDATE','reason':'Finite supported corridor inventoried for a useful natural or range division.'})
                recorded.add(f['id'])
        candidates=[(f,) for f in base]
        if not natural_only:
            from .landuse_split import corridors as landuse_corridors
            candidates.extend((f,) for f in landuse_corridors(geometry,geography))
        roads=[f for f in base if f['category']!='community'][:10]
        if not natural_only:candidates.extend(list(combinations(roads,2))[:24])
        if not natural_only:
            # Test connected park completions separately. Adding every park
            # outline at once can invent unrelated child pieces and conceal a
            # perfectly useful road-plus-park division.
            composites=[]
            for road in roads:
                connected=[park for park in parks if divider_line(road).intersects(divider_line(park))]
                composites.extend((road,park) for park in connected[:8])
            candidates.extend(composites[:64])
            # If stronger finite dividers cannot produce a useful division,
            # try complete mapped streets before constructing a parcel mesh.
            # The same ownership/parcel/continuity gates apply to both paths.
            from .continuity import corridors, composite_corridors
            from .road_candidates import chains
            streets=corridors(geography,geometry)
            candidates.extend((dict(r, category='street_corridor', rank=6,
                evidence='Finite continuous City street; ordinary-road fallback'),)
                for r in streets+composite_corridors(streets,geometry)+chains(geometry,geography))
        best=None
        for chosen in candidates:
            ordinary=all(f['category']=='street_corridor' for f in chosen)
            audit['candidates']+=1
            candidate_id=('natural-' if natural_only else 'range-')+'balance-'+hashlib.sha256((canonical(geometry)+'|'.join(f['id'] for f in chosen)).encode()).hexdigest()[:16]
            from .road_candidates import complete
            boundary_lines=[complete(divider_line(f),geometry,geography) for f in chosen]
            allowed=set()
            for f in chosen:
                # Eligibility depends on actual road alignment, including a
                # municipal edge that genuinely follows a mapped street.
                if f['category'] not in {'community','wide_road','municipal_corridor','broad_corridor','street_corridor','landuse_corridor'}:continue
                line=divider_line(f)
                line_mask=line.buffer(8)
                for j in road_tree.query(line_mask,predicate='intersects'):
                    road=road_values[int(j)]
                    if road['geometry'].intersection(line_mask).length>road['geometry'].length*.7:
                        allowed.add(('ordinary segment',road['id']))
            entry={'id':candidate_id,'name':' / '.join(f.get('name','') for f in chosen),'category':'natural_area_split',
                'rank':4,'state':'REJECTED','source_ids':[f['id'] for f in chosen],
                'stage':'natural correction' if natural_only else 'range',
                'ordinary_road_fallback':ordinary,
                'evidence':'Finite municipal/broad-road lines, optionally completed by mapped park edges. No ordinary-road or alley cutting.'}
            def reject(reason):
                audit['rejections'][reason]+=1;entry['reason']=reason;ledger.append(entry)
            try:
                parts=subdivide(geometry,boundary_lines)
                entry['park_completion_used']=any(f['category'] in {'park','recreation','mapped_open_land'} for f in chosen)
                if len(parts)<2 and natural_only:
                    entry['park_completion_used']=True
                    parts=subdivide(geometry,boundary_lines+[divider_line(f) for f in parks])
            except ValueError:reject('subdivision coverage');continue
            tree=STRtree(parts);ownership={};part_members=defaultdict(set)
            for i in indices:
                hits=[int(j) for j in tree.query(points[i],predicate='intersects')]
                if not hits:hits=[j for j,p in enumerate(parts) if p.distance(points[i])<.02]
                if not hits:break
                ownership[i]=min(hits);part_members[min(hits)].add(i)
            if len(ownership)!=len(indices):reject('point containment');continue
            populated={j:parts[j] for j in part_members}
            if len(populated)<2 or len(populated)>math.ceil(len(indices)/lower)+1:
                reject('no useful serviced division');continue
            split_group=False
            for group,group_members in buckets.items():
                if group in allowed:continue
                owners={ownership[i] for i in group_members if i in ownership}
                if len(owners)>1:split_group=True;break
            if split_group:reject('protected street, site or coordinate group');continue
            # Assign complete empty faces to one adjoining child. These faces
            # are real existing land, never buffers or invented bridges.
            empty={j for j in range(len(parts)) if j not in populated}
            for _ in range(len(empty)+1):
                changed=False
                for j in sorted(empty.copy()):
                    options=[(-parts[j].boundary.intersection(g.boundary).length,k) for k,g in populated.items()]
                    length,k=min(options)
                    if length>=-.1:continue
                    union=populated[k].union(parts[j])
                    if union.geom_type!='Polygon':continue
                    populated[k]=union;empty.remove(j);changed=True
                if not changed:break
            if empty:reject('detached empty face');continue
            cut=internal_seams(populated.values())
            boundary_evidence[candidate_id]={'geometry':cut}
            parcel_cut=False
            for j in parcel_tree.query(cut,predicate='intersects'):
                parcel=parcel_values[int(j)]['geometry']
                owners=sum(parcel.intersection(g).area>max(4,parcel.area*.02) for g in populated.values())
                if owners>1:
                    entry['blocking_parcel_id']=parcel_values[int(j)]['id'];parcel_cut=True;break
            if parcel_cut:reject('serviced parcel cut');continue
            counts=[len(part_members[j]) for j in populated]
            entry['counts']=counts
            if min(counts)<(400 if natural_only else min(400,lower*.5)):reject('would create a new tiny section');continue
            # Candidate labels are not evidence of boundary quality. Compare
            # actual physical support consistently, including real road paths
            # that were previously skipped after any municipal cut succeeded.
            from .boundary_evidence import profile
            physical=profile(cut,geography)
            entry['physical_boundary_strength']=physical
            risk=2*(1-physical['strength'])
            after=sum(count_cost(n,lower,upper) for n in counts)+risk*(len(counts)-1)
            if not natural_only:
                entry['service_shape_penalty']=shape_cost([{'members':part_members[j]} for j in populated],points,geography)
                after+=entry['service_shape_penalty']
            from .continuity import assess
            quality=assess(cut,ownership,points,buckets,geography)
            entry['boundary_quality']=quality
            after+=quality['penalty']
            gain=score(region)-after
            if natural_only:
                if quality['street_breaks'] or quality['alley_side_splits']:
                    reject('unsupported street or opposing alley split');continue
                after=-sum(f.get('municipal_alignment',0) for f in chosen);gain=1
            entry.update({'counts':counts,'score_before':None if natural_only else round(score(region),6),
                'score_after':None if natural_only else round(after,6),'gain':None if natural_only else round(gain,6)})
            if gain<(.01 if natural_only else .4):reject('range benefit does not justify another division');continue
            if any(g.geom_type!='Polygon' or not g.is_valid for g in populated.values()):reject('non-contiguous child');continue
            entry['state']='VALID_CANDIDATE';entry['reason']=('Supported municipal arterial creates useful natural areas without a tiny remnant.' if natural_only else 'Improves requested range without cutting a protected ordinary frontage or site.');ledger.append(entry)
            candidate=(after, len(counts),candidate_id,populated,part_members,allowed,entry)
            if best is None or candidate[:3]<best[:3]:best=candidate
        if best is None and not natural_only and len(indices)>=2*lower:
            from .whole_blocks import regroup
            audit['last_resort_attempts']=audit.get('last_resort_attempts',0)+1
            fallback_review={'addresses':len(indices)}
            fallback=regroup(geometry,indices,points,buckets,parcels,geography,lower,upper,progress,fallback_review)
            audit.setdefault('frontage_attempts',[]).append(fallback_review)
            if fallback:
                from .continuity import assess
                owners={i:k for k,r in enumerate(fallback['regions']) for i in r['members']}
                quality=assess(fallback['cut'],owners,points,buckets,geography)
                fallback_review['boundary_quality']=quality
                fallback_review['score_with_boundary_quality']=fallback['score']+quality['penalty']+shape_cost(fallback['regions'],points,geography)
                if score(region)-fallback_review['score_with_boundary_quality']<.4:
                    fallback_review.update(state='REJECTED',reason='Street/alley quality outweighs count benefit')
                    blocked.add(key)
                    continue
                candidate_id='whole-frontage-'+hashlib.sha256(canonical(geometry).encode()).hexdigest()[:16]
                entry={'id':candidate_id,'name':'Last-resort whole-frontage regrouping','category':'natural_area_split','rank':7,
                    'stage':'last-resort whole frontages','state':'CHOSEN','chosen_for_split':True,
                    'source_ids':[],'parcel_ids':fallback['parcel_ids'],'counts':[len(r['members']) for r in fallback['regions']],
                    'reason':'At least two requested minimum-size sections fit inside this natural area, but supported municipal/broad-road cuts failed. Regrouped complete street frontages and sites; rear-property or alley boundaries require pickup-access review.',
                    'atomic_frontage_blocks':fallback['units'],'whole_block_moves':fallback['moves'],
                    'boundary_quality':quality,
                    'mapped_alley_boundary_m':fallback['mapped_alley_boundary_m'],'frontage_protection':fallback['protection_reasons']}
                ledger.append(entry);boundary_evidence[candidate_id]={'geometry':fallback['cut']}
                audit['last_resort_splits']=audit.get('last_resort_splits',0)+1
                audit['ordinary_or_alley_dividers']+=int(fallback['mapped_alley_boundary_m']>1)
                del regions[key]
                for child in fallback['regions']:
                    regions[next_key]={'geometry':child['geometry'],'members':child['members'],'links':[],
                        'parents':set(region['parents']),'boundaries':region['boundaries']+[candidate_id],'last_resort':True}
                    next_key+=1
                audit['splits']+=1
                continue
        if best is None:blocked.add(key);continue
        _,_,_,geometries,group_members,allowed,entry=best
        entry['state']='CHOSEN';entry['chosen_for_split']=True
        from .continuity import split_frontage_buckets
        split_frontage_buckets(buckets,allowed,{i:j for j,group in group_members.items() for i in group})
        del regions[key]
        for j,g in sorted(geometries.items()):
            regions[next_key]={'geometry':g,'members':group_members[j],'links':[],
                'parents':set(region['parents']),'boundaries':region['boundaries']+entry['source_ids'],
                'last_resort':region.get('last_resort',False)}
            next_key+=1
        audit['splits']+=1
        progress(68,'Checking supported broad municipal boundaries' if natural_only else 'Scoring whole natural-area sections against the requested range')
    if not natural_only:coalesce()
    if not natural_only:
        from .continuity import improve
        improved,audit['continuity']=improve([r for _,r in sorted(regions.items())],points,buckets,parcels,geography,lower,upper,ledger,boundary_evidence,progress)
        regions=dict(enumerate(improved))
        # A repaired division can expose a compatible small neighbour. Score
        # that merge again rather than freezing the earlier, inferior shape.
        coalesce()
    if not natural_only:
        from .landuse_repair import improve as improve_landuse
        improved,audit['landuse_quality']=improve_landuse(list(regions.values()),points,buckets,parcels,geography,lower,upper,ledger,boundary_evidence,progress)
        regions=dict(enumerate(improved))
    if not natural_only:
        from .pockets import separate_sparse_pockets,consolidate_sparse_pockets
        improved,audit['sparse_pockets']=separate_sparse_pockets(list(regions.values()),points,buckets,parcels,geography,progress)
        improved,audit['sparse_pockets']['consolidation']=consolidate_sparse_pockets(improved,points,geography)
        regions=dict(enumerate(improved))
        from .continuity import audit_boundaries
        audit['continuity']['remaining']=audit_boundaries(list(regions.values()),points,buckets,geography)
    audit['score_after']=None if natural_only else sum(score(v) for v in regions.values());audit['rejections']=dict(audit['rejections'])
    final=[]
    for _,region in sorted(regions.items()):
        n=len(region['members'])
        region['score']=score(region)
        region['reason']=('Within the requested range.' if lower<=n<=upper else
            'Below range: no compatible merge improves the score without crossing a protected divider or taking a satisfactory neighbour outside its range.' if n<lower else
            'Above range: the available divisions do not improve the range enough without creating small remnants or breaking protected street frontages, sites or parcels.')
        if region.get('landuse_boundary'):
            region['reason']+=' A mapped school, park or commercial edge keeps neighbouring frontages together.'
        elif region.get('continuity_corridor'):
            region['reason']+=' A continuous mapped street improves street/alley continuity or neighbourhood cohesion.'
        elif region.get('last_resort'):
            region['reason']+=' Last-resort whole-frontage regrouping was needed. Review rear-property/alley boundaries and actual pickup access.'
        if region.get('sparse_pocket'):
            region['reason']+=' Sparse service pocket retained across a real boundary; no compatible nearby planning merge was found. Its truck assignment is evaluated with neighbouring work.'
        final.append(region)
    return final,audit
