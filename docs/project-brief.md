# Winnipeg residential ASL and rear-load routing

## Thursday coordinates complete and estimate review - 2026-11-16

This update supersedes the missing-coordinate status in the earlier delivery
entry below. The user supplied coordinates for AddressIds 178051, 240416 and
240504. They are recorded as User supplied in Thursday's existing workbook and
persisted privately in `data/reference/thursday_coordinate_overrides.json`.
All 19,316 Thursday records now have coordinates and pass offline import
validation; Wednesday's 22,202 and Friday's 19,764 records also pass.

Exactly 12 cells across the three requested Thursday rows changed. All other
cells, formatting, table/filter definitions, panes and dimensions are preserved.
Wednesday and Friday workbooks remain byte-identical. The previous Thursday
delivery is backed up in the existing audit folder. Evidence:
`audit/thursday_coordinate_update_validation.json` and `audit/file_validation.json`.

Five Thursday and eight Friday estimates remain unconfirmed, with their
approximate status unchanged. The user requested the complete list to confirm
or correct them; it is retained privately in
`audit/coordinate_estimates_for_confirmation.json`. Wednesday has no estimates.
The supplied three coordinates do not confirm those other 13 locations.
No files were uploaded and no partitions or truck routes were generated.

## Wednesday, Thursday and Friday upload files - 2026-11-16

The user requested the running app and three separate Excel inputs, with
uploads left to the user. The new local delivery is
`outputs/2026-11-16_weekday_uploads/`. It preserves all six original intake
fields, distinct AddressIds, repeated address strings and Sheet1 row numbers:
Wednesday 22,202, Thursday 19,316 and Friday 19,764 rows. The original workbook
and all existing Monday/Tuesday root deliverables remain unchanged.

Coordinates use the frozen official Winnipeg address cache, explicit
address-label reconciliations, and bounded cached supplementary checks.
Assessment parcel centres and a fractional parent-building fallback are
labelled approximate; the importer treats them as estimates. They are property
display locations, not confirmed curbside/alley pickup points. An exact OSM
building address resolves one Thursday property without a City address match.
No public records add service rows, and no road centroids replace houses.

Wednesday and Friday have coordinates for every row. Thursday is incomplete:
AddressIds 178051 (434 Salter St), 240416 (769 Pritchard Ave), and 240504
(731 Mountain Ave) retain blank coordinates after City address, assessment
and OSM checks. All three source records remain in the workbook. Its complete
day cannot pass import until these locations are resolved. Keep this limitation
visible; do not publish a partial service universe as the full Thursday input.

Preparation, source hashes, lookup receipts, workbook inspections and saved-file
validation are in the delivery's `audit/` folder. No upload, partition or truck
optimization was requested or performed. The existing app runs on port 8765.
The user also authorized small logical project commits and a push to
`Ronak-CWS/Winnipeg-Resi-Route-Planner`; private data, outputs and caches stay
ignored and local.

## School and commercial boundary preference - 2026-11-10

The latest QA distinguishes a valid road-following boundary from the best available
boundary. A coherent school/park/commercial edge should beat an ordinary road;
rail, water and protected major-road evidence remain stronger. The previous final
repair search considered complete City streets but omitted land-use replacements,
so zero street/alley violations did not prove that a stronger nearby edge was
compared. Cullen Drive is evidence for this general issue, not an exception.

The 4.5 change proposes transfers of complete mapped frontage/parcel faces around
nearby non-residential grounds, compares all affected neighbours and retains strict
score improvement. Actual service-bearing parcels cannot become open-land evidence.
Mapped institutional/commercial use may corroborate the complete unserviced City
parcel component. Short completions across road space need mapped land-use and road
endpoints and cannot cross property interiors. All ownership, contiguity, parcel,
street/alley and major-road gates remain. Unrelated zero-service detours are removed.

Final shared boundaries export physical strength for routing. Adjacent work across
a weak seam is preferred on one truck after feasibility, truck-count, load-fill,
small-pocket and whole-parent priorities. This does not force TUE-004/TUE-009 or any
other named pair together. No Tuesday truck solve has been performed in this update.

Resolved 2026-11-10 in engine 4.5, result `448e517113575ac1ea886fa3055b469bba454435eb7f2f33695a79a92f41b27f`. The full Tuesday run transfers 27 addresses from TUE-001 to TUE-009; their counts are 993/930. All 21,233 source IDs and coordinate/address fields reconcile, with zero material parcel cuts, major-road crossing areas or street/alley boundary flags. The offline Chrome before/after map verifies the school frontage and corner access gap. Refinement from the saved partition took 551.1 seconds; 200 Python tests pass. Receipt: `audit/partition_app/landuse_qa_validation.json`. No Tuesday truck routes were regenerated; the new affinity applies to future solves. TUE-006's unresolved oversized section remains OPEN B04.

## Boundary scoring QA - 2026-11-09

The user requested that ongoing QA be retained in `docs/mistakes.md`, with OPEN
issues and evidence-backed DONE fixes, and made required reading in `AGENTS.md`.
Example road names and section IDs remain diagnostic evidence, never exceptions.

The 4.4 correction applies the same 1,000-point penalty per unsupported street
cut or opposing-alley split to the range candidate and frontage-fallback paths.
Complete finite City street combinations are considered before parcel/frontage
regrouping. A street arm reaching a parent boundary is eligible; a dead end is
not extended. A municipal line that follows a street can receive the same
geometric frontage exception as a street candidate, while same-side mid-block,
shared-site, coincident-point and material-parcel protections remain.

Continuity replacements compare all affected neighbouring edges, retain strict
score improvement and reject repeated complete states. A permitted opposing-curb
division retains protection within the resulting frontages and outside the
edited pair. Final section quality aggregates every shared edge, including
inherited natural boundaries, rather than only the last edge that was repaired.

