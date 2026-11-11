# Bicycle stress maintenance

The local backup directory private/backups/github/source-receipts-safe-routes-stress-20261109/ retains the local network and upstream inputs. Restore into a new private directory. Verify `stress-network.tar.gz` SHA-256 `a167a84a9893366a92c41d06bc988ec50b9c5ed5a92455ee38aee7eea9b58333` and `stress-model-inputs.tar.gz` SHA-256 `21e85e135f4b794cabddee098cdb308b4706b73d8e8d2cd7cf14d94f15142d89`. Extract the network archive. Run `python -m scripts.route_stress releases/datasets/safe-routes-to-school/1.1.0 WAYS NODES UTAH NEW_STRESS`, then `python -m scripts.package_stress releases/datasets/safe-routes-to-school/1.1.0 NEW_STRESS NEW_PACKAGE --version 1.2.0`. Set WAYS, NODES and UTAH to the three extracted paths listed in stress-sources.json. Match with Shapely 2.1.2 and pyproj 3.7.2. Compare every public byte with the frozen release. Future monthly reviews use that month's candidate base instead. Check the dated network sources for updates, compare coverage and changes, then explicitly promote a new version. A failed check leaves the last approved pin available.

To refresh the local network, use the analyzer and database image digests in stress-sources.json. Use a new task-private database (4 GiB scratch space or larger) on an isolated Docker network. Run the analyzer's `bna configure custom 2 2048 postgres` against it, supplying DATABASE_URL to both commands. In the analyzer container, mount only the PBF and boundary under /tmp/inputs read-only, create /tmp/outputs writable by the container user, and run the hub script model_bicycle_stress.py with Python. Allow space for the temporary OSM XML. Export and retain both resulting network GeoJSON files before retiring the database. The OSM input clip is the municipal extent buffered 3,000 m; the model uses the actual municipal boundary and 2,680 m buffer, UTM 12N, and 25 mph residential defaults. Generated network IDs belong to that snapshot. Pin refreshed bytes in a new source receipt after review. Recovery does not depend on random database identifiers being stable across fresh imports.

In the November 9 review all 35,211 line features had endpoint coordinates consistent with their from/to IDs. All three higher-stress through crossings also appeared as high-stress approaches in the separate published Provo 26.04 analysis: 300 North at 900 East for Provo Peaks, and the paths crossing 800 North and 100 North for Timpanogos. Opposite movements on the same nodes had different scores. Edgemont had 27 modeled lower-stress crossings and four unassessed plan records. Utah and local BNA disagreed on about 2.41 of the 3.92 km compared at Edgemont. Timpanogos had 8.28 km of unassessed route geometry. These are checks on model interpretation and alignment, not field verification.

For withdrawal or rollback use the hub release ledger and Streets Watch’s consumer workflow. The public map now lives at https://www.provostreets.watch/safe-routes; its `docs/SAFE_ROUTES.md` covers five-layer adoption and backup recovery. The compatibility API keeps its independent historical pin.

## Release evidence, November 9, 2026

Hub 1.2.0 manifest SHA-256 `f651204769e1467f01149996212af4f1a368165fa74ca13d34bf48ede083d83c` at producer commit `34d6821bec383fb6ceafb94077f5d99b980af237`. Two builds reproduced identical package bytes. The 18 hub and 140 crash tests passed. All 94 staging and public catalog files were verified for bytes, MIME type and CORS. Hub deployment `dpl_4Vyrr44cJhYJC2zim67zWYtcqKf8` was promoted to the stable data-hub alias.

Projects adopted that exact pin in commit `32e19a072dd8b4d4cddeb163148650d41026d4c5`, deployment `dpl_9UDqLjYNRKoyMB2rdTBgnb2hHL6k`. Public release identity, all five geometry hashes, dataset listing, switch default and tapping the Timpanogos 800 North crossing were verified. The prior Projects commit was `a43ee341bc471a090bcb77f2f79cb991e193d9a1` with Safe Routes 1.1.0. Provider refresh and field verification are independent of release checks.

