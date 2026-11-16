# Weekday service-area partitioner review

Upload handling was updated on 2026-11-09: Monday and Tuesday can be loaded
directly, and other uploaded weekdays are inferred from rows, worksheet or
filename. Ambiguous files require a day/sheet selection. Each run retains one
day's source IDs and uses day-specific exports. The project brief records the
current Tuesday validation. The geography discussion and figures below retain
their original engine 4.2 review context; the weekday update does not change
boundary scoring.

Reviewed 2026-11-06. This Winnipeg-specific app adapts the reference
partitioner's methods without using its address-deduplicating importer,
network acquisition, route solver or legacy map exporter.

Engine 4.2 uses one range workflow and treats street-following intersections as
valid. The former four Grosvenor intersection flags were false positives;
unsupported mid-block cuts and opposing alley-side splits remain heavily
penalized. Municipal alignment supports scoring without a 60% eligibility gate.
Complete finite City streets with broad-road evidence are considered consistently.
Explicit mapped speed above 60 km/h is major-boundary evidence. Excessively long
internal seams receive a separate neighbourhood-shape cost, not a street-cut flag.

Current output: 31 areas and 21,507 source IDs, with no overlaps, reliable points
outside their areas, material parcel cuts or railway-separated populations in
one area. Five areas meet 900-1,100, 21 are below and five above. Range compliance
is unresolved. The illustrated Whyte Ridge groups are 946 and 1,156, with the
283 across the railway separate. The original alley pair and 144 illustrated
Fleet Avenue IDs now each share an owner. Examples are fixtures only.

Use `verify_partition_exports.py`, `verify_rail_boundaries.py` and
`verify_boundary_hierarchy_examples.py` with the current key. The earlier
`verify_street_alley_examples.py` records the exact historical 4.1 footprint;
its former count/remaining-warning expectations are not the current contract.
Receipts remain under the existing Monday `audit/partition_app` folder. The
City boundaries button overlays local official neighbourhood geometry in amber;
51.84% of current shared boundary length lies within 8 m of those lines.

## Natural areas first

The single range-based workflow first builds a natural partition from frozen City
neighbourhoods and credible physical boundaries. Ordinary street frontages,
shared sites, shared coordinates and serviced parcels stay whole. Protection
ends at real intersections and rail/water/major-road crossings, not at arbitrary
park or land-use outlines. Railways, water and controlled highways are
important separators regardless of count.

It scores compatible whole-area merges and useful splits of oversized
areas. The opening range is 900-1,100; its two endpoints are editable,
with a minimum width of plus or minus 10%. An undersized natural area must not take a
satisfactory neighbour outside its range. Count scoring discourages tiny
fragments: 650 is preferable to two 300s, and two useful 650s can improve a
1,300-area when credible geometry permits. Boundary protection still takes
priority over a numerical improvement.

Municipal divisions and connected broad-road evidence are split candidates.
City parcel right-of-way measurements, mapped multi-lane/divided-road evidence
and municipal alignment support the corridor inventory. A road-plus-park
candidate is tested separately from unrelated park outlines. Direct supported
cuts are considered before park completion; no finite line becomes an
extended ray. Ordinary roads and alleys are excluded from standard splits.

Only when supported divisions fail, and an area contains at least two requested
minimum-size sections, can last-resort whole-frontage regrouping be attempted
inside that area. Its internal mesh uses real parcels, streets and finite
junction-to-parcel connectors. The exported areas are unions of complete mapped
frontage blocks, never the small mesh faces. Shared sites, paired ordinary
curbs and material serviced parcels remain whole. Resulting rear-property/alley
boundaries are flagged for pickup-access review; mapped alleys never establish
confirmed collection access. A modest overage does not enable this fallback.

