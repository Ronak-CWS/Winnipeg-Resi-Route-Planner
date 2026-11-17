# Winnipeg QA and mistake log

## OPEN B07 - Count merges and boundary scoring ignore useful road access

User QA 2026-11-16, Wednesday 4.6 result `7899007b2c8f6638593e9b22f0b307abfafc5c242396fca196067fec46f388e5`
and Thursday 4.6 result `42ca46633dfc5cc58ef662789855f40d388fbcea4f35ff7e36325027399fe977`.
The user requests general rules and before/after visual QA, preserving previous
partitions. Street names and IDs below identify examples only.

- Keep under-limit natural populations separate unless a direct mapped road
  connection joins them. WED-009's northern population may combine better with
  WED-003 during truck allocation; geometric contact is not access evidence.
- Compare Templeton against the WED-008/016 Diplomat/Beecher detour. Prefer the
  stronger continuous boundary when counts and protected frontages permit it.
- Review WED-014/022 around the park and Jefferson: separate weakly accessible
  eastern strips; compare the western/southern population with the closer area.
- Separate WED-012's population north of Jefferson when its internal access is
  disconnected from the rest of its owner.
- Compare WED-005/022 alternatives using Adsum, Mandalay, Sheppard and Jefferson.
  Rear-alley service is reported as likely, not confirmed per address; preserve
  that uncertainty while comparing real road-aligned planning alternatives.
- WED-010 has two user-marked possible soft divisions through mapped roads.
  Generate multi-road alternatives usable by later whole-fleet allocation.
- THU-004 has a long unserviced industrial/rail appendage; inspect its cause.
- Compare THU-026's single address with THU-021 using actual road access.
- Compare Rupert's Land/Matheson East divisions inside oversized THU-005.
- Compare THU-012 north of Jefferson with THU-024's access and adjacency.
- Compare THU-022/020/007/003 using Arlington, McGregor, Salter, Main and
  Burrows; prevent interlocking sections and give stronger multilane roads
  appropriate physical weight using mapped evidence, never street names.
- Compare THU-013/021/017 using William, McPhillips, Sherbrook, Notre Dame and
  Isabel; preserve useful connected frontages and prefer the stronger corridor.

Additional user QA during comparison review: the first WED-010 candidate left
an orange outer ribbon wrapping the two central sections, with narrow serviced
strips along Moselle and the western/eastern edges. This is unacceptable even
when counts, parcels and coverage pass. Preserve
`wed010_wrapping_sliver_user_qa.png`; compare service-population enclosure and
complete road paths, without penalising genuinely unserved park space or
turning a population hull into a published boundary. Keep B07 OPEN until the
saved replacement has been visually checked.

Further user QA rejects the subsequent 701/657/617 focused candidate: the
green stepped residential-road boundary is worse than leaving the parent
unsplit. The user prefers a two-area option along the continuous park strip,
keeping potential pickups on both sides of a road together. Preserve
`wed010_park_two_way_user_qa.png` and `wed010_stepped_road_user_qa.png`. A valid
road path is not automatically a useful planning division. Generate complete
park/road alternatives and compare their frontage cohesion and complexity;
retain the unsplit parent when no better supported division passes. The
three-area focused candidate is withdrawn, not an accepted correction.

Cause found: averaging boundary strength omitted the cost of its full length,
and the candidate search did not connect mapped park edges with checked road
space. An early ordinary-segment group veto also rejected legitimate park-gap
alternatives before the actual street/alley assessment. The revised focused
pipeline chooses 847/1,128 along the stronger park path, retaining its explicit
28-address excess. A subsequent road-network check rejects that candidate too:
92 Baltic Bay/Innsbruck Way addresses would need the other child's roads to
reach the rest of their owner. The split and fallback stages now reject newly
stranded road populations, using the same access check as later refinements.
The earlier focused accepted-for-full-testing option was 444/1,531 on a complete park
path, with one connected mapped road population per child (four addresses still
have unmatched road access). The 1,531 count remains explicitly unresolved.
No named street is an exception. Site/coordinate/parcel protections and real
street/alley rejection remain. This was an isolated proposal, not the final
full-day result; completed whole-day findings are recorded below.

