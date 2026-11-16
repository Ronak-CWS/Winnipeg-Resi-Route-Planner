# Winnipeg Residential Route Planner

The local app detects the collection day from uploaded rows, worksheet names or
filenames. The existing Monday and Tuesday lists are available in the app.
It includes **Truck routes** alongside service areas, with separate
garbage and recycling plans and editable operating inputs. Download the
self-contained truck-review HTML to inspect assignments, loads and full road
trips. See [routing operation and current results](docs/routing-app.md).

The earlier 59-truck result was rejected for poor utilization. The current
search minimizes trucks and paid worker time, combines nearby sections and
checks a 14:30-16:45 return window, preferring 15:30 onward. Coverage PASS alone does not establish an
efficient or feasible fleet. Unresolved return/access issues stay visible.

The current completed Monday review plan has **18 garbage + 11 recycling trucks**,
with garbage returns **15:00-16:22** and recycling returns **15:37-16:44**.
All 57 dumps meet the 60% fill target. The expanded search took 53m39s with
four local workers; it retained the best complete refinement. Truck count is
a calculated output, and ten recycling trucks was not demonstrated by this run.
The reported 17 garbage / 12 recycling operation and the user's ten-recycling
comparison do not constrain the solve. Open the
[offline Monday truck review](http://127.0.0.1:8765/truck-maps.html?day=MONDAY) while the app is
running, or download the self-contained HTML from Truck routes. All 43,014
service events reconcile. Pickup access and garbage mass limitations remain
explicit. See the routing notes for exact results and remaining exceptions.

Last reviewed: 2026-11-16. Weekday files share the existing delivery folder.

Calculate how many ASL and rear-load trucks are needed to complete each
collection day's work within the operating limits. Produce balanced routes,
load divisions, complete driving sequences, and maps. This is a separate project from Winnipeg
front-load recycling, C9/Southern Alberta, and Wood Buffalo.

Start with [inputs needed](docs/inputs-needed.md) and the
[project brief](docs/project-brief.md). The source workbook has been preserved
byte for byte under `data/source/Winnipeg - Area 1 addresses.xlsx`.
A Monday coordinate map and separate road-routing plans are available.
Tuesday has a complete 21,233-address coordinate file; its truck routes must
be calculated separately from Monday's saved plan.
The routing report distinguishes source/geometry checks from operating feasibility.

| Folder | Contents |
| --- | --- |
| `data/source/` | Original address workbook |
| `data/reference/` | Supplied email screenshot and supporting operational inputs |
| `data/working/` | Future cleaned and geocoded derivatives |
| `config/` | Reported requirements and unresolved inputs |
| `docs/` | Project decisions and the intake checklist |
| `scripts/` | Read-only source inspection |
| `outputs/` | Dated audits and future draft/delivery packages |

The workbook contains 104,022 distinct AddressIds in Sheet1. Monday is a
21,507-address subset with one conflicting field, not additional demand.
Preserve IDs and unit addresses. There are 25 extra occurrences of exact
address strings under distinct IDs; review before any aggregation.

The user's current direction is to calculate the required daily fleet and
compare it with the available 45 trucks. Route and truck counts are model
outputs. The email's 20 ASL / 12 rear-load routes and 1,300/1,500 calls are
historical context and comparison benchmarks, not fixed requirements.
Miller maps and boundaries are not required. Plan new routes from the service
addresses, collection access, and confirmed operating inputs.

Obtain an address-level alley-versus-curbside classification and record
ASL/rear-load compatibility separately; collection access alone does not
establish the required truck type. Calls per route do not establish load capacity.

## Weekday partition web app

Wednesday, Thursday and Friday upload workbooks were prepared separately in
`outputs/2026-11-16_weekday_uploads/`. They retain 22,202, 19,316 and 19,764
source AddressIds respectively. All three files now have coordinates for every
row and pass offline import validation. The user corrected six reviewed locations
and confirmed the other seven on November 16; all three files now have zero
unconfirmed estimates. Source address labels and AddressIds are preserved,
including fractional labels where the user's reviewed label differs.
The user handles uploads; the files were not uploaded by the agent.

Wednesday's checked engine 4.6 result has zero overlap and splits the marked
1,454-address school/park area into 911/543. Two other oversized areas remain
flagged. The corrected saved result can be reused for the identical upload and
range; the active Tuesday view was preserved.

In **Truck routes**, select Garbage, Recycling, or both beside Generate. Only
selected streams are sequenced and allocated. Operating parameters include
**Add another depot** and **Add another receiver**, with one-location or
multiple-location selection. Each truck starts and returns to one selected
depot and uses one selected receiver for all its loads.

Open **http://127.0.0.1:8765** while the local server is running. Double-click
[Start Monday Partitioner.cmd](<Start Monday Partitioner.cmd>) to start it again,
or run `python -m partition_app.server --port 8765` from this project.
Partition jobs have a 30-minute calculation limit and can be cancelled in the
app. The earlier ten-minute limit stopped the complete Tuesday boundary pass.

Choose Monday or Tuesday under **Existing address list**, or upload CSV/TSV/XLSX
with latitude and longitude. A recognised collection-day column determines the
day; without one, the app uses the worksheet or filename. A mixed-day file asks
for a selection under **Upload options** and reports the other-day row count.
If no day is present, choose it there. Multiple worksheets are never concatenated.
The app preserves IDs, displays partition polygons and address counts, and exports
assignments, GeoJSON and a validation package. Tuesday uses `TUE-` section IDs and
`Tuesday_` export names. Replacing the input clears the old map, counts and routing
links, including on failed uploads. Saved Monday and Tuesday outputs stay separate.
The app has one workflow with an editable **900-1,100 preferred range**.
Ranges narrower than +/-10% use +/-10%.
It builds natural areas first, then scores compatible
whole-area merges and supported municipal/broad-road splits. Both below-range
and above-range exceptions remain visible; passing geometry checks does not
mean that the requested count range was achieved.
An undersized area stays separate if enlarging it would put an already
satisfactory neighbour outside the range. Smaller naturally bounded areas can remain.
Pockets below 100 addresses join an adjacent larger area, or one within 500 m,
when no important boundary intervenes. Larger is relative: a 1-address pocket
can join a 30-address list. Prefer neighbours that keep the count
within the range. A few larger areas can remain explicit exceptions; they are
not automatically accepted or counted as meeting the preferred upper value. Otherwise
the area shows a specific exception reason. A nearby group can retain separate
real polygon pieces; no connecting land or road access is inferred.
Paired ordinary frontages stay together by default. Unsupported mid-block cuts and
separating opposite sides of a mapped alley carry the same large penalty.
Mapped alleys alone do not establish actual collection access. A continuous
City street can replace a fragmented seam, with municipal alignment as supporting
evidence rather than an eligibility gate. Road-following intersections are valid.
The local **City boundaries** overlay makes official neighbourhood lines visible.
A continuous corridor can replace a fragmented
last-resort seam; any opposite-curb exceptions are recorded explicitly.
Ordinary streets and alleys are excluded from standard count splits.
Only an area containing at least two
requested minimum-size sections can consider last-resort whole-frontage
regrouping after supported boundaries fail. Any such rear-property/alley
boundaries require explicit pickup-access review. Sites and parcels remain whole;
any selected continuous-street curb exception is recorded. Unresolved count
and boundary exceptions are shown explicitly.
Frontage protection stops at actual rail, water and major-road crossings as
well as street intersections. Railways remain important partition boundaries.
The natural partition is the internal baseline, not a separate UI choice. Results stay
provisional pending road/access and geography review; these are planning areas,
not truck routes or a fleet calculation.

Area details appear on click only; address clicks show the address details.
Settings collapse after loading results to give the map more room. Use
**Addresses & settings** to edit inputs or **Expand map** for the largest view.
These controls resize the existing map without creating or refitting it.

Default rendering uses frozen local streets with zero external requests.
Optional OpenFreeMap detail uses the existing bounded queue and overview cache.
No geography downloads or geocoding occur during uploads or partition runs.
Current partition files extend `outputs/2026-11-04_monday_map/` in place, with
receipts/cache in its existing audit area. Original address deliverables remain.

See [partitioner review and operation](docs/partitioner-review.md) for the
reviewed ODA rules, adaptation choices, reference coverage and validation.
Python dependencies are listed in `requirements.txt`; `requirements-geography.txt`
is only for one-time offline PBF preparation. Partitioning does not use OSRM.
The user-started local OSRM supplies routing at port 5001;
its live server table ceiling is 800 locations.

## Monday address map

Current local delivery: `outputs/2026-11-04_monday_map/`.

- Open [Monday map](outputs/2026-11-04_monday_map/Monday_address_map.html).
- [Excel address list](outputs/2026-11-04_monday_map/Monday_addresses_lat_long.xlsx)
  and CSV retain all 21,507 Monday AddressIds and the original six source fields.
- All 21,507 Monday records have coordinates: 21,215 exact city addresses, 287
  building address points, four labelled approximate site centres and one
  user-supplied coordinate. AddressId 49738, `2194 WEST TAYLOR BLVD`, uses
  `49.85008333, -97.22494444`, supplied on 2026-11-04 as
  `49Â°51'00.3"N 97Â°13'29.8"W`. Its status and source are recorded explicitly.
- Coordinates use the official City of Winnipeg Addresses reference downloaded
  2026-11-04, updated 2026-11-02. Public records supply locations only; they do
  not add service addresses. These are property/building points, with actual
  curbside/alley pickup locations still unknown.
- Search by address, ID or postal code; filter by coordinate status; click a
  point to see every Monday record sharing it. Address data and the map library
  are embedded locally; the OpenFreeMap street basemap needs internet.
- The blocked OSMF raster endpoint has been removed. All basemap resources use
  one cached queue: at most four concurrent requests, 200 unique requests per
  page and a 25 MiB transfer-stop threshold. Requests start at least 200 ms
  apart, time out after 12 seconds and stop on failure with no automatic retry.
  Pan/minimum zoom are bounded to Monday's extent plus 50 km. No periodic map
  reload, idle-triggered fit, rerender loop or automatic expired-tile refresh.
- Corrections update this same delivery folder. The basemap fix preserved
  address-file bytes; the subsequent user-supplied coordinate changes only
  AddressId 49738 and its dependent totals. Backups, cached QA resources and
  validation receipts remain inside the existing audit area.
- GeoJSON and detailed validation receipts are included. The source workbook's
  SHA-256 is unchanged. No other weekday was geocoded or mapped.

To repeat against an explicitly supplied local city reference, use a new dated
output directory (existing runs are protected):

```powershell
python scripts/map_monday_addresses.py --source 'data/source/Winnipeg - Area 1 addresses.xlsx' --reference 'data/reference/city_of_winnipeg_addresses_2026-11-04.csv' --overrides 'data/reference/coordinate_overrides.json' --out 'outputs/NEW_DATED_RUN'
python scripts/build_monday_map.py 'outputs/NEW_DATED_RUN'
```

The delivered workbook builder is retained in this run's ignored `audit/`
directory. The original intake and earlier evidence remain preserved.

## Repeat the source audit

With Python 3.10+ and `requirements.txt` installed:

```powershell
python scripts/audit_source.py 'data/source/Winnipeg - Area 1 addresses.xlsx' --out outputs/NEW_RUN/source_audit.json
```

The existing ODA environment can also run this audit without installation:

```powershell
& '..\ODA Data Generation\.venv\Scripts\python.exe' scripts/audit_source.py 'data/source/Winnipeg - Area 1 addresses.xlsx' --out outputs/NEW_RUN/source_audit.json
```

The initial evidence is in `outputs/2026-10-27_intake/`. The audit does not
modify the workbook. Private data and generated outputs are ignored by Git.

Central knowledge: [Winnipeg residential brief](<../ODA Data Generation/knowledge/projects/winnipeg-residential.md>).