Street-run continuity is checked across connected City segments, not just
within each intersection block. A transverse cut between neighbouring houses
and separating the opposite sides of a mapped alley each cost 1,000 score
units, overwhelmingly more than small count gains. Strong supporting feature
edges can justify a street division. Local opposing houses are compared along
each lane, so mixed ownership elsewhere on a long lane cannot hide a split.
Related last-resort neighbours can be repartitioned along a continuous finite
City street, with municipal alignment as supporting evidence. Only the ordinary segment groups
aligned with that selected street can receive a recorded longitudinal curb
exception; sites, shared coordinates and parcels stay protected. An identical
seam cannot be selected repeatedly. Remaining unsupported seams stay visible
as review findings. The natural partition is an internal baseline, not another
UI approach. No road name or MON identifier is an algorithm rule.

Under-100 pockets prefer a compatible local neighbour. Actual service-point
distance and major-highway evidence rank nearby choices; an empty-land centroid
must not pick the wrong neighbourhood. Important physical barriers still veto
a join. Explicit nearby groups retain their real pieces and a checked probe
within 500 m; no buffer bridge or road access is inferred. A small area can
remain when protected or remote.

Both ends of the requested range are reported. Above- and below-range areas
have reasons and are not counted as meeting the range. Passing geometry does
not establish range compliance, pickup access, legal crossings or a truck route.

## Numerical correction and independent verification

The former polygoniser and railway verifier shared a pre-clipping weakness:
a diagonal clipped before noding could stop a floating-point step off the
parent edge and silently fail to divide it. The engine now nodes the complete
finite source lines with the parent before filtering faces. The independent
railway audit uses a separate library split of the full finite rail network;
it correctly rejects the former saved natural result's two missed rail cuts.
The old engine-3 railway-pass claims are superseded by this stronger check.

All reliable source points, protected groups and material parcel cuts are
checked again against the final assignment. Native shared edges are noded
before publication. Published polygons are independently checked for validity,
containment, overlap and owned holes. Four estimated locations do not create
boundaries. The original workbook and five Monday coordinate files are
preserved byte for byte. Fresh-process CSV/XLSX replay must agree before release.

The user's MON IDs and named-road illustrations are saved only as source-ID
regression fixtures in the existing audit area. The algorithm does not read
those fixtures or hardcode named roads, neighbourhoods or output labels.

## Map interaction and resource policy

Area details appear only on click, including clicks in empty space inside an
area. Address clicks retain address details and stop area-popup propagation.
The map has independent area/context/address renderers and polygon hit testing.
Settings collapse on the first result load; Expand map hides the other panels and
resizes the same map. No layout toggle fits, recreates or reloads the map.

Default context is local with zero map-provider requests. Optional OpenFreeMap
retains the all-resource queue/cache limits: four concurrent requests, 200
unique URLs, a 25 MiB stop threshold, 12-second timeout and no automatic retry.
No idle/render handler fits or rebuilds the map. No geography or geocoding
requests occur during uploads or partition runs. The OSMF/Carto raster
endpoints remain forbidden.

Chrome access now works through the installed control-chrome skill. The
unified-computer-use connector's earlier failure is historical. The unrelated
Portal preview at localhost:8190 refused its connection; Monday uses port 8765.
The verified release and Chrome evidence are recorded below.

## Historical 4.1 continuity correction - 2026-11-05

Superseded by the 4.2 result above. The four Grosvenor intersection flags below
were subsequently identified as false positives, not mid-block cuts.

Engine `winnipeg-geography-4.1` runs at **http://127.0.0.1:8765**. The UI has
one preferred-range workflow; the natural partition remains an internal
baseline. Default 900-1,100 produces 29 areas: four within, 20 below and five
above, largest 1,431. Counts do not override the boundary review findings.

