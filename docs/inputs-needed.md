# Inputs for Winnipeg daily fleet sizing

## Wednesday park corridor and publication repair - 2026-11-16

Engine 4.6 result
`7899007b2c8f6638593e9b22f0b307abfafc5c242396fca196067fec46f388e5`
repairs the user's Wednesday QA. The full 22,202-address check took 503.639
seconds, has zero native/published overlap and preserves every source point,
20,724 serviced-parcel checks, major dividers and street/alley continuity.
The original 1,454-address Tyndall Park cohort becomes 911/543 along the mapped
school/park corridor. Useful children may be below the preferred minimum;
900-1,100 is a scoring preference, not an eligibility veto on a good split.

The original 30.013593 m2 published overlap consisted of four-centimetre slivers
caused by differing shared-edge vertex spacing during inverse projection.
Shared metric vertices are now inserted on both owners before publication,
with unchanged real geometry and the overlap failure gate retained. Complete
connected school/park/commercial alternatives are generated; checked short
road-space closures cannot cross properties. Imprecise public land-use outlines
are clipped away from serviced residential parcel components.

Saved Wednesday GeoJSON/assignments/review and the live result API were checked.
Evidence and backup remain under the existing delivery's `audit/partition_app/`,
including `wednesday_boundary_validation_2026-11-16.json` and the offline
before/after PNG. All 25 other root delivery files and the original intake
workbook remain unchanged. Tuesday stays the active app day. The user still
uploads inputs manually; no truck solve was started. Reusing the identical
Wednesday file/range can now reuse the validated cached result.

Wednesday remains PROVISIONAL: WED-005 (1,147) and WED-010 (1,975) are above the
requested maximum. Their unresolved reasons remain visible; no overlap or
coverage pass establishes ideal boundaries or field-verified pickup access.

## Confirmed coordinates and selectable operations - 2026-11-16

This supersedes the earlier pending-estimate entries below. The user corrected
six locations and confirmed seven existing coordinates. Thursday and Friday's
existing workbooks now contain no unconfirmed estimates. Independent saved-file
checks verify 50 changed cells (22 Thursday, 28 Friday), all other cells and
formatting unchanged, and Wednesday's byte-identical file. All 22,202 / 19,316 /
19,764 weekday AddressIds and original six intake fields reconcile. The review
keeps source labels and reviewed labels separately, including the fractional
Selkirk and Sherbrook records. Private overrides preserve the user's exact
coordinates and provenance. Backups, before/after evidence and validation are in
`outputs/2026-11-16_weekday_uploads/audit/`; no files were uploaded by the agent.

The user requested a reusable facility editor: add/remove depots and receivers,
then choose one or multiple locations for a run. Multiple selected locations
produce measured complete-day alternatives before one whole-stream fleet cover.
Each truck starts/returns at one selected depot and uses one selected receiver
for every load. Capacity ranges remain shared operating inputs per stream.

The Truck routes header now selects Garbage, Recycling, or both. Both start
selected. An empty selection cannot run. Unselected streams skip facility road
snapping, section sequencing, fleet allocation and replay; their results show
Not calculated. Scenario/cache keys, coverage checks, exports and offline truck
review retain exactly the selected streams. Failed partitions report their
actual error checks before a routing job can start. These controls pass an
isolated browser/form/API check with no public requests or address uploads,
and synthetic full pipeline checks exercise both single-stream paths.

Saved accepted service areas survive an app upgrade with their original engine
identified. Recreate service areas to apply changed boundary rules. Restarting
does not generate routes or upload inputs.

## Productive days and sparse pockets - 2026-11-06

Truck count must be calculated, never supplied as a ten-truck quota. Fleet
comparison figures are read-only in the app and excluded from allocation keys
and solver objectives. The full revised scenario uses four bounded local CPU
workers; default future settings remain two.

The expanded search uses a 12-second section budget, preserving compatible
earlier orders. Its 1,200-group beam at each size includes intermediate receiver
round trips in ranking; the optimistic feasibility screen and exact load/replay
clocks remain separate. Tests change fleet comparisons from 1 to 99 without
changing the allocation. The longer search is not a request for ten vehicles.

The user reports current operations at 17 garbage and 12 recycling trucks, with
some shifts reaching 12 hours. The user subsequently set a stronger recycling target of 10 trucks. Keep the
reported 12-truck operation as historical comparison. Use 17 garbage and 10
recycling as search benchmarks, not forced answers. Test the same 21,507 Monday pickups per stream with a
10-10.5-hour ceiling: crew 06:15, earliest acceptable return 14:30, preferred
return 15:30-16:45, absolute latest 16:45. Eight paid hours is the overtime
threshold. A 16:45 return is 10.5 paid hours and 2.5 overtime hours; do not
manufacture waiting or longer travel to fill a day. Fewer feasible trucks takes
precedence over avoiding overtime. The preferred return is secondary to actual
paid time so extra driving cannot earn a better score.

