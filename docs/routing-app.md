# Monday routing in the app

Open http://127.0.0.1:8765 and choose **Truck routes** after loading the service
areas. Operating parameters are prefilled and editable. Generate both route
plans starts one cancellable local worker. Reloading reconnects to that job.
Road calculations and complete section orders are cached.

Download **Truck review HTML** for a self-contained map with stream, truck and
load selectors, original address points, pickup sequence, directional arrows,
street names, work areas and full yard/disposal travel. The file works offline
without a basemap provider. Click areas or addresses for details. The app also
exports schedules, pickup order, road lines, work-area polygons and review JSON.
Everything stays in `outputs/2026-11-04_monday_map` and its existing audit area.

## Current operating inputs

- Monday: 21,507 AddressIds, one garbage pickup and one recycling pickup each.
  Preserve separate source identities and original coordinates.
- Current scenario: curbside, collection on the right. Opposite curbs require
  correct-direction passes. Access inferred from GIS is separate from confirmation.
- Yard 385 Eagle Drive. Crew 06:15; 15-minute pretrip/FLHA; depart 06:30.
  Thirty minutes total paid breaks; no extra lunch, posttrip or fueling.
- Earliest acceptable return **14:30**, preferred **15:30-16:45**, latest **16:45**, with no artificial waiting, needless dumps or
  longer driving to meet the earliest time. Eight paid hours is the overtime
  threshold. The latest return means 10.5 paid hours, including 2.5 overtime hours. Minimum paid day: four
  hours. Minimize trucks first, then total paid worker time within the window.
- Garbage: ASL, preferred 580-650 pickups/load, target 615, hard maximum 650.
  Nine tonnes is a separate payload limit; independent mass validation requires
  kg/pickup. Count capacity alone cannot prove compliance with that mass limit.
- Recycling: rear load, preferred 1,200-1,350/load, target 1,300. The user-confirmed
  2% tolerance above the normal maximum gives an absolute limit of 1,377.
  Above-normal pickups incur a soft penalty; garbage has zero tolerance.
  Two loads per truck is a reference, not a fixed limit.
- Target at least 60% of normal capacity on every dump: 390 garbage and 810
  recycling pickups, including the final load. A shortfall incurs 30 score
  seconds per pickup, and stays visible as an unmet utilization target. Final
  unloading remains mandatory. Scores never become elapsed or paid time.
- Garbage stationary service: 12.5 seconds, within 10-15 supplied. Active time
  per load is max(road plus service, pickups / 3.25 per minute), using the user's
  3-3.5 combined pace. Add only the shortfall, never both complete times.
- Recycling stationary service: 8.5 seconds, within 7-10 supplied, plus measured
  driving. The garbage combined-pace floor does not apply to recycling.
- Garbage receiver: Brady Landfill, 1777 Brady Road. Recycling receiver: Canada
  Fibers / GFL MRF, 335 Mazenod Road. Both use 06:00-18:00 and 15 minutes total
  onsite per visit. Brady summer hours can be edited to 05:00-19:00.
  Final unloading is required before the truck returns to the yard.
- Use mapped facility road access. Gate assignment is outside routing scope.
- General OSRM time / 0.95; active time / 0.855. Confirmed reversals of at least
  150 degrees add 30 seconds outside those factors; 60 seconds is a sensitivity.
  The local car profile does not certify truck-size or field turn restrictions.

## Route construction and truck allocation

Solve each complete section as one asymmetric directed-street-pass problem,
with yard/receiver entry and exit alternatives. Bounded HTTP tables assemble
that complete problem; the 800-location infrastructure ceiling is not a reason
to split truck ownership or restart a sequence at the depot.

Then compare connected, nearby section groups using actual road costs. A truck
can finish one section, carry unused capacity into the next, unload partway
through that next section and resume it. Dump breaks are between physical
pickup sites; co-located IDs remain in one load. Do not impose a dump at every
section seam. Do not hardcode a north-to-south route or the user's example roads.

Disconnected service components can link to their nearest road-accessible
neighbours. These links explicitly record the real gap and road distance;
they do not fabricate shared polygon boundaries or combine random distant work.

