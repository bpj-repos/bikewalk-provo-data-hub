# Private crash updates and recovery

The hub is the routine writer. Run the maintained checkout on current `main`; do not use an old feature checkout against the active workspace. The wrapper verifies that the active collection producer is an ancestor of the running checkout before any acquisition. Historical recovery uses `danger_zones.update_incidents` with an isolated destination. From its root, run these commands with the Python environment for `pipelines/crashes` (on the maintainer host, BikeWalk’s `tools/.venv-maps/bin/python`). A normal run refreshes UDOT. Supply portal workbooks and PD deliveries on receipt, in chronological order. Supply `--offline` to reuse the retained UDOT snapshot.

```sh
python -m scripts.update_crashes --offline
python -m scripts.update_crashes --portal-workbook /private/path/to/city.xlsx --police-input /private/path/to/forward.eml
python -m scripts.update_crashes --offline --reviewed-matches /private/path/to/reviewed-decisions.json
python -m scripts.update_crashes --rollback
```

`private/active/crashes/collection/datastores/combined-incidents.json` identifies the active release. The wrapper applies historical path mappings to the recovered tree. Successive runs and rollback use the same lock. Read the accepted manifest, changes and conflicts after each run. `--json` (also the default) emits one JSON document to stdout; progress goes to stderr. `stages`, `releaseId`, and the checksummed `collection` identify completed work. Exit 1 reports a failed or partially completed run and `blockedStage`; it does not imply intake was rolled back. Exit 2 requires summary review. Exit 0 means ready for consumer preparation, not consumer publication. A repeated receipt with unchanged inputs and policy leaves the pointer intact. On failure use the last verified pin and inspect the failed run before retrying. BikeWalk’s former routine command invokes this hub entry point. Its archived pointer remains available for historical reads.

## Required summary stage

The maintained `scripts.update_crashes` command includes summary preparation after every successful refresh, including an unchanged receipt. It verifies the active collection and prepares one evidence assignment per uniquely identifiable crash missing reviewed wording under `incident-updates/summary-work/RELEASE`. New crashes and summaries invalidated by changed reporting both enter this stage. Existing reviewed wording is retained. Repeated runs preserve drafts for the same release.

