# Private crash updates and recovery

The hub is the routine writer. From its root, run these commands with the Python environment for `tools/crash_pipeline` (on the maintainer host, BikeWalk’s `tools/.venv-maps/bin/python`). A normal run refreshes UDOT. Supply portal workbooks and PD deliveries on receipt, in chronological order. Supply `--offline` to reuse the retained UDOT snapshot.

```sh
python update_crashes.py --offline
python update_crashes.py --portal-workbook /private/path/to/city.xlsx --police-input /private/path/to/forward.eml
python update_crashes.py --offline --reviewed-matches /private/path/to/reviewed-decisions.json
python update_crashes.py --rollback
```

`private/crashes/operational-20261107/tools/.danger-zone-private/datastores/combined-incidents.json` identifies the active release. The wrapper applies historical path mappings to the recovered tree. Successive runs and rollback use the same lock. Read the accepted manifest, changes and conflicts after each run. A repeated receipt with unchanged inputs and policy leaves the pointer intact. On failure use the last verified pin and inspect the failed run before retrying. BikeWalk’s former routine command invokes this hub entry point. Its archived pointer remains available for historical reads.

## Recover the cutover pin

The November 7 restricted recovery directory is `private/crashes/recovery-20261107`. Its `crash-recovery.tar.gz` contains 397 files, including the raw acquired inputs, reviewed receipts, the original PD forwards and eight managed releases. Archive SHA-256 is `0a999d43220e42940e2467c2b96b2a7f90c020b49497852aeb041ff871db991f`. The historical incident-map sources are in a second archive inventoried alongside it. Restrict access to authorized data maintainers.

Run the retained verifier from the restricted recovery directory. It checks both archives and inventories against fixed SHA-256 pins, extracts into a new owner-only directory, verifies the eight managed releases and resolves the active pointer locally. The restricted README records the exact checkout and mapping commands.

```sh
python3.11 -IB recover-pins.py /absolute/path/to/new-private-restore
```

From the hub root, replay the recovered state in isolation. Each historical origin maps to the new folder. Include the operational root when restoring a subsequent backup.

```sh
old=/Users/test/dev/bwp-data-hub/private/crashes
PYTHONPATH=tools/crash_pipeline/src python -m danger_zones.update_incidents --offline \
  --restore-path /Users/test/Documents/ChatGPT/bikewalk-provo "$RESTORE_TO" \
  --restore-path "$old/pd-forwards-20261107/verified-hub-intake" "$RESTORE_TO" \
  --restore-path "$old/pd-forwards-20261107/address-geocoding-shadow" "$RESTORE_TO" \
  --restore-path "$old/operational-20261107" "$RESTORE_TO"
```

The drill used producer commit `c423d5b`. Verify the cutover collection SHA-256 `88f62505f351db1f966cef5bfd53efed25923b88bc4c58a60a9b9c9f79da1d34` and manifest SHA-256 `88c29c0a44c63245a485a8761f9e308de1ab9e1a6ad021d67ca89e285bb19e08`. The independent operator reproduced all records after rolling back to the predecessor and reapplying the reviewed receipt. Evidence is in `drill-proof.json` and `consumer-proof.json`. The drill used the existing OS account on one machine. Access for a second human and recovery following loss of this machine still require verification.

Before retiring a receipt location, back up the full current operational tree and any additional evidence together with the producer commit, active pin and checksums. Retain earlier backups. Restore the new backup into a fresh restricted folder, repeat the offline run and compare all pinned files before relying on it. This first archive covers the cutover only.

## Consumer checks

Projects adopts the two 1.0.0 annual packages independently. The restored AT series reproduced its nine rows (680 total), and the retained fatalities and incident-map inputs reproduced 17 incidents with 18 deaths and 1,195 mapped features respectively. The incident map uses its historical input pin.

Streets Watch selects existing concern memberships by state ID. From the hub use `python -m danger_zones.concern_details --release RELEASE_DIRECTORY --manifest-sha256 HASH --output NEW_RESTRICTED_FILE` with `PYTHONPATH=tools/crash_pipeline/src` and `umask 077`. The payload includes seven public field groups. For a reviewed state/PD pair it also carries the case number and match basis. Preserve strong, probable, exact-time-and-address and documentary distinctions. Reviewed narratives and original PD records stay private. The Streets Watch [adoption instructions](https://github.com/bpj-repos/streets.watch/blob/main/docs/CONCERN_CRASH_DETAILS.md) cover its separate preview, backup, apply, replay and rollback.