Apply full seam physical cost to fallback and continuity refinement too. A
later road-only score must not undo a better park edge selected earlier. A
passing count or a visually plausible park line is not road-connectivity QA.

Performance prevention: the first combined-path generator rebuilt an identical
path buffer for every connection. Reuse that buffer per candidate; the change
does not relax geometry checks or alter candidate choices. The indexed frontage
lookup was also checked against the complete scan on real alternatives.

Two full-day checks then reached the 30-minute app limit during optional
land-use polishing, losing their otherwise completed work. Reuse prepared
boundary linework and repeated ground searches without changing acceptance.
All 14 saved park-path alternatives have identical frontage groups and physical
scores under the reference and revised calculations. Reserve the last five
minutes for final validation: optional polishing may retain its completed
state with an explicit incomplete-search warning, but never skip ownership,
parcel, major-divider, street/alley or overlap checks. The complete result still
must pass those checks before publication. Both final runs completed the
optional search and all mandatory checks, as recorded below.

A later QA attempt was interrupted when a requested 30-second wait returned
after approximately 32 minutes. Its wall-clock deadline expired without a
completed result. Do not use those aborted wall times as compute-performance
benchmarks. The local QA workers now make a temporary system-availability
request while running, retain real elapsed and CPU times separately, and
release the request when they exit. No power-plan settings are changed.
The indexed park-path generator also reproduces all 114 reference paths in
the focused cohort, including their order and mapped connection evidence.

Screenshots, original result copies, ownership hashes and a per-example receipt
belong in `audit/partition_app/access_boundary_2026-11-16/`. Coverage alone is
insufficient. DONE requires saved outputs, access/parcel/major-divider and
overlap regression checks, plus visual review of every affected example.

Full-day Chrome QA rejected another draft: the Thursday 1,188/847 division
wrapped a service strip around 448 addresses belonging to its neighbour. A
linear enclosure penalty of `4r` was insufficient; use `4r + 120r²`, where `r`
is enclosed other addresses divided by the area's own count. This is a general
soft penalty, not a street exception. Empty parks and rivers contribute no
addresses. Preserve `browser-qa/thursday-review-2.png` as rejected evidence.
A preliminary quadratic weight of 40 still selected a smaller wrapping
458/1,577 division; preserve `thursday_small_wrapping_rejected.json` and
`browser-qa/thursday-shape-correction-probe.png` as rejected evidence too.

An optional Wednesday school/park comparison also failed parent coverage by
18.373 m² and aborted the whole calculation. Reject that specific candidate,
record the reason, and retain the valid regions. Do not suppress unrelated
errors or loosen final geometry checks. The regression suite has 248 passing
tests; the final saved-result and visual checks are recorded below.

Do not hide final access remnants behind the general road-QA warning. The
Thursday draft retained 41 Burrows and 22 Alfred/Main addresses without a
demonstrated internal connection to their area's main population. These are
specific unresolved planning-access warnings, not proved legal truck routes.
The general final-area review accounts for real short intersection links and
keeps unmatched addresses unknown.

Final engine 4.7 results, visually reviewed in Chrome using cached local vectors:

- Wednesday `8f805fc391887a4e83e4600d202306cb55ae018e3539e320b649ac2ce1f7c228`:
  22,202 unchanged source IDs, 46 areas, zero errors and zero published overlap;
  20,724 independently checked serviced parcels. Complete runtime 1,144.594 s.
- Thursday `6028b0f3bba02da73e15029034c672fa44e47dfb869f91a9e747144a44bc97a6`:
  19,316 unchanged source IDs, 31 areas, zero errors and zero published overlap;
  18,405 independently checked serviced parcels. Complete runtime 804.572 s.
- All 38 case records have actual before/after visual findings and screenshots;
  the rejected outer-ribbon comparison makes 39 views. Both optional searches
  completed. No live basemap requests, input uploads or truck solves were used.
- The full-day Amber Trails cohort is 1,350 / 469 / 156, joining complete owners
  of 1,350 / 1,005 / 432. Its rejected stepped green area and outer ribbon are
  gone. Do not describe the earlier isolated 444/1,531 option as the saved result.
