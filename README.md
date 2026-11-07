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
