"""Whole-section sequencing, real receiver load breaks and connected fleet cover."""
from collections import defaultdict
import itertools
import math

import numpy as np
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from ortools.sat.python import cp_model

from .settings import clock_seconds,stream_settings,load_limits


def solve_section(matrix, incoming, outgoing, seconds):
    """One complete asymmetric problem over directed street-side runs."""
    n=len(incoming)
    if n==1:
        return [0]
    manager=pywrapcp.RoutingIndexManager(n+1,1,n)
    router=pywrapcp.RoutingModel(manager)
    def cost(i,j):
        a,b=manager.IndexToNode(i),manager.IndexToNode(j)
        value=0 if a==b else incoming[b] if a==n else outgoing[a] if b==n else matrix[a,b]
        return min(10**9,round(value*100)) if math.isfinite(value) else 10**9
    callback=router.RegisterTransitCallback(cost)
    router.SetArcCostEvaluatorOfAllVehicles(callback)
    params=pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy=routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic=routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(seconds)
    solution=router.SolveWithParameters(params)
    if solution is None:
        raise ValueError("The complete directed section could not be sequenced; no arbitrary chunks were substituted.")
    order=[]; index=router.Start(0)
    while not router.IsEnd(index):
        node=manager.IndexToNode(index)
        if node<n: order.append(node)
        index=solution.Value(router.NextVar(index))
    if sorted(order)!=list(range(n)):
        raise ValueError("Section sequencing lost or repeated a street-side run.")
    return order


def load_plan(sequence, internal, joins, dispatch, to_rf, from_rf, rf_to_yard, settings, stream):
    """DP chooses dump positions between physical pickup sites, never mid-site.

    Each index denotes the next run. RF cost replaces the direct collection leg.
    Paid/elapsed full-day clocks include every departure and final unloaded return.
    """
    settings=stream_settings(settings,stream)
    n=len(sequence);cfg=settings[stream];normal,cap=load_limits(settings,stream)
    minimum_fill=math.ceil(normal*settings['minimum_dump_fill_percent']/100)
    if not n or cap<1 or any(g['count']>cap for g in sequence):
        return None
    active=settings['active_speed_factor'];general=settings['general_speed_factor']
    counts=np.r_[0,np.cumsum([g['count'] for g in sequence])]
    work=np.r_[0,np.cumsum([internal[g['id']]+g['count']*settings['pickup_seconds'] for g in sequence])]
    travel=np.r_[0,np.cumsum([0]+list(joins))]
    start=clock_seconds(settings['crew_start'])+60*(settings['pretrip_minutes']+settings['fueling_minutes'])
    opens=clock_seconds(cfg['receiver']['opens']);closes=clock_seconds(cfg['receiver']['closes'])
    unload=cfg['receiver']['onsite_minutes']*60
    dp=np.full(n+1,np.inf);prev=[None]*(n+1);dp[0]=start
    preferences=np.zeros(n+1)
    entries=np.array([from_rf[g['id']]/general for g in sequence],dtype=float)
    entries[0]=dispatch[sequence[0]['id']]/general
    exits=np.array([to_rf[g['id']]/general for g in sequence],dtype=float)
    for b in range(1,n+1):
        a=np.arange(np.searchsorted(counts,counts[b]-cap),b)
        collection=work[b]-work[a]+travel[b]-travel[a+1]
        if settings['use_observed_collection_pace']:
            collection=np.maximum(collection,(counts[b]-counts[a])*60/settings['active_collection_pickups_per_minute'])
        arrival=dp[a]+entries[a]+collection+exits[b-1]
        waiting=np.maximum(0,opens-arrival)
        end=arrival+waiting+unload
        # Carry one daily break after the first dump through every later load.
        after_break=end+np.where(a==0,60*(settings['break_minutes']+settings['unpaid_lunch_minutes']),0)
        quantity=counts[b]-counts[a]
        # A final unload remains mandatory, but a nearly empty final trip is
        # not free in the objective. Keep every score outside the real clock.
        fill=np.maximum(0,cfg['capacity_low']-quantity)*settings['load_underfill_seconds_per_pickup'] if b<n else np.zeros(len(a))
        fill=fill+(np.abs(quantity-cfg['capacity'])*.02 if b<n else 0)
        fill+=np.maximum(0,minimum_fill-quantity)*settings['dump_shortfall_seconds_per_pickup']
        fill+=np.maximum(0,quantity-normal)*settings['overflow_seconds_per_pickup']
        score=after_break+preferences[a]+fill+np.maximum(0,end-closes)*1000
        j=int(np.argmin(score))
        if math.isfinite(score[j]):
            begin=int(a[j]);dp[b]=float(after_break[j])
            preferences[b]=float(preferences[begin]+fill[j])
            prev[b]=(begin,float(entries[begin]),float(collection[j]),float(exits[b-1]),
                     float(arrival[j]),float(waiting[j]),float(end[j]))
    if prev[n] is None:return None
    loads=[];b=n
    while b:
        a,enter,collection,dump_drive,arrival,waiting,end=prev[b]
        loads.append({'begin':a,'end':b,'pickups':int(counts[b]-counts[a]),'enter_seconds':enter,
            'collection_seconds':collection,'dump_drive_seconds':dump_drive,'receiver_arrival_seconds':arrival,
            'wait_seconds':waiting,'unload_seconds':unload,'receiver_departure_seconds':end})
        b=a
    loads.reverse()
    elapsed=float(dp[n])+rf_to_yard/general-start+60*(settings['pretrip_minutes']+settings['fueling_minutes']+
        settings['posttrip_minutes'])
    paid=max(elapsed-settings['unpaid_lunch_minutes']*60,settings['minimum_paid_hours']*3600)
    # The break is inserted after a real dump and before remaining work; replay
    # checks receiver windows with this chronological schedule as well.
    return {'loads':loads,'seconds':elapsed,'paid_seconds':paid,'capacity':cap,
            'normal_capacity':normal,'minimum_fill_pickups':minimum_fill,
            'dump_fill_shortfall':sum(max(0,minimum_fill-l['pickups']) for l in loads),
            'underfilled_dump_count':sum(l['pickups']<minimum_fill for l in loads),
            'load_preference_penalty':float(preferences[n]),
            'early_seconds':max(0,clock_seconds(settings['earliest_return'])-clock_seconds(settings['crew_start'])-elapsed),
            'preferred_return_shortfall_seconds':max(0,clock_seconds(settings.get('preferred_return',settings['earliest_return']))-clock_seconds(settings['crew_start'])-elapsed),
            'overtime_seconds':max(0,paid-settings['preferred_paid_hours']*3600),
            'late_seconds':max(0,clock_seconds(settings['crew_start'])+elapsed-clock_seconds(settings['latest_return']))}