Mapped speed above 60 km/h is major-road evidence. At exactly 60 km/h, a mapped
arterial/highway classification also qualifies; unknown speed is never assumed.
Controlled-road evidence must propagate to matching finite City road segments,
including modest offsets between source centreline datasets. Final validation
independently checks serviced populations across complete major-road dividers,
as it already does for rail. Geometry or count PASS is not boundary-quality PASS.

A cadastral identifier can contain disconnected pieces of land. Protect the
complete connected component containing each service point, rather than pulling
unoccupied remote pieces and their neighbours across a highway. Preserve the
source parcel identifier and component evidence; actual shared site IDs and
coincident service points remain indivisible. Reapply complete physical dividers
after cell protection, with independent ownership, parcel and coverage gates.

Tuesday was regenerated and saved separately after geographic and Chrome visual
checks: 21,233 source IDs, 36 areas from 33 natural areas, zero geometry/ownership
errors, zero material parcel cuts, zero major-road crossing areas and zero flagged
street/alley boundaries. Runtime was 544.367 seconds. Nine areas meet 900–1,100;
24 are below and three above. TUE-006 remains 3,432 and is OPEN in the local QA log.
There is no claim that all sections satisfy the requested range.

Result key: `08f40d8260c09abff4233e8ec837402a5078f5c7f8ad4c8edb396988706e8f4c`.
The original workbook, Tuesday input coordinates and accepted Monday routing
package are unchanged. A concurrent Monday app result and its saved day pointer
are retained. The user handles uploads and the Create action. The offline
`Tuesday_boundary_QA_review.html` compares previous/revised boundaries with City
neighbourhood lines and service points. See `boundary_qa_validation.json` in the
existing delivery's `audit/partition_app/` folder; 190 Python tests and both
JavaScript suites pass. No Tuesday truck solve was performed in this correction.

## Weekday-aware uploads - 2026-11-09

The user has now requested Tuesday support in the app, superseding the earlier
file-first deferral. Each run uses one weekday from the collection-day column,
or the worksheet/filename when no day column exists. Recognised abbreviations
are normalised. Mixed-day files require an explicit day selection; excluded
other-day rows are counted. Unknown/blank row days are rejected. Ambiguous
multi-sheet workbooks require a worksheet choice; sheets are never concatenated.

The existing-list picker includes Monday and Tuesday. Day metadata follows the
input through section IDs, map labels, result caches and exports. Tuesday section
IDs start `TUE-`; assignments add a collision-safe `PartitionCollectionDay` field
without modifying source columns. A new upload clears the previous map, counts,
exports and route state even if validation fails. In-flight old route responses
cannot restore another day's lines. Saved routing results require both the same
partition hash and collection day. Routing metadata and export names follow the
selected day; this change does not run Tuesday truck optimization or change
boundary/fleet scoring or operating assumptions.

The initial full Tuesday run reached the existing ten-minute limit during
continuous-boundary refinement. The partition calculation ceiling is now 30
minutes for every weekday, with cancellation and failed-run preservation kept.
This allows the existing algorithm to finish without weakening geometry checks.

HTTP checks accept all 21,233 Tuesday records in both the CSV and XLSX, with no
excluded rows, and retain Monday's 21,507-record import. Source files remain in
`outputs/2026-11-04_monday_map/`; backups and validation are in its existing
`audit/partition_app/` area. See `tuesday_webapp_validation.json` there for the
full Tuesday partition and export check. Browser-independent UI tests exercise
day changes, errors and stale response isolation. Chrome connected successfully
and displayed the completed Tuesday result. Automated Chrome file selection was
blocked by the extension's file-access permission; the user then requested to
handle uploads and inspect the flow manually. No Chrome upload completed and no
extension setting was changed. Uploading validates/loads only; partitioning waits
for the separate Create service areas action.

The complete Tuesday partition took 18m08s and contains 31 areas from 29 natural
areas. All 21,233 source IDs are assigned once; exported polygon/ownership checks
pass with no geometry errors. Seven areas meet 900-1,100, 21 fall below and three
exceed it (largest 3,432). Range and street/alley continuity exceptions remain
visible; this is not a claim that all sections satisfy the requested range or
that Tuesday truck routing has been calculated. All 17 protected input/Monday
delivery hashes remained unchanged.

## Tuesday coordinate file - 2026-11-07

The user initially requested Tuesday extraction first and deferred app support
until the November 9 follow-up above. `outputs/2026-11-04_monday_map/Tuesday_addresses_lat_long.xlsx`
and its CSV companion retain all 21,233 Tuesday AddressIds from original
`Sheet1`, all six source fields and source row references. Monday outputs and
the source workbook are preserved. Both collection-day fields remain TUESDAY.

All 21,233 Tuesday rows now have coordinates: 21,227 exact City address matches,
two building points for missing unit labels, two documented street-type matches
and two user-supplied coordinates received on 2026-11-09.
`326 ZIMMERMAN` and `53 ZIMMERMAN RD` use the unique corresponding City
ZIMMERMAN DR civic records without changing their original service labels.
The user supplied 383 OAKDALE DR (AddressId 86573) at
`49.86106583290263, -97.27007927716208` and 391 OAKDALE DR (AddressId 88627)
at `49.860789165162146, -97.27013839293876`. These replace the two blanks in
the initial November 7 export and are labelled User supplied, separately from
City matches. Overrides are persisted in `data/reference/tuesday_coordinate_overrides.json`.
No external lookup or map load was needed for the correction; the earlier
official address and assessment queries remain historical evidence.

Coordinates are WGS 84 property/building points. At initial delivery the importer
filtered for Monday; the November 9 update above enables Tuesday uploads. The
coordinate delivery itself did not include truck routes. Saved-file reconciliation
are in the existing delivery's `audit/tuesday_*` files. The previous Tuesday
delivery is preserved in `audit/before_tuesday_oakdale_coordinates_2026-11-09.zip`.

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