The illustrated 2,027-address footprint is now split 830/1,197 along 776.5 m
of actual City street line. An independent check confirms identical parent
coverage, no outside IDs taken, full alignment and all 144 Fleet Avenue rows
kept together. Its former 11 street-run and three opposing-alley splits are
gone. A second related seam is corrected by the same generic process. One
remaining shared seam still has four street-run and one opposing-alley-side
split, clearly flagged against its two current areas. No safe eligible City
corridor replacement was found. Opposite curbs of the two selected continuous
street boundaries remain explicit pickup-access review exceptions.

75 Python cases, map interaction tests, all eight earlier user-example
regressions, independent railway audits of both the natural baseline and
range exports, and fresh-process CSV/XLSX replay pass. All 21,507 source IDs,
source and coordinate fields remain unchanged. Geometry checks retain zero
reliable points outside, split protected groups, material serviced-parcel cuts
or unassigned holes. The approximately 0.00000005 m2 published overlap is
numerical noise. Original workbook and all five coordinate deliveries match
their saved hashes.

Chrome confirms the single form, normal cached Monday CSV run, larger map,
click-only area details, address details and visible remaining warnings.
Expanded map at the current 1536 x 826 browser window is 1506 x 618 px, with
one map container, zero tooltips and no browser warnings/errors. Local context
requires zero new provider calls. API checks independently verify Excel upload,
byte-identical Excel download, all three exports and the ZIP. Chrome chooser
permission is a separate extension setting; it was not changed.

Evidence: `street-alley-example-validation.json`, `export-validation.json`,
`natural-first-example-validation.json`, keyed `rail-validation.json`,
`natural-first-api-validation.json`, `source-preservation-street-alley.json`,
`continuity-chrome-validation.json` and `continuity-chrome-*.jpg`, all inside the
existing delivery's `audit/partition_app`. The range partition hash is
`9d0010f8bc52bed64a254fa5601d71ec740d32054d9d950925937646faf7c9ed`.

## Previous natural-first release - 2026-11-05

Engine `winnipeg-geography-4.0` was the previous local release.
The same existing Monday delivery folder is used; earlier current deliveries
and documentation are backed up in its existing audit area.

| Mode | Areas | Largest | In preferred range | Below | Above |
| --- | ---: | ---: | ---: | ---: | ---: |
| Natural sections | 28 | 2,990 | n/a | n/a | n/a |
| Preferred 900-1,100 | 29 | 1,431 | 7 | 18 | 4 |
| Preferred 900-1,200 | 29 | 1,431 | 9 | 19 | 1 |

The range is **not fully met**. Above-1,100 counts are 1,102, 1,105, 1,181
and 1,431. Undersized areas remain visible with boundary/neighbour reasons.
Two large natural parents needed last-resort regrouping into five complete
frontage areas; those rear-property/alley boundaries remain review items.
They do not imply confirmed alley pickups or an accepted operating plan.

All 21,507 IDs are assigned exactly once in each run. Checks cover 19,946
serviced parcels; there are zero material parcel cuts, split protected groups,
reliable points outside, unowned holes or material overlaps. Published numeric
overlap is below one square millimetre. The default has 28 single polygons and
one explicitly supported nearby multi-piece list. Four estimates remain
boundary-excluded; 670 reliable records still lack a containing parcel reference.
Independent 366-feature railway audits pass all three saved runs.

The fresh-process CSV run exactly matches the Excel partition hash
`95902a683ec99f97516a5a3ee6246ed375b9b190c9bc5ff0e49ff8fd4dc5a2e8`.
The API test uploaded Excel, published both cached modes, reconciled the three
root exports/downloads, checked ZIP integrity and rejected invalid preferences.
The original six intake fields, all coordinate fields, manual AddressId 49738
and the original workbook/five coordinate-file hashes are unchanged.

All eight source-ID user-example regressions pass, along with 70 Python cases
and the map's click/point-precedence/hole/layout checks. Representative saved
regressions include the railway split, the previously missed municipal arterial,
local five-house ownership and preserving the 330-address natural area beside
already satisfactory neighbours. Named examples remain QA data only.