A bounded connected-set search keeps geographically diverse candidates at
successive sizes up to ten work areas, using estimated complete-day time rather
than preferring the largest address counts. Each depth retains up to 1,200
geographically diverse groups. Ranking includes estimated intermediate receiver
round trips; this heuristic does not add a new feasibility veto or alter actual
route clocks. Earlier tested territories remain
candidates after refinement. The connected owned territory can include charged
transit through an already served piece; collecting each work area remains one
continuous visit. The best complete measured iteration is retained if later
refinement worsens the result. Complete section orders are shortlisted
using yard/inter-section/receiver travel. Whole-pass load plans screen candidates;
promising and selected territories are refined to exact physical-site dump
positions before publication. Explicit candidates retain complete planning
parents with nearby companions. A further bounded exchange search tests moves
and reciprocal swaps that reunite section pieces; both resulting territories
must remain connected. Actual road/load costs are evaluated before the whole
fleet is reassigned. Each additional truck owning part of one planning section
incurs a fragmentation penalty; subdivisions need not have different drivers.

CP-SAT covers every work area once. First test a complete 14:30-16:45 window
cover. Within that window, prioritize fewer trucks, less dump-fill shortfall,
less excess road connection for small pockets, fewer split planning owners, then total paid time, preferred return and overtime. If the window
cannot be satisfied by the tested pool, minimize latest-return violation first,
then those economic objectives, with early-return shortfall reported afterwards.
This avoids rewarding needless driving to manufacture a later return. An early
route remains an explicit exception. Solver OPTIMAL
is only within the tested candidate pool, not a global fleet-minimum proof.
Truck count is a solver output. The reported fleet of 45 is comparison only,
never a hard solve cap. The user reports 17 garbage and 12 recycling trucks
currently and believes ten recycling trucks are achievable. Compare with ten
only after solving; never provide ten as the required number of vehicles. The
operating form displays comparisons without a truck-count input. An independent
test changes the comparison from 1 to 99 and obtains the identical allocation.

Operational subdivisions can rebalance short or overlong days without changing
the selected planning polygons. Only finite mapped municipal, park, major-road,
continuous City-street or connected street/park boundaries are considered.
Street passes, occupied parcels and opposing alley sides remain whole. Rejected
boundaries and unresolved return windows remain visible. No named-road or MON-ID
exceptions occur in algorithm code. Pickup exports retain `Section` and add
`WorkArea`; load boundaries and truck ownership are separate concepts.

Every selected route is replayed with actual OSRM legs: dispatch, collection,
every intermediate RF visit, breaks, final unloading and return. Source points
remain separate from derived road access. Cached local requests have finite
budgets/timeouts and no automatic retries. Default map review is offline;
optional app street detail retains the bounded OpenFreeMap policy.

Postal street names do not force pickup access onto the outside of a complex.
Eligible closer internal service roads must connect through actual mapped nodes
to the postal street. Preserve ordinary frontage, private/access/construction
restrictions and right-side direction; reject cross-street projections. Internal
anchors use a tight 8 m OSRM snap radius. Independent checks measure the original
property offset as well as whether the replay reaches the inferred anchor.
Large setbacks and conflicting direction/access evidence remain unresolved.

## Current result

Routing 1.6 is published in the existing Monday folder. The expanded search took
53 minutes 39 seconds using four local workers, a 12-second section budget and
120-second staged fleet budget. It tested 33, 54, 77 and 91 work-area layouts,
retaining iteration 1: 54 operational work areas inside 33 planning sections.
Later refinements did not improve the complete result. Ten recycling trucks was
not demonstrated. Solver OPTIMAL describes the tested pool only.

| Stream | Trucks | Pickups/truck | Loads | Paid hours | Yard returns |
| --- | ---: | ---: | ---: | ---: | --- |
| Garbage | 18 | 1,195 | 36 | 170.16 | 15:00-16:22 |
| Recycling | 11 | 1,955 | 21 | 109.86 | 15:37-16:44 |