- Tyndall 911/543 populations remain exact. Eighteen of the old 39 Wednesday
  populations and 19 of Thursday's 32 remain exact; not all previous satisfactory
  populations are preserved. Thursday's 2,035-address parent remains whole.

B07 remains OPEN. Four Wednesday and five Thursday areas exceed 1,100. The
Templeton split, exact two-way Amber Trails alternative, Thursday Matheson/
Rupert's Land split, requested Arlington/McGregor/Salter and Isabel arrangement,
THU-026 merge and smaller Jarvis lobe remain unresolved. Wednesday's narrow
northern road-space extension by old WED-006/023 and isolated one/two-address
site populations also remain review items. Thursday's 41/22-address access
remnants are explicitly warned. See the per-example outcomes in
[partition-access-validation.md](partition-access-validation.md) and local
`case_review.json`; REVIEWED_OPEN means inspected, not corrected or approved.

## DONE B06 - Clear internal park corridor omitted from an oversized Wednesday area

User QA 2026-11-16: WED-001 in result
`d782c943502a7a6d801f52e903e39e71f9902677cba2c3d13d2e7429c0eda357`
holds 1,454 addresses. The supplied screenshot marks the continuous school/park
corridor from Inkster to Burrows. Compare useful children even when both fall
below 900; the user's approximate 800/600 counts are an example, not a quota.
The street-only Garden Grove candidates do not close through the park and
produce no useful split or tiny remnants. Generate complete supported land-use
alternatives, then retain all street/site/parcel/major-divider checks.
Preserve the screenshot and candidate evidence in the existing partition audit.
Resolved in engine 4.6, result
`7899007b2c8f6638593e9b22f0b307abfafc5c242396fca196067fec46f388e5`.
The full 22,202-address run took 503.639 seconds and splits the original cohort
into 911 and 543. It preserves every source point, all 20,724 checked serviced
parcels, major dividers and street/alley continuity. The cached before/after
map and saved CSV/GeoJSON/review verify the affected result. Two other
above-1,100 areas remain unresolved; this repair does not declare the whole
weekday balanced.

Cause and prevention: generate complete connected mapped land-use corridors as
well as ordinary streets. Union duplicate outlines before making short checked
road-space closures; omit unrelated outer-edge strips. Remove serviced property
components from imprecise public park footprints so their outlines cannot slice
residential lots. Never waive the parcel/street gates to accept a candidate.
Regressions cover a below-preferred 600/800 split, a road-gap connection blocked
by property interiors, and a public park outline intruding into a serviced lot.
Evidence: `audit/partition_app/wednesday_boundary_validation_2026-11-16.json`
and `wednesday_tyndall_before_after_2026-11-16.png`.

## DONE D04 - Shared-edge export slivers block Wednesday routing

User QA 2026-11-16 on the same saved result: address ownership passes for all
22,202 IDs, but published WGS84 polygons overlap by 30.013593 m2 along Leila.
The WED-009/010 and WED-009/017 slivers are about 4 cm wide, with areas
6.323646 and 23.689947 m2. Native overlap is zero. Shared vertices must stay
consistent through coordinate conversion; retain the material-overlap failure
gate. Explain the actual failed check in the routing UI. Evidence:
`audit/partition_app/wednesday_overlap_diagnostic.json` and the saved failed
result.

Resolved in the same engine 4.6 result. Native and published overlap are both
zero; an independent intersection-in-WGS84-then-project check confirms zero
across all 741 section pairs. Both owners now carry the same existing collinear
metric vertices before inverse projection. Numerical validity repair preserves
all polygon components and checks symmetric difference; real overlap is never
trimmed by this preparation. The existing material-overlap failure gate remains.
Regressions reproduce different nonlinear WGS84 chords from mismatched vertex
spacing and prove actual overlaps/disjoint land remain unchanged. Saved exports
and the live result API pass; 25 other root delivery files remain unchanged.
Prevention: intersect published polygons before projecting the intersection.
Projecting each polygon separately can conceal the four-centimetre export
slivers. Show actual failed error findings before secondary count warnings.

