# Annual transportation counts contract

The [cross-project ownership contract](../../docs/ownership.md) assigns responsibility for changes to shared data and its consumers.

Publish one version of the entire series under annual-transportation-counts. The mutable /catalog.json points to the current approved version and lists older pins. Every release has a stable /datasets/annual-transportation-counts/<version>/datapackage.json URL. Its resources have relative paths, byte sizes and SHA-256 hashes. Cite BikeWalk Provo, dataset title, exact version and pinned URL. Keep the prior release accessible when updating the catalog.

## What each release contains

Provide a complete UTF-8 CSV, a CSV for every covered year derived from exactly the same rows, a typed dictionary, protocol and historical field mappings, changes and citation. The manifest declares coverage, source dates, preparation, attribution and approved reuse terms. One observation measure is identified by year, source-qualified station, period, mode, breakdown, unit and original source field. Distinguish combined periods and all-mode totals from components. Observations count passages. Recorded zero is numeric zero. Missing observation and unavailable historical category both have an empty value and distinct status codes.

Use 2026 as the reference protocol. Preserve older source IDs and meanings, identify directly comparable or documented convertible measures, and explain uncertain session hours, crossing lines, observer categories and station matches. Additional years require verified provenance. Source dates may vary by delivery and year; document them in the mapping notes. The pilot's 2026 baseline is 14 stations and 6,186 total observations. Release 1.0.0 preserves the original combined scooter field of 236. Beginning in 1.0.1, the official combined measure is 283, derived from 186 Tuesday and 97 Saturday observations.

## Version and promotion decisions

| Example change from 1.0.0 | Required release | Acceptance exercise |
|---|---|---|
| Add a verified year or compatible optional measure | 1.1.0 | Reconstruct each annual slice and verify prior-year rows still agree. |
| Correct a value under identical definitions | 1.0.1 | Explain changed years, source fields, previous and corrected values. Re-fetch 1.0.0 by hash. |
| Change observations to rates, identifiers, required fields or protocol meaning | 2.0.0 | Give a migration note and keep 1.x usable. A consumer must explicitly select the new major version. |

Validate the entire candidate before a production deployment. Promote files and catalog together. Failed validation leaves the previous release available. For a privacy withdrawal, remove affected public resources, purge caches and superseded host deployments that expose them where possible, mark the catalog entry withdrawn, document the reason without repeating sensitive material, and publish a replacement at a new version. Retain a private audit record. Downloaded copies cannot be recalled.

## Audience formats

CSV and the typed JSON dictionary support spreadsheets, R, Python and databases. The JSON manifest supports automated discovery and integrity checks. Add GeoJSON for a separately defined station geography when a GIS or web-map consumer needs it. Parquet is a useful additional encoding when analytical scans, types or size justify it. XLSX is worthwhile if an audience needs a curated workbook experience. Produce any alternate encoding from the same approved rows and verify logical parity, including nulls, types and identifiers. Each format shares the dataset version. A PDF report is a companion interpretation, not the reproducible dataset.

## Wave 3 decisions

Confirm actual collection instructions and periods, verify mapping evidence for each historical year, establish attribution and explicit bulk reuse terms, and obtain release-owner approval. Synthetic prerelease pins reserve no real observations. Only the proof builder accepts synthetic data; a reviewed real-data adapter and release workflow belong to Wave 3.
