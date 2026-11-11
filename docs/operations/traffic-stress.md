# Citywide bicycle traffic-stress maintenance

Use the GIS environment with Shapely 2.1.2 and pyproj 3.7.2. There is no network dependency while preparing or consuming a pinned candidate. The source intake requires HTTPS access and read access to retained model inputs. Original private files are never uploaded to the public host.

## Routine citywide refresh

Run from the hub checkout with Python 3.12, Shapely 2.1.2 and pyproj 3.7.2, curl, and Docker. Allow the Docker VM at least 8 GiB memory and adequate disk for the analyzer/database images. Each model uses an isolated temporary database with 4 GiB scratch plus a 2 GiB worker scratch mount. The command removes only its own UUID-named containers and network. Original downloads and run diagnostics stay private. The source extractor uses osmium inside the approved image and the Python standard library, with no extra host OSM dependency.

    python -B -m scripts.refresh_traffic_stress private/candidates/YYYY-MM-DD-citywide-refresh \
      --previous-receipt /absolute/path/to/retained-inputs/receipt.json \
      --version 1.1.0

Supply the previous verified source receipt so infrequently refreshed study snapshots and approved model settings remain available. The command selects the latest non-withdrawn local published package as its comparison baseline. Choose a new compatible version after the current release. It creates a private candidate and never performs publication or consumer adoption.

| Input or work | Default refresh behavior |
| --- | --- |
| Geofabrik Utah OSM | Check the current checksum, reuse a verified identical PBF or download the fresh delivery, verify checksum stability and read the embedded snapshot timestamp. |
| Reference network extraction | Clip complete OSM ways to a 3 km municipal buffer, retain highway tags and shared node IDs. Cache by PBF, boundary, image and extraction-tool fingerprint. No invented junctions at crossing geometries. |
| Published PFB analysis | Discover Provo's current published vintage and residential default, download the ways, validate IDs and rating fields. Version alone is insufficient proof that bytes are unchanged. |
| Provo boundary | Capture and validate the current polygon on each run. |
| City/SGID streets and Utah Bikeways | Capture the entire municipal envelope, without CITY-label filtering. Reuse a verified prior extract only when URL, query extent and non-null provider edit stamp agree. Sources without reliable edit stamps are recaptured. IDs/counts are verified before and after paging. Attribute-level atomicity remains limited when the provider supplies no edit stamp. |
| Brokenspoke | Reuse only a verified identical recipe. Otherwise run the existing isolated model runner with the approved image/database digests. Recipe includes PBF, boundary, residential default and model/runner tool hashes. |
| Software versions | Report the newest analyzer version and the approved version. Keep the reviewed scoring implementation until a deliberate methodology/dependency review chooses a new digest. |
| Crosswalks and intersection studies | Retain the previous checksummed, dated snapshots by default. Add `--refresh-intersections` for a periodic inventory review or known local change. This captures complete city crosswalk and both UDOT study layers in the municipal envelope. A failed selected source fails acquisition. |

Each run writes `acquisition.json`, `inputs/receipt.json`, `package/` and `review.json`. The review reports added/removed feature IDs, source changes, band changes and geometry changes, old/new coverage, dependency freshness, cache use and the exact independent-rebuild command. Source segmentation can change identities, so ID churn and coverage changes need separate review. Evidence overrides carry forward and must still resolve to dated feature/source records. A stale evidence identity fails preparation for maintainer review.

## Resume and recovery

After acquisition completes, retry an interrupted processing/build with the identical command plus `--resume`. This verifies all retained input hashes, PBF hash, baseline pin, candidate version and tool fingerprints. Identical cached extraction/model output is checked before reuse. The canonical receipt stays unchanged across resume; cache-hit diagnostics belong to the private review. If an existing candidate is present, every manifest resource and its receipt binding are checked.

An incomplete acquisition has no resumable checkpoint. Keep the failed directory and its `failure.json`, correct the source/runtime failure and choose a new output directory. Changed tools, version or published baseline also require a new run. A corrupt cache raises an error. Preserve that cache entry for diagnosis and use a fresh `--cache` directory to rebuild it. Never edit hashes to bypass verification. Cache entries are independently keyed and locked, so concurrent runs cannot replace each other's verified results or duplicate the same expensive processing.