Read OPEN issues before each change and retain the prevention lessons from DONE
issues. Example streets and section IDs identify evidence only; they must never
be algorithm exceptions. Record the affected input/result, cause, correction and
verification. DONE requires a checked result, not just a proposed code change.

## DONE B05 — Ordinary road chosen over a stronger nearby land-use edge

Reported 2026-11-09 on result `08f40d8260c09abff4233e8ec837402a5078f5c7f8ad4c8edb396988706e8f4c`:
TUE-001's west-side Cullen Drive frontage should join TUE-009 using the large
school/open-space boundary behind it. A road-following split is valid but should
score worse than an available coherent school edge. TUE-012's commercial area
similarly offers a stronger division than an ordinary road. These are quality
comparisons, not new mid-block-cut violations. Highways retain higher precedence.

Expected: generate real school/commercial/open-space alternatives, then score
their continuity and separation of residential frontage above ordinary roads.
Do not manufacture connectors or route through school/commercial land. Preserve
all source IDs, served parcels, major barriers and complete-site protections.
TUE-004/TUE-009 illustrate that a weak planning seam should encourage adjacent
truck ownership; no named pair may become a forced routing exception.

Implementation and additional QA, 2026-11-10: the previous repair searched City
street corridors only, so it never compared the coherent school-edge transfer.
The new proposal search uses mapped land-use/City parcel faces, with all affected
neighbours scored before acceptance. Non-residential strength is below protected
major roads and above ordinary streets. Truck allocation receives the same weak
shared-edge evidence as a preference after feasibility and fleet priorities.

Visual QA also caught a proposed corner cut between adjacent Betsworth homes
despite a clean automated check. A projected edge ended nanometres short of its
road, so an exact intersection missed it; a new 3 cm intersection tolerance
retains this check. A property side line is not road space: proposed short
connections must avoid serviced parcel sides as well as property interiors.
The corrected local proposal keeps the complete corner frontage and uses the
actual school access gap (27 addresses transferred, candidate counts 993/930).
Resolved 2026-11-10 in engine 4.5, result `448e517113575ac1ea886fa3055b469bba454435eb7f2f33695a79a92f41b27f`. The full Tuesday run transfers 27 addresses from TUE-001 to TUE-009; their counts are 993/930. All 21,233 source IDs and coordinate/address fields reconcile, with zero material parcel cuts, major-road crossing areas or street/alley boundary flags. The offline Chrome before/after map verifies the school frontage and corner access gap. Refinement from the saved partition took 551.1 seconds; 200 Python tests pass. Receipt: `audit/partition_app/landuse_qa_validation.json`. No Tuesday truck routes were regenerated; the new affinity applies to future solves. TUE-006's unresolved oversized section remains OPEN B04.

The first whole-day comparison exposed a second scoring problem: an optional
land-use reshuffle took a satisfactory neighbour outside the requested range,
and prevented the smaller Cullen improvement. Reject such optional refinements
before accepting their edge score. Required major-divider corrections remain
earlier in the pipeline. Retest from the unchanged street-repair checkpoint and
assert the complete geometry, membership and protection groups match that saved
state; do not publish the rejected intermediate run.

The full-neighbour comparison also exposed a false 1,000-point cut at a
three-area junction: the shared road-following edge stopped at the school gap,
and the checker compared the nearest homes on opposite curbs. For a partly
road-aligned endpoint, compare ownership changes along each curb separately.
Keep the original transverse-cut check when the boundary actually crosses the
road. The complete school candidate then scores 74.7603 versus 76.1461 for the
saved boundaries; the smaller incomplete-corner alternative still fails.

Published scope: only the 27 school-frontage/corner addresses changed owner.
TUE-004 remains 645 and TUE-012 remains 858. The commercial-edge preference is
implemented, but this run did not find a better admissible replacement for
TUE-012. Do not describe its commercial example as a completed redraw or infer
that TUE-004/TUE-009 have already been assigned to the same truck.

## DONE B01 — Fragmented sections accepted despite street/alley penalties

