# Crash context around BYU events

The Hub stores event travel context on each managed Provo incident group and its individual source observations. The initial calendar covers BYU football at LaVell Edwards Stadium, BYU men's basketball at the Marriott Center, and Stadium of Fire from January 2010 through October 27, 2026. Supporting definitions live in [the event register](../../data-definitions/crashes/events/). The managed collection principally contains active transportation incidents. Its portal reference lookup also holds motor-only crashes that are outside this collection and therefore outside this backfill.

## Fields and interpretation

| Stored field | Event series |
|---|---|
| `byu_football_event_context` | BYU home football, including held schedule-listed games |
| `byu_mens_basketball_event_context` | BYU men's home basketball, with schedule-listed scrimmages retained as unverified when no result establishes they occurred |
| `stadium_of_fire_event_context` | The stadium concert and associated documented travel periods |

Each cell has `value`, `matches`, and `reasons`. Observation cells also retain unresolved `candidates`. `value` is `likely_match`, `no_match`, or `indeterminate`. A likely match requires all three of a documented event interval, a qualifying access feature valid at the time, and recorded crossing or parking evidence. This is a contextual association. It supplies neither a measured congestion level nor an individual causal finding.

Crossing evidence requires person type 3, 4 or 5 with nonmotorist location 1–5 or 16, meaning a reported crossing or intersection crossing outside a crosswalk. Parking evidence requires driver contributing circumstance 14, improper parking/stopping, or vehicle maneuver 14, parking during the collision. Backing and parked status alone do not qualify. These field-specific meanings reuse the common crash dictionary. A recorded hazardous sight obstruction can be incorporated only through a future reviewed structured source mapping, since current normalized deliveries do not provide that specific evidence.

Match evidence records event ID, arrival/departure phase, feature ID, source observation ID and the exact normalized fields used. `direct_corroboration` is false for these structured matches. Explicit event statements in narratives would need a reviewed source mapping before changing that value. Original observations retain all reported values. Positive and negative source observations that disagree produce a group-level indeterminate result. A positive with an incomplete secondary observation retains its positive evidence. Source observations are never combined to invent a complete match.

`eventContext` on each group records the fields, policy version, individual input SHA-256 values and their combined digest. The observation fields are also in `enrichment.observations[].fields`. Existing private query predicates read the group result without rerunning matching. A snapshot predating this enrichment returns unknown for an event predicate.

## Calendar and windows

The canonical inputs are CSV files named by `policy.json.registers`. Dates and local intervals use ISO 8601 with explicit offsets and America/Denver daylight saving rules. The Excel workbook is a generated human-readable view of the same register, with local wall-clock dates/times, source URLs and coverage counts. Edit the CSV definitions and regenerate the workbook to change a definition.

| Series | Arrival | Departure |
|---|---|---|
| Football | 120 minutes before kickoff through 15 minutes after | Documented end through 90 minutes after |
| Men's basketball | 60 minutes before tipoff through 10 minutes after | Documented end through 60 minutes after |
| Stadium of Fire | Documented gate opening or edition-specific travel activity through 15 minutes after show start | Documented audience release through 90 minutes after |

Both boundaries are inclusive. Departures may cross midnight. Actual times override scheduled times when retained evidence establishes them. Game ends require an explicit documented end or actual start plus official elapsed duration. Current captures resolve only one football end, September 4, 2010. Other athletics departures remain unresolved. The 2026 Stadium of Fire organizer's 5 p.m. west-lot event and 10:30 p.m. post-fireworks dance establish that edition's travel intervals. The later dance ending remains unresolved. Its 2020 stadium concert is explicitly canceled, while dispersed fireworks viewing is outside this series.

The November 11 capture contains 102 football entries, 299 men's basketball entries, and 17 Stadium of Fire editions. All 401 athletics entries have a published start. Seven basketball scrimmages remain unverified. There are 395 known arrival windows and two known departure windows across the complete register. Gate openings and audience release times remain historical research gaps. Missing intervals remain indeterminate where they could affect membership.

The schedule parser checks venue names, date bounds, duplicate IDs, nested result markup and item class variations. Each season has a retained HTML capture with receipt hash in private research storage. `coverage.json` gives its public URL, hash, total schedule items and selected home entries. Recaps used to establish actual times have their own capture receipt. Stadium of Fire rows cite each edition's dated source. Empty source hashes denote a cited source whose raw bytes have not been retained, and are not a checksum claim.

## Access geometry and uncertainty

