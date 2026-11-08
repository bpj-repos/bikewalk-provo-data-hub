# Initial dataset inventory and roadmap

Decision record, November 7, 2026. The owner selected annual active transportation counts following the inventory. The latest documented count protocol (2026 at this review) is the reference for the public measurement model and future collections. Preserve and align older deliveries when their meanings support it.

## Release and ownership decisions

The hub will own repeatable source intake, reviewed transformations, dataset definitions, release manifests and independently deployed read-only HTTPS downloads. Internal jobs and maintainers alone can update it. Projects owns the public catalog page and presentation. Streets Watch owns submissions and operational state. Anyone can download an approved public release. Consumers pin a version and hash and control adoption independently. Public GitHub visibility is unnecessary. Source licenses, field-level disclosure, and release permissions must be documented before bulk distribution.

| Wave | Handoff and acceptance |
|---|---|
| 1. Inventory | This record identifies source families, consumers, boundaries, three trials, and the owner-selected pilot. |
| 2. Establish | Start a dedicated Codex project and private repository in bpj-repos. Compare existing hosting with actual quota, bandwidth, artifact size, retention and automation. Verify zero additional cost with an independent HTTPS deployment; present any paid exception for an explicit decision. Assign acquisition, review, release and app adoption roles. Specify stable catalog and immutable release URLs, versions, checksums, provenance, licenses, dictionary and change notes. |
| 3. Prove counts | Deliver a complete approved CSV, typed field dictionary and machine-readable release metadata. Evaluate Data Package. Demonstrate source receipt, repeatable updates, validation, compatible and breaking releases, rollback, and reproduction from an old pin. |
| 4. Publish and adopt | Build the Data Hub page on Projects from hub metadata. Include purpose, coverage, preparation, reuse terms, known gaps, versions, citations and downloads. Migrate each app where it actually uses a dataset, verify parity and rollback against the old pin, then retire displaced producers. Streets Watch has an evidenced use for crash details and legacy route layers; no count dependency was identified there. |
| 5. Operate | Onboard the shortlist incrementally. Require a maintainer, freshness expectation, last successful update, failed-refresh behavior, withdrawal procedure, backup and restore exercise for each dataset. A second maintainer should reproduce and recover a release using only the runbook and authorized source access. |

## Current uses and proposed ownership

Evidence snapshots: BikeWalk `8f8b276`, Streets Watch `1b3031b`, historical Walk & Roll `c240e87`. The historical checkout is a documentation and audit repository. Streets Watch's migration record places the former ingestion stack in canonical BikeWalk. Its private migration archive and restored inputs belong outside any public release. Classifications below are proposed future stewardship. Existing publication permissions apply only to their recorded products.

| Dataset and authority | Current path, timing and consumer | Proposed boundary, bulk reuse and limitations |
|---|---|---|
| BikeWalk/City annual station counts | Field counts → ArcGIS service/view and annual exports → Projects annual pages, station maps and trends. Annual plus corrections. | Hub-owned pilot. Confirm attribution and reuse terms. Release approved station observations; exclude volunteer rosters. Durations, station equivalence and mode breakdowns vary. |
| UDOT crash location service, portal workbooks, police deliveries | Service refresh and on-receipt workbooks → managed private incident updater → strict reconciliation, checksummed release and rollback pointer. | Hub-owned private inputs. Preserve provenance, conflicts and distinct source records. Restricted police deliveries and portal material need independent terms review. |
| Annual AT crash trends | Managed release → aggregate exporter → CSV/JSON and Projects report. Update on approved source revision. | Derived from hub release. Existing approval covers annual aggregates. Preserve source coverage limits and denominator definitions. |
| Fatalities and mapped incident details | Reviewed IDs, source definitions and news references → minimized fatalities features; separate reviewed map summary joins → Projects maps. Adopt reviewed snapshots. | Derived from hub release. Case references, exact times and locations can identify people in bulk. Review separately from aggregate products; retain existing map-specific IDs and associations. |
| Concern crash detail export | Verified incident release → allowlisted detail groups by state ID → pinned Streets Watch preview/import into concern crash history. On approved adoption. | Derived from hub release. Review bulk access separately. Exact ages, narratives and private references excluded. App owns memberships, ambiguous-ID handling and import rollback. |
| UDOT Safe Routes schools, route lines and plan points | Monthly official-source review → private candidate → approved static layers and manifest in Projects. Streets Watch legacy endpoint uses its bundled snapshot. | Hub-owned release candidate. Verify UDOT reuse/attribution and preserve field-verification notice. Missing provider IDs/geometry and scope exclusions are documented. Preserve legacy paths, response shape and headers. |
| Streets Watch reports, concerns, reviewed incidents and media | User/admin operations → Firebase and application views, maps, notices and counts. Live. Explicit minimized export supports private research. | App-owned. Reporter identity, photos, exact location and workflows require filtering; only an explicitly reviewed derivative is a potential input. No hub write-back. |
| Other Streets Watch operational and editorial data | Employer/contact and admin workflows, users, delivery, store, notice templates, and curated speed-study pages. App or editor updates. | App-owned. No identified shared release dependency. Private contacts, authentication and payments excluded. Review reusable traffic-study measurements individually. |
| Historical and research-only sources | Source registry and retained study inputs → local analysis/candidates. The registry appendix below gives each steward, cadence, status and limitations. | Potential hub-owned inputs; no general bulk-release permission established. Preserve access restrictions, including licensed sources. A registry entry does not establish an active consumer. |

