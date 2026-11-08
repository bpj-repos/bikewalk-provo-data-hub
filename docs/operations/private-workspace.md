# Private workspace

The ignored private directory is restricted to authorized maintainers.

| Location | Contents |
|---|---|
| active/crashes/collection | Active pointers, immutable collection releases, retained incident inputs and source snapshots |
| active/crashes/geography | Supporting geographic sources and normalized artifacts |
| active/crashes/review-evidence | Documents and evidence referenced by accepted reviews |
| intake | Deliveries as received |
| candidates | Proposed packages grouped by dataset |
| reviews | Comparisons, audits and review reports |
| exports | Consumer handoffs and adoption evidence |
| backups | Recovery archives, verifiers and inventories |
| archive | Superseded experiments and preserved historical layouts |
| migrations | Restricted relocation inventories and verification records |

New private run directories use YYYY-MM-DD-description. Keep immutable bundles internally intact. The collection engine retains its established datastores, incident-inputs, incident-updates and sources subdirectories. The local README explains those implementation directories.

Routine commands select active roots from the crash configuration. Historical manifest paths resolve through active/crashes/path-map.json with checksum verification. The original paths remain part of the audit record. No implicit search for the newest similarly named file selects a source.