All 43,014 service events reconcile, each original AddressId exactly once per
stream. All 57 dump visits meet the 60% fill target. Garbage loads range from
454 to 650 pickups; recycling loads range from 811 to 1,375, within its explicit
1,377 maximum. Every truck includes its final unload and yard return. No truck
returns before 14:30 or after 16:45; five garbage routes return before the
preferred 15:30. No waiting, needless dump or extra driving pads a day.
Total paid route time is 280.02 hours, including 48.02 hours above the eight-hour
threshold. This remains a planning result, not a globally minimal or field-
certified required fleet. The reported 17 garbage / 12 recycling operation
included longer shifts and is comparison only, not a like-for-like validation.

The small western pockets share G-17 and R-10 with their western neighbours,
including MON-023. These are outcomes, not named assignments in the algorithm.
Recycling has zero small-pocket road-connection regret in the selected plan.
Planning polygons, protected road passes and physical pickup sites remain whole.

Independent replay again checks all 62 addresses in the first illustrated
complex (G-04 / R-02) and all 20 Fairhaven units (G-15 / R-03). Both have nearby,
correctly directed path segments with the source property on the right. Maximum
pickup offsets remain 30.46 m and 24.25 m. One first-complex address retains its
detailed direction warning. Across Monday, 313 source properties remain over
80 m from inferred pickup access and 16 direction diagnostics remain. Those
warnings, other access uncertainties and the unknown garbage mass per pickup
are not erased by passing coverage/capacity-count checks.

Result key: `9ae48ace9d44518a97bd6855e5908fc61867ce1d318e1ef3523e7950580eb227`.
The original 53m39s solve is
`4b0d70c09a8d787803f2e2abd0bf251799419a8a645c550a8e4b4c46e3a8d238`.
A seven-second cached presentation refresh corrected the HTML window separator
and clarified that the fleet figure is comparison only. Independent comparison
proves every route, load, clock, setting and work-area geometry is unchanged.

All six files match the API ZIP. The offline HTML is served at
http://127.0.0.1:8765/truck-maps.html. Chrome verified final fleet totals, route
selection, pickup details, comparison labels and full yard/receiver travel,
without enabling external basemaps. Tests: 157 pass. Independent receipts are
`routing-independent-validation.json`, `internal-access-replay-validation.json`,
`routing-api-validation.json` and `productive-day-chrome-validation.json` in
`audit/partition_app`. The original workbook and five coordinate deliverables
remain byte-identical. Earlier complete deliveries and search receipts stay in
that same audit folder.

## Local parallel computation

OR-Tools runs in local Windows Python; Docker hosts OSRM. New calculations
default to two local CPU worker processes, editable from one to four and capped
to leave one logical CPU available. Whole section alternatives and complete
route/load candidates run independently. One coordinator owns HTTP/SQLite cache
access, and a single fleet-wide cover still assigns all work for each stream.
Do not split the address universe into independently assigned geographical halves.

The queue holds at most two tasks per worker. Workers are joined after each
phase, including cancellation/failure; there is still only one app calculation
at a time. Completed section orders from an interrupted job can resume when the
exact geometry/settings key and both stream coverages match; partially finished
sections are solved again. The section-search setting is twelve seconds (six seconds
for each entry/exit alternative). Compatible complete orders from a shorter
search are retained alongside the new orders, using exact geometry/operating
cache keys and checking every directed pass. Fleet cover has a 120-second budget per staged
solve, with the largest share assigned to minimizing trucks. These are solver
time limits, not total elapsed runtime. The
four-refinement/two-hour job limits remain. Result JSON includes phase
wall times to distinguish CPU search, road work and replay.

The cached Monday benchmark used no HTTP requests and preserved the published
result. With two workers, 260 complete recycling load evaluations took 20.433 s
serially versus 11.841 s in parallel, with identical loads and clocks (1.726x).
Four alternatives for a complete 169-pass section took 8.015 s versus 5.260 s
(1.524x); every pass remained present. Time-limited section orders may vary.
Both measurements include process startup/shutdown. A smaller 26-plan sample
had little improvement because startup dominated. These are component results,
not a measured end-to-end speedup. The earlier 32-truck plan took 58m59s
serially. The earlier 33-truck correction took 35m33s, but changed access/scoring
and cache reuse mean that difference is not a controlled parallel speedup test.
