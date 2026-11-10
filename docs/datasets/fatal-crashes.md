# Provo fatal active transportation crashes

`provo-active-transportation-fatal-crashes/1.0.0` publishes a GeoJSON point for each reviewed fatal crash in the active-transportation collection that the state portal assigns to Provo. The retained city series starts in 2018. The latest city delivery covers the provisional 2026 reporting period. At 1.0.0 the separate 2010–2017 archive was outside the release. The historical comparability review is recorded below. Ten fatal groups at the wider lookup boundary lack a Provo city assignment and are outside the initial release.

The standalone series is retired. Both published versions remain available at their pinned URLs for the fatalities map and existing citations. The following notes record historical release evidence.

The owner approved the geographic fields and attribution terms for manifest `fcc243f1d113810bd8b7180a3f8283008f73b7986e9f3212afb565352cec1a58`. Two builds from managed release `incidents-4fbbb5835c07b4789304` reproduced identical output. Its 17 features account for 18 deaths. Thirteen crashes involved people coded as pedestrians, two pedalcyclists, and two people in the broader other-conveyance category. Every ID, month, mode, count and coordinate matched the November 4 map download. The previously published map’s full file, including editorial details, also reproduced byte for byte in Projects. The grouped mode refers to the people recorded killed. A two-death crash is one feature.

The hub’s production deployment is `dpl_GqJKbk9sCMynxZBh1ZCyanCH8Crp`. All 71 staged and public files verified; rollback deployment `dpl_B1sh32zRnndXSF9U1soJeGErNPAK`. Four new public files total 8,294 bytes. Team usage for November 1–7 before promotion was $5.1348 effective, $0.00 billed to the nearest cent.

Projects adopted the release at commit `7e2c26726be5e9b2723f0975dcce9f5e1e789868`; a repeated adoption was a no-op. Production deployment `dpl_FurKqeewfnWS1GEf8uHeXktRwFQh` serves the public map and catalog. The preceding Projects deployment is `dpl_CccCNjQeuJMW6xYZhZDzoV4aKqyV`. All six desktop, phone and tablet browser checks passed, including keyboard marker selection, popups and catalog navigation. The anonymous GeoJSON returned the approved bytes with the geographic content type and cross-origin header.


## Comparing 2010–2017 with the published cases

Version 1.1.0 uses the same GeoJSON schema and disclosure terms as 1.0.0. The narrow historical input for this dataset is the retained Provo portal workbook `99eedb508fd52388f7c44dfaf7645e4b7816f53ceeb55a562be8458587c424c7`. Its SHA-256 and selection period are recorded in the new manifest. 

The independent field check reads both original workbooks directly. It verifies their pinned bytes, sheet headers and filter settings, unique IDs across 26,481 city crashes, and the public geometry, month, mode and person-level deaths for each of the 25 selected crashes. The original 17 features compared equal individually. The corresponding UDOT lookup in the operational receipt has no records for these eight historical IDs, so the archival death counts are corroborated within the state portal by the fatal crash severity and person injury records. These checks do not establish complete historical reporting or ground-truth location accuracy.

| Year | Fatal crashes in the reviewed archive | Recorded deaths |
|---|---:|---:|
| 2010 | 1 | 1 |
| 2011 | 0 | 0 |
| 2012 | 1 | 1 |
| 2013 | 1 | 1 |
| 2014 | 1 | 1 |
| 2015 | 1 | 1 |
| 2016 | 2 | 2 |
| 2017 | 1 | 1 |

The 2011 city export includes 97 active transportation crashes, with no qualifying fatal record. For the eight archive cases, the fatality person types agree with pedestrian or cyclist flags in Rollups. The flags on the older Crashes sheet are empty. Historical functional road class and special vehicle function are frequently missing, and legacy labels and unknown-age codes require year-specific interpretation. Counts and modes can be compared under the published definitions. A change over time is not by itself evidence of a change in risk.

Reproduce the direct-workbook comparison with the crash environment:

```sh
python pipelines/crashes/reviews/fatalities_archive.py NEW_PACKAGE APPROVED_1_0_0 HISTORICAL_CITY_XLSX RECENT_CITY_XLSX
```

The comparison uses the recent Provo workbook with SHA-256 `3405efb346c9b839a21a7812679b1a8dd6d504a8f24d775b985ef54c1b59ad14`. The separate annual crash series retain their own source scope and pins.

The release owner approved publication of 1.1.0 and Projects adoption under the existing geographic reuse terms. The manifest SHA-256 is `122e4f56a86b0a94f21eccbced54904754522493d1caa57f7a92a5f2623e73b0`. Hub commit `535d0ed` and deployment `dpl_7GFzG2Vs4Tw3yhKdoCb2wEZ6uXFw` serve the release. All 75 files matched on staging and production, including version 1.0.0. The preceding hub deployment is `dpl_GqJKbk9sCMynxZBh1ZCyanCH8Crp`.

Projects commit `4093e07` and deployment `dpl_B4wpBcfUh7rcr7jPVLZosYmUAow1` serve the adopted snapshot. The preceding Projects deployment is `dpl_FurKqeewfnWS1GEf8uHeXktRwFQh`. The public map matched the hub for all 25 features, preserved the original 17 complete records in their previous order, and exposed both download links. The production smoke check and six desktop, phone and tablet browser tests passed, including selection of a historical crash.