The first durable input archive is the local private/backups/github/source-receipts-traffic-stress-20261110/ directory. Retrieve its archive into a new private directory, verify SHA-256 `371543ee6b00dd58aecb6e7258fd933a414268033bedceba71732bbf87523961`, and extract it only into a new recovery directory. Its root receipt is a valid first `--previous-receipt`. Subsequent runs can use `RUN/inputs/receipt.json`. Keep source originals and the exact input receipt with each eventual release. Cache contents are reproducible conveniences; the input archive, tool commit and image digests provide recovery.

Review the printed independent-rebuild command and compare every package byte. Run both test groups. Review coverage by class, source switches, source-only records, known pilot locations and any evidence failures. Then use the existing exact-pin release/catalog procedure and Streets Watch adoption commands below. An update to source data or a new available analyzer version alone never promotes a release. Scheduling remains a separate operator decision; this command supports manual invocation and an existing job runner.

## Manual receipt and publication tools

The lower-level capture/prepare commands remain supported for reviewed bespoke inputs and historical recovery.

1. Preserve original OSM PBF, extraction recipe, extracted node/way/tag network, published PFB ways, local Brokenspoke ways/nodes, municipal boundary, statewide Utah Bikeways and local intersection study inputs. A holdings JSON maps each key to path, origin, version and date. Run `python -B -m scripts.capture_traffic_stress HOLDINGS NEW_PRIVATE_INPUTS`. This copies those sources, captures complete city and SGID street layers and writes receipt.json. It verifies returned ArcGIS IDs and stable editing metadata. Refresh dates refer to capture, not installation.
2. Run `python -B -m scripts.prepare_traffic_stress INPUTS/receipt.json NEW_PRIVATE_PACKAGE --version VERSION`. The receipt verifies every input SHA-256. The command produces geometry, source register, dictionary, method, coverage and source-only pilot. Evidence overrides must have dated references and resolve to a feature and observation in that build. Unsupported or stale evidence fails the build.
3. Build again into another directory and compare bytes. Run both hub and crash test groups in the pinned environment. Compare physical/directional length, actual approach counts, source selection and native disagreements with the prior version. Changes in the denominator need a separate explanation from changes in ratings. Inspect bridges, parallel paths, asymmetry, service exclusions, City-only additions, and the seven pilot strata. The pilot does not imply independent field or rider validation.
4. Retain the input archive privately under private/backups/github/source-receipts-traffic-stress-20261110 for the first release, including the receipt, OSM extraction recipe, original November 7 reference PBF, November 8 model PBF and original model provenance. Archive SHA-256 `371543ee6b00dd58aecb6e7258fd933a414268033bedceba71732bbf87523961`. Record the archive SHA-256. After review of exact package and terms, copy the package to releases/datasets/provo-bicycle-traffic-stress/VERSION, append the manifest pin to release-ledger.json and assemble through scripts.build_catalog. Verify every existing and added resource on staging before stable-alias promotion. Old packages retain their bytes.
5. Streets Watch scripts/adopt-crash-stress.py SOURCE PACKAGE MANIFEST_SHA NEW_REVIEW verifies the whole package and compares the published-reference projection against current map geometry. On the initial adoption it must reproduce all 719 line pieces and 74 nodes. Inspect combined counts and removed-crossing reasons. The application's speed/lane screen remains local. `--apply` rechecks input and candidate hashes and writes the immutable combined archive before switching map.json. Details and crash membership are preserved. Future ordinary imports accept --stress-package and --stress-manifest-sha256. The consumer records dataset/version/pin in stressHub and needs no hub checkout at runtime.

The citywide refresh command is independent of the monthly Safe Routes workflow and uses the whole municipal extent. Both reuse the same model runner. Source reconciliation and dataset adoption remain independently reviewed.

