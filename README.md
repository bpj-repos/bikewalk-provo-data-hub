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

### Which Utah cities had the most reported active transportation crashes?

These ten cities ranked highest in both sources in **calendar year 2024**. Counts are distinct reported crashes involving at least one motor vehicle. Each source counts a crash involving multiple modes once. The sources overlap, so adding their counts would double-count crashes.

| Statewide rank | City | Utah Crash Data Portal | UDOT Crash Locations |
|---:|---|---:|---:|
| 1 | Salt Lake City | 253 | 252 |
| 2 | Provo | 101 | 102 |
| 3 | Ogden | 98 | 98 |
| 4 | West Valley City | 93 | 93 |
| 5 | St. George | 83 | 83 |
| 6 | Logan | 58 | 58 |
| 7 | Murray | 47 | 47 |
| 8 | Sandy | 46 | 46 |
| 9 (tie) | Layton | 43 | 43 |
| 9 (tie) | Millcreek | 43 | 43 |

The portal uses the state-assigned city. The Hub selects crashes involving a cyclist, pedestrian or other nonmotorist conveyance from person types, falling back to cyclist and pedestrian involvement flags. In 2024, 1,619 crashes qualified statewide, including 40 recorded outside city limits. [Utah Crash Data Portal](https://utaps.shinyapps.io/DataPortalAWS/)

UDOT uses bicycle and pedestrian involvement flags. We assigned crash points to the municipal boundaries available on November 11, 2026. Of 1,617 qualifying 2024 crashes, 37 could not be assigned to exactly one municipality. The latest qualifying crash returned by the 2025 UDOT layer was August 4, so the side-by-side ranking uses 2024. [UDOT Crash Locations](https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/Crash_Locations/MapServer) · [Utah municipal boundaries](https://gis.utah.gov/products/sgid/boundaries/municipal/)

For the **two full years 2024–2025**, the portal recorded 3,503 qualifying crashes statewide. Its top ten cities were Salt Lake City (522), Ogden (208), West Valley City (201), Provo and St. George (182 each), Orem (119), Logan (113), Layton (103), Sandy (92) and West Jordan (89). Both rankings were calculated November 11, 2026.
