# Approved releases

`datasets/<dataset-id>/<version>/` contains approved package files. Each datapackage.json binds its resources by size and SHA-256. `release-ledger.json` records approvals and withdrawals. `baseline-pins/` preserves the original real and demonstration counts pins.

The two real counts baselines and demonstration packages are reconstructed from pinned Git inputs by the catalog builder. Their pins remain in baseline-pins rather than duplicating generated packages here.

Build with `python3 -m scripts.build_catalog SOURCE_REPO NEW_OUTPUT`. Never replace bytes under an existing version. Publication and withdrawal follow the [maintainer guide](../docs/operations/maintainer-guide.md). Candidate packages stay in private/candidates until reviewed.
