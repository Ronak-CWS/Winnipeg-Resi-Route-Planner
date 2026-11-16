# Winnipeg QA and mistake log

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