## Monthly refresh and reviewed publication

The local LaunchAgent org.bikewalkprovo.safe-routes runs at 7:41 a.m. Mountain on the first of each month. macOS coalesces missed calendar events after waking while the user agent is loaded. Verify each month's outcome after a shutdown or logout. On this Mac the Python 3.12 environment is private/hub-env. Install the pinned crash package there, which supplies Shapely 2.1.2 and pyproj 3.7.2. Docker and curl must be available on PATH and Docker must be running. The pinned July archive lives at private/backups/github/source-receipts-safe-routes-20261107/safe-routes-july.tar.gz and is checked before extraction.

Run manually from the hub:

    private/hub-env/bin/python -m scripts.monthly_route_review

The command serializes runs with a filesystem lock, receives current providers, runs the model, prepares a candidate and independently rebuilds every package byte. It writes a dated directory under private/candidates with run.log and, on success, review.md. Failed runs retain their logs. Outer scheduling failures appear in private/route-publication/monthly.stderr.log. Check both places after each attempt. The LaunchAgent's external guard requires a clean main checkout before executing repository code. Use a separate checkout to review untrusted contributor branches. Pending work in this shared checkout postpones the monthly attempt and requires a manual retry after it is clean.

Install the schedule and load it as the current macOS user:

    private/hub-env/bin/python -m scripts.monthly_route_review --install-launchagent
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.bikewalkprovo.safe-routes.plist
    launchctl print gui/$(id -u)/org.bikewalkprovo.safe-routes

Installation refuses to replace a different existing plist. To change it, review and unload the old job with launchctl bootout, preserve its plist privately, then install the reviewed replacement. The runner creates private candidates. Source/model failure leaves the latest approved release serving.

Review provider freshness, campus/roster changes, coverage, calibration strata, independent corridors, native disagreements, published comparisons and unrated leads. Neither comparison agreement nor a school designation establishes field safety. Research leads remain private. Each success summary prints a local candidate path and exact manifest SHA-256:

    python -m scripts.publish_route_update CANDIDATE_DIRECTORY MANIFEST_SHA256 --verify-only

For a contributor's approved candidate, create a release branch, then prepare the versioned package and ledger:

    python -m scripts.publish_route_update CANDIDATE_DIRECTORY MANIFEST_SHA256 --prepare-pr

Run both maintainer test groups, commit only the release and ledger, and open a PR for @brycepj. The owner may instead exercise direct-push rights when recording a reviewed package. The promotion command requires the approved package and ledger already on a clean, current main checkout:

    python -m scripts.publish_route_update CANDIDATE_DIRECTORY MANIFEST_SHA256

Each mode checks the exact pin, retained input hashes, predecessor and withdrawals and independently rebuilds the candidate. Preparation and promotion retain a deterministic checksummed source archive under private/backups/source-receipts-safe-routes-VERSION-PINPREFIX/. A repeated backup must match both its SHA256SUMS and candidate bytes. Retain the versioned public package separately so recovery can compare the rebuilt manifest. Verify-only performs no publication. Historical numeric run IDs work only for already downloaded private/route-publication/RUN_ID/candidate directories.

Promotion verifies complete catalog downloads on staging and the stable alias. Checkpoints stay under private/route-publication. A retry rechecks the reviewed pin and current main. Consumers adopt separately through Streets Watch's stage/review/apply PR workflow. Keep independent backups of the private originals and receipts in owner-approved storage. The local archives and recovery rehearsal protect against accidental updates, while recovery from loss of this disk still depends on an independent backup.

The refresh also writes a private comparison with the published Provo BNA download. It compares only compatible directions/geometry on the same OSM way and reports unmatched mileage/directions separately. Interpret differences with both input vintages in view. The continuity report counts all adjacent BNA/Utah switches and the smaller subset of qualifying through movements on the same Utah feature. An actual crossing, a turn or an unrated gap is not smoothed for visual continuity. Each fresh run includes its calibration strata in public sources.json and reports the private diagnostics with the candidate. None of those research leads is applied as a rating merely because the route is school-designated.