def connected_sets(ids, adjacency, counts, maximum_count, max_sections=10, layer_limit=1200,
                   estimate=None, time_limit=None, seeds=(), rank_estimate=None):
    found={frozenset([s]) for s in ids};frontier=set(found)
    ranking=rank_estimate or estimate
    # Bounded connected territories; no geographic nearest-neighbour fake links.
    for _ in range(1,max_sections):
        next_frontier=set()
        for group in sorted(frontier,key=lambda x:tuple(sorted(x))):
            neighbours=set().union(*(adjacency[s] for s in group))-set(group)
            for s in sorted(neighbours):
                candidate=group|{s}
                if (candidate not in found and sum(counts[x] for x in candidate)<=maximum_count
                        and (estimate is None or estimate(candidate)<=time_limit)):
                    next_frontier.add(candidate)
        # Keep a geographically diverse beam at EACH depth. A dense small-area
        # district must not consume the budget before larger connected chains
        # are considered. This limits search, never service coverage.
        if len(next_frontier)>layer_limit:
            ranked=sorted(next_frontier,key=lambda g:(
                abs(time_limit-ranking(g)) if ranking else -sum(counts[s] for s in g),tuple(sorted(g))))
            by_member={s:iter([g for g in ranked if s in g]) for s in ids}
            retained=set()
            while len(retained)<layer_limit:
                changed=False
                for choices in by_member.values():
                    candidate=next((g for g in choices if g not in retained),None)
                    if candidate is not None:retained.add(candidate);changed=True
                    if len(retained)>=layer_limit:break
                if not changed:break
            next_frontier=retained
        found.update(next_frontier);frontier=next_frontier
        if not frontier:break
    # Finer work areas must not silently remove an earlier tested territory
    # merely because it fell outside a bounded search beam.
    found.update(frozenset(g) for g in seeds if g and set(g)<=set(ids))
    return sorted(found,key=lambda x:(len(x),tuple(sorted(x))))


