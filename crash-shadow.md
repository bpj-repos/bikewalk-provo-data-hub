# Crash updater transfer and private annual candidate

November 7, 2026. The private hub hosts the updater, matching and enrichment policy, dependency pins, reference captures and crash regression tests under `tools/crash_pipeline`. The source transfer came from BikeWalk commit `dcba0a96ff265a51a5d21b5797a94205c31b8541`. The hub producer used for the comparison is `99addc7`. The existing canonical producer still owns the operational pointer during this parallel-run phase.

## Run the producer

Use a dedicated Python 3.11+ environment with the pinned dependencies. From the hub root, install with `python -m pip install -e ./tools/crash_pipeline` so the package can locate its reviewed catalogs and references in the checkout. Alternatively set `PYTHONPATH=tools/crash_pipeline/src` for a Python interpreter with the matching dependencies. The hub's ordinary static build is independent of this package.

Use `python -m danger_zones.update_incidents --help` for receipt, offline and rollback arguments. For an isolated restored tree use `--restore-path ORIGINAL_ROOT RESTORED_ROOT` in each command. The restored tree needs the retained data and active pointer described in [the recovery drill](crash-recovery.md). New police or portal deliveries enter via their respective workbook arguments. Keep original deliveries, managed bundles and review records in authorized private storage.

## Side-by-side result

Run `python crash_restore.py BASELINE_CHECKOUT RETAINED_REPO --producer-src SRC --exercise-writer` twice with the SRC of each producer. BASELINE_CHECKOUT is at the pinned Wave 6 reference commit. Each invocation restores its own input tree. Compare the two printed shadow results by records, reviewed links, annual totals and CSV hash. Producer fingerprints and temporary private release IDs can differ.

Using the same four restored managed releases, each producer ran its actual offline update CLI, a no-change repeat and two rollbacks. Both returned the same 1,139 incident groups, 1,755 original observations and 50 reviewed links. The full incident-record hash was `e1174782a5329aa1feb66eb9a931973ab5b6a2794df43fd9625bb8341b420033`. The reviewed-link file hash was `a10b89a854a3ebe7cc8cb04a992544ddd486b2aab34747b3c4c30f557118e144`.

Both reproduced the published AT annual CSV SHA-256 `7daf9244f56900f05e9691914f3fc1be633fbe1adf0770fd84b1477a2105598a`, including each mode column. Totals for 2018–2025 were 77, 70, 46, 72, 79, 77, 101 and 81. The partial 2026 total was 77. The existing producer created the isolated release `incidents-b4b7b930184d52b5c01e` and the hub producer created `incidents-7910764a354705a56d83`. The original private pointer and public catalog stayed on their previous pins.

## Prepare and review the motor vehicle series

From the hub, using the documented environment:

    python -m danger_zones.motor_vehicle_candidate PRIVATE_MANIFEST MANIFEST_SHA256 RECEIPTS NEW_PRIVATE_OUTPUT --complete-through 2025

For this candidate use the manifest at `incident-updates/releases/incidents-e5a4665997a4cac4f5be/manifest.json`, checksum `c614ca99200bc25ce4d77491061e0d23529f59be24e42bcbff0f16759f4ca979`, and the `incident-inputs` directory in the retained private store. The command reads the original city workbooks, verifies their hashes, parses them with the shared portal adapter and overlays deliveries by state crash ID in intake order. Two city receipts contained 13,631 and 13,635 records. County lookup deliveries are excluded. The latest city event in this candidate is September 30, 2026.

The original, pre-review output is under `private/crashes/motor-vehicle-candidate-20261107`. Two builds reproduced the same CSV, dictionary, methodology, manifest and private review file. Manifest SHA-256: `c05fa83f8afa979ca1b5c0026ef35c8d488060d4966adc7cf7b2a10fbe48a6c8`. The review file contains state IDs and belongs only in restricted storage. This candidate has no public version, approved reuse terms or download pin.

| Year | Included motor vehicle crashes | Reported nonmotorist | Unresolved |
|---|---:|---:|---:|
| 2018 | 1,740 | 77 | 134 |
| 2019 | 1,652 | 70 | 108 |
| 2020 | 1,066 | 46 | 12 |
| 2021 | 1,321 | 72 | 56 |
| 2022 | 1,313 | 79 | 112 |
| 2023 | 1,396 | 77 | 93 |
| 2024 | 1,440 | 101 | 107 |
| 2025 | 1,366 | 81 | 91 |
| 2026 (partial) | 884 | 77 | 64 |

