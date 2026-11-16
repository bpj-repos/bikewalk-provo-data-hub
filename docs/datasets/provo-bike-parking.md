# Provo bike parking

Provo City GIS maintains the [Bike Parking item](https://www.arcgis.com/home/item.html?id=0ef3b3178f5f4d3d8ee5ce88318e3437). The Hub prepares a point for each mapped location. Source OBJECTID is the GeoJSON feature ID and GlobalID is preserved for identity reconciliation. Place name and caption are plain source text. Empty names stay empty in the dataset. Projects displays “Unnamed location.” One location is the unit regardless of how many racks are described there.

## Prepare and review

Use the item's current URL and verify the owner (ProvoGIS), layer (Bike Rack Points), and point geometry. Save the item and layer metadata privately. Query the layer's /query endpoint with where=1=1, returnIdsOnly=true, and f=json. Separately request geometry in outSR=4326 with OBJECTID, GlobalID, NAME, FOLDERPATH and CAPTION. If ArcGIS limits the response, query batches of the inventoried object IDs and reconcile the combined result. Keep dated inputs and checksums in private intake.

Run from the Hub root with a new candidate directory.

    python3 -m scripts.prepare_bike_parking FEATURES_JSON IDS_JSON NEW_DIRECTORY --date YYYY-MM-DD --version 1.0.0

The producer validates complete ID membership and emits only locations.geojson and its checksummed datapackage.json. It recognizes the first category below Provo Bike Parking/Provo Bike Parking, including nested school and landmark folders. Missing or unfamiliar parents normalize to Unclassified; unfamiliar paths interrupt packaging for review. Add reviewed new paths to the fixture and producer before packaging. An unknown category may remain Unclassified after review. Recheck added, removed and changed IDs, category counts, missing names, captions and moved points against the preceding pin. The archived November 8 fixture uses EPSG:3566 and the test requires pyproj to transform it. The archived courthouse and the new WGS84 point agree within two meters.

## November 16, 2026 candidate

The archived and fresh results both have 503 points. All OBJECTID/GlobalID pairs, names, categories and captions match. The four city categories have 108 ideal, 93 improvable, 44 suggested and 10 locker/maintenance/other locations. The other 248 are unclassified. Seven have empty names. The private candidate manifest SHA-256 is 275e5298ea4b5bf3ca0783b0f7cfa68ec463cdb00d7682d44dd3b331c8835512.

The [Transparency Portal](https://www.provo.gov/1331/Transparency-Portal) invites reuse of open datasets. This item is in the Provo Open Data Content group and the [city catalog feed](https://city-of-provo.opendata.arcgis.com/api/feed/dcat-us/1.1.json) lists GeoJSON downloads. Its license field is empty. The item, layer, and map service supply no specific redistribution terms. The candidate remains outside the public ledger pending confirmation that BikeWalk can republish the full derived point file and city captions as a downloadable package. Keep raw popups, photos, editor metadata and intake private.

After rights review, record the terms in the manifest, register the reviewed new hash, build and verify the catalog and ZIP through the maintainer workflow, and promote the verified Hub deployment. Projects then reviews the same package, updates its manifest pin, and verifies the build and browser interactions before deployment. Older approved versions stay immutable; withdrawals follow the Hub withdrawal procedure.