def section_orders(members, adjacency, costs):
    members=sorted(members)
    visited={members[0]}
    while True:
        expanded=visited|set().union(*(adjacency[s]&set(members) for s in visited))
        if expanded==visited:break
        visited=expanded
    if visited!=set(members):return []
    if len(members)<=4:
        return [list(p) for p in itertools.permutations(members)]
    # The owned territory must be connected. Consecutive collection pieces do
    # not have to share an edge: travel through already served owned territory
    # is legitimate and is charged using the actual road connection.
    orders=[]
    def walk(order,remaining,local):
        if not remaining:
            local.append(order);return
        choices=sorted(remaining,key=lambda x:(costs[order[-1],x],x))
        for nxt in choices[:2]:
            if len(local)>=4:return
            walk(order+[nxt],remaining-{nxt},local)
    # The former global quota was exhausted by the alphabetically first start.
    # Give every possible entry area its own bounded alternatives, then rank
    # them with actual yard/receiver costs in the caller.
    for start in members:
        local=[];walk([start],set(members)-{start},local);orders.extend(local)
    return orders


def territory_connected(members, adjacency):
    members=set(members)
    if not members:return False
    visited={min(members)}
    while True:
        more=visited|set().union(*(adjacency[s]&members for s in visited))
        if more==visited:return visited==members
        visited=more


def cohesive_candidates(ids, adjacency, parents, counts, max_count):
    """Explicitly retain whole parents and their nearby companion work."""
    families=defaultdict(set)
    for s in ids:families[parents.get(s,s)].add(s)
    result=set()
    for family in families.values():
        neighbours=set().union(*(adjacency[s] for s in family))-family
        options=[family,*[family|{n} for n in neighbours],
                 *[family|families[parents.get(n,n)] for n in neighbours]]
        for members in options:
            if len(members)<=10 and sum(counts[s] for s in members)<=max_count and territory_connected(members,adjacency):
                result.add(frozenset(members))
    return result


def reunion_exchanges(chosen, adjacency, parents, counts, max_count, limit=80):
    """Propose paired moves/swaps that reunite planning sections, city-wide.

    Both resulting territories must remain connected. The caller evaluates
    actual entry/exit roads, loads and clocks and re-solves the entire cover;
    these proposals never directly assign a named example to a truck.
    """
    proposals={}
    for a,b in itertools.permutations([set(c['sections']) for c in chosen],2):
        ap={parents.get(s,s) for s in a};bp={parents.get(s,s) for s in b}
        for parent in ap&bp:
            incoming={s for s in b if parents.get(s,s)==parent}
            outgoing=[set(),*[{s} for s in a if parents.get(s,s)!=parent],
                      *[{s for s in a if parents.get(s,s)==p} for p in ap-{parent}]]
            for back in outgoing:
                left=(a|incoming)-back;right=(b-incoming)|back
                if not left or not right or max(len(left),len(right))>10:continue
                if max(sum(counts[s] for s in left),sum(counts[s] for s in right))>max_count:continue
                improvement=len(ap)+len(bp)-len({parents.get(s,s) for s in left})-len({parents.get(s,s) for s in right})
                if improvement<=0 or not territory_connected(left,adjacency) or not territory_connected(right,adjacency):continue
                imbalance=abs(sum(counts[s] for s in left)-sum(counts[s] for s in a))
                key=tuple(sorted([tuple(sorted(left)),tuple(sorted(right))]))
                proposals[key]=(-improvement,imbalance,key)
    result=set()
    for _,_,pair in sorted(proposals.values()):
        if len(result|{frozenset(s) for s in pair})>limit:break
        result.update(frozenset(s) for s in pair)
    return result