## Pickup access and fleet cohesion - 2026-11-06

Recycling's normal maximum remains 1,350; the user confirmed a 2% planning
tolerance, giving an absolute maximum of 1,377. Garbage remains capped at 650.
Aim for at least 60% of normal capacity at every dump (810 recycling, 390
garbage), including the final unload. A remaining shortfall is penalized and
reported, never hidden by omitting the final dump or adding fictitious time.

Prefer one truck owning a complete planning section. Explicitly test complete
parents plus adjacent companions and reciprocal moves/swaps that reunite
siblings. Both resulting territories must remain connected; evaluate their
actual roads, load breaks and complete-day clocks before assigning the entire
stream fleet together. Similar counts alone do not establish a useful exchange.
Names and MON IDs are regression examples only, never algorithm exceptions.

Try the full 15:00-16:00 return window first. If no such cover is found, mark
the exception and prioritize the latest deadline, fewer trucks, dump fill,
whole-section ownership and paid hours. Do not reward extra driving merely
because it reduces an unavoidable early-return shortfall.

Postal street names are not reliable pickup-road evidence inside complexes.
Consider closer eligible internal service roads connected by actual road nodes
to the postal street. Preserve ordinary frontage, access restrictions and
right-side direction; do not jump across another public street or infer links
from lines that merely cross. Distinct interior unit locations can support
near-entrance units in the same civic site. Source coordinates stay unchanged.
Validate original-property distance as well as anchor-to-route coverage.

Routing 1.4 is published against the unchanged partition: 19 garbage and 14
recycling trucks, 60 loads, 43,014 source-verified pickups, all dumps at least
60% full and no late returns. Four garbage and six recycling trucks return
before 15:00 (earliest recycling 11:26), so this is still TIME_LIMITS_UNMET,
not an accepted fleet requirement. Planning sections shared between drivers
fell from 11 to 8 for garbage and from 8 to 6 for recycling. The 35m33s solve
retained iteration 1; finer later iterations worsened the selected objectives.

Independent replay finds nearby, correctly directed path segments with each
illustrated property on the right: all 62 in the first complex and all 20
Fairhaven units, in both streams. Final snapped pickup offsets are at most
30.46 m and 24.25 m respectively. One first-complex address still has a detailed
direction diagnostic; it is shown explicitly. Across Monday, 313 property
offsets exceed 80 m and 16 direction diagnostics remain. Their warnings are
preserved in individual pickup exports/popups as well as the global review.
The source workbook and five coordinate deliverables remain byte-identical.

Result key: `771fde3ca5bf53c26fb39e307abf907e7ab49d4146a6d0a331debe87c0c78977`.
All six exports, API package and offline HTML passed reconciliation and Chrome
review. The final warning-only refresh took 7.3s from cache and preserved all
route paths, load choices, clocks and pickup sequences. See the routing notes.

## Boundary clarification - 2026-11-06

A boundary following a mapped street through intersections is valid. The four
previous flags at Lindsay, Borebank, Campbell and Niagara on Grosvenor were
false positives for this requirement. They are not mid-block cuts. Unsupported
cuts between neighbouring homes and opposing alley-side splits retain the same
heavy penalty. A road-following boundary is compared with other valid corridors
by strength, continuity, municipal evidence, count fit and neighbourhood cohesion.
The user's preference for Corydon and Queenston illustrates stronger or more
consistent alternatives; these names are QA examples, never code exceptions.

The old MON-016/018 seam followed official neighbourhood edges for only 12.14 m
of 1,657.14 m (0.73%, 8 m comparison tolerance). The full finite Queenston
candidate had 1.44% alignment, so the old 60% eligibility gate excluded it even
though it could give 891/1,328 versus 792/1,427. Municipal alignment now supports
comparison rather than vetoing that candidate. Actual mapped speeds above
60 km/h form major barriers. Preserve coherent neighbourhoods and score weak
internal seams for merging before crossing stronger highways or commercial gaps.

Engine 4.2 is published locally: 31 areas, all 21,507 IDs preserved, no overlap,
no material serviced-parcel cuts and no crossings of the 366 checked rail
features. The illustrated northern Whyte Ridge group plus the former 272 west
of Kenaston now forms 946; its southern neighbour has 1,156. The 283 across the
railway stay separate. The former alley pair shares an owner, and all 144 Fleet
Avenue records in the illustrated cohort stay together. No example names occur
in partition or routing algorithm code. The source workbook and all five
coordinate deliverables are byte-identical.

The later corner screenshot is the old parcel/alley detour near Academy and
Niagara. In 4.2, 420 Academy, 174/178/180 Niagara and 171 Waterloo share MON-016.
Within 50 m of 174 Niagara, all remaining section boundary follows Academy;
no off-road corner seam remains. The address IDs are regression fixtures only.

Five areas are within 900-1,100, 21 below and five above; the range remains
unmet and is not described as achieved. The City boundaries toggle uses local
neighbourhood GIS. Of 59.30 km of shared section boundaries, 30.74 km (51.84%)
lies within 8 m of the municipal lines; this is alignment, not a quality score.
The corrected North River Heights internal seam follows 1,163.55 m of mapped
street but only 16.71 m of municipal boundary. Internal roads need not be City
neighbourhood edges to be valid candidates.

Partition key: `fc836082d794748d9d2e2ac69b55c1f2817a1ee4b7579000fcb7f4595682fbfc`.
Routing 1.3 completed against that partition in 58 minutes 59 seconds. The
published review plan has 19 garbage and 13 recycling trucks, with 43,014
independently reconciled pickups, 62 loads and no returns after 16:00. One
garbage and six recycling routes return before 15:00, so the utilization rule
remains unmet; this is not an accepted required-fleet recommendation. All six
exports, including the offline truck HTML, are saved in the existing folder
and the app/HTML passed Chrome review. See `docs/routing-app.md` for the exact
result, counts, clock exceptions and receipts.

