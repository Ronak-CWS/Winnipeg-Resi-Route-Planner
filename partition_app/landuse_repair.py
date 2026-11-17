"""Prefer supported non-residential edges over weaker existing road seams."""
import hashlib
import time
from shapely.ops import unary_union
from .geography import shared_boundary,canonical,SubdivisionCoverageError
from .boundary_evidence import profile,land_features


def improve(regions,points,buckets,parcels,geography,lower,upper,ledger,evidence,progress,deadline=None):
    from .balancing import count_cost,hard_separator
    from .continuity import assess,neighbourhood_division_cost,split_frontage_buckets
    from .landuse_candidates import candidates
    audit={'candidates':0,'changes':[],'rejections':[],'time_budget_reached':False};tested=set()
    def pair_cost(left,right):
        seam=shared_boundary(left['geometry'],right['geometry'])
        if seam.length<1:return 0.
        owners={i:0 for i in left['members']}|{i:1 for i in right['members']}
        return assess(seam,owners,points,buckets,geography)['penalty']+profile(seam,geography)['preference_cost']+neighbourhood_division_cost(seam,left['geometry'].union(right['geometry']))
    def affected(a,b,left,right):
        from .service_shape import cost as shape_cost
        return count_cost(len(left['members']),lower,upper)+count_cost(len(right['members']),lower,upper)+shape_cost([left,right],points,geography)+pair_cost(left,right)+sum(pair_cost(r,left)+pair_cost(r,right) for k,r in enumerate(regions) if k not in {a,b})
    for _ in range(len(regions)):
        if deadline is not None and time.monotonic()>=deadline:
            audit['time_budget_reached']=True
            return regions,audit
        pending=[]
        for a,left in enumerate(regions):
            for b in range(a+1,len(regions)):
                right=regions[b];key=tuple(sorted((canonical(left['geometry']),canonical(right['geometry']))))
                if key in tested:continue
                seam=shared_boundary(left['geometry'],right['geometry'])
                if seam.length<150:continue
                strength=profile(seam,geography)
                nonmajor_road=sum(strength.get(k,0) for k in ('ordinary_road_m','wide_road_m','supported_corridor_m'))
                if nonmajor_road<100:continue
                if not land_features(seam.buffer(140),geography):continue
                pending.append((-nonmajor_road,a,b,key))
        changed=False
        for position,(_,a,b,key) in enumerate(sorted(pending),1):
            if deadline is not None and time.monotonic()>=deadline:
                audit.update(time_budget_reached=True,remaining_pairs=len(pending)-position+1)
                return regions,audit
            left,right=regions[a],regions[b]
            if key!=tuple(sorted((canonical(left['geometry']),canonical(right['geometry'])))):continue
            tested.add(key);parent=left['geometry'].union(right['geometry'])
            if parent.geom_type!='Polygon' or hard_separator(parent,[points[i] for i in left['members']|right['members']],geography):continue
            progress(71,f'Comparing school and commercial boundaries {position}/{len(pending)}')
            try:
                alternatives=candidates(left,right,points,buckets,parcels,geography)
            except SubdivisionCoverageError as error:
                # This optional comparison cannot invalidate completed work.
                # Reject only its proposal; the original regions and every
                # mandatory final geometry check remain intact.
                audit['rejections'].append({'reason':'Candidate subdivision does not preserve coverage',
                    'detail':str(error),'counts':[len(left['members']),len(right['members'])]})
                continue
            before=affected(a,b,left,right);options=[]
            for option in alternatives:
                audit['candidates']+=1;children=option['children'];counts=[len(c['members']) for c in children]
                if min(counts)<min(400,lower*.5):continue
                # This is an optional quality polish of already valid areas.
                # Do not sacrifice a satisfactory neighbour to improve a weaker
                # edge elsewhere. Required major-divider repairs run earlier.
                if any(lower<=len(old['members'])<=upper and not lower<=count<=upper
                       for old,count in zip((left,right),counts)):
                    audit['rejections'].append({'counts':counts,'reason':'Would move a satisfactory area outside its preferred range'})
                    continue
                ownership={i:k for k,c in enumerate(children) for i in c['members']}
                quality=assess(option['geometry'],ownership,points,buckets,geography)
                if quality['street_breaks'] or quality['alley_side_splits']:
                    audit['rejections'].append({'counts':counts,'reason':'Street/alley violation','quality':quality});continue
                if any(hard_separator(c['geometry'],[points[i] for i in c['members']],geography) for c in children):continue
                from .access import disconnected_count,respects_separations
                if not respects_separations(children,geography):continue
                if disconnected_count(children,points,geography)>disconnected_count([left,right],points,geography)+5:
                    audit['rejections'].append({'counts':counts,'reason':'Would combine disconnected road populations'});continue
                after=affected(a,b,*children)
                if before-after<.2:continue
                options.append((after,canonical(option['geometry']),option,quality))
            if not options:continue
            after,_,option,quality=min(options,key=lambda item:item[:2]);children=option['children']
            identifier='landuse-repair-'+hashlib.sha256(canonical(option['geometry']).encode()).hexdigest()[:16]
            owners={i:k for k,c in enumerate(children) for i in c['members']}
            allowed={key for key in option['flexible_groups'] if len({owners[i] for i in buckets.get(key,[]) if i in owners})>1}
            split_frontage_buckets(buckets,allowed,owners)
            evidence[identifier]={'geometry':option['geometry']}
            ledger.append({'id':identifier,'name':'Supported school / park / commercial edge','category':'natural_area_split',
                'rank':3,'stage':'land-use boundary quality','state':'CHOSEN','chosen_for_split':True,
                'source_ids':option['source_ids'],'reason':'A complete mapped non-residential edge improves all affected boundaries over an ordinary-road seam.',
                'quality_after':quality,'boundary_strength':option['strength'],'counts':[len(c['members']) for c in children],
                'road_space_completions':option['road_space_completions'],
                'frontage_exception_ids':sorted(key[1] for key in allowed)})
            for target,child in zip((a,b),children):
                regions[target]={**regions[target],**child,'links':[],
                    'parents':left['parents']|right['parents'],'boundaries':left['boundaries']+right['boundaries']+[identifier],
                    'landuse_boundary':True,
                    'continuity_corridor':None,'continuity_support':None,'boundary_quality':quality}
            audit['changes'].append({'candidate':identifier,'previous_counts':[len(left['members']),len(right['members'])],
                'counts':[len(c['members']) for c in children],'score_before':round(before,6),'score_after':round(after,6),
                'source_ids':option['source_ids'],'moved_addresses':len(left['members']^children[0]['members'])})
            progress(71,'Retaining a stronger school or commercial boundary with complete service ownership')
            changed=True
        if not changed:break
    return regions,audit
