# Utah city crash data

For a local point map, start with the [lightweight install and offline mapping example](city-crash-mapping.md). Annual packages in the [annual crash guide](../datasets/annual-at-crash-aggregates.md) contain statistics. The city point exporter produces GeoJSON for GIS and web maps. City commands support --json for coding agents.

## Set up a checkout

Fork the repository on GitHub, clone your fork, and create a contribution branch with `git switch -c city-annual-crashes`. Use Python 3.11 or newer, Git and a full clone of this repository. The city tools run independently of the BikeWalk website checkout.

```sh
python3 -m venv pipelines/crashes/.venv
. pipelines/crashes/.venv/bin/activate
python -m pip install -e pipelines/crashes
export PYTHONPATH=.:pipelines/crashes/src
```

## Prepare and contribute one city

Download the city's XLSX from the Utah Crash Data Portal as described in the [annual crash guide](../datasets/annual-at-crash-aggregates.md#prepare-annual-active-transportation-crash-counts-for-a-utah-city). Select every available year and the full date range for an all-history package. Keep all other filters unrestricted. Save the original file under ignored private intake and record its SHA-256 with `shasum -a 256 FILE` or PowerShell `Get-FileHash FILE -Algorithm SHA256`.

From the repository root, set the workbook, received SHA-256, exact city name, last reviewed full year and new private output path.

```sh
python -m scripts.prepare_city_crashes private/intake/city.xlsx WORKBOOK_SHA256 \
  private/candidates/city-1.1.0 --city 'Salt Lake City' --complete-through 2025
```

City builds default to version 1.1.0. If that version is already registered, use a new version with `--version`. When selected years include years before 2018, the builder also writes `annual-from-2018.csv` using the same rows and columns as the corresponding slice of Provo’s annual product. Explicit 1.0.0 builds reproduce the earlier single-CSV format.

The printed dataset name identifies the package subdirectory. Review its annual CSV, dictionary, method and manifest. Rebuild in a second private directory and compare the manifest SHA-256. Once reviewed, register that exact pin. For the example above:

```sh
python -m scripts.register_city_crashes \
  private/candidates/city-1.1.0/salt-lake-city-annual-at-crash-aggregates/1.1.0 MANIFEST_SHA256
```

Registration copies only the annual public package into `releases/datasets/CITY-annual-at-crash-aggregates/VERSION/`, creates the complete ZIP through the catalog builder's maintained ZIP routine, appends the immutable manifest pin to `releases/release-ledger.json`, and updates `data-definitions/crashes/city-coverage.json` and the annual crash guide table. Download links appear only after the complete version is selected for public publication. Repeating the same registration verifies the existing pin. Updates use a fresh version. The source workbook and receipts stay in private storage. Registration and table updates share a local directory lock and replace each metadata file atomically. After a terminated process, confirm no city update is running before removing the empty `private/city-release.lock` directory and retrying the same pin.

```sh
python -B -m unittest discover -s tests/hub -t .
python -B -m unittest discover -s tests/crashes -t .
git add releases/datasets/salt-lake-city-annual-at-crash-aggregates \
  releases/release-ledger.json data-definitions/crashes/city-coverage.json docs/datasets/annual-at-crash-aggregates.md
git commit -m "Add Salt Lake City annual crash dataset"
```

Push your contribution branch with `git push -u origin HEAD` and submit a pull request under the repository's current contribution rules. The relative ZIP link works directly from the repository after the files are committed. Static Hub publication uses the usual catalog build and [hosting verification](maintainer-guide.md). Consumer adoption follows independently.

## Refresh city counts automatically

The portal capture uses Node.js and Playwright. Install its browser in your local environment. The following setup keeps downloaded tooling inside ignored private storage.

```sh
npm install --prefix private/browser-tools playwright@1.61.1
export NODE_PATH="$PWD/private/browser-tools/node_modules"
node private/browser-tools/node_modules/playwright/cli.js install chromium
node scripts/capture_city_crash_portal.cjs private/reviews/NEW_PORTAL_RUN \
  'Salt Lake City' Provo Ogden
python -m scripts.capture_city_crash_udot private/reviews/NEW_UDOT_RUN
python -m scripts.city_crash_history \
  private/reviews/NEW_PORTAL_RUN private/reviews/NEW_UDOT_RUN \
  'Salt Lake City' Provo Ogden --write
```

