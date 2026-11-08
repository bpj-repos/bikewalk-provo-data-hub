# Data definitions

- `annual-transportation-counts/` holds the contract, protocol, field mapping, source ledger and reviewed historical exceptions.
- `safe-routes-to-school/` holds version-specific coverage text and the reviewed campus baseline.
- `crashes/` holds the active source registry, field/derivation/matching catalogs, JSON schemas and retained reference documents.
- `historical-incident-map/historical-v1/` freezes the historical map definitions, source-free receipt and reference captures.

Reference captures retain original relative names so existing hashes and locators remain reproducible. A captured src/danger_zones/police.py under historical references is evidence. Runnable processing code lives in [pipelines](../pipelines/README.md).

Published package definitions are also retained verbatim in [releases](../releases/README.md). Edits to a shared meaning follow the [ownership contract](../docs/ownership.md) and release review.