New calculations default to two local worker processes (editable 1-4) for
complete section alternatives and route/load evaluations. OR-Tools runs on the
PC; Docker runs OSRM. Keep HTTP/cache coordination and the final fleet-wide
assignment together. Never obtain parallelism by independently assigning two
geographical halves. The real cached component benchmark showed 1.726x load
evaluation and 1.524x section-search speedups with two workers; no full-run
speedup has been measured. The published route files remain the serial run.

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

## Current Monday section correction and routing intake

The user explicitly keeps the section correction active. The routing discussion
is the next step, not a replacement for the requested street/alley seam repair
and single range workflow. Engine 4.1 is now published locally and verified
with a fresh-process replay, independent source/rail/seam checks and Chrome.

Latest routing clarification supersedes the intake text below: treat every
address as curbside for now; garbage uses ASL and recycling rear load, with
separate route plans. Recycling receiver is the user-supplied GFL MRF address
335 Mazenod Rd (formerly Canada Fibers). Collect only to the right of travel;
serve opposite owned curbs through correct-direction return passes/legal loops.
One pickup per AddressId per stream still applies, so two-direction travel does
not double pickup demand. Break allowance is 30 minutes overall, no separate
unpaid lunch, and no added posttrip time. The preferred eight-paid-hour finish
from 06:15 is 14:15. The ignored operating-input JSON contains the updated
record. Road-side routing, effective load count and fleet optimisation have
not yet been implemented or solved. The user authorizes OSRM table resizing
to fit complete section/load problems and adjustment of solver time. The
current 800-location server ceiling is not a section-size or route-size rule.
Do not create independently solved sequence chunks merely to fit HTTP tables.
Build section pickup orders and entry/exit options first, then optimize
adjacent sections and their stream-specific RF visits. Keep one driver per
section; capacity-driven dumps can interrupt the same truck's section work.

The corrected user-example footprint retains all 2,027 original addresses and
exactly the same polygon union, with 830 and 1,197 addresses divided along
776.5 m of continuous City street geometry. Its 11 former street-run cuts and
three opposite-alley-side splits are removed. All 144 Fleet Avenue records in
that footprint now share one owner. Names and former MON labels occur only in
QA fixtures. A second related seam improves through the same generic rule.
One remaining seam has four street cuts and one opposing-alley split and stays
flagged for review; no eligible continuous replacement was found.

The default 900-1,100 run has 29 areas, four in range, 20 below and five above,
with a largest count of 1,431. These are explicit exceptions, not a claim that
the range was achieved. All 21,507 source IDs and coordinates are preserved;
19,946 serviced parcels have no material cuts, and all 366 rail features were
independently checked. All five original coordinate deliverables and the
workbook remain byte-identical. See `docs/partitioner-review.md` and the existing
`outputs/2026-11-04_monday_map/audit/partition_app/` receipts. No extra delivery
folder was made. The single range form, click-only area/address details and
expanded map passed Chrome review with zero new provider calls.

## Monday routing discussion and operating intake - 2026-11-05

The next step is Monday fleet sizing for **two separate route plans**, garbage
and recycling, with no organics. The user confirms one pickup per Monday
AddressId per stream: 21,507 pickups per stream, 43,014 service events total.
Distinct source identities and co-located demand must be preserved. Each stream
is optimized separately using the common geography and road cache.

The supplied operating reply and follow-up answers are recorded, with provenance
and pending fields, in the local ignored file
`data/reference/monday_routing_operating_inputs_2026-11-05.json`.
The user gives stationary pickup time of 10-15 seconds, excluding driving,
and a combined active-collection pace of 3-3.5 pickups/minute. The latter is
approximately 17.1-20 seconds per pickup including nearby driving. It is a
calibration/check on the complete active block, not another delay to add to
stationary service plus OSRM pickup-to-pickup travel.

For the current routing scenario, treat every address as curbside. Garbage
uses ASL; recycling uses rear load. Collect only to the right of travel, using
correct-direction return passes or legal loops for opposite owned curbs.
The earlier back-lane rule is retained for future access inference, not applied
to this scenario. Keep inferred access, field-confirmed access, derived pickup
coordinates and original property points separate. Mapped alley geometry is
not field confirmation. Opposite pickup sides of an alley should stay together.

Reported yard is 385 Eagle Drive: crew start 06:15, pretrip/FLHA 15 minutes,
road departure 06:30, originally requested return 16:00. Include 30 minutes
of breaks overall, with no additional unpaid lunch. Fueling time is explicitly
zero because OSR fueling is supplied. Post-trip time is explicitly zero.
The latest preference is to avoid/minimise overtime and finish early. Seek
minimum fleet for zero overtime at eight paid hours, then show smaller-fleet
tradeoffs. Preferred crew completion and yard return are 14:15. Retain 16:00
as the separate latest return from the operating reply.

Waste goes to Brady Landfill (reported winter 06:00-18:00, summer 05:00-19:00);
recycling to the GFL MRF, formerly Canada Fibers, at the user-supplied
335 Mazenod Rd address (reported 06:00-18:00). Each receiving visit averages
15 minutes on site, and every truck returns unloaded. Do not charge another
15 minutes independently for queue, weighing and unloading without evidence.
Garbage pickup capacity is 570-630 per load and recycling 1,200-1,300 per load.
Waste also has a reported nine-tonne payload limit; mass-per-pickup/load evidence
is still needed for independent tonne validation. Two loads is a reference
scenario; the user explicitly wants effective load counts optimized. Partial
loads are allowed; no other city's nonfinal minimum or 650-pickup cap is imported.

Truck territories must be connected, adjacent service-section clusters, with
consecutive physical pickup groups. Do not justify a north/south disconnected
assignment by a cheap nearest-neighbour link. Remote outliers need an explicit
handling decision. Required fleet is an output; 45 available trucks remains a
comparison, not a preset answer or required-fleet ceiling.