Reported 2026-11-09: Tuesday 001/004 and 003/021 have rear-lane seams,
mid-block cuts and narrow frontage fingers. The saved Tuesday result
`3c9b51e9d347b781f2e062c80e859453c717a59157cabd0ea6e9a8135639d164`
flags 11 street breaks/3 alley splits for 001/004 and 2/3 for 003/021.
The whole-frontage fallback optimizes counts before continuity; repair can leave
violations as warnings. A section's last repaired edge may report zero penalty
although another shared edge still fails. Count status is not boundary status.

Expected: use consistent street/alley quality across every split path and all
affected neighbours. Prefer complete supported road/school/park edges over
opposite-curb strips and back-lane detours. A boundary following a road through
intersections is valid; a transverse cut between adjacent homes is different.
Do not erase frontage protections globally just because one valid road-aligned
boundary is permitted. Retain the best complete state and prevent repair cycles.

Resolved 2026-11-09 in engine 4.4. Standard and fallback admission now both pay
1,000 points for each unsupported street/opposing-alley split. Repair compares
all affected neighbours, requires strict improvement and disallows repeated
complete states. Frontage exceptions remain scoped to their actual children.
The regenerated Tuesday result has zero flagged street/alley boundaries across
all final shared edges. Chrome comparison verifies the reported frontage and
Westdale detours are removed. Receipt: `audit/partition_app/boundary_qa_validation.json`;
190 Python tests and two JavaScript suites pass.

Lesson: apply quality before accepting a candidate, and audit the whole final
partition. A clean last-edited edge cannot clear a dirty neighbouring edge.

## DONE B02 — Valid connected street corridor omitted at parent boundary

Reported 2026-11-09: the finite Dale/Rannock combination was never a candidate.
An arm reaching the parent boundary exactly was rejected for not extending
outside a buffer. Diagnostic `audit/partition_app/tue001_tue004_dale_rannock_diagnostic.json`
shows 807/1,097 addresses with complete ownership and no material parcel cuts,
versus saved 843/1,061. This diagnostic alone is not an accepted replacement.

Expected: accept mapped arms reaching the real boundary, without extending a
dead end or inventing a connector. Evaluate complete candidate quality.

Resolved 2026-11-09. Finite arms reaching the actual parent boundary are now
eligible. The corrected candidate check generates 807/1,097 with all 1,904 IDs
and zero street/alley violations. Full optimization considers the surrounding
sections too and chooses continuous road divisions without forcing this example.
Evidence: `audit/partition_app/tue001_tue004_corrected_candidate_check.json` and
the final comparison map. Lesson: boundary contact is sufficient; do not require
an artificial extension outside the parent. Keep dead-end rejection tested.

## DONE B03 — Strong roads replaced by parcel detours

Reported 2026-11-09: Portage Avenue's major corridor is crossed by commercial
parcel-shaped fingers. Related screenshot: a narrow opposite-curb strip near
Bruce/Lodge has a school boundary behind it; Conway/Moorgate between Ness and
Bruce is another poor ownership protrusion at 003/021.

Expected: rail, water and physically major roads take precedence over count
balancing. Use mapped speed, carriageways, lanes/width and actual land-use edges,
never street names. A single frontage/parcel must not silently dissolve a major
corridor or drag neighbouring residential territory across it. Audit every
final boundary, including boundaries inherited from natural sections.

Implemented speed policy: explicit speeds above 60 km/h are strong dividers;
60 km/h roads also qualify with mapped arterial/highway classification.
Unknown speed is unknown. Ordinary residential roads do not become major roads
merely to reach an address target.

Resolved 2026-11-09. Controlled-road evidence propagates to matching finite City
centreline segments despite source offsets. The final major-road gate checks
populated banks independently. Portage now follows the corridor, the reported
Conway/Moorgate strip's 80 IDs all belong to revised TUE-003, and the Strathmillan
frontage detour is removed. No street-name or area-ID exception was added.
Final Tuesday: 21,233 IDs, 36 areas, zero major-road crossing areas, zero material
parcel cuts and zero ownership/geometry errors. Comparison:
`Tuesday_boundary_QA_review.html`; complete evidence in the validation receipt.