Producer evidence: [command index](https://github.com/bpj-repos/bikewalk-provo/blob/main/tools/README.md), [source registry](../../data-definitions/crashes/source-registry.yml), [migration](https://github.com/bpj-repos/bikewalk-provo/blob/main/docs/maps-migration.md), [approved counts and historical definitions](https://github.com/bpj-repos/bikewalk-provo/blob/main/docs/active-transportation-counts-rollout.md), [research releases](https://github.com/bpj-repos/bikewalk-provo/blob/main/docs/research-reports.md). Consumer evidence: Streets Watch `docs/BIKEWALK_MAPS_MIGRATION.md`, `docs/CONCERN_CRASH_DETAILS.md`, `data/safe-routes-legacy/`, and `scripts/export-danger-zone-reports.ts`.

## Consumer trials

Trials used committed application data locally. Byte counts describe file contents before HTTP compression. These checks assess usability and do not estimate traffic or verify hosting quotas.

| Use | Trial and result | Design implication |
|---|---|---|
| Reproduce annual result | Sum the 14 rows of Projects' 2026 CSV. Field y26Total yields 6,186, matching the annual inventory. Daily scooter fields yield 186 + 97 = 283, while y26Scoot yields 236. | CSV works. Publish the field choices and discrepancy so researchers can reproduce both measures. |
| Load GIS data outside Projects | Parse all three Safe Routes GeoJSON files with MapLibre's GeoJSONVT. At zoom 12, tile (777,1547) contains 8 school, 127 route and 516 plan features. Full input layers contain 15, 188 and 800 features respectively. | Standard GeoJSON supports independent tooling without a bespoke map endpoint. Tile counts reflect clipped tile contents. |
| Select one month of incident features | Parse the 17,253,370-byte map file and filter properties.month for 2024-11. Returned 32 of 1,195 features, 453,458 bytes as a compact UTF-8 feature array. | Local filtering works for occasional analysis, but requires the entire transfer. Consider date partitions if repeated demand emerges. The map payload is evidence for sizing only; it needs separate bulk disclosure review. |

## Counts pilot handoff

Start with the published 2026 station records and documented counting-line method, session definitions, modes, units and treatment of missing observations. Version the protocol alongside the dataset. Confirm observer instructions and actual session coverage with the collection lead. An annual total counts observations; it cannot establish the number of unique people.

Inventory the historical ArcGIS base layer and view, the retained 2019 spreadsheet and station slides, and any earlier workbooks or tallies the owner or researchers can locate. Published years are 2019 and 2021–2026. The checked web map and services provide no 2020 report. Additional older holdings remain unverified. Keep original deliveries private and checksummed, then map each year's source fields, units, sessions, categories and station identity to the 2026 definitions. Record whether a measure is directly comparable, convertible by a documented rule, or unavailable/incomparable. Never assign historical hours or counting methods from the current protocol alone. Mark missing separately from zero; preserve original values when correcting a spelling or deriving a measure.

Reuse the existing historical exporter and field mappings. It handles the base/view split and validates 14 roster entries for its known years. Inspect other deliveries before applying that assumption. Pilot acceptance includes reproducing 6,186 for 2026, preserving both scooter measures, importing an older differently formatted delivery with documented mappings, and preserving unknown values and cross-year gaps. Establish public redistribution terms, authorized updater and correction review before the first release.

## Migration shortlist

1. Counts: chosen for small complete files, reproducible results and a meaningful historical harmonization test.
2. Safe Routes: strongest second test for GIS interoperability and independent adoption by both apps.
3. Annual crash aggregates: established checksummed product with a narrower disclosure boundary than incident details.
4. Concern crash details, fatalities and incident-level maps: consider separately following bulk privacy/rights review and identity/consumer parity checks.

## Registered research sources

The inventory below transcribes the inspected registry. Cadence describes intended source review, not a running schedule. See the registry for source URLs, formats, dependencies and per-source limitations.

| Source | Steward | Access/status | Expected cadence |
|---|---|---|---|
| Provo Streets | Provo City | public / available | monthly-check |
| UDOT Crash Locations | Utah Department of Transportation | public / available | weekly |
| Provo Police active transportation incident workbook | Provo Police Department | restricted / available-periodic-delivery | on-receipt |
| UDOT Annual Average Daily Traffic | Utah Department of Transportation | public / available | annual |
| Provo traffic studies | Provo City | public / available | on-discovery |
| UDOT Active Transportation Intersection Safety Data | Utah Department of Transportation | public / available | quarterly-check |
| UGRC Utah Bikeways and Level of Traffic Stress | Utah Geospatial Resource Center | public / available | monthly-check |
| UDOT active transportation counters | Utah Department of Transportation | public / available | monthly-or-quarterly |
| UDOT Safe Routes to School public views | Utah Department of Transportation | public / available | monthly-check |
| Provo school-zone traffic-control inventory | Provo City Traffic Engineering | public-derived-only / request-needed | annual-before-school-year |
| Provo official crosswalk inventory | Provo City Public Works | public / available | monthly-check |
| FRA railroad grade crossing inventory | Federal Railroad Administration | public / available | weekly |
| UDOT Traffic temporary construction and closure events | Utah Department of Transportation | restricted / developer-key-needed | hourly-when-operational |
| UTA stops and recent ridership | Utah Transit Authority | public / available | monthly-check |
| Provo Parks and Recreation trails | Provo City Parks and Recreation | public / available | monthly-check |
| Strava Metro | Strava | restricted / requested | agreement-dependent |
| MAG Utah Bike Demand Model output | Mountainland Association of Governments | public-derived-only / requested | on-model-release |
| MAG High Injury Network | Mountainland Association of Governments | public-derived-only / requested | quarterly-check |
| Provo Streets Watch reports and concerns | Provo Streets Watch | internal-sensitive / available | daily-or-release |
| Provo 311 service requests | Provo City | public-derived-only / deferred | deferred |