Reviewed the ODA routing history/mistakes and the Wood Buffalo optimizer's
input, connected-flow assignment, load-break dynamic program, exact replay,
current client-adjusted policy and verification contracts. Its reference
travel profile divides general OSRM drive time by 0.95 and active drive time
by 0.855. Confirmed local reversals require at least 150 degrees and use a
30-second allowance when preferable to forward travel; review 60 seconds as
sensitivity, retain highway legal-forward rules, and keep maneuver allowances
outside speed factors. These are a reviewed reference profile, to be checked
against Winnipeg's observed collection pace. Do not also stack Alberta's
separate long-haul 0.90 calibration. Winnipeg requires the complete yard-to-yard
working day, unlike Wood Buffalo's historical 11-hour collection-only clock.

No routing solve or best fleet recommendation has been produced. Actual site
entrance coordinates, payload evidence and field access restrictions remain
pending. Local OSRM is available at http://127.0.0.1:5001, using Manitoba MLD
data and an 800-location table ceiling; the live command and a small road-route
probe were checked. This does not establish truck restrictions or posted
speed-limit coverage. The earlier conditional intake calculations predate the
latest break clarification and are superseded, not feasible truck plans.

The section correction is published as engine 4.1. Repeated-candidate stability,
local opposite-alley-side checks and fresh-process replay pass. The current
version and exact section exceptions are recorded above; engine 4.0 remains
preserved in the existing audit backup. No source or original coordinate
deliverable changed for this work.

## Natural-first range correction - 2026-11-05

The user's latest review supersedes the count-first refinement below. Build
the same natural partition in both modes, then score whole-area merges and
credible splits against an editable preferred range (opening at 900-1,100).
The range has priority among geometrically sound alternatives, while ordinary
street frontages, shared sites and serviced parcels stay whole. Alleys cannot
be ordinary count dividers. Do not enlarge an undersized area by taking a
satisfactory neighbour outside its range. Prefer useful near-range sections
over multiple small fragments; retain specific exceptions where the necessary
boundary evidence is absent. Rail, water and controlled-highway separators
remain protected regardless of count. Municipal lines and actual broad-road,
park and open-land corridors are candidates, not automatic permission to cut
an ordinary street. Examples supplied with MON labels and road names are
regression references only and are not algorithm rules.

A numerical fault in the earlier subdivision/audit path was found: clipping
a finite diagonal before noding could miss a genuine railway crossing. The
engine now nodes complete finite lines before filtering to the original
parent. The railway verifier uses a separate library split of the full rail
network and rejects the former natural result's two missed crossings. Earlier
railway-pass claims below do not establish correctness under this stronger
test. The saved source and coordinate files are unaffected.

Standard target splits use municipal/broad-road evidence. Only after those
fail, and only inside a natural area with at least two preferred minimum-size
sections, may whole-frontage regrouping be attempted. It cannot split sites,
coordinates, serviced parcels or ordinary paired curbs. Any resulting rear
property/alley boundary is flagged for actual pickup-access review.

Area details are click-only. The settings panel collapses after results load,
and Expand map hides the remaining panels while resizing the existing map.
Chrome is now connected through the installed control-chrome skill; the prior
connector failure below is historical. The unrelated Portal preview on port
8190 refused its connection; the Monday app uses port 8765.

Verified local engine `winnipeg-geography-4.0`: 28 natural areas; the opening
900-1,100 range has 29 areas (7 in band, 18 below, 4 above; largest 1,431).
All 21,507 rows remain assigned once. Range exceptions and five last-resort
frontage areas remain review items. Eight user-example checks, 70 Python cases,
independent railway/source/export checks, fresh-process CSV/XLSX replay and
Chrome Natural/range/area-click/address-click checks pass. The expanded map is
1,890 x 824 pixels with no page errors. Automated file selection needs the
Chrome extension's file-URL permission; app Excel upload passes API checks.
Receipts, screenshots and publication status are recorded in
docs/partitioner-review.md and the existing delivery's audit/partition_app.

## Earlier partition preference clarification - 2026-11-05

The earlier review setting was 900 +/-12% (792-1,008), superseding the earlier
600 +/-15% default below. Most areas should remain within the preferred upper
value. A small number of larger whole geographic areas may remain as explicit
review exceptions; the user's examples of 1,500 or below 2,000 are not a new
blanket capacity allowance. Do not change settings to make compliance appear
green, and do not weaken railway/major-boundary or whole-curb protection.
Consolidate pockets below 100 with an adjacent larger area or one within 500 m
where no important boundary intervenes. Prefer a merge within the range; a
larger neighbour is not by itself a reason to leave a tiny area isolated.
Larger is relative: a 1-address pocket may join a 30-address neighbour. Keep
the real pieces and record a nearby grouping; never invent connecting land.
The earlier local release was `winnipeg-geography-3.0`: 65 provisional areas,
all 21,507 Monday records assigned once, largest 1,001 and none above 1,008.
Six areas are in the preferred band; smaller geographic areas remain visible.
Independent railway, source/export and fresh-process CSV/XLSX replay checks
passed before the local API published the result. Original workbook and
coordinate deliverables are unchanged. Chrome visual QA remains unavailable
because the browser connector cannot reach its host; no desktop fallback used.

The later UI preference is click-only area details: remove area hover tooltips.
Clicking inside an area shows its details; address clicks show address details.

Last reviewed: 2026-11-05
Status: Monday partition web app available locally; operational requirements under review. No routes approved.

## Purpose and scope