def consolidation_candidates(chosen, adjacency, parents, counts, max_count,
                             estimate, time_limit, limit=160, rank_estimate=None):
    """Remove a short truck by absorbing its complete nearby work, or rebalance.

    Count/time bounds only screen proposals. Actual roads, physical-site load
    breaks and a whole-fleet cover decide whether any proposal is used.
    """
    territories=[frozenset(c['sections']) for c in chosen]
    proposals={}
    ranking=rank_estimate or estimate
    def eligible(members):
        return (members and len(members)<=12 and sum(counts[s] for s in members)<=max_count
                and territory_connected(members,adjacency) and estimate(members)<=time_limit)
    def add(groups,priority):
        groups=[frozenset(g) for g in groups if g]
        if not groups or not all(eligible(g) for g in groups):return
        # A complete group of replacement territories stays together in the
        # search budget so pruning cannot retain half of a useful exchange.
        key=tuple(sorted(tuple(sorted(g)) for g in groups))
        fragmentation=sum(len({parents.get(s,s) for s in g}) for g in groups)
        values=[ranking(g) for g in groups]
        proposals[key]=(priority,fragmentation,sum(values),max(values)-min(values),key)
    for a,b in itertools.combinations(territories,2):
        if not set().union(*(adjacency[s] for s in a)).intersection(b):continue
        add([a|b],0)
        # Transfers need not reunite siblings to improve truck utilization.
        for left,right in [(a,b),(b,a)]:
            units=[{s} for s in left]
            units += [{s for s in left if parents.get(s,s)==p} for p in {parents.get(s,s) for s in left}]
            for unit in units:
                add([left-unit,right|unit],1)
    # A truck can disappear by sharing its work among several adjacent trucks.
    # Keep each work area intact; try whole parents before individual pieces.
    donors=sorted(range(len(chosen)),key=lambda i:(chosen[i]['plan']['seconds'],tuple(sorted(territories[i]))))
    for donor in donors:
        remaining=territories[donor]
        neighbours=[i for i,t in enumerate(territories) if i!=donor and
            set().union(*(adjacency[s] for s in remaining)).intersection(t)]
        if not 2<=len(neighbours)<=6:continue
        for whole_parents in [True,False]:
            units=({frozenset(s for s in remaining if parents.get(s,s)==p) for p in {parents.get(s,s) for s in remaining}}
                   if whole_parents else {frozenset([s]) for s in remaining})
            states=[{i:territories[i] for i in neighbours}]
            for unit in sorted(units,key=lambda u:(-sum(counts[s] for s in u),tuple(sorted(u)))):
                expanded={}
                for state in states:
                    for receiver in neighbours:
                        merged=state[receiver]|unit
                        if not eligible(merged):continue
                        new={**state,receiver:merged}
                        key=tuple(tuple(sorted(new[i])) for i in neighbours)
                        expanded[key]=new
                states=sorted(expanded.values(),key=lambda st:(sum(ranking(g) for g in st.values()),
                    max(ranking(g) for g in st.values()),tuple(tuple(sorted(st[i])) for i in neighbours)))[:24]
                if not states:break
            for state in states[:8]:add(list(state.values()),0)
    # Removing a truck sometimes needs both remaining trucks to give up work
    # as well as receive it. Repack neighbouring triples into two connected
    # territories instead of restricting the search to one-way absorption.
    triples=[]
    for indexes in itertools.combinations(range(len(territories)),3):
        union=frozenset().union(*(territories[i] for i in indexes))
        if len(union)>18 or sum(counts[s] for s in union)>2*max_count or not territory_connected(union,adjacency):continue
        triples.append((sum(chosen[i]['plan']['seconds'] for i in indexes),tuple(sorted(union)),union))
    for _,_,union in sorted(triples)[:16]:
        possible=connected_sets(sorted(union),{s:adjacency[s]&union for s in union},counts,max_count,
            max_sections=12,layer_limit=96,estimate=estimate,time_limit=time_limit,rank_estimate=ranking)
        for left in possible:
            right=union-left
            if right and min(left)<min(right) and eligible(right):add([left,right],0)
    result=set()
    for *_,key in sorted(proposals.values()):
        pair={frozenset(g) for g in key}
        if len(result|pair)>limit:continue
        result.update(pair)
    return result


def pocket_affinity_regret(members,adjacency,counts,costs,threshold=100):
    """Excess road connection for a small pocket versus its closest neighbour.

    This is an assignment score, never invented driving time. Capacity/day
    feasibility and fleet count still take precedence over this preference.
    """
    members=set(members);regret=0.
    for pocket in members:
        if counts[pocket]>=threshold:continue
        neighbours=adjacency[pocket]
        owned=neighbours&members
        if not neighbours or not owned:continue
        def road(s):return min(costs.get((pocket,s),math.inf),costs.get((s,pocket),math.inf))
        best=min(map(road,neighbours));assigned=min(map(road,owned))
        if math.isfinite(best) and math.isfinite(assigned):regret+=max(0,assigned-best)
    return round(regret)