Test complete truck merges, transfers and absorption of a short truck into
several adjacent territories. Retain whole road passes, physical sites, load
limits and final unloading. Every possible section entry gets order candidates;
a global shortlist must not be exhausted by the alphabetically first entry.
The fleet solver budget is 120 seconds per staged fleet solve, prioritizing truck-count search; this is not the
end-to-end runtime. Local CPU workers remain bounded at two by default.

Apply the under-100 check to isolated service pockets within large sections,
not only the section's total count. A pocket separated from its own population
by over 500 m can be exposed on existing finite municipal/physical boundaries,
with protected street/site/parcel/alley checks. Merge with the nearest compatible
neighbour; a rail, water or major highway divider still vetoes a planning merge.
Truck ownership can combine nearby sections using actual mapped road access.
Score excess road connection to a small pocket relative to its closest neighbour;
this assignment penalty never becomes elapsed time. No example names or IDs are
algorithm exceptions.

A full R-05/R-06 counterfactual on the previous published plan covers 2,702
pickups in loads 1,336/1,366, but returns 18:29 (12h14). That exact merge does not
fit the new ceiling. Test nearby redistribution instead. The complete expanded
run now publishes 18 garbage and 11 recycling trucks: 43,014 service events,
57 dumps, all within pickup-count capacity, fill and 14:30-16:45 return limits.
Actual returns are 15:00-16:22 for garbage and 15:37-16:44 for recycling. It took
53m39s with four workers and retained the 54-work-area refinement inside the
33 planning sections. Ten recycling trucks was not demonstrated; this is not a
global minimum proof or a field-certified fleet requirement. Access diagnostics
and missing garbage mass evidence remain. The app, offline HTML and six-file
package are updated in place; 157 tests and independent reconciliation pass.
See docs/routing-app.md for exact results and provenance.


## Latest confirmed load settings - 2026-11-06

The recycling load range is normally 1,200-1,350, with a user-confirmed 2%
tolerance above the maximum: 1,377 is the absolute planning limit. Garbage's
650 maximum has no tolerance. Target at least 60% of normal capacity for every
dump, including final loads; report any unavoidable shortfall explicitly.
Keep complete planning sections together when connected exchanges can achieve
that without increasing the truck fleet or violating stronger constraints.
Internal site roads must be considered for inferred curbside pickup access.
These decisions supersede conflicting earlier capacity/final-load text below.

## Earlier fleet priorities (superseded return window) - 2026-11-06

The previous 30-garbage / 29-recycling plan was rejected for poor utilization.
Coverage and geometry checks did not make its truck allocation efficient.
The current objective is the fewest trucks, then the least paid worker time,
within a **15:00-16:00 yard-return window**. Do not add waiting, needless RF
visits or longer driving merely to make a short day appear productive. If the
search cannot satisfy the window, expose those routes as unresolved.

A truck may collect several adjacent or nearby sections. Choose section order
using actual yard, inter-section and receiver travel. Carry remaining capacity
into the next section before dumping; a necessary dump can interrupt a section
and the same truck resumes it. Connect isolated service pockets to their nearest
road-accessible territory, without inventing shared polygon boundaries. Clean
mapped operational subdivisions can rebalance work; the selected planning
sections remain unchanged. No named roads or section IDs are code exceptions.

Garbage: preferred 580-650 pickups/load, midpoint target 615, hard maximum 650;
12.5 seconds stationary plus driving, calibrated to 3-3.5 pickups/minute total
(default 3.25). Recycling: preferred 1,200-1,350/load, target 1,300, hard maximum
1,350 normally, with a confirmed 2% tolerance and absolute maximum 1,377;
7-10 seconds stationary (default 8.5) plus driving, with no garbage pace floor.
Two loads is a reference, not a fixed restriction. All dump visits, including
final loads, target at least 60% of normal capacity. Score penalties remain
separate from real clock time; final unloading is always required.

Crew 06:15, pretrip 15 minutes, departure 06:30, total breaks 30 minutes; no added
lunch/posttrip/fueling. Eight paid hours remains the overtime threshold, not a
reason to buy extra trucks. The requested return window means 8h45-9h45 paid.
Mapped yard and receiver access is sufficient; assigned gates are outside scope.
All 21,507 Monday AddressIds receive one pickup per stream. Curbside/right-side
collection is the current user-directed scenario; inferred access and garbage
mass remain limitations. See [routing app](routing-app.md) for the current run.

The app includes a self-contained offline truck-review HTML with stream, truck
and load selectors, pickup details, direction arrows and complete yard/RF trips.
All outputs and validation remain in the existing Monday delivery/audit folder.

Earlier entries below are historical and superseded where they conflict.

## Current Monday intake - 2026-11-05

The original questions below are historical. The user has now supplied the yard,
receivers/hours, visit time, pickup capacities, breaks, service pace and the
current all-curbside assumption. Follow `docs/project-brief.md` and the ignored
`data/reference/monday_routing_operating_inputs_2026-11-05.json` for the full
current record. Monday requires one garbage and one recycling pickup per
source AddressId, with separate route plans. Avoiding overtime is preferred;
route territories must comprise adjacent service sections.