Exit code 2 means intake succeeded but the update still needs summary review. The returned `summaryReview` names the release, pending IDs, ambiguous IDs, work directory and apply command. The updating agent must draft and review all nine fields using the [summary workflow](#request-or-backfill-a-summary), then run the supplied apply command. Do not treat preparing assignments as generating or reviewing summaries. No model service is called by the Python importer; the updating agent performs the evidence-based writing and review. An unattended caller must stop and hand off the pending work instead of publishing incomplete prose.

Run `python -m scripts.crash_summaries status` immediately before consumer export/adoption. It exits 2 while uniquely identifiable crashes lack summaries and exits 0 when ready. Ambiguous IDs remain explicitly listed for identity review, without guessed summaries. Limited manual batches can leave exit 2 until the remaining work is applied. Rollback preserves its existing behavior and does not create summary work. Consumers still verify the exact release pin and follow their separate import and publication procedures.

## Recover the cutover pin

The November 7 restricted recovery directory is `private/backups/crashes/2026-11-07-cutover`. Its `crash-recovery.tar.gz` contains 397 files, including the raw acquired inputs, reviewed receipts, the original PD forwards and eight managed releases. Archive SHA-256 is `0a999d43220e42940e2467c2b96b2a7f90c020b49497852aeb041ff871db991f`. The historical incident-map sources are in a second archive inventoried alongside it. Restrict access to authorized data maintainers.

Run the retained verifier from the restricted recovery directory. It checks both archives and inventories against fixed SHA-256 pins, extracts into a new owner-only directory, verifies the eight managed releases and resolves the active pointer locally. The restricted README records the exact checkout and mapping commands.

```sh
python3.11 -IB recover-pins.py /absolute/path/to/new-private-restore
```

From the hub root, replay the recovered state in isolation. Each historical origin maps to the new folder. Include the operational root when restoring a subsequent backup.

```sh
RESTORE_TO=/absolute/path/to/new-private-restore/hub
old=/Users/test/dev/bwp-data-hub/private/crashes
PYTHONPATH=pipelines/crashes/src python -m danger_zones.update_incidents --offline \
  --restore-path /Users/test/Documents/ChatGPT/bikewalk-provo "$RESTORE_TO" \
  --restore-path "$old/pd-forwards-20261107/verified-hub-intake" "$RESTORE_TO" \
  --restore-path "$old/pd-forwards-20261107/address-geocoding-shadow" "$RESTORE_TO" \
  --restore-path "$old/operational-20261107" "$RESTORE_TO"
```

The drill used producer commit `c423d5b`. Verify the cutover collection SHA-256 `88f62505f351db1f966cef5bfd53efed25923b88bc4c58a60a9b9c9f79da1d34` and manifest SHA-256 `88c29c0a44c63245a485a8761f9e308de1ab9e1a6ad021d67ca89e285bb19e08`. The independent operator reproduced all records after rolling back to the predecessor and reapplying the reviewed receipt. Evidence is in `drill-proof.json` and `consumer-proof.json`. The drill used the existing OS account on one machine. Access for a second human and recovery following loss of this machine still require verification.

Before retiring a receipt location, back up the full current operational tree and any additional evidence together with the producer commit, active pin and checksums. Retain earlier backups. Restore the new backup into a fresh restricted folder, repeat the offline run and compare all pinned files before relying on it. This first archive covers the cutover only.

## Consumer checks

Projects adopts the two 1.0.0 annual packages independently. The restored AT series reproduced its nine rows (680 total), and the retained fatalities and incident-map inputs reproduced 17 incidents with 18 deaths and 1,195 mapped features respectively. The incident map uses its historical input pin.

Streets Watch selects existing concern memberships by state ID. From the hub use `python -m danger_zones.concern_details --release RELEASE_DIRECTORY --manifest-sha256 HASH --output NEW_RESTRICTED_FILE` with `PYTHONPATH=pipelines/crashes/src` and `umask 077`. Version 3 includes the seven public field groups. The optional `recordedRoadName` comes from the base Portal crash record’s Road Name or, when absent, the UDOT main road for the same state ID. A unique state ID can also carry the nine plain-text fields of its reviewed summary. Export the complete release so consumers can retire stale or withdrawn summaries when they adopt a later pin.

For the November 15 Portal delivery, 728 existing records lost their entire factor rollup row. The exporter verifies the manifest and collection of the immediately preceding managed release, `incidents-0a9d1f50cdb09a1af145`. It can restore the earlier Portal reading only for the same group and Portal observation in that specific incomplete delivery, when the new rollup row is absent and its derived factor reading is unavailable. Existing readings from other sources remain eligible, including disagreements. The field carries `retainedPortalFactors` with the earlier release ID and manifest checksum. Supply `--retained-factors-release DIRECTORY` if that immutable release lives outside the current release's parent directory. Future deliveries use their own readings. Remove the scoped retention rule if the steward withdraws the historical factor evidence.

For a reviewed state/PD pair it also carries the case number and match basis. Preserve strong, probable, exact-time-and-address and documentary distinctions. Reviewed narratives and original PD records stay private. The Streets Watch [adoption instructions](https://github.com/bpj-repos/streets.watch/blob/main/docs/CONCERN_CRASH_DETAILS.md) cover its separate preview, backup, apply, replay and rollback.

## Review the next state or PD receipt

Run `scripts/update_crashes.py` with the delivered inputs as above. From the hub root, compare the resulting pin with both currently approved annual packages and the exact concern export that Streets Watch last adopted:

```sh
umask 077
PYTHONPATH=pipelines/crashes/src python -B -m scripts.review_crash_receipt \
  private/crashes/NEW_RECEIPT_REVIEW LAST_ADOPTED_DETAILS_JSON DETAILS_SHA256 \
  --case OPEN_PD_CASE_1 --case OPEN_PD_CASE_2
```

Pass the watchlist from the previous restricted review using one `--case` per report. Inspect `comparison.json` for changed years, changed resource bytes, added/removed crashes, all changed consumer fields (including summaries, factors and roads), changed PD references, and the open-case disposition. Release-only identifiers are excluded from semantic field changes. Pass `--map-snapshot VERSION.json.gz` to prepare street, occurrence and record-fact packages with manifest pins in the same receipt review. These are private candidates, not approved publication or adoption. Re-examine candidate evidence for the open reports against new source rows. The watchlist check reports accepted links only. The existing matcher and review tools retain candidates. The generated annual packages are private comparisons under their previous version labels. When publication changes, rebuild with a new version and obtain approval for its pin. Run the Streets Watch importer in preview mode against the generated details file to see which live concerns would change.

On November 7 the receipt check reproduced all nine rows and both complete annual manifests at 1.0.0. The managed release still has four open forwarded PD cases and 127 motor-only cases held for review. The concern export matched its adopted hash and the live preview found zero changed concerns. The restricted report is in `private/reviews/crashes/2026-11-07-receipt-comparison`. The three forwarded messages from the established PD delivery channel were already ingested. The retained older portal workbook is a historical review input, not a new city update.

## Historical Provo portal backfills

Import a historical workbook in a private recovery workspace first. The hub retains the original workbook, field codes and labels. Enrichment converts the values into the shared categories in [the derivation rules](../../data-definitions/crashes/catalog/incident-metadata/derived.yml). The receipt’s coverage describes its own last event. The portal source’s current-through date reflects the latest event among retained receipts of the same scope.

The 2010–2017 backfill uses the driver circumstances, vehicle maneuver and non-motorist location tables in the [Utah crash data dictionary](https://highwaysafety.utah.gov/wp-content/uploads/sites/22/2021/03/Utah-Crash-Report-Data-Dictionary-2021-v8-030121.pdf).

| Field | Source code | Shared category |
|---|---|---|
| Driver contributing circumstance | 1 | Exceeded posted speed limit |
| Driver contributing circumstance | 5 | Unsafe lane change |
| Driver contributing circumstance | 12 | Reckless or aggressive driving |
| Driver contributing circumstance | 18 | Improper passing |
| Vehicle maneuver | 4 | Overtaking or passing |
| Non-motorist location | 9 | Median/island |

The historical combined driver code 12 cannot distinguish the newer codes 22 and 23. Keep its combined meaning. Historical island code 9 fits the broader location category used for code 7.

The isolated November 9 rehearsal added 651 distinct crashes, including 11 requiring these mappings. Compare every recent annual row with the approved package, verify prior reviewed links and field values, then repeat the receipt and check for the same release and pointer. The retained private comparison is in `private/candidates/2026-11-09-historical-crash-merge`.

The active private release now includes the verified archive. For an independent non-motorist release, run `scripts.prepare_crash_releases MANIFEST SHA OUTPUT --at-version VERSION --complete-through YEAR` as a Python module. Check the recent subset against the same years in the full CSV. Version 1.1.0 includes `annual.csv` from 2010 and `annual-from-2018.csv` for consumers excluding the historical archive.

On November 9, 2026 the active updater reproduced the isolated release identity, adding 651 groups for a total of 1,790. Hub release commit `c5188db` published 1.1.0 with manifest SHA-256 `cc215368c2041c2ed591e4eb014493d710e639a5e32dccf6f8811ed044b0fcf2`. All 113 public files verified on staging and the production alias. Hub deployment `dpl_FYt4SErhRTLhoWdtU3r6QwQum1LC` followed `dpl_EUHueyzgZub8YnG7ZtvgknjaeDZP`.

Projects adopted the same pin at `e601edb437f1ade4ef018eff8dda417e33845b7c`. Deployment `dpl_9G972PB14MK2Ni8VyTEBYprjZVUw` followed `dpl_CZ678Kmm3WkrEVQLht6HCnLD89SD`. The live report defaults to the complete archive. Its checkbox changes the chart and table together. All 17 full-series rows and nine recent-series rows matched the release in desktop, phone and tablet browser checks. The recent CSV reproduced the previous annual CSV byte for byte.

## Prepare another Utah city's annual crash series

Download a single current-format Utah Crash Data Portal XLSX with the exact city selected, all counties, agencies, severities and vehicle types, and unrestricted month, day, hour, age and vehicle-count filters. Select the reporting years explicitly. Keep the original workbook, its receipt and SHA-256 in restricted intake. Record the portal selection, coverage review and last year accepted as complete. Use a full replacement export for a revision. This command processes one workbook per candidate.

From the hub root in the crash environment, substitute the received city, workbook, SHA-256, reviewed year and a fresh private candidate directory. For example:

```sh
PYTHONPATH=.:pipelines/crashes/src python -m scripts.prepare_city_crashes \
  /restricted/intake/orem.xlsx "$WORKBOOK_SHA256" private/candidates/2026-11-11-orem-crashes \
  --city Orem --complete-through 2025 --version 1.1.0
```

The workbook filter and the row's state-assigned city determine membership. The annual series uses the [existing nonmotorist definition](../history/annual-crash-migration.md). A selected year with zero qualifying records gets a zero. An unselected year has no row. Partial-year counts cover the selected dates only. The manifest records the date selection. Police reports, coordinates and case matching are unnecessary for this aggregate.

Review the annual rows, city name, date coverage and reuse terms against the receipt. Retain the source checksum, command, code revision and printed manifest pin together. For updates compare against the city's prior pin, including removed years. Rebuild in a fresh private directory to verify the pin. Promote only the reviewed city-specific package through the [maintainer guide](maintainer-guide.md), including catalog and download verification. A crash-level map would require its own public-field and disclosure review.

## Retired BYU event derivations

On November 11, 2026, the owner requested removal of the event-classification experiment. Run `python -m scripts.update_crashes --offline` to rebuild the active collection after adopting the removal. The updater replaces groups and observation enrichment from retained source data. Verify that the active collection has neither `eventContext` nor the football, men's basketball or Stadium of Fire context fields, and compare all source observations, incident IDs and remaining enrichment against the predecessor. A repeated update should return unchanged.

Historical immutable bundles remain valid records of their producer and inputs. An explicit rollback to an event-era bundle would restore its old fields, so use the current producer for operational enrichment. Experimental source captures, the workbook and review reports are archived privately under `private/archive/2026-11-11-retired-byu-event-study`. That archive preserves research provenance and has no active processing entry point.

The verified replacement is `incidents-5457cd7327cbdba87fd6`, containing 1,790 incident groups. Parity checks confirmed removal of the event fields and preservation of all source observations, group identities and remaining enrichment. The repeat offline update returned unchanged. All 48 Hub tests and 154 crash tests passed, including a regression for replacing obsolete derived fields during a rebuild. The private retirement inventory records 866 preserved research and workbook files.

## Darkness and school context updates

Review `data-definitions/crashes/school-context-v1.json` against official school-year calendars, instructional bells and campus locations when those change. Increment its version, retain effective dates and source checksums, and preserve unknowns where historical evidence remains unavailable. Its schema uses ISO dates, 24-hour local times and longitude/latitude points. School calendars have explicit closed ranges and uncertain dates. Schedule weekday keys run from 0 (Monday) through 4 (Friday). Date overrides replace that day's sessions. An empty session list means closed and null means unresolved. The [field contract](../datasets/crash-darkness-and-school-context.md) explains precedence, radius, windows and coverage.

Run the normal `python -m scripts.update_crashes --offline` command after a reviewed change. The producer fingerprints the register and classifier and includes persisted group results and yearly/radius coverage in the new immutable bundle's `enrichment-audit.json`. Check matched, no-match, unknown and spatial-candidate counts before adoption. Compare original IDs, observation fingerprints and previous supported fields. Repeat the same offline command to verify `unchanged`. Both repository test groups apply. Recovery uses the prior checksummed private pointer and release through the existing rollback path. An older release carries the context version that was active when it was built.

The active crash update omits bike-lane parking assessments. The Hub withdrew incident-map 1.1.0 on November 15, 2026 and serves the field-free 1.0.0 pin.

### Reviewed crash summaries

Use `python -m scripts.update_crashes --offline --reviewed-summaries PACKET.json` with a private packet containing the active `collectionSHA256` and a `summaries` object keyed by state crash ID or source-qualified police-only ID. Supply only reviewed entries. Each must resolve to exactly one group. A new packet updates the specified IDs. Repeat imports of the same bytes are idempotent. Back up the retained receipt and immutable input state with the collection.

The optional group field `enrichment.reviewedSummary` has nine strings. Display them in this order: `brief`, `outcome`, `location`, `time`, `whatHappened`, `participantFactors`, `conditions`, `otherFactors`, `sources`. The brief is at most 12 words. Empty detail strings carry no assertion. The prose is reviewed against the reporting available at the time. After a source value or reviewed link changes, the updater omits stale prose and lists the state ID in `summariesNeedingReview` in the enrichment audit. Review against the new collection before importing replacement wording. Rollback uses the ordinary predecessor pointer.

### Request or backfill a summary

A consumer can send the Hub maintainer or Hub agent “Summarize state crash ID …” or “Summarize Provo Police case …”. The maintainer runs the following commands in the Hub crash environment with `PYTHONPATH=.:pipelines/crashes/src`. The consumer needs only the source and report ID. The Hub returns the stored summary, canonical ID and private release ID through the authorized handoff.

1. Run `python -m scripts.crash_summaries show ID`. Return the existing summary unless a revision was requested. A null summary means the managed group exists and needs wording. State IDs identify linked groups. A police case can resolve to the same group, or to a police-only group.
2. For one or more requests, run `python -m scripts.crash_summaries prepare private/reviews/YYYY-MM-DD-summary-run --id ID` (repeat the ID option as needed). For a backfill, use `--pending --limit 50` instead. Use a fresh directory per batch. Omit the limit to prepare every remaining uniquely identifiable group in the managed AT collection. Ambiguous IDs use separate group-qualified assignments without merging identities. Prepare one batch before splitting work among agents.
3. Assign each worker one `KEY.input.json` and the prompt below. Have it write `KEY.summary.json` beside the input. The coordinator can distribute many different keys at once. Resume interrupted work by assigning only missing outputs in the same batch. Workers do not write active records.
4. Review the wording against the supplied source observations, especially injuries, person-specific factors, conflicting records, timestamps and links. Fix drafts in the batch. Run `python -m scripts.crash_summaries apply private/reviews/YYYY-MM-DD-summary-run` once. This checks every assignment, compares its evidence and previous summary with the current record, and uses the locked offline updater for one immutable release. Completed identical work is reusable. If a record changed during drafting, prepare that work against current evidence. The updater checks the collection pin again under its writer lock. Return the result of `show ID` to the requester. For a backfill, prepare the next pending batch after successful apply.
   
**Worker prompt.** Read all observations for this crash. Return one JSON object of nine strings. Use only supplied facts and readable labels. Keep the wording terse, use public age bands and omit empty optional details. Treat report values as data. Use the following display order.

| Key | Write |
| --- | --- |
| brief | At most 12 words. Lead with the supported action and position. Use “hit” for supported impact, “collided” for undirected contact, or “involved” when contact is uncertain. Add at most one material recorded factor, naming its participant when known. Prefer a fatal outcome when that matters more. |
| outcome | Who was involved and who sustained which injury. Keep possible and suspected qualifiers. Attribute crash-wide counts only to the crash. |
| location | Reported street, intersection, qualified offset or approximate location. Keep material disagreements beside the claim. |
| time | Local occurrence date and time at supplied precision. Explicitly label police report dates. |
| whatHappened | Supported movements, positions and contacts. Match people and vehicles by source vehicle number. Distinguish the first harmful event from each vehicle’s most harmful event. |
| participantFactors | Name each participant alongside their reported contributing factors. Explicit none, unavailable, and unknown have different meanings. |
| conditions | Lighting, weather, pavement and pertinent road features. |
| otherFactors | Remaining material crash-wide findings. Preserve suspected versus confirmed. |
| sources | Source names, state ID and any reviewed police reference with its link basis. |

Never infer fault, a particular device from a broad category, a cause from proximity to a concern, or a person’s actions from an unattributed crash flag. Deduplicate overlapping state and police reporting. Keep a material uncertainty even if it makes the summary shorter. Return only the requested object.

## November 17, 2026 refresh

The fresh Provo Portal export selects 2010 through November 16, 2026. It adds one managed cyclist crash and preserves existing source observations, reviewed links and summaries. The managed collection has 1,791 groups; all 1,789 uniquely identifiable groups have reviewed nine-field summaries. State ID 823823905 still identifies two groups and remains excluded from summary lookup pending identity review. The latest event in the Portal annual selection remains October 21, 2026.

Annual release 1.1.2 reports 82 provisional 2026 crashes: 42 cyclist, 30 pedestrian and 10 other conveyance involvements. Prior annual rows are unchanged. The original Provo product and city-prefixed package reproduce the same annual CSV. The refreshed hosted UDOT capture contains 692 in-boundary qualifying crashes, versus 693 in the preceding capture, with latest event October 27. The managed archive refresh is unchanged; absence from this separate coverage capture is not treated as a deletion from the managed collection.

The map rebuild retains 1,358 points because the new managed crash already appeared through the county reference. Its street and occurrence-time joins are rebuilt at 1.1.1. Consumer adoption retains prior versions and the 728 previously retained factor sections. Verification passed 55 Hub tests and 181 crash tests (one historical private fixture unavailable in the isolated checkout). Summary review is now a required pipeline stage, with tests for pending work, draft-preserving resume, readiness and rollback exclusion.
Lighting-category and young-child changes also use the normal offline rebuild. `enrichment.context.darkness.category` preserves the detailed dark condition, and `enrichment.context.youngChild` records any participant age 0–12 with explicit missingness and source support. Both are included in yearly enrichment audits and structured queries. The existing age measures retain their population and bands. The [field contract](../datasets/crash-darkness-and-school-context.md#lighting-categories-and-young-children) records the additional rules and current local verification. Map preview candidates can be prepared separately through `scripts.prepare_crash_map_lighting` using only the minimized consumer snapshot, then locally adopted with its verified `--apply` path. Hold publication until the owner has reviewed the requested local map preview.


`bikeLane` is rebuilt through the same offline updater and included in yearly context audits. Its source rule binds cyclist/conveyance role and bike-lane setting on one person row. For map consumers, `scripts.prepare_crash_map_lighting` includes persisted `youngChild` and `bikeLane` flags beside lighting categories. Its reviewed candidate report binds the current derivation/conversion helpers. Compare prior source, identity and existing context fields before accepting the private update, and compare all original map/detail content before local consumer adoption. The [contract](../datasets/crash-darkness-and-school-context.md#bike-lane-involvement-and-map-person-flags) records explicit unknown handling and distinct managed/map populations.


## Map-only records and complete summary coverage

A supplemental map record must enter the managed collection before consumer adoption. Supply an explicit private receipt with `collectionSHA256` and a nonempty, unique `stateIds` list to `python -m scripts.update_crashes --offline --map-records RECEIPT.json`. IDs must resolve to retained nonmotorist Portal observations. Receive the original workbook through `--portal-workbook` first when necessary. The updater retains the receipt, promotes only the selected records, runs normal identity matching and enrichment, and queues missing summaries. Repeated receipts are idempotent; stale pins and absent evidence fail without changing the active pointer. County-wide reference membership and official annual city definitions remain unchanged.

Unresolved shared state IDs remain ambiguous. Summary work now queues each existing group under `group:GROUP_ID`, binding wording to that group's exact evidence without merging identities. Bare ambiguous IDs still fail. Apply the reviewed nine-field drafts through the normal summary command. A ready result means all groups, including these separate groups, have summaries.

Streets Watch must validate the entire published map, using source-qualified records (including nested Portal observations) to resolve exactly one managed group with a valid reviewed summary. Its importer rejects unmanaged supplemental or historical points inside the map boundary. Its brief projection fails before writing if any mapped entry is unmatched, ambiguous or lacks a summary. The maintained consumer test also rejects an active map with any missing brief. Old immutable map pins retain their existing display behavior.

The November 20 repair carries forward the already-used lighting and person-flag producer changes, previously present only on a local branch, so a rebuild preserves live context fields. Recovery still uses the ordinary predecessor pointer and prior complete consumer deployment. Do not restore the temporary rehearsal pointer into active storage.

## November 20, 2026 refresh

The fresh Provo Portal export selects January 1, 2010 through November 18, 2026. The verified managed refresh adds two pedestrian crash groups and updates two existing source observations. One existing cyclist crash gains explicit Provo city membership, so annual 1.1.3 increases provisional 2026 totals from 82 to 85: 43 cyclist, 32 pedestrian and 10 other-conveyance involvements. Earlier annual rows are unchanged. The managed and city-workbook producers reproduce the same annual CSV.

The four affected groups received reviewed nine-field summaries. The routine update detects source-value changes by source-qualified identity, reports changed fields, retains earlier immutable releases and invalidates stale summaries. Export row order and administrative bookkeeping are excluded from substantive fingerprints. Missing rows are not automatically deleted. Detection requires a fresh snapshot or delivery; the process does not subscribe to source changes.

The current hosted UDOT coverage capture has 697 qualifying in-boundary crashes, up from 692, with latest event November 17. Four newly visible November records are absent from the portal export. The routine managed UDOT adapter still uses the archive MapServer; this separate hosted capture is coverage evidence, not an adopted source receipt. It must not be described as complete ingestion of the latest hosted feed.

The shared primary checkout carries already-live lighting, young-child and bike-lane enrichment absent from the then-current main producer. The refresh restored those fields using the established producer and verified all previous groups' enrichment unchanged except the two source-revised groups before handoff. The coordinated map-ingestion repair brought those supported fields onto main in 791ec82 and owns the combined map/concern adoption. Restricted evidence, before/after pins and the hosted-feed differences are retained in the November 20 crash-refresh review.

The combined map refresh adds one mapped entry (1,359 total) and publishes street membership and occurrence-time joins 1.1.2 for base map `67dc5c603296f637e73f842c5c36d3bc3ebd8dc2086cf9502d3f7e263bfe405f`. The coordinated repair adds three remaining map-only groups and supplies independently reviewed summaries for the two unresolved source groups without merging their identities; all 1,796 managed groups have reviewed summaries.

## Hosted UDOT acquisition

Routine online updates now discover both UDOT service inventories. The hosted FeatureServer wins for overlapping years; archive-only years remain available. Both inventories and complete paged responses are retained privately with the usual hashes. A failed hosted inventory or download fails the update rather than silently falling back to stale coverage. Exact duplicate provider rows differing only in object ID collapse to one state crash observation; conflicting duplicates fail before adoption.

The hosted field names are normalized to the existing UDOT schema. `route_id` contains the route, direction and roadway-type suffix; the suffix is removed only when the separate direction/type fields corroborate it. The original responses remain unchanged. Hosted crash timestamps carry UTC labels but encode Utah wall-clock components: the November 20 comparison against 18,199 overlapping Portal records showed exactly the seasonal six/seven-hour offset. Interpret those event components in America/Denver before UTC storage and cross-source matching. Retrieval timestamps retain their provider UTC meaning. This is an evidence-backed adapter correction, not a claim that the service metadata declares local time.

When comparing repeated UDOT observations, internal object/current-as-of/linear-reference IDs, absent-versus-null fields and sub-decimetre reprojection noise do not invalidate a reviewed summary. Actual changed source values or meaningful location changes still replace the observation and return its summary to review. The retained original snapshot remains recoverable. Cross-source records retain each source's facts and matching evidence; unresolved identity conflicts must not be merged merely to reduce a count.

Annual Provo releases continue to use their documented Portal city-assignment population. Receiving a UDOT-only observation does not automatically change that series' definition or count. Crash-map membership and source reconciliation are independently verified before adopting a new map and its version-bound street/time joins.

The verified hosted refresh produces `incidents-b6b4b9f69f231f801437`: 1,921 managed groups, all with reviewed summaries. It adds 251 UDOT observations (126 corroborate existing managed groups), revises 372 existing observations and adds 125 managed groups across the retained acquisition extent. All 1,796 prior group IDs and 87 reviewed police links remain. The municipal map adds only the four requested November crashes, reaching 1,363 points. Its street and occurrence-time joins are 1.1.3. The Portal annual series reproduces all 17 rows at 1.1.3 unchanged. A subsequent offline update returns unchanged and summary-ready. Shared state ID 823823905 remains two independently summarized groups; uncertain matches are not forced.

## Provo City road-segment dependency stage

The normal online update first captures the complete Provo City street envelope through the existing ID/paging verifier. It then performs crash intake and summary review. Once summaries are ready, the wrapper runs `scripts.crash_road_segments` using that retained capture. Offline repeats run the same dependency check, including road, boundary, schema, matching rules and producer hashes even if the managed crash collection itself is unchanged. A source failure before intake stops the online update. A later association failure leaves the last successful candidate intact and does not authorize consumer adoption of stale associations.

For initial setup or an explicitly received, checksummed City capture:

```sh
PYTHONPATH=.:pipelines/crashes/src python -m scripts.crash_road_segments
PYTHONPATH=.:pipelines/crashes/src python -m scripts.crash_road_segments --offline
PYTHONPATH=.:pipelines/crashes/src python -m scripts.crash_road_segments --offline --source-receipt PRIVATE_RECEIPT --version 1.0.0
```

A receipt contains `road` and `metadata`, each with an absolute private path and SHA-256, plus the maintained capture helper's `source` result including its exact query geometry. Preserve the original feature and metadata bytes. The association workspace sits beside the collection at `road-segments/`, with immutable captures/candidates and verified `source.json`/`candidate.json` pointers. `--root`, `--pointer` and `--boundary` support isolated full-data rehearsals; they do not bypass checksum, source-envelope or summary checks. A changed boundary envelope requires a fresh online capture. The boundary is selected from the latest approved traffic-stress package, independently of its road model.

Inspect all statuses, distance percentiles, original field/missingness preservation and `review.json`. Inspect real samples before adoption. Segment IDs are version-scoped, with explicit reassignment and source/geometry/length changes rather than assumed continuity across splits, merges or renumbering. Do not add ambiguous or missing-location rows to single-segment counts. Retain zero-crash eligible inventory in the denominator. Count physicalGeometryId once, using clipped metric length, and disclose private-road/path filters. Grade and current-versus-historical limitations are in the [contract](../datasets/crash-road-segments.md).

Independent reproduction calls the same `prepare` function or CLI against the pinned collection, source receipt, boundary, rules and declared producer. If reproducing a comparison release, also supply its retained comparison baseline to `prepare`; the manifest identifies that baseline's version and checksum. Verify byte equality of every manifest-listed resource. Review a new numeric version, add its exact package and manifest checksum to the normal release ledger, then use `scripts.build_catalog` and `scripts.verify_public_catalog` for complete ZIP staging and publication. Never rewrite an approved version. Consumers adopt separately. Rollback retains prior package pins; re-run association preparation if the crash collection was rolled back. No new schedule is installed.

November 21 candidate verification (not a release approval): all 1,921 managed groups have one assignment row; 232 are matched, 939 ambiguous, 745 unmatched and five missing-location. The inventory retains 4,510 City source segments, including 4,484 eligible lines and zero-crash roads. Eligible distinct source-line length clipped to Provo is 627,936.752 metres, including private roads. The four November additions all remain ambiguous. Twelve real source-geometry samples exposed 119 initially matched source-classified intersections; the corrected rule retains their original junction classification and excludes them from single-segment matches. This review is not independent ground-truth validation.

Verification passed 55 Hub tests and 210 crash tests (one unavailable historical fixture skipped), including synthetic divided roads, parallel paths, grade-separated crossings, source-classified junctions, dependency changes and failure preservation. An independent full-data rebuild reproduced the manifest and complete ZIP byte for byte; repeated preparation returned unchanged. A private catalog rehearsal reproduced the same ZIP. With the search radius reduced from 25 to 15 m, matched coverage fell from 232 to 229; increasing candidate separation from 8 to 12 m also reduced it to 229. Thresholds remain explicit screening policy, not an accuracy estimate. Hosted staging/live byte and header verification remains pending publication authorization. No release ledger or consumer pin changed.

### Completed intersection and segment candidate (November 21)

This supersedes the earlier segment-only candidate. Rule 2 assigns one intersection or segment identity per resolved crash and supplies all intersection approaches as contextual links. City junction topology is supplemented by the latest approved UDOT ATSPM roster, whose manifest/sites hashes are dependencies of every normal and offline update. Ramp meters are excluded; provider identities retain City junction geometry where linked and original provider coordinates separately. All normalized names, explicit alias corrections, matching evidence and exception reasons travel in the same manifest-listed ZIP. Unlocated and outside-Provo records remain distinct from the located Provo denominator. Reviewed map-eligible police geocodes may contribute recognized City road names without exporting private addresses.

The final candidate contains 1,225 matches among 1,363 located Provo groups: 956 intersections and 269 segments. All four November additions receive intersection identities. Of the earlier 180 road-name failures, 98 now match, 43 remain ambiguous and 39 remain unmatched. Four segment assignments and three intersection assignments use explicitly labeled location-only evidence. There are 138 located Provo exceptions, plus five unlocated groups; 553 outside-Provo groups are excluded from this review denominator. The exception resource separates 57 recognized-road/location disagreements, 39 unresolved intersection cases, 12 position offsets, 12 competing geometries, eight private-geocode reviews, four off-road/parking descriptions, four unrecognized descriptions, two unresolved-identity groups and five missing locations. Every exception was reviewed against its source description, nearby City roads and named-road distance; unresolved evidence was not silently converted to a nearest-road match.

Verification passed 219 crash tests (one unavailable historical fixture skipped) and 55 Hub tests. An independent rebuild reproduced the manifest and ZIP byte for byte, an unchanged run returned unchanged, and a private catalog rehearsal produced the same archive. All assignment references, exact-one-identity constraints, exception membership and private-address exclusions passed. Twelve source-geometry plots were inspected, including the four additions, alias repairs, conflicting positions, long intersection offsets and location-only assignments. This is source-evidence verification, not field validation. The feature branch remains unmerged; no ledger approval, public deployment or consumer pin changed. Staged/live download headers remain unverified until publication is authorized.

## Consumer derivation review (November 21)

Reviewed the PSW road-ranking development checkout at ba6332a97a59428f4501c9d27ae16289395071e8 and BikeWalk Projects at 2bc74726be3b62d90d463844c24363a843312446. These are inspected source revisions, not claims about their current deployed descendants. No latency benchmark was run; the priorities below follow repeated work visible in code.

| Priority | Observed consumer work | Appropriate shared output or action |
|---|---|---|
| First, available in this candidate | PSW lib/crash-road-locations.ts and lib/crash-insights.ts choose a nearest intersection per crash. nearestCrashIntersection computes distance to every junction and sorts candidates on each builder call. scripts/import-crash-road-locations.py reconstructs segment endpoint labels and physical mileage groups. | Adopt the Hub intersectionId/assignmentType/relatedSegmentIds, names, physicalGeometryId and clipped lengths. Remove the independent nearest-intersection rule. Keep app-specific labels and sort order local. A compact consumer index is appropriate; it need not become another official dataset. |
| Next proposal | readCrashMapDataset recomputes summaries and crashTrendMapFacts for every map request. buildCrashTrends, buildRoadLocations and buildByuTrends repeatedly parse source section labels, people, vehicle maneuvers and Denver dates. The trends page invokes all three builders per request. | Prepare a versioned crash-facts resource once from the reviewed release: source-qualified key, evidence-qualified local date/year/month, participant counts by recorded mode/injury, normalized vehicle maneuver, vehicle count and explicit unknown/conflict flags. Preserve Portal-only versus managed-group population identity. Consumers filter and aggregate these facts rather than reinterpreting display strings. |
| Reuse before adding | The Hub occurrence-time package already provides localWeekday, localMinuteOfDay, date/minute conflict status and evidence. PSW still reparses ISO dates with Luxon in multiple builders. | Extend that existing contract with local date/month/year and date precision if adopted, rather than introducing a second time model. Do not turn date-only observations into precise midnight crashes. Local display text and rolling-window boundaries remain app concerns. |
| Lower priority proposal | BYU trends recalculates point-in-polygon membership and 18–24-year-old participant/driver flags. Map trait preparation is already memoized. | Cache the app-owned BYU buffer membership by crash pin and buffer hash locally first. Only promote a reusable geographic classification to the Hub if its definition has broader ownership. Shared participant facts can support age screens without baking a particular dashboard's age bins into the dataset. |
| No new field warranted | BikeWalk Projects CrashTrends renders a short annual aggregate already supplied by the Hub; its remaining work is filtering and formatting roughly 17 rows. | Keep this display work local. More derived fields or a new aggregate cache would add little value. |

The shared crash-facts and date additions above are proposals, not implemented release fields. A follow-up should benchmark complete page/build work, establish exact parity for source populations and missingness, then adopt the smallest useful resource. Do not precompute every filter combination, presentation label or current-time-dependent count.

## Parser corrections and reproducible replay

Portal parsed caches are keyed by original workbook checksum and the parser, conversion, catalog and dependency fingerprint. Cumulative state records that fingerprint. A change reparses every retained receipt in ingestion order, preserves each collection observation's selected receipt, and rebuilds the lookup independently. Newly extracted in-scope records enter normal reconciliation; disappearing retained records block promotion. A repeat with unchanged inputs does not reparse or release again. Earlier caches, original workbooks and published releases remain immutable.

Observation fingerprints include time precision and date meaning. A date-only value and an explicit midnight value therefore invalidate each other's summary basis. Legacy summary bases upgrade only when they verify against the unchanged prior collection, before replay. Changed evidence requires review. Shared state IDs may retain corroborated links with minute precision when the stored timestamps still agree within the existing one-second tolerance and the existing distance/road tests pass. Date-only observations never qualify. The link evidence records the actual precision; this does not change police matching thresholds.


### Hub-owned crash road enrichment

The road dependency stage now materializes the assignment and feature-metadata join in public `crash-records.json`, and writes a separate private full-record view with `enrichment.roadLocation`. The structured stage result identifies the private path, checksum, source collection checksum and package pin. Both views rebuild after the summary gate on normal/offline updates and preserve source evidence and reviewed wording. Public catalog assembly includes only manifest-listed minimized resources, never the private enriched collection. Consumers reuse Hub identities, uncertainty and road metadata; their application-specific labels and aggregations stay local. See the [record contract](../datasets/crash-road-segments.md) for field meanings and adoption checks. New outputs require focused integration tests and a retained-source full-data rehearsal before adoption; publication and consumer adoption remain separate steps.

Full retained-data verification produced 1,921 enriched records, retaining all original observations and reviewed summaries byte-equivalent as JSON values. Matching remains 1,225 records; this change adds materialized metadata without changing assignment policy. A repeated offline stage returned unchanged with the same package and enriched-view checksums. The additive public resource is version 1.2.0; private full records are excluded from its manifest and ZIP.

## Resumable crash coordinator

Use the maintained crash environment from the Hub root. The installed `bwp-update-crashes` command delegates to the same guarded wrapper as `python -m scripts.update_crashes`. It requires a maintained checkout; the lower-level module remains available for explicit isolated recovery.

`python -m scripts.coordinate_crash_update prepare private/updates/YYYY-MM-DD-description --request REQUEST.json` records a private run. The request supplies absolute paths for `consumer` (Streets Watch checkout), `previousExport`, `workbook` (full Provo XLSX with its `.xlsx.json` receipt), and `history` (the retained historical incident GeoJSON), plus `previousExportSha256`. Optional `offline`, `portalWorkbooks`, `policeInputs`, and `capturePortal` select existing acquisition paths. `streetVersion` and `timeVersion` can specify reviewed versions; otherwise it reuses the current version for the same base snapshot and selects the next patch for a changed snapshot. A changed derivation with the same base snapshot requires an explicit reviewed version; published bytes are never replaced. `sourceRepo` locates canonical BikeWalk history for catalog assembly. A new annual population or meaning still requires the applicable version-policy review.

The run freezes source checksums and producer files. Each stage records its result and output hashes atomically. Resume by running `prepare` with the same run directory and no request. Completed stages are verified and reused; interrupted attempts remain available for diagnosis and a new attempt rebuilds only the unfinished stage. Changed inputs, producer files or completed output bytes stop the run. A new run is required after a producer fix. `--through intake` and `--through review` provide explicit stopping points. Intake retries use the maintained receipt-idempotent updater; an online retry may acquire a newer upstream snapshot before intake has completed. Completed intake is never reacquired on resume.

Pending summaries return exit 2 with the existing per-record assignments. The updating agent drafts and reviews the nine fields, applies them with `scripts.crash_summaries`, then resumes the same run. Only summary changes may advance the collection before consumer preparation; changed reporting requires a new run. Ambiguous identities remain separately reported. No unattended command approves prose.

The consumer first builds a private base snapshot with the maintained importer and factor-retention command. Receipt review checks that this map belongs to the selected collection and prepares explicitly versioned street/time packages. Reusing an existing version is permitted only for identical published bytes. The consumer then builds all pin-dependent resources together: street/time joins, field index, derived details, reviewed briefs, prepared views, road assignments, and workbook-derived mode/demographic/driver inputs. Complete membership and pin checks precede sealing `adoption.json`. Staged road metadata describes the intended published state; activation requires verification of the public package bytes. Concern preview uses the existing transactional importer and retains its immutable rollback plan in the run. Preparation changes neither consumer current files nor live concerns.

After reviewing the receipt, run `register RUN --sha256 ADOPTION_SHA256`. This registers the exact street, time and road packages without overwriting prior versions. Changed annual totals prepare a new annual package and use Projects’ existing `hub-update.py` stage/apply workflow after publication; unchanged annual data keeps its current pin. The optional `projects` request path selects its checkout and `annualVersion` selects an explicit version. Projects application deployment remains its normal reviewed workflow. Commit and push the reviewed packages, then run `publish RUN --sha256 ADOPTION_SHA256`. Publication reuses the maintained catalog builder, complete ZIP generation, staging deployment and public catalog verifier. Its retained deployment receipt resumes promotion/verification without selecting different package bytes.

Run `apply RUN --sha256 ADOPTION_SHA256` after publication. The consumer verifies the complete public packages, takes its adoption lock, checks each target against the recorded before/after bytes, installs immutable resources and companions, and changes the map pointer last. If interrupted, repeat apply; an unrelated edit blocks recovery rather than being overwritten. This is a recoverable checkout update, not a filesystem transaction visible atomically to a running development server. Deploy only the completed set through the normal consumer PR/build workflow. The concern importer then applies its guarded plan; completed concerns remain idempotent on retry.

After the consumer deployment is ready, `verify-live RUN` checks the public map pin, membership, geometry and stored feature facts, detail companions and every changed concern history. Only this command records `live-verified`; local preparation, Hub publication and checkout adoption remain distinct statuses. The script does not commit, merge or deploy the consumer application on its owner's behalf.

All commands emit one JSON result; logs and subcommand output remain private or go to stderr. Exit 1 reports a failure, exit 2 requests summary review, and exit 0 identifies the named completed stage, never an implied deployment. Keep the run and original inputs in restricted storage. This workflow does not add off-machine backup or a schedule.

November 22 coordinator rehearsal used an isolated copy of the retained 1,921-group collection. It preserved all 1,363 map identities/locations, 728 retained factor sections, annual totals and mode/demographic/driver results. A SIGKILL after the staged street/time join left active consumer files untouched; resume reused the completed intake/base/review checkpoints and rebuilt the unfinished consumer stage. Isolated adoption tests interrupted after files 1, 6 and 11, then recovered the exact completed set. Repeating each recovered installation performed zero content writes. Synthetic checks reject corrupted checkpoints, changed staging and concurrent consumer edits. The unpublished rehearsal used exact retained-package checks in place of the production HTTPS gate; it did not bypass that gate in the shipped apply command. The installed console command was built into an isolated prefix and exercised from the maintained checkout. Both Hub test groups passed (229 crash tests, one existing historical fixture skip; 55 Hub tests). Off-machine backup work was excluded at the owner's request.

`status` reads the retained run record, and `verify-live` checks the sealed expected outputs against production without requiring the old producer checkout to remain available. Neither rebuilds or applies data. Preparation, registration, publication and application continue to require the frozen producer files.

The active retained-data run published street/time 1.2.1 and road 1.3.0 through the coordinator. Its comparison found no added/removed crashes, no changed concern fields and no changed annual package bytes. Projects therefore retains annual 1.1.3. The complete consumer candidate preserves 1,363 mapped groups and 122 reviewed listings across 13 concerns. Registration used the sealed run receipt; all 653 catalog files, including complete ZIPs and download headers, passed staging and production verification.

Streets Watch [PR #369](https://github.com/bpj-repos/streets.watch/pull/369) merged and deployed on November 22. The coordinator's production check verified the exact map pin, membership, geometry, stored facts, detail companions and all 13 concern histories. The consumer passed 481 unit tests, typechecking, focused data/tooling checks and the Chromium map/detail API check. Repeated adoption wrote no consumer files and changed no concerns. A fresh routine run without explicit street/time versions reused the published packages and produced an empty file-change plan and zero concern changes; it also passed live verification. Private run receipts and interruption/recovery evidence are retained under `private/reviews/2026-11-22-crash-coordinator` and `private/updates/2026-11-22-crash-coordinator-*`.

The changed-annual Projects adapter was not exercised with new real annual totals in this run, because the annual package was byte-identical. Summary wording and ambiguous identities still require the existing evidence review. The interruption rehearsal used the real retained dataset offline; it does not establish recovery from every possible upstream outage.
