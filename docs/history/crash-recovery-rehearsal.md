# Crash producer recovery drill

On November 7, 2026, a fresh detached checkout of BikeWalk at `fff781bd28e8ec96f01210e0589c2b6225a40486` recovered the annual report pin and the enriched successor from locally retained files. Run the fixture from the hub with the BikeWalk pipeline dependencies installed. Use a new private directory for the reference checkout.

    git clone --no-hardlinks --no-checkout /path/to/bikewalk-provo reference
    git -C reference checkout --detach fff781bd28e8ec96f01210e0589c2b6225a40486
    /path/to/bikewalk-provo/tools/.venv-maps/bin/python -B -m scripts.restore_crash_collections reference /path/to/retained-repo-layout

The second argument supplies the retained files in their original relative directory layout. The fixture follows pinned manifests, resolves references relative to the supplied recovery root, copies verified inputs and bundles into a mode-0700 temporary directory, and runs the producer’s state validator and aggregate calculation there. It removes its temporary copies when finished. With `--producer-src /path/to/new/package/src`, run a separately installed or relocated source tree against the same pins and CSV. Run once per implementation in separate processes. See the [wave plan](annual-crash-migration.md) for the two manifest hashes.

**Result.** All four managed releases verified, including the intervening enrichment release and the references to the preceding unmanaged snapshot and its reviewed links. For each target, the validator matched cumulative input state against the collection. Both had 1,139 groups, 1,755 flattened original observations and 50 reviewed police/state links. All nine rows matched the adopted CSV byte for byte, including the partial 2026 row. Running from a separately located copy of the producer gave the same result. Replacing the newest manifest with an invalid file in a disposable input root stopped the drill at its checksum check.

## Inputs and access

| Material | Retained location in the canonical BikeWalk checkout | Verification and responsibility |
|---|---|---|
| Managed releases and cumulative state | `tools/.danger-zone-private/incident-updates/releases` | Current → enriched predecessor → report pin → initial managed release → legacy snapshot. Bundle manifests bind all resources. The data maintainer needs private read access. |
| Portal intake | `tools/.danger-zone-private/incident-inputs/<sha256>` and legacy `sources/utah-crash-portal` under that private root | Two city and two county-reference workbook receipts verified against the managed manifests. Preserve each delivery’s filters and chronology. The current city receipt hash begins `3405efb3`. |
| Police intake | `tools/.danger-zone-private/sources/provo-police-incidents/snapshots` and `incident-inputs` under the same root | Three original XLSX/Numbers files verified against receipt manifests, plus the normalized police datastore against its pinned hash. The owner grants access to these restricted sources. |
| UDOT | `tools/.danger-zone-private/incident-updates/runs/20261103T212435.608493Z-522cc258/udot` | Normalized parquet hash `bbd69df1…`. Verified all 95 raw request/response files against the retained snapshot manifest `79c44665…`. |
| Municipal street network | `tools/.danger-zone-data/{sources,normalized,manifests,runs}` for `provo-streets` | Two retained street snapshots, each with 13 verified raw files. Preserve their normalized geometry and run manifests for local geocoding on new police receipts. |
| Review evidence and code | Pinned Git checkout, `tools/danger_zone_pipeline`, and `docs/incidents-metadata` | Keep source registry, catalogs, schemas, reference captures, matching decisions, dependency pins and synthetic tests together. The newest baseline’s matching-policy SHA starts `5dabfa4a` and its tool SHA starts `198c56b4`. |

The original service and police intake remain under their source stewards. The hub maintainer needs access to the retained deliveries and their approved backup. This drill used the same machine and OS account. An independent restricted backup and another human’s access still need verification. The older maps migration archive predates these managed releases.

## Producer and caller inventory

Tracing local Python imports from `update_incidents` and `research_reports` at the reference commit produced these 25 modules:

    arcgis common_structure config contextual crash_enrichment crash_portal
    derived_incidents field_inventory geoparquet incident_conversions incident_updates
    incidents judgment match_review normalize normalize_incidents pipeline police
    police_datastore police_portal_candidates registry research_reports update_incidents
    util validate_normalized

Carry the package-relative catalogs and captured references loaded by those modules, as well as the source registry, schemas, pyproject and its pinned dependencies. Keep the dedicated checks on fixtures for intake, linkage, enrichment, rollback and aggregation. The existing tool hash covers only a subset of the import list. Compare policy and runnable dependencies separately when testing the transfer.

| Entry point or caller | Migration implication |
|---|---|
| `update_incidents` | Managed writer, locking, verification, predecessor and rollback. |
| `match_review`, `police_portal_candidates`, `query_incidents` | Read the collection for matching or research. Preserve pin selection and path resolution. |
| `incidents`, `reconcile_review` | Historical writers. Preserve the guard against rebuilding a managed collection through a legacy path. |
| `research_reports` / Projects `research-data.mjs` | Public annual series and its existing adoption path. Decouple the aggregate from counter inputs. |
| `fatality_map` and `crash_enrichment` | Separate pinned private inputs or bundle exports. Streets Watch imports minimized details by state ID. |
| Incident map summary, derived previews and parking research | Follow their own reviewed inputs. Parking screening uses the full portal workbook. Inventory local research tools and one-off consumers again before retiring the old writer. |

## Rehearse the writer and rollback

Use a separate producer checkout of the canonical BikeWalk repository at commit `dcba0a9` and keep the baseline checkout at the commit above. From the hub run:

    /path/to/bikewalk-provo/tools/.venv-maps/bin/python -B -m scripts.restore_crash_collections reference /path/to/retained-repo-layout --producer-src /path/to/producer/tools/danger_zone_pipeline/src --exercise-writer

The fixture runs the normal updater CLI against a temporary restored tree. It denies Python file opens under the original crash data directories and the original reconciliation evidence directory. It compares all incident records and the annual report with the pinned collection, checks that a repeated offline update preserves the active pointer bytes, and exercises rollback through both newly written and historical predecessor pointers. The canonical runbook in `docs/incidents-metadata/update-pipeline.md` gives the operator commands for an actual restore.

On November 7, 2026 the committed producer passed all 200 pipeline tests and the drill above. The isolated offline release `incidents-b4b7b930184d52b5c01e` preserved the full incident records and aggregate report. A repeat kept the active pointer byte-identical. Two rollbacks recovered `incidents-e5a4665997a4cac4f5be` and `incidents-53ed6405327df2765eca`. The original active pin stayed at `c614ca99200bc25ce4d77491061e0d23529f59be24e42bcbff0f16759f4ca979`. This was a same-machine drill under the existing operator account.