Of 13,635 distinct Provo records, 12,178 qualified, 680 had a recorded nonmotorist, and 777 were unresolved in the original candidate. That candidate required an occupant linked to every reported vehicle. Of the 747 cases with incomplete participant-to-vehicle links, 667 have complete links for the listed people and only parked units among the vehicles lacking a listed occupant. A parked vehicle can be empty. The parked-vehicle review below resolves how to treat that pattern. The remaining unresolved reasons are 29 missing participant rosters and one inconsistent or missing vehicle count. These counts describe the retained receipts and the proposed rule.

## Current private candidate

The rebuilt series is in `private/crashes/motor-vehicle-candidate-20261107-parked`, with manifest SHA-256 `e30a0f432e5491a7ad911b4354c29aae42934834fbf9715876b2365e74b1148e`. It uses the same city receipts. It includes 663 previously held crashes and holds 13 previously included ones. Of 13,635 distinct city crashes, 12,828 qualify, 680 are excluded for reported nonmotorist involvement, and 127 are held. The [parked-vehicle review](parked-vehicle-review.md) verifies every annual total and every held case ID and year. The original candidate remains available for comparison. Private review files remain restricted. Approved annual aggregates are published separately below.

## Published annual releases, November 7, 2026

The release owner approved both 1.0.0 packages, 2018–2025 calendar-year coverage,
provisional 2026 through the latest event of September 30, and the attribution
terms in each manifest. Only annual statistics, dictionaries, methods and
manifests are public. The two series have independent pins in releases.json.

| Dataset | Manifest SHA-256 |
|---|---|
| annual-at-crash-aggregates | af08b4fb7b7a9264a160d555341bab8fc791d26513de8c9933eb75574f8e1d19 |
| annual-motor-vehicle-crashes-without-nonmotorists | 909f7b37b708b434a7e301bd07d223769895c8c2b5ece46d52316ba98a8ab35e |

From the hub root, use the crash Python environment with
`PYTHONPATH=.:tools/crash_pipeline/src python -B crash_receipt_drill.py`.
The drill restored the first managed collection, supplied the second retained city
workbook to the offline updater, repeated the receipt and rolled back. The only
annual change was in 2026, from 935 to 939 qualifying motor vehicle crashes.
All nine AT totals and mode columns, all review counts and all prior years agreed.
On the published inputs the 680 distinct AT IDs and years matched the 680
exclusions, and all 127 held crashes were outside both populations.

Rebuild the public packages in a new private directory with
`PYTHONPATH=tools/crash_pipeline/src python -B crash_packages.py MANIFEST MANIFEST_SHA MOTOR_CANDIDATE MOTOR_SHA private/crashes/NEW_DIRECTORY`.
The managed pin and motor candidate pin are documented above. The two versions can
advance separately. Two builds reproduced the eight approved files. The AT CSV
also matched the existing Projects download byte for byte.

Deployment `dpl_B1sh32zRnndXSF9U1soJeGErNPAK` passed the staged and anonymous
production checks for all 67 files, including previous pins. Its rollback target
is `dpl_2Z29JRY1sLYVBkXpSnRfw62gyFhg`. Team usage for November 1–7 showed
$5.1267 effective and $0 billed immediately before deployment.

## Remaining work

1. Review the remaining unresolved cases and year coverage with the data steward. Exercise future city deliveries with the same year-by-year comparison.
2. Adopt the published independent aggregate pins, add both downloads to the Projects Data Hub page and migrate the existing crash trends report to the AT pin. Verify chart, CSV and rollback parity. Projects can adopt each version on its own schedule.
3. Establish an independently recoverable backup for the restricted sources and test it with a second maintainer's access. Move the operational writer after verifying private readers for fatalities, incident maps and the Streets Watch crash-detail export. Retire the legacy writer once those callers are accounted for.
4. For subsequent expansion, evaluate minimized concern crash details and the fatalities map as separate products, each with its own disclosure and reuse review. Continue annual counts updates on receipt and monthly Safe Routes review while the crash releases progress.
