# Data Hub completion and maintenance

Status checked November 8, 2026. The foundational roadmap is implemented: independent private repository and static host, reproducible versioned releases, documented ownership and dataset structures, pinned consumer adoption, and agent-operated recovery drills. Periodic review and future source deliveries are ongoing maintenance. The incident-map migration below awaits final production verification at this point in the record.

| Product | Working update path | Structure and definitions | Consumer pin |
|---|---|---|---|
| Annual transportation counts | Reviewed annual delivery → counts_candidate.py → approved release | contract.md, dictionary, historical mappings and protocol | Projects 1.0.1 |
| Safe Routes to School | Monthly private acquisition and campus review → safe_routes.py | Three GeoJSON layers, source/campus provenance, dictionary | Projects 1.1.0; Streets Watch independently retains 1.0.0 |
| Annual AT crashes | State/PD receipt → update_crashes.py → crash_packages.py | Annual dictionary, source population and provisional-year rules | Projects 1.0.0 |
| Annual motor-vehicle crashes without nonmotorists | Same private crash updater → motor_vehicle_candidate.py and crash_packages.py | Participant completeness and reviewed parked-vehicle rules; unresolved held separately | Projects 1.0.0 |
| Fatal AT crash geography | Pinned managed release plus reviewed 2010–2017 archive → fatalities.py | 25 crashes, 26 deaths; approximate points, month, mode and death count | Projects 1.1.0 |
| Reviewed concern crash details | Pinned managed release → danger_zones.concern_details → preview/apply/rollback | Versioned public allowlist; state IDs and reviewed PD references, no raw narratives | Streets Watch reviewed import: 30 crashes across seven concerns, four PD references |
| Historical incident-map extract | Reviewed normalized/derived inputs → incident_map.py | Frozen historical definitions, public field validators and dictionary; 1,195 groups, not unique crashes | Projects 1.0.0 (migration verification below) |

Updates intentionally require review. Counts needs mapping of the next delivery to the protocol. State and police updates depend on delivery. Safe Routes automates acquisition of a candidate, not release approval. New source populations, public fields or disputed identities require their own review. Consumers select releases independently; an older supported pin is not a failed migration.

The untouched transit, bike-parking, bike-lane, counter and intersection captures are research inputs in the canonical BikeWalk research archive, not processed hub datasets. Dashboard ideas and most-dangerous-intersection research remain TODOs, not hidden completion requirements. A separate human/off-machine recovery exercise was explicitly deferred by the owner; the completed agent drills used authorized access on this host. No new schedules, paid services or query API are needed for this closeout.

## Verification and rollback

Before migration, all 75 existing public hub files matched rebuilt production bytes. Projects' five existing datasets matched catalog pins, live fatalities and annual crash data matched adopted files, and Streets Watch's three Safe Routes layers and all seven concern imports matched their adopted snapshots.

Incident-map candidate: manifest `e9fdbe0101380792235c2ff1c43bccf0645c220730cf6d0ab12e8f403ea9df8e`; layer `9f5c4f56645ea7467e21cbff900d5831835d34a525304281f10c27c91f1c5a01`. Two builds were byte-identical. Corrupt input was rejected without creating a candidate or changing approved files. All 133 crash producer tests passed, including the migrated summary tests. Projects passed 23 JavaScript and three Python adoption regressions. Production IDs and final browser verification follow after staging.

Previous production hub: `dpl_7GFzG2Vs4Tw3yhKdoCb2wEZ6uXFw`; Projects: `dpl_B4wpBcfUh7rcr7jPVLZosYmUAow1`. Retain these for rollback after consulting withdrawals. Existing public-map data bytes must remain unchanged by this migration. No worktree is created for this task, and unrelated checkout work is preserved.