Determine the operating ASL/rear-load fleet needed for each collection day,
then generate collection routes, load divisions, full-trip driving sequences,
and maps from the supplied addresses and operational requirements. Report
daily and peak fleet needs, route hours and loads, and compare with 45 trucks. Keep this
project separate from the existing front-load recycling planner. Reuse proven
inspection and map-delivery methods after checking suitability, while retaining
Winnipeg residential source authority and operating parameters.

## Authoritative inputs

- User-supplied workbook, received 2026-10-27, originally at
  `C:/Projects/ODA Data Generation/data/Winnipeg - Area 1 addresses.xlsx`.
- Current path: `data/source/Winnipeg - Area 1 addresses.xlsx`.
- SHA-256: `fbff92cbe50d4a56aa39883a8fafbe0de97ac3a542c47df2f02a8e106c18d5a2`. Size: 5,099,663 bytes.
- This is the intake address source. Completeness for Area 1 and the collection
  streams covered remain unconfirmed. Other project workbooks do not expand it.
- Email screenshot supplied in this conversation, retained at
  `data/reference/michael-loewen-email-received-2026-10-27.png`.
  The date in that filename is receipt date, not the undated email's send date.
- User confirms 45 available trucks. Michael's screenshot requests 20 ASL and 12 rear-load
  routes, near 1,300 and 1,500 calls per route respectively, retaining Miller
  areas where possible. This is historical email context. The user's later
  2026-10-27 clarification supersedes its fixed route counts and Miller-area
  preservation: calculate fleet needs and design routes without Miller maps.

## Current baseline and deliverable

Project: `C:/Projects/Routing/winnipeg-residential-route-planner`.
Evidence: `outputs/2026-10-27_intake/source_audit.json` and
`outputs/2026-10-27_intake/intake_receipt.json`.

Sheet1 has 104,022 populated address records, 104,022 distinct AddressIds,
no blank ID/address/postal/day/cycle values, and no duplicate full rows.
It has 103,997 distinct exact address strings. Preserve the 25 repeated-string
occurrences with their different source IDs pending review.

| Garbage weekday | Source address rows |
| --- | ---: |
| Monday | 21,507 |
| Tuesday | 21,233 |
| Wednesday | 22,202 |
| Thursday | 19,316 |
| Friday | 19,764 |
| Total | 104,022 |

Monday contains exactly the same 21,507 IDs as Sheet1's Monday subset.
One field differs: AddressId 248343 has a backtick at Sheet1!E103942, versus
MONDAY in the Monday sheet. Sheet1's column E header is whitespace; Monday's
corresponding header is RecyclingCollectionDay. Record this interpretation
and discrepancy without editing the source or concatenating the two sheets.

No coordinates, ASL/RL classification, collection-access side, Miller route IDs,
cart quantities, depot/receiver details, or truck capacities are supplied in
the workbook. Existing garbage days and yard-waste A/B labels are present;
permission to change days and calendar meaning remain to be confirmed.

## Decisions and assumptions

### Address preference and whole-frontage correction - 2026-11-05

The user initially confirmed **600 Â±15% (510â€“690)**; the later 900 Â±12%
clarification above superseded that opening preference; the latest range
correction now takes precedence. Count and
tolerance remain editable, and an explicit range is also supported. Tolerance
under 10% is widened to 10%. The lower end is a preference: useful smaller areas
with strong boundaries must not be enlarged merely to hit 600. Any area above
the upper end is explicitly target unresolved, even if geometric checks pass.
These address counts are neither truck capacity nor an operational route count.

The user also confirmed keeping both curbs together until pickup access is
confirmed. Mapped rear alleys alone cannot enable a road divider; the UI has no
inferred-alley override, and the API/engine reject that option. An optional
CollectionAccess field accepts confirmed alley/curbside evidence, separately
from truck compatibility. Missing access remains unknown. Street names from the
user's examples are not hardcoded.

Frozen City neighbourhoods, streets, parks and assessment parcels are used.
Additional local-only PBF inventories add road width/lane and opposing-carriageway
evidence, recreation/schools, mapped open land, alleys and non-sidewalk greenways.
No geocoding, tile, Overpass or new City requests occur during these corrections.
Road speed 40/50 or road class alone does not establish a divider.

Version 2.1 nodes street protection at actual mapped intersections. Before an
oversized group is split, it refines its coarse cells with actual parcel edges,
street geometry and finite junction-to-nearest-parcel-edge connectors (3â€“45 m,
no parcel-interior crossing). It attaches road-space faces to whole ordinary
frontages, then uses a deterministic adjacency queue. No coordinate scan cut,
infinite ray, point hull or buffer bridge is used. The boundary ledger preserves
parcel IDs, street segment IDs and the exact junction/parcel connector anchors.

All edges are noded together before WGS 84 publication. Unserved enclosed faces
receive one owner. A serviced inner pocket may remain its own bounded area;
every interior ring must be completely covered by other valid sections, with
no overlap or unassigned gap. This preserves useful small areas instead of
merging them only to erase an otherwise legitimate enclosed pocket. Single
connected polygon, ID, containment, parcel and frontage gates still apply.

Area hover and empty-space click show the area's name and address count.
Address clicks take priority and show service details. Separate map renderers
and explicit geometry hit testing avoid the address canvas swallowing area
events. There remains one map instance and the bounded, cached optional basemap.
Chrome-only access currently reports browser access host unavailable; local
geometry/event regression tests are not represented as a new visual Chrome QA.

The original coordinate files stay byte-identical in the existing Monday
folder. Its Excel file is downloadable from the app as the Monday upload.
Old v1 natural/target figures below are historical and superseded by this
correction; the prior partition delivery is preserved in its existing audit.

### Monday partition web app - 2026-11-05

The user requested a thorough review of the existing CWS service-area
partitioner and central rule/mistake/result histories, followed by a running
local web app for uploaded Monday addresses with latitude/longitude.
The review, differences and evidence are in [partitioner-review.md](partitioner-review.md).

