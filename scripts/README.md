# Operator commands

Run module commands from the repository root. Use a new output directory for builders. Crash commands require the pinned pipeline environment and PYTHONPATH=.:pipelines/crashes/src.

| Command | Purpose |
|---|---|
| `python3 -m scripts.adopt_routes --help` | Historical compatibility adapter. Maintained map adoption lives in Streets Watch `scripts/safe-routes-update.mjs`. |
| `python3 -m scripts.audit_counts_sources SOURCE_REPO NEW_OUTPUT` | Audit pinned counts source holdings (requires xlrd). |
| `python3 -m scripts.audit_coverage` | Audit UDOT coverage against Provo city limits and the state school roster (requires shapely). |
| `python3 -m scripts.build_catalog --help` | Restore approved releases and complete dataset ZIP downloads into a new private staging directory. |
| `python3 -m scripts.build_counts_releases --help` | Prepare a counts release from checksummed Git blobs; never contacts a live service. |
| `python3 -m scripts.build_demo_counts --help` | Build the synthetic hosting proof in a new directory. No private inputs. |
| `node scripts/capture_city_crash_portal.cjs NEW_PRIVATE_DIRECTORY CITY [CITY ...]` | Capture all portal years per city with Playwright. |
| `python3 -m scripts.capture_city_crash_udot NEW_PRIVATE_DIRECTORY` | Capture all available UDOT pedestrian/bicycle year layers and municipal boundaries. |
| `python3 -m scripts.city_crash_history PORTAL_DIRECTORY UDOT_DIRECTORY CITY [CITY ...] --write` | Verify captures and update the annual crash guide city coverage table. |
| `python3 -m scripts.register_city_crashes PACKAGE MANIFEST_SHA256` | Register a reviewed annual city package, its generated ZIP and annual crash guide link. |
| `python3 -m scripts.export_city_crashes --help` | Validate a city XLSX and create a minimized local GeoJSON package and complete ZIP. |
| `python3 -m scripts.demo_city_crashes NEW_PRIVATE_OUTPUT --json` | Exercise the real mapping workflow with invented records offline. |
| `python3 -m scripts.prepare_city_crashes --help` | Prepare one Utah city’s private annual aggregate candidate from a checksummed city-filtered portal workbook. |
| `python3 -m scripts.prepare_counts_candidate --help` | Prepare a private revision using reviewed, complete annual slices and pinned evidence. |
| `python3 -m scripts.prepare_crash_releases --help` | Build private, aggregate-only release packages for owner review. |
| `python3 -m scripts.prepare_incident_map_release --help` | Reproduce a reviewed incident-map package from checksummed private presentation inputs. |
| `python3 -m scripts.rehearse_crash_receipt` | Replay the retained second Provo delivery in a temporary recovery tree. |
| `python3 -m scripts.restore_crash_collections --help` | Offline restore and parity fixture for the two Wave 6 crash collection pins. |
| `python3 -m scripts.review_campus --help` | Report changes to reviewed Treeside records and the provider's campus address. |
| `python3 -m scripts.review_crash_receipt --help` | Compare a managed crash receipt with published annual series and the previous Streets Watch export. |
| `python3 -m scripts.review_routes --help` | Compare a complete Safe Routes candidate to the approved hub package by feature identity. |
| `python3 -m scripts.safe_routes --help` | Receive UDOT records privately and prepare the Provo Safe Routes package. |
| `python3 -m scripts.update_crashes --help` | Update the active private crash workspace using verified historical path mappings. |
| `python3 -m scripts.migrate_crash_map_labels SOURCE NEW_OUTPUT [--apply]` | Prepare or adopt readable crash-map base fields from the existing minimized snapshot; preserve immutable versions. Requires the crash environment and `PYTHONPATH=.:pipelines/crashes/src`. |
| `python3 -m scripts.verify_demo_host --help` | Compare every anonymous HTTPS response with the verified synthetic build. |
| `python3 -m scripts.verify_public_catalog --help` | Compare every restored file against production or an explicitly selected staging host. |

The source-inventory audit accepts SOURCE_REPO and NEW_OUTPUT directly. The receipt rehearsal and coverage audit have no arguments. The coverage audit reads provider services over the network. Routine updates use the configured private collection. Publication builders and review commands create local output. Only the explicitly invoked updater or consumer apply operation changes active state. See the [operations guides](../docs/operations/README.md) before updates, adoption or publication.

`reviews/` contains the forwarded-police, parked-vehicle and historical-fatalities verification commands. The forwarded_police and parked_units modules provide --help. The fatalities_archive module takes PACKAGE PREVIOUS_PACKAGE OLD_WORKBOOK NEW_WORKBOOK positional paths.

| Bicycle stress | Command |
| --- | --- |
| Match pinned networks to route geometry | `python -m scripts.route_stress BASE WAYS NODES UTAH NEW_OUTPUT` with Shapely 2.1.2 and pyproj 3.7.2. |
| Verify pins and build the augmented package | `python -m scripts.package_stress BASE STRESS NEW_OUTPUT --version VERSION` |
| Recalculate the network inside pinned Brokenspoke | `scripts/model_bicycle_stress.py` inside the dedicated analyzer container. See [recovery](../docs/operations/bicycle-stress.md). |

| Routine | Maintained command |
| --- | --- |
| Run the monthly candidate and independent rebuild, retaining private logs | python -m scripts.monthly_route_review; install the macOS schedule with --install-launchagent. |
| Receive all Safe Routes sources, run the updated model and generate a private candidate | `python -m scripts.refresh_route_sources NEW_DIRECTORY` with Docker, curl, pinned GIS dependencies and the retained local July archive. |
| Rebuild or publish an explicitly reviewed Hub update, without deploying consumers | `python -m scripts.publish_route_update CANDIDATE_DIRECTORY MANIFEST_SHA256 [--verify-only | --prepare-pr]`; [operation and recovery](../docs/operations/bicycle-stress.md). |
| Screen unrated route portions without changing their ratings | `python -m scripts.unrated_route_review SEGMENTS WAYS UTAH OUTPUT`. Calibration and held-out evidence are generated by the refresh. |

| Citywide traffic stress | Command |
| --- | --- |
| Refresh frequent citywide sources, extract OSM, cache/run Brokenspoke and compare a private candidate | `python -B -m scripts.refresh_traffic_stress NEW_RUN --previous-receipt RECEIPT --version VERSION` |
| Capture pinned inputs plus complete Provo/SGID street layers | `python -B -m scripts.capture_traffic_stress HOLDINGS NEW_INPUTS` |
| Build a private versioned citywide candidate | `python -B -m scripts.prepare_traffic_stress RECEIPT NEW_PACKAGE --version VERSION` |

See [citywide maintenance](../docs/operations/traffic-stress.md). GIS dependencies match route_stress. No consumer or live release changes during preparation.

City workbook preparation, map export, demo, registration and history reporting accept --json for structured results. Use the [city mapping guide](../docs/operations/city-crash-mapping.md) for the lightweight install, output contract and GIS example.

- [prepare_crash_streets.py](prepare_crash_streets.py) builds the [Provo crash street membership package](../docs/datasets/crash-street-membership.md) from a pinned Streets Watch snapshot.

- [prepare_crash_time.py](prepare_crash_time.py) builds [local crash occurrence fields](../docs/datasets/crash-occurrence-time.md) from the pinned map archive.

- `build_provo_intersections.py` regenerates the versioned intersection records and manifest from retained UDOT responses.