For rollback restore map.json from a previous retained version and verify its details agree with that archive, or redeploy the complete previous application version. Respect hub withdrawals when selecting a pin. Withdrawal uses the existing hub ledger and public-tree procedure, plus removal of affected consumer copies and caches. Do not overwrite existing packages or version archives. Failed acquisition, matching or verification leaves approved releases available.

## November 10 refresh implementation checks

A cold live run acquired the sources, extracted the reference network and completed the approved Brokenspoke model in Docker. Subsequent runs reused the verified model output. The final acquisition recaptured city streets, reused SGID and Utah extracts after checking unchanged provider edit stamps, and retained the three dated intersection inventories. Forty hub tests and 143 crash tests passed with no skips in the pinned GIS environment and retained canonical source history.

Retained run `private/candidates/2026-11-10-citywide-refresh-release-check` contains the review, independent rebuild and `reproducibility-check.json`. All 11 package files reproduced byte-for-byte. Resume preserved manifest SHA-256 `8dd4289900c1d8b60e43393f8ecf3db1ec9e1f511e5f6af1017463cbd66745ec` and its receipt binding, with both processing caches reused. The comparison reported no added/removed identities or changed source, band or geometry for segments and approaches. Candidate 1.1.0 is an operational verification artifact, not an approved release.

The optional `--refresh-intersections` branch has acquisition unit coverage but was not exercised against the live study endpoints. These checks establish reproducible processing and source accounting; they do not add field validation, local-attribute injection or a new scoring method. All refresh trials remain private candidates. No schedule or public release was created by this maintenance change.


## November 10 release evidence

Version 1.0.0 manifest SHA-256 is `fa704cf166a895cc4e829ec144f5e6701b9802ac523d0729a44e3c88c8b761f1`. Two receipt-based builds reproduced every resource byte. The initial source-only map projection exactly reproduced 719 line pieces and 74 crossing nodes. The final combined projection has 734 high-stress pieces and 76 crossing nodes, with every prior displayed crossing retained. Source-native junctions and line portions outside the OSM match remain selected, scoped and separately counted.

Reference physical geometry totals 819,748.016 m with 704,736.327 m rated. Of 11,393 eligible reference approaches, 8,470 have a rating. Another 12,585 publisher-native approaches and 111,169.813 direction-meters are retained outside the reference match. These additional counts overlap the represented network and cannot be summed into a citywide unique denominator. Provo capture returned 4,508 street records and SGID returned 8,898 envelope records. Capture is geographically clipped during processing.

Thirty hub tests and 143 crash tests passed in the pinned environment. Consumer Python checks cover import compatibility and adoption. Browser and deployment evidence is recorded after their checks complete. The local source-only pilot cannot establish refuge-island status or full movement attributes from the retained study data, so no city crossing receives a Furth score merely from proximity. Independent field/rider validation and local-attribute model injection remain unperformed.

The private recovery asset was uploaded and its GitHub SHA-256 digest verified against the local archive. Hub commit `0e4361e` publishes the immutable release. Deployment `dpl_HAv3RKa9YBnSDNTmvAqKqYyjcez7` was verified across all 124 files on its staging URL and the stable public alias, including hashes, MIME and CORS. Six focused Chromium consumer cases passed with the existing local app configuration loaded in memory.

Streets Watch PR https://github.com/bpj-repos/streets.watch/pull/259 merged as `89b9c696c0fdf09d58321b3efc5fd23fa8ff3316` after required unit-tests passed. Its production API was verified serving map `7139327b1228bedca212e3fd07617130e3627041c19ea17a809affc334cf1bcc`, the exact 1.0.0 hub manifest pin, 1,358 crashes, 734 segment pieces and 76 crossing nodes. The previous `1ef697d2b359b1991167cf7a0d110b2cc3afbc4008aa67c4ef81f07e565b7997` view remains available with 1,358 crashes and its original 74 crossing nodes. Production deployment check for the merge succeeded. Task-owned preview at localhost:3127 was stopped after merge; the pre-existing server was retained. No linked worktrees were created. Both primary checkouts remain on main with the completed commits preserved.
