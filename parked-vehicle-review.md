# Parked vehicles in the private motor vehicle crash candidate

**Recommendation, November 7, 2026.** Count a Provo crash when every reported person is a driver or passenger linked to a listed vehicle, both involvement flags are explicitly negative wherever populated, and every vehicle without a linked person has maneuver code 13 and label Parked. Preserve the existing vehicle-count and roster checks. Require at least one reported person. Hold conflicting harmful-event codes and records where every vehicle is coded parked for review.

Utah defines parked as a vehicle status. Stopping in a travel lane and entering or leaving a parking position have separate codes. The state manual separately recognizes an occupant of a vehicle outside transport and asks whether at least one motor vehicle was in transport for a qualifying crash. The legacy dictionary identifies driver and passenger as motor vehicle occupant roles. Missing linkage to a parked unit therefore supplies no evidence of an additional person. The dataset describes reported participants. [Utah crash report instruction manual, crash classification and person types](https://highwaysafety.utah.gov/wp-content/uploads/Utah-Crash-Report-Instruction-Manual.pdf) · [Utah 2021 data dictionary](https://highwaysafety.utah.gov/wp-content/uploads/sites/22/2021/03/Utah-Crash-Report-Data-Dictionary-2021-v8-030121.pdf)

UDOT's documented rollups derive pedestrian involvement from person types 3 and 5, and cyclist involvement from type 4. Negative rollups corroborate the person-table interpretation but do not independently establish complete reporting. All 667 had explicit negatives for both flags. In 99 cases the rollup supplied a negative missing at crash level. [UDOT/UTAPS rollup definitions](https://support.numetric.com/en/articles/5063363-udot-utaps-rollup-definitions)

## Comparison

The baseline is private candidate SHA-256 `c05fa83f8afa979ca1b5c0026ef35c8d488060d4966adc7cf7b2a10fbe48a6c8`. Both original city workbooks were checked against their hashes and overlaid in receipt order. Baseline annual totals and the unresolved record IDs and reasons reproduced. Values are distinct crash counts. The latest included city event is September 30, 2026.

| Year | Current | All eligible parked additions | Recommended parked additions | Existing cases to review | Recommended total |
|---|---:|---:|---:|---:|---:|
| 2018 | 1,740 | 99 | 99 | 1 | 1,838 |
| 2019 | 1,652 | 80 | 80 | 0 | 1,732 |
| 2020 | 1,066 | 5 | 4 | 4 | 1,066 |
| 2021 | 1,321 | 51 | 51 | 2 | 1,370 |
| 2022 | 1,313 | 109 | 108 | 2 | 1,419 |
| 2023 | 1,396 | 85 | 85 | 2 | 1,479 |
| 2024 | 1,440 | 98 | 97 | 2 | 1,535 |
| 2025 | 1,366 | 84 | 84 | 0 | 1,450 |
| 2026 (partial) | 884 | 56 | 55 | 0 | 939 |
| **Total** | **12,178** | **667** | **663** | **13** | **12,828** |

The literal person/flag rule alone gives 12,845. Holding four of those additions gives 12,841 if the baseline is kept fixed. A 2020 case had vehicle harmful-event code 22 (pedestrian). One case each in 2022 and 2024 had code 24 (other nonmotorist). A separate 2026 case had every vehicle coded parked, leaving the in-transport criterion unresolved. An event code signals conflicting evidence for review and does not confirm who was involved.

Applying the same two conflict checks to the 12,178 existing inclusions identifies eight with nonmotorist harmful-event codes (first or most harmful event 22, 23 or 24) and five additional cases with every vehicle coded parked. Counts in the final column include the 663 additions and hold those 13 existing cases. Across the 13,635 retained crashes that leaves 680 excluded and 127 unresolved. The four cohort holds and thirteen baseline holds are provisional review decisions.

Reproduce with the hub crash environment from the repository root:

    PYTHONPATH=tools/crash_pipeline/src python tools/crash_pipeline/reviews/parked_units.py private/crashes/motor-vehicle-candidate-20261107 /absolute/path/to/retained/incident-inputs

This analysis preserves the original private candidate and release pins.
