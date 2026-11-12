# Darkness and school arrival/dismissal context

The private managed Provo collection stores `enrichment.context` once during intake or rebuilding. `darkness.value` and `school.value` are independent crash-group classifications. Version 1.0.0 uses the reviewed [school register](../../data-definitions/crashes/school-context-v1.json). Original observations and their existing enrichment retain their own provenance. The maintained updater fingerprints this register and the classifier. Editing either triggers an offline rebuild on the next update.

## Reported darkness

`darkness.value` is `dark`, `daylight`, `dawn/dusk` or `unknown`. Normalized `dark-lighted`, `dark-unlighted` and `dark-lighting-unknown` all produce `dark`. `darkness.lighting` retains every supported subtype, and `evidence` identifies supporting observations. A missing source contributes no vote. Disagreement between the four known lighting groups after collapsing the three dark subtypes produces `unknown` and `reason: source-conflict`. Missing lighting produces `lighting-unavailable`. Occurrence hour, participant age, mode and crossing location impose no conditions on this field.

## School matching

`school.value` is `drop-off`, `pickup`, `both`, `no match` or `unknown`. The rules use WGS84 ellipsoidal straight-line distance within **402 metres**, inclusive, from a dated campus point. Arrival runs from 30 minutes before the instructional start through that bell. Dismissal runs from the final instructional bell through 30 minutes afterward. Boundaries include the exact recorded timestamp. These windows apply independently to each published student session, including staggered kindergarten sessions. Optional lunch after the final class does not extend the instructional dismissal bell.

Each match retains `schoolId`, `locationId`, `scheduleId`, source observation ID, distance and local window boundaries. `nearby` retains spatial candidates before applying time or calendar rules, with a flag indicating whether geography was verified for that occurrence date. A group counts once in summaries even when multiple campuses, sessions or observations support it. `both` means at least one arrival and one dismissal match across those sessions or campuses.

The register supplies explicit campus effective periods, school-year bell schedules, Monday–Friday patterns, calendar closures and date overrides. An empty override means no attendance. A null override or uncertain calendar date means the exceptional bell schedule remains unresolved. Closures take precedence. Dates outside each recorded term and weekends are closed for these documented regular-school calendars. Unknown exception dates, conflicting schedules, absent campus history or absent bell schedules produce reasons on the result. A confirmed match can coexist with unresolved coverage at another nearby campus. Conflicting complete crash-source outcomes produce `unknown`.

Only occurrence dates and clocks participate. Report-only police timestamps remain `unknown`. A known occurrence clock can supply a second source's missing clock. Normalized Utah source clocks with an unspecified zone are interpreted as local America/Denver, consistent with their source contracts. Coordinates come from the resolved crash point when present, then that same observation's source point. Missing geography stays unknown. Provider point accuracy remains a limitation of the source.

The register records the years with a reconciled citywide inventory. Outside those periods, a positive match remains usable but a negative remains `unknown` with `historical-inventory-incomplete`. This protects against historical schools omitted by a modern directory. Within covered inventory periods a point outside all applicable perimeters can be `no match` without a bell time. Missing historic campus positions are considered as possible spatial candidates at their retained positions for diagnostics, and never generate a positive historical match.

## Evidence and coverage

The register has 32 campus entries and 24 school-year schedules, including the former Dixon campus, distinct Freedom Prep and Walden secondary campuses, and Slate Mountain's three teaching sites. District elementary and secondary schedules cover 2026–27. Dated historical schedules cover Dixon 2022–23, Provo High 2024–25 and Centennial 2025–26. Treeside and both Freedom Prep campuses have 2026–27 schedules and their own calendars. Walden's published bell pages are retained in private research, but its accessible annual sheet did not establish a usable dated instructional calendar. Other private and residential programs retain missing-schedule status.

The acquisition surveyed the official district directory and the USBE directory, school pages and linked calendars, dated handbooks and historical schedule searches. Retained captures and search attempts are under `private/research/2026-11-11-school-context/`. Private acquisition pages can contain staff contacts and remain in ignored storage. The register contains public campus and schedule references and checksums. Its source records identify references that are retained repository evidence or URL-only references.

Review resolved several provider-data issues. USBE's Provo High point refers to the former University Avenue campus. The current point uses the NCES-derived location corroborated against the official school address and relocation history. UDOT supplies the reviewed elementary and middle-school campus points. Current Treeside uses its East Bay address, with the planned 1600 South campus excluded from operating-campus matches under the existing campus decision. USBE's American Legacy and Kurious entries have Provo mailing addresses and physical addresses in American Fork and Lindon, so those physical campuses are excluded. Ivy Hall's directory closure conflicts with its available provider website, so later nearby crashes retain unresolved campus history.

