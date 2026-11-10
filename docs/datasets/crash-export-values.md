# Readable crash export values

The hub owns translation of source categories. `danger_zones.crash_labels.export_values(table, values)` produces a separate readable projection for Streets Watch's crash-map importer. Received workbooks, managed collections, normalized analytical records and published historical pins retain their original codes and source labels. No observations are merged or reclassified by this export operation.

In the readable projection, a supplied nonempty companion label replaces its base value and the companion field is omitted. Catalog bindings handle differently named companions such as `roadwayContribCircumstances_label`. A label without a corresponding code column becomes its own base field, so the second roadway circumstance is retained. County code/name aliases retain their separate provenance; the exporter does not assume they are interchangeable.

When a companion label is absent, the field's codebook supplies the value. Existing common codebooks are reused. [Supplementary export codebooks](../../data-definitions/crashes/catalog/incident-metadata/export-codes.json) cite the checksummed retained 2021 field tables/dictionary and the 2026 manual. Leading zeros are interpreted only inside categorical fields. Crash IDs, route identifiers, vehicle numbers, counts, ages and measurements are not decoded as categories. Missing values remain missing. Supplied labels take precedence, including legacy labels and source-recorded Unknown values; this projection does not silently correct disputed source labels.

An unsupported numeric category becomes `Unmapped code: VALUE`, not an invented meaning or an observed negative. Current unresolved examples include route direction/type `0` and driver/nonmotorist circumstance sentinel codes without a verified field-specific definition. Reporting these gaps does not change private source values. New deliveries or code versions need evidence and regression coverage before extending a mapping.

## Migrate an existing Streets Watch snapshot

Use the pinned crash Python environment from the hub root. This requires only the already minimized public projection, not credentials or private source workbooks:

```sh
PYTHONPATH=.:pipelines/crashes/src python -B -m scripts.migrate_crash_map_labels \
  /absolute/path/to/streets-watch/data/crash-stress \
  private/candidates/YYYY-MM-DD-crash-label-migration
```

The script verifies current map/details against their immutable version, folds and decodes exported fields, and writes a new candidate with map, compressed details, immutable version and `migration.json`. The report records old/new pins, input/output hashes, definition/tool hashes, changed-record count and unmapped fields. Only record section fields change; geometry, membership, IDs, years, filter categories, associations and privacy exclusions stay intact. Duplicate displayed aliases are coalesced only when equal; conflicting duplicates stop migration. Repeating transformation of a migrated snapshot yields the same version and bytes.

Review the candidate, then repeat that command with `--apply`. This checks candidate bytes and refuses a changed source or replacement of an immutable version. It writes the new immutable version first and switches the current map last. Repeat apply is safe, including recovery after details switched but before the map pointer changed. Retain earlier version files. Existing shared links continue to resolve their old evidence. The output directory must be new for preparation; apply can reuse its verified report. A corrupt source, candidate or conflicting immutable destination fails without switching the current map.

The source manifest is a dataset identity/checksum mechanism, not an approval signature. Run only against the intended checkout and a reviewed candidate. Local adoption does not deploy the app. Commit the two current files, new immutable version, importer and summary-reader changes together, then follow Streets Watch's required checks and deployment workflow. Its summary reader must accept readable base fields as well as historical companion fields so old pins remain usable.

For future imports, make the hub pipeline available with `PYTHONPATH=/absolute/path/to/hub/pipelines/crashes/src`. Streets Watch's minimized projection calls the same `export_values` function. The deployed app reads its bundled version and has no runtime dependency on this checkout. The raw query engine and analytical code predicates retain their existing source-code semantics.
