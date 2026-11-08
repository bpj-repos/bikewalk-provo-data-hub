# Provo fatal active transportation crashes

`provo-active-transportation-fatal-crashes/1.0.0` publishes a GeoJSON point for each reviewed fatal crash in the active-transportation collection that the state portal assigns to Provo. The retained city series starts in 2018. The latest city delivery covers the provisional 2026 reporting period. The separate 2010–2017 archive has eight historical fatal crash groups and awaits its own coverage and field review. Ten fatal groups at the wider lookup boundary lack a Provo city assignment and are outside the initial release.

From the hub root, use the crash Python environment to prepare a new private candidate. Read the manifest path and exact checksum from the operational pointer:

```sh
umask 077
PYTHONPATH=tools/crash_pipeline/src python -B fatalities.py PRIVATE_MANIFEST MANIFEST_SHA private/crashes/NEW_DIRECTORY --version 1.0.0
```

Review the state identifiers, Mountain Time months, modes, rounded points and deaths against the previously adopted map. Inspect additions, removals and corrections. The hub holds ambiguous identities, mixed categories among people killed, and conflicting death counts for review. The map owns news, local notes and richer descriptions. A published resource checksum and manifest pin cover the exact bytes adopted by consumers.

The owner approved the geographic fields and attribution terms for manifest `fcc243f1d113810bd8b7180a3f8283008f73b7986e9f3212afb565352cec1a58`. Two builds from managed release `incidents-4fbbb5835c07b4789304` reproduced identical output. Its 17 features account for 18 deaths. Thirteen crashes involved people coded as pedestrians, two pedalcyclists, and two people in the broader other-conveyance category. Every ID, month, mode, count and coordinate matched the November 4 map download. The previously published map’s full file, including editorial details, also reproduced byte for byte in Projects. The grouped mode refers to the people recorded killed. A two-death crash is one feature.

The hub’s production deployment is `dpl_GqJKbk9sCMynxZBh1ZCyanCH8Crp`. All 71 staged and public files verified; rollback deployment `dpl_B1sh32zRnndXSF9U1soJeGErNPAK`. Four new public files total 8,294 bytes. Team usage for November 1–7 before promotion was $5.1348 effective, $0.00 billed to the nearest cent.