Use new output directories. Capture commands preserve completed files and fail on incomplete responses. For a failed portal run, capture the unfinished cities into a fresh directory and combine the verified workbook/receipt pairs in private review storage before reporting. Reporting verifies checksums, applied city/date/year filters, workbook row counts, UDOT year continuity and feature membership. It rejects conflicting repeated state IDs and counts identical duplicates once. It updates only the requested cities and retains existing dataset links when the package coverage agrees. Register a revised package first when its public annual coverage changes.

The UDOT capture discovers all annual layers. It uses the maintained MapServer for years available there and the newer hosted UDOT FeatureServer for overlapping years and newer records. It verifies every requested feature ID and retains the municipal polygons and a checksummed receipt. Portal exports include the current default start/end dates and every year between them. The report's year range describes the selected source coverage. Latest dates describe qualifying events within each city.

## Counts and coverage

The portal annual population is the [existing shared nonmotorist rule](../history/annual-crash-migration.md). A crash needs at least one reported motor vehicle and person type 4, 3 or 5 for a cyclist, pedestrian or other conveyance. Cyclist and pedestrian involvement flags supply mode evidence when none of these person types are present. A crash involving multiple modes counts once in the total and in each applicable mode. State-assigned city names define portal membership.

UDOT screening selects pedestrian or bicyclist involvement flags, requires at least one motor vehicle, and intersects points with the retained Utah municipal boundaries. A point matching exactly one municipality contributes there. Points with missing or ambiguous municipal membership stay outside the city totals. The two sources overlap and use different coverage and membership rules. Their counts are separate series.

The annual crash guide's latest-date columns use event dates in America/Denver. Neither source exposes a report-submission date through these captures. A latest event is evidence of observed coverage, with the current year provisional. Captures do not guarantee that earlier years are complete.

November 11, 2026 verification captured the first 12 listed cities and the next ten remaining municipalities ranked by all-history UDOT counts. Portal years span 2010–2026. UDOT years span 2018–2026, using the archived 2018 layer and hosted 2019–2026 layers. Private receipts and verification reports are retained under the Hub's November 11 city-history reviews.

[Utah Crash Data Portal](https://utaps.shinyapps.io/DataPortalAWS/) · [UDOT archived layers](https://maps.udot.utah.gov/central/rest/services/TrafficAndSafety/Crash_Locations/MapServer) · [UDOT hosted layers](https://services.arcgis.com/pA2nEVnB6tquxgOW/ArcGIS/rest/services/Utah_Crash_Locations/FeatureServer) · [Utah municipal boundaries](https://gis.utah.gov/products/sgid/boundaries/municipal/)

City ZIP registration updates the repository table. To host a city version publicly, add its approved dataset ID and version to `publicCityReleases` in the release ledger, assemble the catalog and verify the staged and promoted downloads. Projects links the four published 1.1.0 city ZIPs in a collapsed section of its [Data Hub catalog](https://projects.bikewalkprovo.org/data-hub#utah-city-crashes).

On November 11, 2026, Hub deployment `dpl_4MBtg4kuhEmPuPr1wZ8C5tNKMvz4` published the four city packages from commit `c27e79e`; all 159 staged and live files passed byte and header checks. The previous Hub deployment was `dpl_Bie4sswH9LRe4JKTsZ5hc8PDMkbZ`. Projects deployment `dpl_CESEuDNvrbYrt1BMRWGzCE2kJ5de` serves application commit `aafce551a019582d56c4b23c9baeedd633b1cefa` and its pinned datasets recorded in `/release.json`. The collapsed and deep-linked states passed live desktop, phone and tablet checks. The previous Projects deployment was `dpl_9bWb6h6QPmwixggYEwU79FQFCKBq`.

The annual crash guide table links complete city versions selected in the ledger’s publicCityReleases list and not withdrawn. Provo links to its original public annual-at-crash-aggregates product. Other coverage rows show “Not yet available.” After publishing a city version, rerun its registration command to refresh the table.
