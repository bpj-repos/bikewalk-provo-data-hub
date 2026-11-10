# Operations guides

| Task | Guide |
|---|---|
| Set up access, build, stage, promote or withdraw a release | [Maintainer guide](maintainer-guide.md) |
| Receive crash data, compare consumers or restore retained pins | [Crash updates and recovery](crash-updates-and-recovery.md) |
| Refresh citywide bicycle traffic stress and its dependencies | [Traffic stress](traffic-stress.md) |
| Find active data, private reviews or backups | [Private workspace](private-workspace.md) |
| Understand the filesystem migration and rollback | [Layout migration](layout-migration.md) |

Use [module commands](../../scripts/README.md) from the repository root. Local path overrides belong in config/paths.local.json, using [the example](../../config/paths.example.json). Crash tools need the editable pipeline environment. The [hub test group](../../tests/README.md) uses the Python standard library.
