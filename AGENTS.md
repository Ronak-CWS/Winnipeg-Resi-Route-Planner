# Winnipeg residential routing instructions

- Read `docs/mistakes.md` before changing or reviewing partitioning, routing or
  maps. Read both OPEN issues and the prevention lessons from DONE issues.
  Record new user QA there, preserve its evidence, and mark an issue DONE only
  after regression checks and the affected saved result verify the fix. Keep
  unresolved examples visible; a passing count/coverage check is not boundary QA.
- A boundary following a mapped street through intersections is valid. Do not
  count its crossings with other streets as mid-block street cuts. Penalize
  unsupported cuts between neighbouring houses and opposite sides of a rear
  alley heavily. Compare valid roads by physical strength, continuity, municipal
  evidence and neighbourhood cohesion; a weaker road is not an invalid cut.
- Explicit mapped speeds above 60 km/h, and 60 km/h with mapped arterial or
  highway evidence, are major boundary evidence. Unknown speed stays unknown. Rail,
  water and controlled/high-speed roads take precedence over count balancing.
  Apply the same finite-corridor evidence rules throughout the city. Municipal
  alignment supports scoring; it must not be an eligibility gate that protects
  an inferior existing alley seam. Never hardcode example street names or IDs.
- Valid is not necessarily best: prefer a complete mapped school, park or
  commercial edge over an ordinary-road split when it preserves useful adjacent
  frontages. Major rail/water/highway evidence still wins. Generate these
  alternatives as well as scoring them. Only corroborated unserviced parcels may
  expand mapped institutional grounds. Any short road-space completion must have
  mapped endpoints, cross no property interior, and pass all final street/site/
  parcel checks. Do not redraw unrelated empty road-space edges.
- Do not let projection-sized endpoint gaps bypass street-cut checks. A short
  school-edge connection between two serviced property lots is not road space;
  validate frontage continuity and the mapped access gap visually as well.
- At a road-following three-area junction, compare ownership changes along the
  same curb. Comparing opposite curbs can invent a transverse cut at the end of
  a valid shared road edge. Genuine transverse cuts and rear-alley splits retain
  their heavy penalties; check every affected neighbour, not only the new seam.
- Optional boundary-quality refinement must not take an already satisfactory
  neighbour outside the requested range. Keep required major-divider repairs
  separate from this refinement; score validity, counts and physical quality
  consistently before accepting a nearby reshuffle.
- Carry physical boundary strength into route allocation: weak shared planning
  seams favour one adjacent truck territory. This is a preference after fleet,
  capacity/time and whole-parent considerations, never a named section pairing
  or a reason to add trucks or manufacture driving time.

- Read README.md, docs/project-brief.md, and docs/inputs-needed.md first.
  Read ../ODA Data Generation/START_HERE.md and its Winnipeg residential brief,
  plus the relevant roadmap and mistake-log entries, before routing work.
- Preserve the original workbook and AddressId. Sheet1 and Monday overlap.
  Do not concatenate them or automatically merge repeated address strings.
- The supplied residential workbook defines the intake service universe,
  pending operational confirmation of Area 1 coverage and collection streams.
  Public geocoding data supports coordinates only and cannot add service rows.
- Keep reported requirements separate from confirmed operating constraints.
  Do not equate 45 trucks, 32 named routes, route-days, calls, cart lifts, and
  load capacity. Record missing constraints as unknown, not zero.
- Do not inherit depots, receivers, capacity, shift times, service times,
  collection frequencies, or approved scenarios from another project.
- Current objective: calculate the required operating trucks by weekday and
  type, peak daily fleet, route durations, load counts, and whether the reported
  45-truck fleet can meet the work. Treat fleet quantities as outputs; apply
  actual availability only to a separately identified availability scenario.
- Miller maps and route preservation are not prerequisites or constraints.
  Earlier email route counts/call targets remain historical comparisons only.
- Require address-level alley versus curbside classification. Keep collection
  access separate from ASL/rear-load compatibility and actual pickup location.
- Future route costing must include yard departure, all collection legs,
  every intermediate and final dump, queue/unload time, and the end location.
- Keep private inputs, geocoding/road caches, and outputs local and ignored.
  Save new runs in dated output directories. Preserve accepted deliverables.
- For a correction to an existing delivery, update its existing folder when
  requested; keep backups and validation in that folder's existing audit area.
- Read the central Public Basemap And HTTP Request Policy and map-rendering
  mistake-log entries before building or opening maps. Use bounded OpenFreeMap,
  never the blocked OSMF or Carto raster endpoints. Enforce the request queue,
  cache, concurrency and session limits for every resource, not images alone.
- Basemap loading must have a timeout and stop on failure without automatic
  retries. Never fit, reload or recreate a map from its idle/render handlers.
  Validate offline first; allow one capped live viewport and reuse its cache.
- Record changed decisions in docs/project-brief.md and the central matching
  brief/roadmap; update the mistake log when a repeated risk is found.
- Parallelize complete independent section alternatives and route/load
  evaluations, then assign the whole stream fleet together. Never split the
  service universe into separately allocated halves to gain speed. Keep road
  requests/cache access coordinated, cap local workers, join them on completion
  or cancellation, and distinguish solver limits from total elapsed runtime.
- Keep the best completed tested fleet if later subdivision/search worsens it.
  Early-return exceptions do not become acceptable merely because coverage and
  load checks pass; publish their actual clocks without manufactured waiting.
- Validate source-property-to-pickup distance as well as anchor-to-route
  coverage. A postal street can differ from the actual connected site road.
  Use real network nodes, access restrictions and right-side direction; never
  invent access across intersecting but unconnected roads or another street.
- Penalize extra truck owners of one planning section. Generate whole-parent
  alternatives and connected reciprocal exchanges, then recalculate complete
  load/clock costs and solve fleet-wide. Similar counts are not adjacency proof.
- Treat the confirmed recycling tolerance as bounded: normal 1,350, 2% allowance,
  absolute 1,377. Garbage remains 650. Score the 60% dump-fill target on final
  as well as intermediate loads; required final unloading is never omitted.
