# BikeWalk Provo Data Hub

The private Data Hub receives transportation data, maintains shared definitions and publishes reviewed, versioned files. Projects and Streets Watch independently adopt verified snapshots.

## Where do I find something?

| I want to… | Start here |
|---|---|
| Understand the system and its responsibilities | [System design](docs/system-design.md) and [ownership](docs/ownership.md) |
| Update data, publish a release or recover a workspace | [Operations guides](docs/operations/README.md) |
| Find a command and its inputs, effects and prerequisites | [Scripts index](scripts/README.md) |
| Understand a dataset's scope and limitations | [Dataset guides](docs/datasets/README.md) |
| Inspect mappings, protocols, source definitions or schemas | [Data definitions](data-definitions/README.md) |
| Find approved data and manifest pins | [Releases](releases/README.md) |
| Rebuild or review the pinned Safe Routes bicycle stress annotations | [Stress maintenance](docs/operations/bicycle-stress.md) |
| Build the citywide bicycle stress dataset | [Traffic stress maintenance](docs/operations/traffic-stress.md) |
| Prepare annual crash statistics for another Utah city | [City workbook workflow](docs/operations/crash-updates-and-recovery.md#prepare-another-utah-citys-annual-crash-series) |
| Develop the crash-processing library | [Crash pipeline](pipelines/crashes/README.md) |
| Find a past decision or migration record | [Documentation map](docs/README.md) |
| Work with received inputs and local candidates | [Private workspace guide](docs/operations/private-workspace.md) |

[Public catalog](https://bikewalk-provo-data-hub.vercel.app/catalog.json) · [Agent instructions](AGENTS.md)

## Build and check

From the repository root, with the full canonical BikeWalk Git history available locally

```sh
export BWP_SOURCE_REPO=/absolute/path/to/bikewalk-provo
python3 -B -m unittest discover -s tests/hub -t .
python3 -B -m scripts.build_catalog "$BWP_SOURCE_REPO" build/new-staging
```

Use a fresh output directory. Publication uploads only the generated `public/` directory and `vercel.json` after the [staging and promotion checks](docs/operations/maintainer-guide.md). Local `private/`, `build/` and configuration overrides are ignored by Git. Retain original inputs and recovery archives in authorized private storage.

Every available catalog release also provides a complete ZIP download: one folder containing its data and all manifest-listed supporting files. The catalog's `download` object provides the path, size and SHA-256; existing manifest and individual resource URLs remain unchanged.

`update_crashes.py` and `adopt_routes.py` preserve the entry points used by existing consumers. Maintained commands live in `scripts/`.

## Prepare annual active transportation crash counts for a Utah city

1. In the [Utah Crash Data Portal](https://utaps.shinyapps.io/DataPortalAWS/), select the city by its portal name and choose the date range and years. Leave the other filters unrestricted, including county, agency, vehicle type, severity and time of day. Apply the filters and choose **Downloads → Download Filtered Data**. Keep the original XLSX in restricted intake and record its SHA-256.
2. From the repository root, activate the crash pipeline’s Python environment. Set the city, workbook path, received checksum, last reviewed full year and a fresh output path under `private/`. For example, a workbook covering 2024–2025 for Salt Lake City can be processed with

   ```sh
   CITY='Salt Lake City'
   WORKBOOK='private/intake/crashes/salt-lake-city.xlsx'
   WORKBOOK_SHA256='replace-with-the-recorded-64-character-sha256'
   PYTHONPATH=.:pipelines/crashes/src python -m scripts.prepare_city_crashes \
     "$WORKBOOK" "$WORKBOOK_SHA256" private/candidates/2026-11-11-salt-lake-city-crashes \
     --city "$CITY" --complete-through 2025 --version 1.0.0
   ```

3. Review `annual.csv`, the field dictionary, the method and the manifest under the output directory. Each qualifying crash counts once in the total and once in each applicable mode. Selected years can have zero crashes. Partial years are flagged. Keep the workbook private and record the printed manifest pin for release review. [Publication and recovery instructions](docs/operations/crash-updates-and-recovery.md#prepare-another-utah-citys-annual-crash-series)

## Utah cities with crash data

<!-- city-crash-data:start -->
| City | Portal crashes | Portal years | Latest portal crash | UDOT crashes | UDOT years | Latest UDOT crash | Dataset |
|---|---:|---|---|---:|---|---|---|
| Salt Lake City | 3,961 | 2010–2026 | 2026-10-15 | 2,025 | 2018–2026 | 2026-11-07 | [Generated ZIP](releases/datasets/salt-lake-city-annual-at-crash-aggregates/1.0.0/salt-lake-city-annual-at-crash-aggregates-1.0.0.zip) |
| West Valley City | 1,611 | 2010–2026 | 2026-10-20 | 835 | 2018–2026 | 2026-10-28 | [Generated ZIP](releases/datasets/west-valley-city-annual-at-crash-aggregates/1.0.0/west-valley-city-annual-at-crash-aggregates-1.0.0.zip) |
| Ogden | 1,336 | 2010–2026 | 2026-09-30 | 743 | 2018–2026 | 2026-10-25 | [Generated ZIP](releases/datasets/ogden-annual-at-crash-aggregates/1.0.0/ogden-annual-at-crash-aggregates-1.0.0.zip) |
| Provo | 1,332 | 2010–2026 | 2026-09-30 | 693 | 2018–2026 | 2026-10-27 | [Generated ZIP](releases/datasets/provo-annual-at-crash-aggregates/1.0.0/provo-annual-at-crash-aggregates-1.0.0.zip) |
| St. George | 872 | 2010–2026 | 2026-10-16 | 595 | 2018–2026 | 2026-11-07 | [Generated ZIP](releases/datasets/st-george-annual-at-crash-aggregates/1.0.0/st-george-annual-at-crash-aggregates-1.0.0.zip) |
| Orem | 843 | 2010–2026 | 2026-10-26 | 477 | 2018–2026 | 2026-11-02 | [Generated ZIP](releases/datasets/orem-annual-at-crash-aggregates/1.0.0/orem-annual-at-crash-aggregates-1.0.0.zip) |
| Sandy | 766 | 2010–2026 | 2026-10-06 | 407 | 2018–2026 | 2026-11-03 | [Generated ZIP](releases/datasets/sandy-annual-at-crash-aggregates/1.0.0/sandy-annual-at-crash-aggregates-1.0.0.zip) |
| West Jordan | 700 | 2010–2026 | 2026-10-09 | 385 | 2018–2026 | 2026-10-30 | [Generated ZIP](releases/datasets/west-jordan-annual-at-crash-aggregates/1.0.0/west-jordan-annual-at-crash-aggregates-1.0.0.zip) |
| Millcreek | 680 | 2010–2026 | 2026-10-16 | 350 | 2018–2026 | 2026-10-30 | [Generated ZIP](releases/datasets/millcreek-annual-at-crash-aggregates/1.0.0/millcreek-annual-at-crash-aggregates-1.0.0.zip) |
| Logan | 679 | 2010–2026 | 2026-10-03 | 380 | 2018–2026 | 2026-11-06 | [Generated ZIP](releases/datasets/logan-annual-at-crash-aggregates/1.0.0/logan-annual-at-crash-aggregates-1.0.0.zip) |
| Layton | 649 | 2010–2026 | 2026-10-04 | 381 | 2018–2026 | 2026-10-26 | [Generated ZIP](releases/datasets/layton-annual-at-crash-aggregates/1.0.0/layton-annual-at-crash-aggregates-1.0.0.zip) |
| Murray | 634 | 2010–2026 | 2026-09-23 | 286 | 2018–2026 | 2026-11-07 | [Generated ZIP](releases/datasets/murray-annual-at-crash-aggregates/1.0.0/murray-annual-at-crash-aggregates-1.0.0.zip) |
| Taylorsville | 625 | 2010–2026 | 2026-10-16 | 283 | 2018–2026 | 2026-10-16 | [Generated ZIP](releases/datasets/taylorsville-annual-at-crash-aggregates/1.0.0/taylorsville-annual-at-crash-aggregates-1.0.0.zip) |
| South Salt Lake | 588 | 2010–2026 | 2026-09-28 | 303 | 2018–2026 | 2026-11-06 | [Generated ZIP](releases/datasets/south-salt-lake-annual-at-crash-aggregates/1.0.0/south-salt-lake-annual-at-crash-aggregates-1.0.0.zip) |
| Midvale | 476 | 2010–2026 | 2026-09-24 | 259 | 2018–2026 | 2026-11-05 | [Generated ZIP](releases/datasets/midvale-annual-at-crash-aggregates/1.0.0/midvale-annual-at-crash-aggregates-1.0.0.zip) |
| South Jordan | 381 | 2010–2026 | 2026-10-06 | 227 | 2018–2026 | 2026-10-07 | [Generated ZIP](releases/datasets/south-jordan-annual-at-crash-aggregates/1.0.0/south-jordan-annual-at-crash-aggregates-1.0.0.zip) |
| Clearfield | 365 | 2010–2026 | 2026-10-06 | 198 | 2018–2026 | 2026-11-05 | [Generated ZIP](releases/datasets/clearfield-annual-at-crash-aggregates/1.0.0/clearfield-annual-at-crash-aggregates-1.0.0.zip) |
| Kearns | 323 | 2010–2026 | 2026-09-29 | 160 | 2018–2026 | 2026-10-31 | [Generated ZIP](releases/datasets/kearns-annual-at-crash-aggregates/1.0.0/kearns-annual-at-crash-aggregates-1.0.0.zip) |
| Bountiful | 317 | 2010–2026 | 2026-09-14 | 156 | 2018–2026 | 2026-10-22 | [Generated ZIP](releases/datasets/bountiful-annual-at-crash-aggregates/1.0.0/bountiful-annual-at-crash-aggregates-1.0.0.zip) |
| Lehi | 311 | 2010–2026 | 2026-10-15 | 229 | 2018–2026 | 2026-10-28 | [Generated ZIP](releases/datasets/lehi-annual-at-crash-aggregates/1.0.0/lehi-annual-at-crash-aggregates-1.0.0.zip) |
| Springville | 246 | 2010–2026 | 2026-07-07 | 135 | 2018–2026 | 2026-10-17 | [Generated ZIP](releases/datasets/springville-annual-at-crash-aggregates/1.0.0/springville-annual-at-crash-aggregates-1.0.0.zip) |
| Spanish Fork | 231 | 2010–2026 | 2026-09-22 | 139 | 2018–2026 | 2026-11-06 | [Generated ZIP](releases/datasets/spanish-fork-annual-at-crash-aggregates/1.0.0/spanish-fork-annual-at-crash-aggregates-1.0.0.zip) |
<!-- city-crash-data:end -->

[Run the workflow, contribute a dataset, and check methods](docs/operations/city-crash-data.md).
