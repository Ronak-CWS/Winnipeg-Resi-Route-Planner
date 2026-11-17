# Partition road-access and shape review

Engine 4.7 compares actual mapped road access before optional count merges.
Two polygons touching, or being joined by empty industrial land, does not prove
that their service populations connect. Access-based divisions remain separate
through later count and boundary-quality refinement.

## General rules

- Use the local road inventory's actual node identities. Geometrically crossing
  roads without a shared node do not connect. Clip paths to the proposed planning
  footprint, retaining real junctions and separate clipped endpoints.
- Keep major-divider rules ahead of balancing. A short arterial intersection
  connection may demonstrate local access, with a 60 m budget over the entire
  connection, never 60 m per edge. This does not waive rail, water or highway
  separation checks.
- Require the dominant known address populations to connect. Unmatched road
  access stays unknown; small isolated populations remain visible for review.
  Planning connectivity is undirected topology, not a legal truck route or a
  confirmed bin location. Directed access and truck restrictions belong to the
  subsequent routing checks.
- Compare complete finite paths through mapped streets, including paths that
  change street names. Endpoint completion is limited to supported road space
  and cannot cross property interiors or protected frontage gaps.
- Score all eligible road and municipal candidates using their physical
  evidence and complete seam length. A candidate label cannot exclude a
  stronger road alternative, and average strength cannot make a long stepped
  residential-road division artificially cheap. Retain the unsplit parent
  when count improvement does not justify the complete physical boundary cost.
- Generate connected paths combining actual mapped park edges and short checked
  road-space connections. An over-broad ordinary road group near a real park gap
  is assessed geometrically; coordinate/site/parcel groups and actual
  street/alley-cut rejection remain mandatory.
- Penalize service populations wrapping around another owner's addresses.
  Let `r` be the number of other addresses strictly inside the population's
  convex hull divided by its own count. The soft score is `4r + 120r²`, so a
  substantial wrapping population is much more costly than a small corner.
  Empty land contributes
  nothing. The hull is a measurement only; published boundaries still follow
  checked mapped features and preserve parcels, frontages and major dividers.
- Remove only substantial, wholly unserviced lobes beyond complete mapped major
  dividers. Reconcile complete enclosed empty faces after all refinements while
  preserving serviced enclaves and the publication overlap failure gate.

No example street names, section identifiers or requested hand-drawn lines are
algorithm exceptions. The road-chain search is bounded; these comparisons do
not establish a globally best partition.

## Validation and evidence

The regression suite currently has 248 passing tests. It covers real road nodes,
clipped paths, outside-footprint detours, prohibited connections, the complete
intersection-distance budget, persistent access separations, mapped road chains,
property-blocked endpoint gaps, empty railway lobes, serviced enclaves, and a
wrapping ribbon versus equally sized compact populations, a legitimate park gap
inside an over-broad street group, and retaining an unsplit parent over a long
stepped road division, and rejecting a park split that strands a population
whose connection passes through the other proposed child.
It also verifies that count improvement cannot buy a heavily wrapping service
population, and that an invalid optional subdivision retains the valid areas
without suppressing unrelated input errors.

The rejected first Wednesday candidate, the user's wrapping-strip screenshot,
original saved results and before/after comparisons are preserved locally in
`outputs/2026-11-04_monday_map/audit/partition_app/access_boundary_2026-11-16/`.
The focused original 1,975-address Amber Trails cohort produced 701/657/617
addresses with the revised score and no street/alley findings. Although this
removed the outer ribbon, user visual QA rejected its stepped road boundaries.
That candidate is withdrawn. A continuous two-area park-strip division must be
compared against retaining the whole parent; count improvement cannot justify
a convoluted residential-road boundary. A later 847/1,128 park candidate is also
rejected: 92 Baltic Bay/Innsbruck Way addresses become disconnected from their
owner's internal road network. Split candidates and fallback now receive the
same access checks as later quality refinements. The normal focused pipeline
selects a complete park-path option of 444/1,531. Each child has one connected
known road population; four addresses have unmatched access. The larger count
remains explicitly above the requested range. Later continuity and fallback
steps use the full physical seam cost, so they cannot replace a stronger park
edge merely because a road-only score omits that preference.
This was a focused intermediate result. The completed full-day calculation and
all affected-neighbour checks below supersede it for the saved delivery.

Complete reference and optimized calculations agree on the frontage groups and
physical scores of all 14 saved park-path alternatives. The full nearby-area
comparison also returns the same alternatives. Prepared boundary linework and
repeated ground searches are reused; the narrow edge of the eight-metre search
still receives the original rounded-buffer intersection test. Source geometry
and acceptance thresholds are unchanged.

The earlier full checks reached the 30-minute app limit during optional
school/park polishing. Interactive runs now reserve the last five minutes for
mandatory final validation. Only the optional polishing stage can stop early;
it keeps the complete current regions and reports that alternatives remain
untested. Ownership, parcels, major dividers, street/alley continuity and
published overlap checks still run. Candidate ordering remains deterministic;
the amount of optional search completed can depend on available runtime.

