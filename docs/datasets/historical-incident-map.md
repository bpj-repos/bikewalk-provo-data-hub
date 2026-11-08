# Reviewed historical incident map

Dataset `provo-active-transportation-incident-map`, version 1.0.0. Manifest SHA-256 `e9fdbe0101380792235c2ff1c43bccf0645c220730cf6d0ab12e8f403ea9df8e`. The GeoJSON is byte-identical to the already approved Projects extract: `9f5c4f56645ea7467e21cbff900d5831835d34a525304281f10c27c91f1c5a01`. Its 1,195 mapped groups and four unmapped groups are historical, not the latest operational collection. No additional public fields, source associations, times or coordinate precision are introduced. This is not a unique-crash count. The official annual series has a different, documented denominator.

## Rebuild and recover

Use the pinned crash Python environment and Node, with no new dependencies:

```sh
PYTHONPATH=pipelines/crashes/src python -B -m scripts.prepare_incident_map_release \
  private/candidates/provo-active-transportation-incident-map/2026-11-08-historical-restore/receipt.json private/crashes/NEW_MAP_PACKAGE
```

Compare all five files against `releases/datasets/provo-active-transportation-incident-map/1.0.0`. The receipt binds the retained normalized manifest, derived manifest, original feature selection and existing public map manifest by SHA-256. Each manifest binds its resources. Validation checks normalized JSONL/Parquet agreement, duplicate observations, source references, derived issues, exact source snapshots, public-field allowlists, approximate coordinates and original output bytes. A failed build creates no candidate and does not touch the catalog or an app.

The original 14 inputs are in `private/backups/crashes/2026-11-07-cutover/incident-map-archive.tar.gz`, with `incident-map-inventory.json`. Follow `crash-operations.md` to restore into private storage. The tracked recipe is `data-definitions/historical-incident-map/historical-v1/receipt.json`. After restoring the original 14 inputs into `inputs/`, copy that recipe beside `inputs/` and copy `releases/datasets/provo-active-transportation-incident-map/1.0.0/map-manifest.json` beside the recipe as `map-manifest.json`. The recipe contains paths and hashes only. Its original prepared copy is in `private/candidates/provo-active-transportation-incident-map/2026-11-08-historical-restore`; its references are relative and can be relocated inside a restored hub's private directory. The two GitHub repositories retain all approved public pins independently of Vercel retention. `data-definitions/historical-incident-map/historical-v1` freezes original fields, common definitions, derived rules and their source captures. Later source/PD rules must not invalidate this historical rebuild. Current validation defaults remain unchanged.

## Next update

1. Receive new crash inputs with `scripts/update_crashes.py`. Retain originals, hashes and review decisions; don't change the historical receipt.
2. Review which source groups belong in this particular public map, public fields and unresolved identities. New links use the existing matching review process; proximity alone does not establish identity. The latest operational collection is not automatically approved for this detailed bulk extract.
3. Run the hub normalization/derived tools on reviewed inputs. Preserve source-qualified identifiers, report versus occurrence dates, missing times and disagreements. Prepare and review a new base feature selection and public map manifest. The historical selection cannot be silently paired with new source snapshots.
4. Copy the old receipt into a new private directory. Set its new semantic version and reviewed definition identity; update each path and SHA. Keep the exact approved output hash in the map manifest. `scripts/prepare_incident_map_release.py` reconstructs summaries and verifies that exact hash. Compare changed records, sources, coverage, privacy and schemas, then obtain approval for the changed candidate. Byte-identical migration permission does not approve extra future fields.
5. Prepare twice, reject a corrupt input, and compare output bytes. Copy only the approved five package files to `releases/datasets/DATASET/VERSION`, append its manifest pin to `releases/release-ledger.json`, and run `scripts/build_catalog.py`. Failed builds leave the prior catalog intact. Use the withdrawal ledger on restore.
6. Stage and verify the full static hub tree, promote, then have Projects independently stage/apply the pin with `hub-update.py`. That command rejects bad manifests/resources, stages the full snapshot, locks adoption and switches one local pointer. Repeat is a no-op; older pins remain available for rollback unless withdrawn. Build and check the map at desktop/phone/tablet widths. Public URLs, noindex and the 121-record serious/fatal AT filter remain stable at 1.0.0.

The hub owns normalization, source interpretation and prepared summaries. Projects owns filters, camera, marker selection, layout and presentation, per `ownership.md`. The retired Projects summary approval refuses to overwrite a hub-adopted release. Its source exporters stay available for exact historical recovery only.

## Hosting and migration verification

Five files total 17,262,595 bytes including the manifest. Ten thousand full downloads would be about 173 GB before overhead; use actual usage before expanding this detailed product. November 1–8 team usage before staging: $5.7928 effective, $0.00 billed to cent precision (billing can lag). Static hosting adds no functions, storage product, seats or add-ons. The existing allowance is shared. Keep the geographic dataset's existing source-specific permissions and attribution; no CC0 grant is inferred from the counts release.

Deployment and final production verification are recorded in `completion.md`: hub dpl_A7PATyGdRNAdiPdUEVzuQVKPWSmY and Projects dpl_AtcJ8ZDGZGs95BaVALkuavmoxFzV. All 80 hub files, unchanged map bytes, anonymous adoption, clean-path restore and 24 real-data responsive browser cases passed. Both exact-commit CI workflows passed. The release is live.