The app runs at `http://127.0.0.1:8765`; `Start Monday Partitioner.cmd` starts
the local server. It accepts CSV/TSV/XLSX, preserves every AddressId and raw
source field, and selects Monday once without appending Sheet1. Files without
a day column require explicit Monday-only confirmation or a Monday sheet.
Invalid Monday coordinates or blank/duplicate IDs reject the upload; other
explicit weekdays are excluded and counted. No service rows are added from GIS.

Use a Winnipeg-specific adaptation rather than the generic legacy importer,
which collapses repeated address keys, or the legacy map writer, which defaults
to blocked OSMF raster. Repeated strings alone are not must-link proof. Fixed
official neighbourhood geometry and finite physical separators create candidate
pieces; shared points, explicit sites, ordinary road segments and serviced
parcels protect membership. Estimated coordinates are assigned after boundaries
are fixed. No coordinate hull, H3, Voronoi outline, extended ray or buffer bridge.

Natural mode produces 21 draft sections for the current 21,507 records. The
optional 600-address example produces 36 draft sections, with a soft preference
and a 3,616-record largest area. This does not inherit the reference tool's
600-tip hard ceiling or any fleet/capacity assumptions. All otherwise passing
results are PROVISIONAL because full areal-gap/road/crossing/access proof is
pending. Failed topology, ownership, protected groups or material parcel cuts
are shown explicitly; the last valid result remains available.

References are frozen locally: 237 neighbourhoods, 17,805 official road
segments, 1,401 parks, 163,919 assessment parcel geometries and 8,162 physical
features extracted from the existing Manitoba PBF. Receipts capture source
dates, licence, coverage and hashes. The large survey export and a truncated
assessment extract were rejected; the final bounded extract is cached. Never
repeat reference acquisition per upload. Property/coordinate sources do not
expand the service universe or establish pickup positions.

Default mapping uses local streets and performs zero provider requests.
Optional OpenFreeMap detail shares the existing all-resource limits (4 / 200
URLs / 25 MiB / 200 ms / 12 seconds), successful/failed URL cache and stop/no-retry
behavior. One map instance, actual input extent plus 50 km and zoom capped at
19; no idle/render-triggered fits, recreation, reload or recurring refresh.
Cached QA replays 13 resources / 586,961 bytes with zero upstream requests and
zero stationary render frames. Resize handling only invalidates actual changed
container dimensions.

Keep the same requested delivery directory. New root files are
`Monday_partition_assignments.csv`, `Monday_partition_areas.geojson` and
`Monday_partition_review.json`; flat content-keyed caches and receipts are
inside `audit/partition_app/`. Do not replace original coordinate outputs or
create a new dated folder on each click. A single worker supports progress,
checkpoint cancellation and a ten-minute budget. Uploads stay local.

The target example assigns all 21,507 IDs once, contains all reliable points,
keeps protected groups intact and has zero material cuts among 19,946 serviced
parcels checked. Native numerical overlap is about 0.1893 mÂ². Publication uses
an approximately 1 mm WGS 84 grid and normalizes only numerical edge overlaps
of at most 1 mÂ² per section. Published polygons undergo separate validity,
containment and overlap checks after inverse projection. Parcel references cover
20,833 reliable records; 670 reliable records lack a containing parcel and
remain a visible review issue. The four estimates retain their count/provenance
without affecting boundary discovery. Source/coordinate fields, the original
workbook hash, fresh-process determinism, CSV/XLSX upload, search, selections,
exports, desktop/mobile and mocked/cached HTTP behavior are checked.

No operating truck count, route duration, load count, equipment compatibility,
depot/receiver, shift or service-time assumption is introduced by this app.

### Monday coordinate map - 2026-11-04

Current completion: all 21,507 Monday AddressIds now have coordinates, with no
unlocated records. The user supplied `49Â°51'00.3"N 97Â°13'29.8"W` for AddressId
49738, 2194 West Taylor Blvd. Decimal conversion is `49.85008333333333,
-97.22494444444444`. This is labelled **User supplied**, with the original DMS
and receipt date in CoordinateNote; it is not relabelled as an official city
match or a confirmed collection position. The persistent local override is
`data/reference/coordinate_overrides.json`, applied only to that existing ID
after checking its source address. All original source fields are unchanged.

Update the same delivery folder's HTML, CSV, GeoJSON, review list and workbook.
Only AddressId 49738 and dependent completion/status labels change; all other
21,506 records are identical. There are now 21,290 distinct coordinates. The
previous deliverables and metadata are preserved in
`audit/before_coordinate_49738.zip`. Workbook verification checks the requested
cells, recalculated totals and unchanged unrelated values, styles, tables,
panes, views and dimensions. Map checks use offline/cached resources, with no
new external requests. Evidence: `audit/coordinate_49738_change.json`,
`audit/coordinate_49738_validation.json` and refreshed data/basemap checks.

Basemap correction, same day: the user reported the OSMF raster 403 block and
directed reuse of ODA's rendering policy. Update the existing output folder,
not a new run. During that basemap correction, address CSV/Excel/GeoJSON/review
data remained byte-identical; the subsequent coordinate update is recorded above.
The original HTML is retained as an inert text backup in the existing audit
area. The map now uses OpenFreeMap Liberty with locally embedded, pinned
MapLibre 5.7.1, its Leaflet bridge 0.1.3 and Leaflet 1.9.4.

Rendering policy follows `ODA Data Generation/docs/roadmap.md` (Public Basemap
And HTTP Request Policy), `c9-address-router/c9addr/basemap.py` and
`bounded_basemap.py`, plus the map-exporter's cache and idle-readiness checks.
Reference revision: `853785ea04492f378ab41a955608332d715104db`. The map is
bounded to the actual Monday address extent plus 50 km, with matching minimum
zoom and a maximum zoom of 19. Provider attribution is retained; the blocked
OSMF raster server and Carto raster endpoints are absent.

