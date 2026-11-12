# Approved releases

`datasets/<dataset-id>/<version>/` contains approved package files. Each datapackage.json binds its resources by size and SHA-256. `release-ledger.json` records approvals and withdrawals. `baseline-pins/` preserves the original real and demonstration counts pins.

The two real counts baselines and demonstration packages are reconstructed from pinned Git inputs by the catalog builder. Their pins remain in baseline-pins rather than duplicating generated packages here.

The catalog builder derives complete ZIP downloads under `/downloads/<dataset-id>/<version>/` from these approved bytes. Each ZIP contains one dataset/version folder with the manifest and every listed resource. Catalog `download` metadata records its path, size and SHA-256. This does not replace or modify any approved package or manifest pin; withdrawn and retired catalog releases have no generated ZIP.

Build with `python3 -m scripts.build_catalog SOURCE_REPO NEW_OUTPUT`. Never replace bytes under an existing version. Publication and withdrawal follow the [maintainer guide](../docs/operations/maintainer-guide.md). Candidate packages stay in private/candidates until reviewed.

City annual packages also retain the complete generated ZIP beside their manifests for direct repository downloads. `scripts.register_city_crashes` produces this archive through the shared catalog ZIP routine and updates the [annual crash guide](../docs/datasets/annual-at-crash-aggregates.md) link. Hosted catalog downloads are generated from those same manifest-listed resources. [City contribution workflow](../docs/operations/city-crash-data.md).
