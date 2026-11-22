# Provo crash occurrence time 1.0.0

Join occurrence.json by exact opaque crash ID to the manifest's crashDataset, shared with street membership 1.0.0. The file contains one row per mapped group. localWeekday uses ISO Monday 1 through Sunday 7. localMinuteOfDay ranges from 0 (midnight) through 1439. Null denotes unavailable or conflicting evidence. Compare weekday exactly. For a target minute, use the inclusive test min(abs(value-target), 1440-abs(value-target)) <= 30 after excluding nulls. For example, 23:30 and 00:30 both qualify near midnight. Weekday remains the actual local occurrence weekday.

The Hub reads original portal Crash date and Crash dateand time fields and the UDOT occurrence timestamp. Explicit offsets are converted into America/Denver, and local portal clock readings are interpreted in Denver civil time. Seconds are discarded after conversion. Date-only evidence supplies no clock. Police report times are excluded. The snapshot formatter can produce midnight from an original date-only value, so the portal's formatted date is excluded. Both occurrences of a repeated fall-back minute share the same local value. An offset-free nonexistent spring-forward minute supplies only the date.

All supported local dates must agree. A date conflict suppresses both fields, and a minute conflict suppresses only the minute. A date-only observation can corroborate the date of a timed observation. Each evidence entry records the zero-based recordIndex within the pinned details array of records, source, field, localWeekday and localMinuteOfDay. The underlying value can be audited against that record in the pinned map archive. No-occurrence-evidence rows have empty evidence.

Run python -m scripts.prepare_crash_time SNAPSHOT NEW_DIRECTORY using the versioned gzip snapshot described in the street membership contract. The standard catalog builder generates the ZIP. Consumers pin its manifest and validate every resource hash before adoption. A consumer can independently omit the join on rollback. The original map and street packages retain their pins.

Release b027f4c was published on owner request with manifest SHA-256 2752b89586b0627040d30fcbe9bcccf7ac7ef43165f10617f462786edbdda6bb. Deployment dpl_7WuWnfwcos6zvyMwtMBS1DUbzLUf succeeded dpl_7eAVHKZmMH2Fgszpp5orHEFrrPpz. All 168 files passed staged and stable-alias verification. Independent builds reproduced the time and prior street packages. Of 1,358 mapped crashes, 1,344 have both fields, one has weekday alone, and 13 lack occurrence evidence. The production pin contains no date or minute conflicts.

Version 1.1.0 uses the November 15 rebuilt map snapshot `d0e5f1c9fdbeca56cb71e14b78c0b890570c7ed3fbfedb61c3f48ce5cb725095`. Rebuild from its retained archive using `--crash-pin d0e5f1c9fdbeca56cb71e14b78c0b890570c7ed3fbfedb61c3f48ce5cb725095 --version 1.1.0`. The snapshot is retained with the private release review until a map consumer adopts it.

Version 1.1.1 binds the November 17 refresh snapshot `3ad1d844df66b7df38e82346d81761dcedf961a6dc813d6532923df57b530b83`. It retains 1,358 mapped groups and the existing field definitions. The map includes the newly managed crash through the earlier county reference, so map membership is unchanged.

Version 1.1.3 binds hosted-refresh base map `42e4ef6263566256f97e68b0a4d1e5bb32d7791471983c3ba91e457f48cf8cab`, with 1,363 mapped groups. It includes the four newly ingested November crashes and preserves prior opaque references. Definitions and earlier pins are unchanged.

## Compatible record facts in 1.2.0

Occurrence rows additionally carry `localDate` (ISO), `localYear`, `localMonth` and `precision` (`minute`, `date` or null). Precision describes this minute-resolution product, not source seconds. Date conflicts suppress the date, year and month. Existing weekday/minute definitions remain unchanged.

`facts.json` is a reusable index over the same minimized, pinned map records. Each map ID maps to an array aligned with its detail records, with null for police report records. State entries retain source-qualified identity, per-record occurrence status/evidence, base-field dictionaries by section, and person/vehicle rows. Missing source readings remain explicit unavailable strings; absent rows remain absent. Person roles, injuries, ages, nonmotorist settings and vehicle maneuvers retain the Hub export definitions. No people are deduplicated across source records. Consumers choose their existing populations and denominators, including Portal-only charts and state-linked road charts. This resource avoids re-decoding display fields on each request without introducing a service or a second time model.

Streets Watch verifies the package and prepares its map summary/filter views at adoption. Its aggregates, calendar windows, age groupings and BYU screen remain consumer-owned. Earlier archive pins retain their original behavior.