def fleet_cover(section_ids, candidates, seconds, overtime_first=False, parent_sections=None):
    model=cp_model.CpModel()
    variables=[model.NewBoolVar(f'c{i}') for i in range(len(candidates))]
    for section in section_ids:
        model.Add(sum(variables[i] for i,c in enumerate(candidates) if section in c['sections'])==1)
    # Complete on-time coverage comes first. Within that, minimize vehicles and
    # total paid worker time. Avoiding one overtime minute cannot buy a truck.
    late=sum(math.ceil(c['plan']['late_seconds'])*v for c,v in zip(candidates,variables))
    early=sum(math.ceil(c['plan'].get('early_seconds',0))*v for c,v in zip(candidates,variables))
    preferred=sum(math.ceil(c['plan'].get('preferred_return_shortfall_seconds',0))*v for c,v in zip(candidates,variables))
    overtime=sum(round(c['plan']['overtime_seconds'])*v for c,v in zip(candidates,variables))
    trucks=sum(variables)
    total=sum(round(c['plan'].get('paid_seconds',c['plan']['seconds']))*v for c,v in zip(candidates,variables))
    shortfall=sum(c['plan'].get('dump_fill_shortfall',0)*v for c,v in zip(candidates,variables))
    pocket_regret=sum(c.get('pocket_affinity_regret',0)*v for c,v in zip(candidates,variables))
    weak_seams=sum(c.get('weak_boundary_separation_cost',0)*v for c,v in zip(candidates,variables))
    parents={s:(parent_sections or {}).get(s,s) for s in section_ids}
    # Each extra truck touching one planning parent is one fragmentation.
    # Work areas may remain useful load/order units while one driver owns all
    # siblings. Do not reward a clean geometric split as an end in itself.
    fragmentation=sum(len({parents.get(s,s) for s in c['sections']})*v for c,v in zip(candidates,variables))-len(set(parents.values()))
    # First try to satisfy the entire return window. If this tested candidate
    # pool cannot, preserve economic priorities in an explicit exception plan.
    # Reducing a partial early-return shortfall must not reward extra driving
    # or an extra truck just to make the clock later.
    window=model.NewBoolVar('require_return_window')
    model.Add(late==0).OnlyEnforceIf(window)
    model.Add(early==0).OnlyEnforceIf(window)
    model.AddAssumption(window)
    solver=cp_model.CpSolver();solver.parameters.num_search_workers=1
    solver.parameters.random_seed=0;solver.parameters.max_time_in_seconds=max(.05,seconds*.1)
    probe=solver.Solve(model)
    strict=probe in {cp_model.OPTIMAL,cp_model.FEASIBLE}
    model.ClearAssumptions()
    model.Add(window==int(strict))
    stages=['RETURN_WINDOW_'+solver.StatusName(probe)]
    chosen=[c for c,v in zip(candidates,variables) if solver.Value(v)] if strict else None
    if strict:
        objectives=[overtime,trucks,shortfall,pocket_regret,fragmentation,weak_seams,total,preferred] if overtime_first else [trucks,shortfall,pocket_regret,fragmentation,weak_seams,total,preferred,overtime]
    else:
        objectives=[late,overtime,trucks,shortfall,pocket_regret,fragmentation,weak_seams,total,early,preferred] if overtime_first else [late,trucks,shortfall,pocket_regret,fragmentation,weak_seams,total,early,preferred,overtime]
    for objective in objectives:
        # Spend most of the bounded fleet budget on the economically primary
        # truck count. Overtime and other tie-breakers must not consume it.
        solver.parameters.max_time_in_seconds=max(.05,seconds*(.45 if objective is trucks else .05))
        model.Minimize(objective)
        status=solver.Solve(model)
        stages.append(solver.StatusName(status))
        if status not in {cp_model.OPTIMAL,cp_model.FEASIBLE}:break
        chosen=[c for c,v in zip(candidates,variables) if solver.Value(v)]
        model.Add(objective==round(solver.ObjectiveValue()))
        model.ClearHints()
        for variable in variables:model.AddHint(variable,solver.Value(variable))
    if chosen is None:raise ValueError('No complete section assignment found in the fleet search budget.')
    return chosen,stages
