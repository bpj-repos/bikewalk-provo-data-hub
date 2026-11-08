# Filesystem migration, November 8, 2026

The hub now groups documentation, operator scripts, processing libraries, definitions, releases and tests by purpose. The [repository guide](../../README.md) describes where to find each kind of material. Two script entry points remain at the root for consumers. SYSTEM-DESIGN.md and crash-operations.md preserve existing documentation bookmarks.

## Reproduce the checks

From the hub root, use the pinned crash Python environment for crash commands

```sh
export BWP_SOURCE_REPO=/absolute/path/to/bikewalk-provo
python3 -B -m unittest discover -s tests/hub -t .
PYTHONPATH=.:pipelines/crashes/src python -B -m unittest discover -s tests/crashes -t .
python3 -B -m scripts.build_catalog "$BWP_SOURCE_REPO" build/fresh-staging
```

Use a new staging directory. Compare every public file with the retained baseline inventory before publishing. This migration changes local organization and code paths. Public manifests, resource files, approved pins, dataset definitions and the catalog reproduce the baseline bytes.

## Private cutover and recovery

The restricted record is private/migrations/2026-11-08-layout. baseline.json inventories the original 1,036 private files with SHA-256, size and permissions. tracked-path-map.json records tracked moves. private-path-map.json records each private destination. public-hashes.json records all 80 baseline public files. The two independent catalog rebuilds are retained under build/layout-migration-2026-11-08. The isolated recovery drill, recovery-proof.json and copy recipe are retained in the restricted migration directory.

The original updater lock was held during copying and verification. Active collection data, supporting geography and review evidence were copied into private/active/crashes. The historical path map is private/active/crashes/path-map.json. The mutable active pointer was relocated. Immutable manifests, received files and old receipts preserve their original bytes.

The updater accepts repeated `--restore-path OLD NEW` options and `--restore-root WORKSPACE` for separate destinations inside one workspace. Existing single-destination restores continue to work. A mapped path must remain inside the declared workspace after symlink resolution and match the referenced checksum. Overlapping origins, traversal and unmapped external paths fail. The default command loads the restricted workspace map, including the installed bwp-update-crashes entry point. Explicit recovery roots take precedence over local defaults.

The isolated drill copies the active workspace into a fresh directory, blocks reads from original working directories, then exercises offline update, an unchanged repeat, rollback and reapply. It compares all 1,139 incident records. Producer fingerprints can create a new private release after code relocation, while the source records, reviewed links and annual outputs retain their meanings.

After acceptance the superseded working tree is retained as private/archive/layout-migration-2026-11-08/original-crashes. Its mutable pointer and manifests remain available for diagnosis. Keep earlier recovery archives and current path mappings together. The recovery test used this machine. Other-laptop access remains unverified.

## Rollback

Stop new writes by acquiring the active updater lock. Restore the pre-migration code commit recorded in the restricted baseline into a separate checkout, restore the original workspace from the retained archive, and verify every inventory entry before selecting its original pointer. Preserve any post-migration receipts and releases first. Follow the original recovery runbook and check withdrawals before restoring any public deployment. A code rollback alone cannot relocate private data.

## Recorded checks

The final suite passed all 156 tests with no skips. Two full catalog rebuilds matched all 80 baseline public files. Both compatibility commands passed from another working directory. The historical map package reproduced its original manifest and layer hashes. Seven focused workspace tests cover multiple destinations, legacy restore behavior, checksums, ambiguous and unmapped paths, traversal, symlink escapes, relative definition roots and installed-command defaults. The isolated and active update/repeat/rollback/reapply checks preserved all 1,139 incident records. All 1,036 original private files were verified before archival.
