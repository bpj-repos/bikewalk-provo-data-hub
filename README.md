# BikeWalk Provo Data Hub

The private repository produces independently deployable, read-only data releases. Projects will present the public catalog. Application maintainers pin a manifest URL and SHA-256 and verify resource hashes before adopting a release. The current public demonstration contains entirely invented data.

[Public synthetic catalog](https://bikewalk-provo-data-hub.vercel.app/catalog.json) · [Counts release contract](contract.md) · [Hosting evidence](hosting.md) · [Wave 1 inventory](wave-1.md)

## Build and verify

Run with Python 3 and its standard library from the repository root:

    python3 -m unittest
    python3 release.py build public
    python3 release.py validate public
    python3 verify_host.py

Build requires a new output directory. Add --first to reconstruct the first deployment. The tracked pin ledger fixes the checksum of each public manifest. Treat released entries as append-only, and verify predecessor pins against the public catalog before approving a change. Each manifest binds its resources by hash.

To deploy, create a fresh empty staging directory outside the repository, build its public subdirectory, and copy vercel.json beside public. Validate the exact public directory. From that staging directory link to bikewalk-provo-data-hub under brycepjs-projects and run vercel deploy --prod. The upload contains only approved output and static-host configuration. Build and verify again from a clean clone for recovery. Keep original deliveries in private storage outside this repository.

The collection lead signs off the protocol and historical mappings. The hub maintainer prepares and validates candidates. The BikeWalk release owner approves redistribution and promotion. Each app maintainer tests and adopts a pin independently. Source corrections enter through the internal release process. The public host exposes static files.

## Annual counts 1.0.0

[Public release manifest](https://bikewalk-provo-data-hub.vercel.app/datasets/annual-transportation-counts/1.0.0/datapackage.json) · [Release decision](counts/REVIEW.md)

With the canonical BikeWalk repository available locally, set BWP_SOURCE_REPO to its absolute path. Run:

    python3 -m unittest
    python3 counts.py "$BWP_SOURCE_REPO" /path/to/new/private-build

Export BWP_SOURCE_REPO before running the tests. counts.py verifies pinned input blobs, CSV/JSON parity, schema coverage and the approved real release hash. It produces an exact public tree containing both demonstrations and the real release. review-issues.json belongs in private storage. The synthetic-only commands above reproduce the prior host for rollback; verify_host.py is specific to that historical production state. For the current production deployment compare all anonymous downloads to the generated public tree using check_public.py.
