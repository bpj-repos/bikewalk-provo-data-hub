# Annual active transportation crashes

[Released Provo data in this repository](../../releases/datasets/annual-at-crash-aggregates/) · [Utah city coverage and downloads](#utah-cities-with-crash-data)

Dataset `annual-at-crash-aggregates` is the Provo annual series. Other cities have separate dataset IDs and share the preparation workflow below.

[Population and migration](../history/annual-crash-migration.md) · [Producer transfer](../history/crash-producer-transfer.md) · [Updates and recovery](../operations/crash-updates-and-recovery.md) · [City mapping quick start](../operations/city-crash-mapping.md)

## Prepare annual active transportation crash counts for a Utah city

1. In the [Utah Crash Data Portal](https://utaps.shinyapps.io/DataPortalAWS/), select the city by its portal name and choose the date range and years. Leave the other filters unrestricted, including county, agency, vehicle type, severity and time of day. Apply the filters and choose **Downloads → Download Filtered Data**. Keep the original XLSX in restricted intake and record its SHA-256.
2. From the repository root, activate the crash pipeline’s Python environment. Set the city, workbook path, received checksum, last reviewed full year and a fresh output path under `private/`. For example, to process a Salt Lake City workbook covering 2010 through provisional 2026, run

   ```sh
   CITY='Salt Lake City'
   WORKBOOK='private/intake/crashes/salt-lake-city.xlsx'
   WORKBOOK_SHA256='replace-with-the-recorded-64-character-sha256'
   PYTHONPATH=.:pipelines/crashes/src python -m scripts.prepare_city_crashes \
     "$WORKBOOK" "$WORKBOOK_SHA256" private/candidates/2026-11-11-salt-lake-city-crashes \
     --city "$CITY" --complete-through 2025 --version 1.1.0
   ```

3. Review `annual.csv`, the 2018-onward CSV if included, the field dictionary, the method and the manifest under the output directory. Each qualifying crash counts once in the total and once in each applicable mode. Selected years can have zero crashes. Partial years are flagged. Keep the workbook private and record the printed manifest pin for release review. [Publication and recovery instructions](../operations/crash-updates-and-recovery.md#prepare-another-utah-citys-annual-crash-series)

4. [Register the package and submit a pull request](../operations/city-crash-data.md#prepare-and-contribute-one-city). Registration generates the ZIP and adds or updates your city's table link. Commit the generated public files on your fork. Once the PR is approved and merged, readers can download the ZIP from the table below.

## Utah cities with crash data

<!-- city-crash-data:start -->
| City | Portal crashes | Portal years | Latest portal crash | UDOT crashes | UDOT years | Latest UDOT crash | Dataset |
|---|---:|---|---|---:|---|---|---|
| Salt Lake City | 3,961 | 2010–2026 | 2026-10-15 | 2,025 | 2018–2026 | 2026-11-07 | [Generated ZIP](../../releases/datasets/salt-lake-city-annual-at-crash-aggregates/1.1.0/salt-lake-city-annual-at-crash-aggregates-1.1.0.zip) |
| West Valley City | 1,611 | 2010–2026 | 2026-10-20 | 835 | 2018–2026 | 2026-10-28 | [Generated ZIP](../../releases/datasets/west-valley-city-annual-at-crash-aggregates/1.1.0/west-valley-city-annual-at-crash-aggregates-1.1.0.zip) |
| Ogden | 1,336 | 2010–2026 | 2026-09-30 | 743 | 2018–2026 | 2026-10-25 | Not yet available |
| Provo | 1,332 | 2010–2026 | 2026-09-30 | 693 | 2018–2026 | 2026-10-27 | [Generated ZIP](https://bikewalk-provo-data-hub.vercel.app/downloads/annual-at-crash-aggregates/1.1.0/annual-at-crash-aggregates-1.1.0.zip) |
| St. George | 872 | 2010–2026 | 2026-10-16 | 595 | 2018–2026 | 2026-11-07 | [Generated ZIP](../../releases/datasets/st-george-annual-at-crash-aggregates/1.1.0/st-george-annual-at-crash-aggregates-1.1.0.zip) |
| Orem | 843 | 2010–2026 | 2026-10-26 | 477 | 2018–2026 | 2026-11-02 | Not yet available |
| Sandy | 766 | 2010–2026 | 2026-10-06 | 407 | 2018–2026 | 2026-11-03 | Not yet available |
| West Jordan | 700 | 2010–2026 | 2026-10-09 | 385 | 2018–2026 | 2026-10-30 | Not yet available |
| Millcreek | 680 | 2010–2026 | 2026-10-16 | 350 | 2018–2026 | 2026-10-30 | Not yet available |
| Logan | 679 | 2010–2026 | 2026-10-03 | 380 | 2018–2026 | 2026-11-06 | Not yet available |
| Layton | 649 | 2010–2026 | 2026-10-04 | 381 | 2018–2026 | 2026-10-26 | Not yet available |
| Murray | 634 | 2010–2026 | 2026-09-23 | 286 | 2018–2026 | 2026-11-07 | Not yet available |
| Taylorsville | 625 | 2010–2026 | 2026-10-16 | 283 | 2018–2026 | 2026-10-16 | Not yet available |
| South Salt Lake | 588 | 2010–2026 | 2026-09-28 | 303 | 2018–2026 | 2026-11-06 | Not yet available |
| Midvale | 476 | 2010–2026 | 2026-09-24 | 259 | 2018–2026 | 2026-11-05 | Not yet available |
| South Jordan | 381 | 2010–2026 | 2026-10-06 | 227 | 2018–2026 | 2026-10-07 | Not yet available |
| Clearfield | 365 | 2010–2026 | 2026-10-06 | 198 | 2018–2026 | 2026-11-05 | Not yet available |
| Kearns | 323 | 2010–2026 | 2026-09-29 | 160 | 2018–2026 | 2026-10-31 | Not yet available |
| Bountiful | 317 | 2010–2026 | 2026-09-14 | 156 | 2018–2026 | 2026-10-22 | Not yet available |
| Lehi | 311 | 2010–2026 | 2026-10-15 | 229 | 2018–2026 | 2026-10-28 | Not yet available |
| Springville | 246 | 2010–2026 | 2026-07-07 | 135 | 2018–2026 | 2026-10-17 | [Generated ZIP](../../releases/datasets/springville-annual-at-crash-aggregates/1.1.0/springville-annual-at-crash-aggregates-1.1.0.zip) |
| Spanish Fork | 231 | 2010–2026 | 2026-09-22 | 139 | 2018–2026 | 2026-11-06 | Not yet available |
<!-- city-crash-data:end -->

Coverage figures describe the retained source captures and may be newer than the linked release.

[Run the workflow, contribute a dataset, and check methods](../operations/city-crash-data.md).

## Related crash datasets

The [Provo crash street membership contract](crash-street-membership.md) documents the crash-ID join and release inputs.

The [Provo crash occurrence-time contract](crash-occurrence-time.md) documents local weekday, minute, precision and conflicts.
