# Bike-lane parking contribution

The Hub assesses whether a stationary motor vehicle occupying any part of a designated bike lane contributed to an active transportation crash. Include parking, standing and loading. Contact with the vehicle is optional. A rider moving around a van into traffic, falling during avoidance, or being hidden from another road user can qualify when the report describes the sequence. The affected person can be a pedestrian or another AT user. Ordinary traffic queues, red lights, a nearby delivery, and a door opening from an adjacent parking bay alone do not establish this mechanism. The result carries no finding of legal fault.

| Value | Evidence required |
|---|---|
| documented | The original narrative, diagram or supplement establishes both the vehicle's stationary position in the lane and how that obstruction contributed. |
| possible | Case-specific evidence points to this sequence but leaves position or contribution unresolved. |
| ruled_out | The original affirmatively excludes this mechanism, for example by establishing that the suspected obstruction arrived after the crash. |
| unknown | Missing, silent, unreadable, conflicting or insufficient evidence, or an uncertain link. |

Use the crash sequence and road-user positions as in the [FHWA crash typing guidance](https://highways.dot.gov/turner-fairbank-highway-research-center/pbcat/getting-started). An improper-parking code, a delivery vehicle, and a cyclist in a bike lane are retrieval clues. Each alone leaves the category unknown.

## Review a delivery

Use the pinned crash environment, set `PYTHONPATH=.:pipelines/crashes/src` and `umask 077`. Retain every original privately. Screen all reports received for AT cases, including those without a carrier name or structured parking code. For retrieval prioritize the existing 14 bicycle leads, beginning with state cases 821685964 and 821711934. Screen each case with its supplements together.

```sh
python -m scripts.bike_lane_parking screen state:CRASH_ID private/reviews/NEW.json ORIGINAL.pdf SUPPLEMENT.txt
python -m scripts.update_crashes --offline --parking-review private/reviews/NEW.json
python -m scripts.bike_lane_parking candidate private/candidates/NEW
```

The first command accepts state or police identifiers and records the original hashes, source links, suggested value and matching text windows by page. PDF extraction uses local Poppler pdftotext. Form feeds separate pages in UTF-8 text. An empty or incomplete extraction requires inspection of the original pages. Review all diagrams and conflicting accounts visually. Resolve uncertain identities before importing. Read all flagged passages in the original. Before the first release inspect every non-unknown decision and sample the unflagged reports for missed wording. If fewer than ten unflagged cases are available, inspect them all; otherwise inspect ten by sorted case ID spaced across the list. Record the sampled cases privately.

Before the second command, fill the packet's value, reviewer and rationale after checking the original identity, position, timing and contribution. Cite the page or diagram in the rationale. A proposal cannot directly update the collection. Include all current originals when replacing a case assessment. To retract a finding, submit a corrected unknown assessment. A changed original checksum requires a new packet. The update retains checksummed originals and decision packets with the private input history and binds findings to current case links. Group or case-link changes invalidate the finding. Include these files in ordinary private backups and use the normal private updater rollback to restore a predecessor.

## Candidate and publication

The candidate builder verifies the 1.0.0 base package, adds only the category on each existing GeoJSON feature and reports the number of reviewed mapped groups plus counts in each category. A reviewed unknown counts toward coverage. Only unique reviewed source IDs shared with the historical feature can transfer a finding. Private evidence never belongs in the public package. The initial real-data build has 1,790 private groups and 1,195 historical mapped groups, all unknown. There were zero original reports available for review or sampling.

The catalog checks that reviewed coverage reconciles and that at least one mapped group has a reviewed documented, possible or ruled_out result before accepting 1.1.0. Keep the initial candidate private. After the evidence criterion is met, compare two builds and remove the one added property in memory to verify exact historical feature equality. Follow the [maintainer publication workflow](../operations/maintainer-guide.md) for approval, registration, generated ZIP, staging and production checks. The historical product is retired from listings. Its pinned files, the current operational collection and the Streets Watch app have separate publication and adoption paths.