Lesson: carry physical evidence between source representations and independently
check the published geometry. Count/parcel protection cannot silently dissolve
a major corridor. Retain small isolated populations when a real barrier prevents
merging them.

## OPEN B04 — Municipal split gate inconsistent with fallback

Reported 2026-11-09: TUE-006 has 3,432 addresses. Westwood/Kirkfield gives
2,586/846. A fully road-aligned opposing-curb group was vetoed just because the
candidate is municipal, while another group genuinely separates neighbouring
same-side homes and parcel 187470 is materially cut. The separate whole-frontage
fallback stopped on one disconnected protected group.

Expected: apply road-following exceptions by geometry, not candidate label.
Preserve real coordinate/site/parcel and mid-block protections. Do not waive all
municipal checks or imply that the municipal split alone meets 1,800/2,000.
Evidence: `audit/partition_app/tue006_municipal_split_diagnostic.json` and
`Tuesday_TUE-006_municipal_boundary_review.html` in the existing delivery folder.

Partial correction 2026-11-09: municipal candidates now receive the same genuine
road-following exception as other candidates, and fallback quality is scored
consistently. TUE-006 still has 3,432 addresses in the checked 4.4 result. Real
same-frontage/parcel constraints remain; no artificial 1,800/2,000 cap or waiver
was introduced. Keep this issue OPEN until a valid better division is generated.

## DONE D02 — Disconnected cadastral land joined populations across highways

The new major-road gate found five rural addresses grouped across highways.
One source parcel ID covered four disconnected pieces; only one held the service
point. Whole-ID geometric protection pulled the remote pieces and their populated
neighbours into one section. Protect each complete connected serviced component,
preserving its original parcel ID. Shared sites and coincident points remain
protected. The full run now keeps the three physically separated populations
apart and passes all parcel/coverage/major-road checks. Synthetic regressions
also verify whole local parcels and real shared-site conflicts.

Lesson: a cadastral identifier is not proof of physical connectivity. Unoccupied
remote land must not establish collection adjacency across a major barrier.

## DONE D03 — Geometry comparison failures and repeated scoring work

Expanded all-neighbour scoring exposed mixed-precision GEOS overlays and isolated
corner contacts masquerading as shared dividers. Compare unchanged coordinates
without precision metadata and keep only actual shared linework. Repeated seam
buffers and full municipal/park buffers also dominated runtime; reuse local
buffers and clip evidence to the relevant window. One difficult edge fell from
37.428 to 2.121 seconds with identical complete quality output. The final full
Tuesday run completed in 544.367 seconds. Evidence: regression tests,
`boundary_score_equivalence_1.json` and `boundary_qa_staged.log` in the audit folder.

Lesson: profile and prove score equivalence instead of weakening geographic
checks to make the calculation faster.

## DONE D01 — Monday-only upload and stale day state

Resolved 2026-11-09. Row weekday takes precedence over worksheet/filename;
mixed-day input requires selection, and old map/routes clear on replacement.
Tuesday CSV/XLSX retain all 21,233 IDs; Monday remains 21,507. Receipt:
`audit/partition_app/tuesday_webapp_validation.json`; 177 Python tests and two
JavaScript suites passed at delivery. The user handles uploads/flow review.

Lesson: day identity must follow import, labels, cache, exports and route
compatibility; changing a filter alone is insufficient. Preserve original IDs
and never concatenate overlapping workbook sheets.

## Standing lessons from earlier user QA

- Natural geography first, then merge/regroup only where useful. Do not raid a
  satisfactory neighbour simply to enlarge an undersized section.
- A small count deviation is preferable to an unsupported mid-block or
  opposing-alley split. A whole ordinary road can be a supported divider when
  stronger alternatives do not give a useful division.
- Merge under-100 pockets to a compatible nearby larger area within 500 m,
  unless a real major boundary or remoteness prevents it.
- Truck counts are outputs. Keep adjacent work together, prefer whole sections,
  include every disposal trip and right-side road pass, and never manufacture
  waiting to make a short route look productive.
- Preserve accepted outputs and source files. Back up corrections in their
  existing audit folder, validate offline first, and distinguish a diagnostic,
  a code fix and an actually regenerated/verified app result.