Unlike an image-only limiter, every style, source, vector tile, glyph and
sprite passes through a single custom-protocol request queue. Limits are four
concurrent requests, 200 unique URLs per page, a 25 MiB transfer-stop threshold,
at least 200 ms between starts and a 12-second request timeout. Successful and
failed URLs are memoized; failures, policy limits and timeouts halt further
automatic requests. Only the approved OpenFreeMap host can be fetched. No
automatic retry, expired-tile refresh, world copies, recurring render timer,
or idle/render-triggered fit/reload/recreation is allowed. The address layer
and search remain usable if the basemap pauses.

Offline mock tests verify request caps, concurrency, pacing, cache reuse,
worker-safe buffers, rejected hosts, timeouts, and stop-on-403/429/500 behavior.
Offline browser checks precede one bounded live overview: 13 requests, 586,961
bytes, peak three concurrent, successful style/tile/idle readiness, no provider
errors and no further requests while stationary. The captured resources are
reused for subsequent visual checks, with no additional provider requests.
Receipts: `audit/basemap_policy_unit_validation.json`,
`audit/basemap_offline_validation.json`, `audit/basemap_live_validation.json`
and `audit/basemap_cached_validation.json`.

The user requested only Monday addresses and latitude/longitude at this stage.
Current local delivery: `outputs/2026-11-04_monday_map/`, containing a portable
HTML address map, Excel and CSV lists, GeoJSON, a location-review CSV and audit
receipts. The Monday sheet alone supplies all 21,507 distinct service AddressIds.
All original fields, source row references, repeated address strings and IDs
are retained; the source workbook hash remains unchanged.

The official City of Winnipeg Addresses dataset (`cam2-ii3u`) downloaded
2026-11-04 has 244,986 reference rows and was updated 2026-11-02. It supplies
coordinates only and does not expand the intake universe. No other weekday is
geocoded. Coordinate status is explicit:

- 21,215 exact address matches, including civic suffixes and unit identity.
- 287 building address points where the source unit is absent from the public
  reference. The unit and its separate service ID are retained.
- Four approximate site centres: AddressIds 41005 (188 Centennial St), 166241
  (112 Pulford St), 167228 (112 Wilmot Pl) and 229327 (592 Stradbrook Ave).
  Each is the mean of three official unit/subdivision points for the same
  parent civic address, with maximum pairwise separation below 15 m. This is
  a labelled display estimate, not a confirmed pickup position.
- One user-supplied coordinate: AddressId 49738, 2194 West Taylor Blvd, resolved
  using the user's DMS location. It remains absent from the current official
  address and assessment references; provenance stays distinct from city matches.

In total 21,507 records are mapped at 21,290 distinct coordinates. Map popups
show all source IDs at a shared coordinate. All locations are property/building
points in WGS 84; collection access, truck compatibility and actual pickup
positions remain unknown. Matching normalizes case, accents, punctuation,
spacing and the intervening space before a civic suffix. It preserves civic
suffixes, street direction, unit strings and every source row.

Validation independently reconciles all original Monday fields and city
coordinates across CSV, GeoJSON, embedded HTML and the saved workbook; checks
spreadsheet tables/panes and formula errors; and exercises map search, all
status filters, colocation, pagination and mobile layout. Receipts are in
`audit/data_validation.json` and `audit/browser_validation.json`.

### Operating scope retained

- Follow the agreed canonical Routing sibling layout with an independent Git
  repository. Keep source data and outputs ignored; no commit or push is part
  of this setup.
- Preserve the workbook byte for byte and retain the email as intake evidence.
- Count source AddressIds once. An address is not automatically a call, a lift,
  a vehicle stop, or a weekly collection event.
- Daily operating truck counts by type, peak fleet, final route counts, hours,
  and loads are model outputs. The available 45 trucks form an availability
  comparison, not the required fleet size or an implicit hard cap.
- The earlier 20 ASL / 12 rear-load counts and 1,300/1,500 call targets are
  historical comparisons only. They do not constrain the new route design
  or establish load capacity. Apply confirmed physical/time limits separately.
- Require address-level alley versus curbside collection classification, with
  stream-specific exceptions and actual pickup points. Record ASL/rear-load
  compatibility separately; do not assume alley means rear load.
- Evaluate the smallest practical fleet supported by the tested scenarios,
  report uncertainty, and keep operating trucks separate from spare allowance.
  Daily fleet demand is not the sum of all weekly route starts.
- Start/end points, receivers, capacity, service time, unload/queue time, shift
  limits, crew, and permissible day/area changes are unknown. The existing
  Winnipeg front-load yard and receiver are not adopted for this project.
- The user explicitly removed Miller maps and route boundaries from the
  required inputs. Design routes from the service list and operating inputs.
- No optimizer run or operational maps are part of the intake setup.

## Run and validate

`scripts/audit_source.py` uses Python and openpyxl in read-only mode. Run the
command in README.md into a new dated output folder. It counts populated rows,
IDs, repeated exact addresses, day/cycle values, invalid day cells, and the
Monday/master overlap. It hashes the workbook before and after inspection.

The setup receipt records the original/destination workbook hashes and the
email screenshot hash. Verify the new Git root and that data/outputs are ignored.

## Open questions and next action

Use the operations questions in [inputs-needed.md](inputs-needed.md). Obtain
collection scope/calendar, address-level alley/curbside and truck compatibility,
truck specifications and crew availability, yards, receivers, load limits, and
shift/service times. Address preparation can proceed independently; practical
fleet sizing and route feasibility depend on these inputs. Do not ask for
Miller maps or a predetermined number of trucks/routes to complete the model.

## Knowledge returned to ODA

The new `knowledge/projects/winnipeg-residential.md`, START_HERE index, roadmap,
and mistake log record this separate intake and its counting/assumption risks.
The parent Routing README and projects.json identify the new sibling project.