The dated 2019 district demographics register and current official addresses support the retained campus continuity periods for district schools. Current geography is never assigned to an earlier period solely from the school's opening year. Historical citywide inventory coverage remains incomplete before July 2026. COVID-era in-person schedules are unresolved. The 2024–25 district calendar has contradictory May end dates, and those dates are uncertain. Elementary conference-week early-outs and high-school testing dates with unresolved student release times remain explicit exceptions.

A match describes proximity during a documented arrival/dismissal window. Trip purpose and fault require other evidence. Darkness uses the officer/source-recorded condition. Exposure counts would be needed for per-trip comparisons.

## Queries and verification

`danger_zones.query_incidents` reads the saved group context through `darkness`, `school_context` and `school_id`. Existing source-specific `lighting` queries retain their meanings. Combine `darkness = dark` with `lighting = dark-unlighted` to find reported dark/unlighted crashes. Select `school_context in [pickup, both]` for pickup matches. An unresolved group has a null `school_id` in the query view, while its detailed evidence remains available on the returned record. Collections from before this addition produce unknown results for the new predicates.

The immutable release's `enrichment-audit.json` contains counts by occurrence year, lighting category, school classification and unknown reason. It compares 402-metre and 201-metre classifications and spatial candidate counts. `spatialCandidates` counts groups near a campus with verified dated geography. `possibleHistoricalSpatialCandidates` also includes possible nearby sites with unresolved effective dates. The `unknown` year contains report-only or conflicting-year groups. Reason counts can overlap.

Regression cases cover exact time and distance boundaries, Friday early-out, holiday/weekend closure, late start and date overrides, relocated schools, overlapping campuses, staggered sessions, incomplete/conflicting inputs, saved query behavior and darkness without crossing evidence. Normal release verification compares all group identities, source fingerprints and pre-existing per-observation enrichment, then checks a repeated offline update.

## Initial backfill review
The November 11 preflight preserved all 1,790 group IDs, original observation fingerprints and pre-existing per-observation enrichment. It found 401 reported-dark groups, 1,291 daylight groups, 63 dawn/dusk groups and 35 with unknown lighting. School classifications were 0 confirmed matches, 43 no matches and 1,747 unknown. Historical inventory gaps dominate the school unknowns, and these results support no conclusion about the prevalence of school-trip crashes.
| Occurrence year | Groups | Dark | School matches | No match | Unknown | Spatial 402 m | Spatial 201 m | Possible historic 402 m |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010 | 103 | 24 | 0 | 0 | 103 | 9 | 2 | 28 |
| 2011 | 97 | 17 | 0 | 0 | 97 | 11 | 1 | 25 |
| 2012 | 72 | 11 | 0 | 0 | 72 | 0 | 0 | 7 |
| 2013 | 60 | 15 | 0 | 0 | 60 | 5 | 0 | 12 |
| 2014 | 80 | 18 | 0 | 0 | 80 | 8 | 1 | 24 |
| 2015 | 86 | 21 | 0 | 0 | 86 | 6 | 0 | 21 |
| 2016 | 75 | 21 | 0 | 0 | 75 | 8 | 1 | 15 |
| 2017 | 78 | 18 | 0 | 0 | 78 | 5 | 0 | 14 |
| 2018 | 116 | 20 | 0 | 0 | 116 | 1 | 1 | 13 |
| 2019 | 94 | 25 | 0 | 0 | 94 | 8 | 3 | 14 |
| 2020 | 104 | 30 | 0 | 0 | 104 | 10 | 3 | 12 |
| 2021 | 130 | 30 | 0 | 0 | 130 | 10 | 3 | 14 |
| 2022 | 147 | 35 | 0 | 0 | 147 | 11 | 1 | 14 |
| 2023 | 153 | 33 | 0 | 0 | 153 | 13 | 3 | 20 |
| 2024 | 157 | 42 | 0 | 0 | 157 | 16 | 6 | 21 |
| 2025 | 135 | 26 | 0 | 0 | 135 | 8 | 2 | 12 |
| 2026 | 85 | 15 | 0 | 43 | 42 | 11 | 3 | 12 |
| unknown | 18 | 0 | 0 | 0 | 18 | 0 | 0 | 0 |

The 402-metre radius contains 140 groups with dated campus geography and 278 including possible historic sites. Detailed yearly reason counts, the full radius comparison and the campus/school-year evidence matrix are retained in the private review directory. Current dated nearby cases reviewed for the fall 2026 term included a Labor Day crash, a crash after the arrival bell, a crash beyond the pickup window and a residential-program location with no published bell schedule. Zero confirmed school matches chiefly reflects unresolved historical evidence.
