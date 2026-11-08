# Data Hub agent instructions

Read the [data ownership contract](docs/ownership.md) before changing a transformation, derived measure, query shortcut or release. Follow the applicable dataset contract and preserve published pins.

## Keep the system design current

Read [the system design](docs/system-design.md) before changing the hub. For every improvement, enhancement or refactor, review the system design and update it and the affected dataset contracts or operations guides in the same change to reflect the resulting design. Cover changes to data flow, ownership, public/private boundaries, interfaces, dependencies, release and withdrawal behavior, scheduling, consumer adoption, deployment or recovery. Keep implementation evidence and verification limits current. Describe proposed future work as proposals until implemented and verified. Keep raw private records and credentials out of documentation.

## Keep the tree understandable

Use the [folder guide](README.md) and [scripts index](scripts/README.md) before adding files. Put documentation in docs, commands in scripts, reusable processing code in pipelines, definitions in data-definitions, approved immutable packages in releases, and tests in tests. Keep private inputs and generated build output in their ignored directories. Use descriptive lowercase hyphenated documentation names, snake_case Python names and YYYY-MM-DD-description names for private runs. Update the applicable folder guide and command index when adding or moving an entry point. Preserve frozen evidence and published bytes. Run both test groups for changes affecting shared paths.