Receipts: `export-validation.json`, `natural-first-example-validation.json`,
`natural-first-api-validation.json`, `csv-replay-cache-validation.json` and
keyed `.rail-validation.json` files in `audit/partition_app`. Range key:
`eb12342296c010957cd5b07ac5fdf4d4439aec3ac9319d139c42e5fede483dfa`.
Natural key:
`123b888cef9968641168a263980df05c77cba8e7e1e80b339555e55b17aff604`.

Chrome navigation and the current local page are verified. The default map
measured 1,645 x 726 pixels at a 1,920 x 1,032 viewport with settings collapsed.
Automated file selection through the ChatGPT extension needs its Allow access
to file URLs permission. This is separate from the app's standard upload button. Excel upload is verified by the independent API test; browser-mode
checks use Load Monday addresses. Chrome completed Natural sections (28) and the cached 900-1,100 range (29)
through the actual UI. Its fresh Natural CSV solve exactly matches the
independently saved Excel natural partition. Empty-space area clicks and
address-marker clicks show the correct, separate details. The expanded map
measured 1,890 x 824 pixels with one map container, no area tooltips and no
page errors/warnings. No external detail was enabled and no provider calls
were made. Screenshots: `natural-first-chrome-natural.jpg`,
`natural-first-chrome-address.jpg` and `natural-first-chrome-map.jpg`.
Receipts: `natural-first-chrome-validation.json` and
`natural-first-browser-replay-validation.json`. Verification workers have
finished; the local app is intentionally retained.

## Sources reviewed

