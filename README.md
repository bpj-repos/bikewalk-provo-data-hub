# BikeWalk Provo Data Hub

The private repository produces independently deployable, read-only data releases. Projects presents the public catalog. Application maintainers pin a manifest URL and SHA-256 and verify resource hashes before adopting a release. The public catalog includes annual counts, Provo Safe Routes to School, both annual crash series, Provo fatal active transportation crashes, and the reviewed historical incident-map extract.

[Public catalog](https://bikewalk-provo-data-hub.vercel.app/catalog.json) · [Counts release contract](contract.md) · [Data ownership](ownership.md) · [Hosting evidence](hosting.md) · [Wave 1 inventory](wave-1.md)

Read [System design](SYSTEM-DESIGN.md) for the as-built data flow, implementation map, release and consumer contracts, recovery limits, and prioritized future improvements. Agents maintain it with design changes under [AGENTS.md](AGENTS.md).

See [Completion and maintenance status](completion.md) and [Incident map releases](incident-map.md).

See [Fatalities release and scope](fatalities-release.md) for the geographic dataset and Projects adoption.

Use [Private crash updates and recovery](crash-operations.md) for the operational writer, consumer checks and recovery commands. The [migration record](crash-shadow.md) covers the two published annual crash series.

See [Maintainer operations](OPERATIONS.md) for the production build and recovery drill, and [Safe Routes coverage](coverage.md) for the verified campus scope.

## Historical synthetic proof

Run with Python 3 and its standard library from the repository root:

    python3 -m unittest
    python3 release.py build public
    python3 release.py validate public
    python3 verify_host.py

Build requires a new output directory. Add --first to reconstruct the first deployment. The tracked pin ledger fixes the checksum of each public manifest. Treat released entries as append-only, and verify predecessor pins against the public catalog before approving a change. Each manifest binds its resources by hash.

For the complete current catalog, use build_hub.py as described in [Maintainer operations](OPERATIONS.md). Stage only its public directory and vercel.json, deploy with --prod --skip-domain, verify the exact staged tree, then promote that deployment and check the stable alias. Build and verify again from a clean clone for recovery. Keep original deliveries in authorized private storage outside the tracked tree.

The collection lead signs off the protocol and historical mappings. The hub maintainer prepares and validates candidates. The BikeWalk release owner approves redistribution and promotion. Each app maintainer tests and adopts a pin independently. Source corrections enter through the internal release process. The public host exposes static files.

## Annual counts 1.0.1

[Public release manifest](https://bikewalk-provo-data-hub.vercel.app/datasets/annual-transportation-counts/1.0.1/datapackage.json) · [Release decision](counts/REVIEW.md)

With the canonical BikeWalk repository available locally, set BWP_SOURCE_REPO to its absolute path. Run:

    python3 -m unittest
    python3 counts.py "$BWP_SOURCE_REPO" /path/to/new/private-build

Export BWP_SOURCE_REPO before running the tests. counts.py verifies pinned input blobs, CSV/JSON parity, schema coverage and the approved real release hash. It produces an exact public tree containing both demonstrations and both real releases. Version 1.0.1 corrects the 2026 combined scooter measure using its two session counts; 1.0.0 retains the original field. review-issues.json belongs in private storage. The synthetic-only commands above reproduce the prior host for rollback; verify_host.py is specific to that historical production state. For the current production deployment compare all anonymous downloads to the generated public tree using check_public.py.