The initial named crossing inventory includes University Parkway at University Avenue, Canyon Road, 450 East and 900 East, plus Stadium Avenue at Canyon Road. Frontages include University Avenue, Canyon Road, University Parkway, Stadium Avenue, Cougar Boulevard, 450 East and 900 East within the study envelope. Large parking review envelopes cover stadium west, stadium north, Marriott north/east and the west intramural fields.

The geometry builder uses the retained Provo street snapshot with SHA-256 `3d87e00fa393ebcf9c842323832339f8b1846ebe24083c51ae2407da2b48f8f5`. The 2026 street geometry and venue access references support the current access screen. Junction locations and approximate lot envelopes are explicitly specified in the builder. The lot envelopes remain candidates, and historical frontage/crossing features remain candidates pending dated footprint and event-use evidence. Their presence keeps possible historical cases indeterminate. Do not promote a candidate merely because a modern map shows a lot in the same location.

Geographic calculations use EPSG:26912. Crossing footprints use a 45 m radius and street frontages a 25 m buffer. A 15 m boundary margin must fit entirely inside the footprint for a positive. These are documented screening tolerances, not measured crash positional accuracy. Points within the margin of a boundary remain indeterminate. Source geometries can have larger unquantified errors. Grade-separated pedestrian bridges are not qualifying crossing points. Police report dates and approximate police geocodes cannot establish event occurrence.

## Operation, adoption and recovery

The ordinary `scripts.update_crashes --offline` command rebuilds enrichment from retained sources under the existing writer lock, validates it, writes an immutable private release, and atomically switches the active pointer. The updater fingerprints the matcher and all calendar, coverage, geometry and policy bytes. A repeated unchanged run is a no-op. The normal rollback restores the predecessor pointer. Retain the definitions and producer commit with private release backups for offline reproduction.

Run commands from the root with the crash Python environment and `PYTHONPATH=.:pipelines/crashes/src`.

```sh
python -m scripts.capture_byu_events private/research/NEW_EVENT_CAPTURE data-definitions/crashes/events --through YYYY-MM-DD
python -m scripts.capture_byu_event_details private/research/NEW_EVENT_CAPTURE data-definitions/crashes/events/athletics.csv
```

Replaying those two commands with `--offline` verifies retained hashes and reproduces the athletics register. Review the policy's coverage end and source calendar completeness together when extending coverage. Stadium of Fire dates and timings are edition-specific reviewed CSV entries. Regenerate locations with `scripts.build_byu_event_locations NETWORK_PARQUET OUTPUT_GEOJSON`, review the resulting features and effective dates, then run the updater.

```sh
python -m scripts.update_crashes --offline
python -m scripts.review_event_context private/active/crashes/collection/datastores/combined-incidents.json private/reviews/NEW_EVENT_REVIEW.json
python -m scripts.prepare_event_workbook build/event-workbook/workbook-data.json
```

For the workbook, copy `scripts/build_event_workbook.mjs` into the build directory beside a `node_modules` symlink to the configured bundled runtime. Invoke it with the prepared JSON and a new `build/outputs/THREAD_ID` directory. It exports `byu-event-register.xlsx` and renders previews for all three sheets. The workbook contains public event/reference information. Crash review reports and source captures remain private.

A stored-field query can use `{"field":"byu_football_event_context","op":"eq","value":"likely_match"}` through `danger_zones.query_incidents`. Existing consumers adopt private releases independently. Any future public crash-detail export needs a versioned allowlist/contract change and the normal manifest/catalog/ZIP pipeline.

The review command lists every positive for evidence review and reports counts by year/source plus missing-evidence reasons. Its controls shift known intervals by -14, -7, +7 and +14 days at the same local clock time. It excludes dates containing another registered held or unverified event. It reports window counts and distinct qualifying crashes. Differences in available source records, historical parking use, holiday activity, missing clocks and unknown game ends constrain comparison. There is no attendance or traffic exposure denominator.

To add another city event, add its series/field/window policy, a CSV register named in `policy.json.registers`, and sourced, dated access features. Extend policy coverage only where the calendar is enumerated. The matcher, stored fields and review command consume these inputs without a series-specific matching implementation. Event research and geometry preparation may use additional source-specific acquisition scripts.

## Verification record

Focused regressions exercise inclusive basketball departure boundaries at 60 minutes and one second later, midnight, actual extended game ends, cancellations, absent occurrence clocks, report-only dates, historical geography, parked/backing exclusions, source disagreement and the schedule parser. Run both repository test groups for shared changes. Current release and review results are recorded in the operations guide and private reports.
