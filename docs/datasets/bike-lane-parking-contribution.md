# Bike-lane parking contribution

The Hub assigns each active transportation incident group an ordinal likelihood tier using the crash fields already available. The target mechanism is a stationary motor vehicle occupying part of a designated bike lane and contributing to a crash through contact, avoidance, or impaired visibility. A vehicle may be standing or loading. Carrier identity and contact with the vehicle are unnecessary.

| Value | Structured evidence in one source crash record |
|---|---|
| `highly_suggestive` | An AT participant in a designated bike lane plus a driver parking factor linked by vehicle number to a parked or stopped unit, a parked unit with an AT harmful event, or a parked unit together with a parked-vehicle impact or non-contact vehicle causing evasive action. |
| `stronger_lead` | An AT participant is recorded in an on-street or separated bike lane and a driver is coded for improper parking/stopping or a vehicle is recorded parked or hit while parked. |
| `possible_lead` | Bike-lane location plus a parking maneuver or traffic-lane stop, or driver evasive action or a non-contact vehicle causing evasive action together with improper parking or a parked vehicle. |
| `weak_lead` | Improper parking/stopping, a parking maneuver, a parked vehicle, or a parked-vehicle collision without a stronger combination. |
| `no_specific_signal` | Identified AT participant and known vehicle maneuver, with none of the qualifying combinations. |
| `insufficient_data` | The record lacks the detail needed for this screen. |

The tiers express relative strength of evidence. They are uncalibrated and do not measure prevalence. A cyclist's recorded position does not establish the vehicle's position. A stop for traffic, an evasive maneuver on its own, a cargo van, and a bike lane on the street are each too nonspecific to flag. A cyclist who left a blocked lane may have a recorded position elsewhere. Pedestrians and other conveyance users are included. A grouped incident takes the strongest tier from a single source observation. The method does not combine unrelated clues across source records. City-filtered portal rows provide person locations, driver circumstances, and crash/vehicle events. UDOT can supply a parked-vehicle collision clue. Limited police roster fields alone yield insufficient data.

## Rebuild and use

Run `PYTHONPATH=.:pipelines/crashes/src python -m scripts.update_crashes --offline` in the crash environment to populate group enrichment, including the supporting signals. Run `python -m scripts.bike_lane_parking candidate private/candidates/NEW` in the same environment to rebuild the public package. The candidate uses the 1,195 original map features and their own frozen structured fields. The current private population covers additional years and observations. Only the category is added to the historical features. The manifest reports the count in every tier.

An optional original-report review can record stronger case evidence privately. Use `python -m scripts.bike_lane_parking screen state:CRASH_ID private/reviews/NEW.json ORIGINAL.pdf`, complete the case and evidence review, and import with `scripts.update_crashes --offline --parking-review private/reviews/NEW.json`. The structured likelihood workflow runs on all records independently of this optional evidence.