Canonical source: `C:/Projects/Routing/ODA Data Generation/` (the legacy
`C:/Projects/ODA Data Generation/` path is the user's compatibility location).
Reference Git revision: `853785ea04492f378ab41a955608332d715104db`.
Current working-file hashes are retained in the local audit manifest because
the reference repository also has work newer than that commit.

| Review coverage | Findings carried into this application |
| --- | --- |
| Partitioner README, CUSTOMERS_WORKFLOW, configuration, CLI/run, models and input/adapters | Separate natural communities, planning sections and routes; preserve Winnipeg source identity; bypass address-key deduplication and city-specific adapters |
| Geography, sources, official areas, barriers and divider scoring | Freeze source geometry; use projected metres; inventory candidates; finite features cannot become invented infinite cuts; rank credible separators before count balance |
| Atomic groups and capacity tests | Keep shared points, explicit sites, ordinary intersection-bounded segments and serviced parcels whole; never silently split a protected site to meet a planning preference |
| Partition, solid boundaries, shape quality, QA and independent verifier | Validate final ownership and published geometry; deterministic ordering; no point hull, H3 or Voronoi operational boundaries; no buffer bridges or marker-shaped fingers |
| Export, workbook, maps, OSRM and output tests | Avoid the old default OSMF renderer; one UI map; offline checks first; road proof remains separate from polygon connectivity; no automatically started OSRM service |
| All five focused central rule documents | Read the splitting rules, boundary discovery, ELI10 explanation, visual QA and output retention policies |
| Roadmap and mistake histories | Reviewed the relevant Brooks/Redcliff/Crowsnest refinements, 134 → 79 → 57 section corrections, the later authoritative-source 19,094-row / 77-section result, deterministic replay failures and current HTTP/map policy. These are different source/policy snapshots, not Winnipeg expected counts |

Important evidence:

- [Splitting rules](<../../ODA Data Generation/docs/community-splitting-rules.md>):
  complementary ownership, full service coverage, exact finite geometry,
  street-name/direction exceptions and ordinary street-segment protection.
- [Boundary discovery](<../../ODA Data Generation/docs/community-boundary-discovery.md>):
  discover broadly before ranking; address gaps alone cannot prove empty land.
- [Visual QA](<../../ODA Data Generation/docs/service-area-visual-qa.md>):
  inspect final shapes, selected/rejected evidence and serviced sites.
- [Mistake log](<../../ODA Data Generation/docs/mistakes.md>): approximate
  coordinates influencing boundaries, missed separators, repeated-ID loss,
  false divider ownership, H3 outlines, narrow patches and same-process-only
  determinism checks recur across the iterations.

## Integration decisions

The original `cwsarea.input.load_input` groups by normalized locality, unit,
civic and street, generates a synthetic identity and can retain only the first
demand value. This is unsuitable for Winnipeg. The new importer preserves
every source AddressId and original field; repeated address strings do not
automatically link or merge records. Missing IDs get explicit source-row IDs.
Blank/duplicate IDs and invalid selected-day coordinates reject the upload rather
than silently dropping rows. A workbook selects one worksheet; Sheet1 is never
appended to a day sheet. Mixed-day rows require a day selection, with exclusions
counted. A file without a day column uses its worksheet/filename or the user's
explicit collection-day selection. A row's weekday takes priority over its name.

The source's `50 / 100–300 / 570 / 600` thresholds and the earlier six-city
minimum of 80 are separate historical planning policies. None becomes a
Winnipeg truck, lift, load or route constraint. Natural mode has no address
capacity. Optional target mode offers an editable **soft address-count
preference**; the current default is the preferred range 900-1,100. A protected group or
lack of credible dividing geometry may leave an area above that preference.

The reference engine's successful official-hierarchy path requires both large
and small official layers. Its non-official fallback can leave buffered point
hulls. This app instead uses a limited, explicit adaptation: official Winnipeg
neighbourhood polygons form reference parents; finite cached water, railway
and controlled-road features subdivide them. Target mode also considers major
and collector roads. Ordinary-street, shared-point, supplied-site and material
serviced-parcel conflicts dissolve whole adjoining pieces. There are no point
cluster outlines, artificial rays or thin polygon repairs.

Four `Approximate site centre` records are explicitly estimated; the legacy
classifier would miss that label. They do not create or move boundaries and
are assigned only after the reliable-point partition is fixed. Building and
user-supplied coordinates retain their distinct provenance. Property points
do not establish curbside/alley access, vehicle compatibility or pickup spots.

## Frozen geography and limits

Preparation is a separate manual script, never an upload side effect. Local
source receipts record URLs, source/retrieval dates, licence, CRS and hashes.

| Reference | Frozen features | Use |
| --- | ---: | --- |
| City Neighbourhoods `8k6x-xxsy` | 237 | Reference polygon edges; 33 contain Monday records |
| City Road Network `ngsx-caav` | 17,805 | Local map context and same-name segment checks within 80 m |
| City Parks and Open Space `tx3d-pfxq` | 1,401 | Inventory/context for review; not automatically promoted to complete areal-gap proof |
| City Assessment Parcels `d4mq-wa44` | 163,919 distinct extracted geometries | Bounded parcel/site checks; reference coverage is explicitly incomplete |
| Existing Manitoba OSM PBF | 8,162 extracted physical features | Local water/rail/road/land-use way geometry; no OSM tile, Overpass or geocoding requests |

The survey-parcel bulk export exceeded its size guard; a first assessment
extract also hit its row limit. Those incomplete extracts were rejected. The
final bounded geometry-only assessment extract groups identical geometries
and is frozen at 61,807,990 bytes. Do not repeat these exports per upload or
increase a guard blindly. Count limits must exceed a preflight source count.

The PBF is an existing September 2026 snapshot; its complete relation-based
water/land-use geometry is not extracted. Complete areal-gap discovery,
legal road crossings and road reachability are not certified. Official
neighbourhoods are references, not approved service ownership. The app labels
all otherwise passing results **PROVISIONAL**; failed topology/coverage gates
produce **FAILED**, with diagnostic output and the last valid result retained.

Geometry uses EPSG:32614, with a 0.01 m precision grid for official shared-edge
noise. GeoJSON publication uses eight decimal places (about 1 mm here), then
dissolves numeric shared-edge overlaps of at most 1 m² per section in stable ID
order. It retains all polygonal components and reliable service containment;
larger overlaps fail. Both native and published geometry are checked. Only
numerical holes no larger than 1 m² may be removed. The tested
600-address result removed six holes totalling about 0.00000003 m². Material
holes, disconnected pieces, overlaps above 1 m², split protected groups or
reliable points outside their area fail. A 40 m erosion flags serviced lobes
for review; it is a geometry diagnostic, not a truck-access standard.

## Web app and delivery

Run `Start Monday Partitioner.cmd`, or:

```powershell
python -m partition_app.server --port 8765
```

The app binds only to `127.0.0.1`. Uploads are processed locally; the server
checks Host, Origin and a local session token. CSV, TSV and XLSX are supported.
One worker runs at a time, with progress, checkpoint cancellation and a
ten-minute processing budget. Input/settings/code/geography hashes cache
identical work. Four recent uploads are kept in memory. This is a local
desktop workflow, without authentication or remote hosting.

The existing delivery folder is extended in place:

`outputs/2026-11-04_monday_map/`

- `Monday_partition_assignments.csv`: every source column plus collision-safe
  PartitionAddressId, PartitionAreaId, PartitionStatus and PartitionSourceRow.
- `Monday_partition_areas.geojson`: final geographic polygons and section counts.
- `Monday_partition_review.json`: settings, source receipts, checks and candidate ledger.
- Existing `audit/partition_app/`: flat hash-keyed result cache, independent
  receipts, source review manifest, screenshots and server logs. No new run
  directory per click. Prior coordinate/map/Excel deliverables stay intact.

The default map renders cached local roads and physical features, requiring
zero provider requests. Optional OpenFreeMap detail reuses the previous
overview cache and the all-resource queue: concurrency 4, at most 200 URLs,
25 MiB transfer stop, 200 ms minimum start spacing and 12-second timeouts.
Failures stop loading without retry. Pan and minimum zoom use the uploaded
extent plus 50 km, max zoom 19. One map instance; no idle/render-triggered
fit, recreation, reload or recurring refresh. Resize invalidation happens
only when the container size changes. File processing does not initialize maps.

## Historical first-adaptation validation

These first-adaptation numbers are historical and are superseded by the
natural-first release evidence above. The source still has 21,507 source IDs
at 21,290 coordinate locations. The first natural mode produced 21 draft
sections. An earlier 600-address preference produced
36 draft sections, from 1 to 3,616 records; the target is deliberately soft.
Neither number is a required fleet or a route count.

For the target example: 21,507 assignments, zero reliable points outside,
zero split protected groups, 19,946 serviced parcels checked, zero material
parcel cuts, and about 0.1893 m² native numerical overlap. Published shared
edges are independently checked after inverse projection and normalization.
Parcel reference covers
20,833 reliable records; 670 reliable records remain without a containing
parcel reference. All four estimates remain labelled and boundary-excluded.

That validation included 17 focused regression cases, full CSV/XLSX upload and
desktop/mobile UI checks, original source/coordinate-field comparison,
single connected hole-free output polygons, shared-coordinate ownership and
two fresh-process target runs with identical polygons and assignments. The
original workbook SHA-256 remains
`fbff92cbe50d4a56aa39883a8fafbe0de97ac3a542c47df2f02a8e106c18d5a2`.
Cached basemap QA replays 13 resources / 586,961 bytes, with zero upstream
requests and zero stationary render frames. HTTP errors, budgets, pacing,
timeouts and no-retry behavior are also tested with mocked resources.

Current receipts are in `audit/partition_app/`; inspect them alongside the
map before using a section operationally. Depot, receiver, service/load/shift
constraints, truck compatibility and access remain in the existing input
checklist. No fleet optimization or route durations are implied by this app.