Still needed for a defensible route/fleet recommendation:

- Payload evidence for independently checking the nine-tonne garbage limit;
  the first count-capacity scenario can use the supplied pickup ranges explicitly.
- Field restrictions and ambiguous pickup points as review issues, plus explicit
  treatment of isolated service outliers if they cannot join adjacent sections.

The observed 3-3.5 pickups/minute includes local driving; it must not be added
again to 10-15 seconds stationary service and modeled active driving.
For this first scenario, garbage uses ASL and recycling rear load. Treat all
addresses as curbside and collect only to the right of travel. Opposite curbs
need correct-direction passes, without doubling pickup demand. Breaks total
30 minutes overall; no extra unpaid lunch or post-trip allowance is added.
The preferred eight-paid-hour finish from 06:15 is 14:15; retain the reported
16:00 latest return as a separate outer limit. Local OSRM is verified at
http://127.0.0.1:5001 with an 800-location server table ceiling.

Reviewed 2026-10-27 after the user's scope clarification.

## What the application will answer

Calculate how many operating ASL and rear-load trucks are needed to finish
each collection day's scheduled work, how long each route takes, how many
loads and dump visits it needs, and how the resulting routes should be driven.
Show daily requirements, the peak simultaneous fleet, and a comparison with
the available 45 trucks. Keep spare allowance separate from operating trucks.
Use practical evaluated routing scenarios; do not claim a proven minimum
without the supporting optimization evidence.

Design routes from the address list and operating requirements. Miller's old
maps and route boundaries are not required. The email's 20 ASL / 12 rear-load
routes and 1,300/1,500 calls are historical comparison benchmarks, not fixed
route counts or load capacities.

## Questions to send to operations

We have 45 trucks available. To determine how many are needed to complete
each day's collections and build the Winnipeg routing application, please confirm:

1. **Which addresses are alley collection, and which are curbside?** Please
   identify this against each address in the supplied list, including any
   differences between garbage, recycling, and yard-waste pickup locations.
2. **What equipment can we use?** Which addresses require ASL or rear load,
   and where can either be used?
3. **Where do trucks start and finish?** Please provide yard addresses or
   entrance locations, departure times, and required return locations.
4. **Where does each waste stream get unloaded?** Please provide disposal-site
   locations, operating hours, typical queue/weigh/unloading times, and
   whether trucks must unload before finishing the day.
5. **How much fits in one load?** Approximate carts/calls or tonnes per load,
   separately for each truck type and waste stream. Are there restrictions
   on dump trips per day? Historical load records or driver estimates would help.
6. **What working-day limits apply?** Normal and maximum shift length,
   breaks, pre/post-trip checks, fueling time, overtime rules, and required
   completion time.
7. **What workload and collection speed should we use?** Cart/bin quantities
   and sizes, shared-bin or multi-unit arrangements, special pickups, and
   typical collection time per cart/stop or calls per hour. Please clarify
   what counts as one call.
8. **What access restrictions apply?** Narrow alleys, truck-size restrictions,
   collection-side requirements, restricted turns/reversing, gated properties,
   construction, or time windows.

The required truck count, final route count, route hours, load divisions, and
number of dump visits are application results. Ask for physical/time limits
and operational observations rather than asking operations to supply the
answer the model is meant to calculate.

## Source details to retain internally

- Sheet1 has 104,022 distinct AddressIds. Monday repeats 21,507 of them;
  do not concatenate the two tabs.
- Sheet1 column E has a whitespace-only heading. Monday identifies the
  corresponding column as RecyclingCollectionDay; confirm that interpretation.
- AddressId 248343 has a backtick in Sheet1!E103942 while its Monday record
  says MONDAY. Resolve this only in a documented working derivative.
- Keep the 25 extra occurrences of exact address strings under different IDs
  until shared-service/unit relationships are confirmed.
- No coordinates, alley/curbside classification, or ASL/RL compatibility are
  supplied. Keep access type, truck compatibility, and pickup coordinates as
  separate fields. Do not infer rear-load service solely from an alley label.

## Work sequence

1. Validate the service list and collection calendars; preserve source IDs;
   geocode addresses and identify actual curbside/alley collection locations.
2. Add address-level access and equipment compatibility, demand, and operating
   limits. Separate collection events by waste stream and frequency.
3. Evaluate daily fleets and build compact routes from scratch. Sequence
   capacity-limited loads with every dump trip, unload, break, and yard return.
4. Report the evaluated fleet needed by day/type, peak simultaneous trucks,
   spare assumption separately, route time, loads, and comparison with 45 trucks.
   Show the limiting inputs and uncertainty where operational data is missing.
5. Produce overview/driver maps, route/load/address assignments, and requested
   exports. Check coverage, compatibility, payload, shifts, and map readability,
   then obtain operations review before treating routes as dispatch-ready.