Full-day visual QA also rejected a Thursday 1,188/847 division that surrounded
448 of the other area's addresses. The earlier linear enclosure penalty was
too weak; the quadratic term increases only with occupied interleaving, never
with empty park or river land. A weaker quadratic weight still selected a
458/1,577 wrapping alternative; that draft is also rejected. Both remain in
the audit folder. Final saved-result checks use the stronger weight above.
Wednesday additionally exposed an optional frontage subdivision with an
18.373 m² coverage discrepancy. That proposal is now explicitly rejected in
the comparison audit. The original areas remain intact, and the mandatory
final coverage check is unchanged.

Final areas also report their remaining mapped road populations. The review
distinguishes actual short intersection connections from disconnected groups,
and unmatched address access stays unknown. Unresolved significant groups
appear as area-specific `PLANNING_ROAD_ACCESS` warnings in Checks. This does
not establish legal directed truck access or a confirmed collection position.

## Final whole-day checks

| Check | Wednesday | Thursday |
| --- | ---: | ---: |
| Source IDs preserved | 22,202 | 19,316 |
| Planning areas | 46 | 31 |
| Published overlap | 0 m² | 0 m² |
| Validation errors | 0 | 0 |
| Serviced parcels independently checked | 20,724 | 18,405 |
| Above the preferred 1,100 maximum | 4 | 5 |
| Below the preferred 900 minimum | 38 | 22 |
| Exact prior populations retained | 18 of 39 | 19 of 32 |
| Complete partition elapsed time | 19 min 4.6 s | 13 min 24.6 s |
| Optional search complete | Yes | Yes |

These timings include partition calculation and final validation using cached
prepared geography; they are not truck-route timings or cold-cache guarantees.
All source point fields reconcile, and ownership, parcel, major-divider and
street/alley checks pass. The independent parcel check detects no material cuts.
Chrome visual QA covers 38 recorded cases in 39 before/after views, including
every materially changed population or boundary and the rejected ribbon draft.
It uses local cached vectors with no public map requests. Screenshot hashes,
source-population hashes and exact result keys are retained in `case_review.json`.
No workbook upload or truck-route solve was started.

The six existing Wednesday/Thursday exports and matching result-cache entries
are updated after these checks, with the prior files backed up in the audit
folder. The other 22 root delivery files remain byte-identical. The restarted
local app serves engine 4.7 and both exact checked results; Thursday stays the
active day. `publication_receipt.json` records the keys and live verification.

The full-day Amber Trails result removes the rejected green stepped area and
outer ribbon. The original 1,975-address cohort becomes 1,350 / 469 / 156 within
complete owners of 1,350 / 1,005 / 432, because the southern populations join
adjacent areas. This is neither the earlier focused 444/1,531 result nor the
user's exact two-way park line. The 1,350 count remains above range.

| Original example | Observed final outcome / remaining issue |
| --- | --- |
| WED-009 / 003 | Northern 274 join the earlier 940; southern 705 separate. Combined 1,214 remains oversized. |
| WED-008 / 016 | Diplomat/Beecher detour removed, but whole 1,568 retained; Templeton split unresolved. |
| WED-014 / 022 | Western/southern population separates from eastern park strip; one resulting owner remains 1,268. |
| WED-012 | Northern population joins western access group; exact north-of-Jefferson separation not achieved. |
| WED-005 / 022 | North of Adsum is complete at 913; southern 1,268 and two-address site pocket remain review items. |
| WED-001 / 002 | Earlier 911/543 populations and park/school boundary preserved. |
| THU-004 | Large empty railway appendage removed; smaller Jarvis lobe remains. |
| THU-026 / 021 | Single-address merge unresolved under the recorded important-boundary veto. |
| THU-005 | Complete 2,035 retained; both wrapping divisions rejected, satisfactory split still missing. |
| THU-012 / 024 | Northern Jefferson population reassigned north; 1,305/1,268 counts remain. |
| THU-022 / 020 / 007 / 003 | Interlocking/cross-Main assignment simplified; requested full arrangement, 41/22 access remnants and two-address pocket remain open. |
| THU-013 / 021 / 017 | Western block joins western owner, giving 977/687; requested Isabel division remains open. |

Additional changed-neighbour findings are retained in the local case receipt.
They include the northern narrow road-space extension by old WED-006/023,
isolated service parcels and previous satisfactory populations that are no
longer standalone areas. These concerns are not erased by passing coverage.

OPEN B07 in [mistakes.md](mistakes.md) continues to track unresolved examples.
`REVIEWED_OPEN` means visually inspected with an outstanding issue, not approved
or fixed. The results remain provisional for field pickup and directed truck
access; no global optimum or complete preservation of earlier areas is claimed.
