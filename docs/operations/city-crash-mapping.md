# Make a city crash map from a fresh clone

These commands process one Utah Crash Data Portal city workbook. Start with the invented offline example to check your setup. The workflow produces a GeoJSON point layer, field dictionary, method, checksummed manifest and complete ZIP.

## Install the city tools

Use Python 3.11 or newer and Git. From a clone of this repository:

    python3 -m venv pipelines/crashes/.venv
    . pipelines/crashes/.venv/bin/activate
    python -m pip install -r pipelines/crashes/requirements-city.txt
    export PYTHONPATH=.:pipelines/crashes/src

On Windows, activate pipelines/crashes/.venv/Scripts/Activate.ps1 in PowerShell and set $env:PYTHONPATH=".;pipelines/crashes/src". The requirements include the Windows timezone database. This smaller environment supports workbook-to-annual preparation, map export, the offline example and city package registration. Automated UDOT capture/reporting and private reconciliation use the full environment described in the [city guide](city-crash-data.md).

## Run the example offline

    python -m scripts.demo_city_crashes private/candidates/example-city --json

Use a fresh directory. The command creates a clearly labeled synthetic XLSX, its SHA-256 receipt, and a map package through the real validator/exporter. Its JSON result provides absolute file paths and hashes. The map is at:

    private/candidates/example-city/map/example-city-crash-points/1.0.0/crashes.geojson

Expect two points, one with bicycle involvement and one with pedestrian involvement. Three invented crashes qualify under the annual rule. The third has no coordinates and is counted in excluded.missingCoordinates. A fourth invented vehicle-only crash is counted in excluded.noNonmotorist. Synthetic data may be freely reused and does not describe actual crashes.

## Open the points in QGIS

1. Open QGIS and drag crashes.geojson onto the map canvas. You can also use Layer → Add Layer → Add Vector Layer to choose the file.
2. Right-click the added layer and choose Zoom to Layer. The coordinate reference system is WGS 84, EPSG:4326.
3. Open its attribute table. Expect two features with source-qualified IDs and the fields documented in dictionary.json.
4. In Layer Properties → Symbology, choose Categorized, select severity and classify the values. The example contains Possible and Fatal.
5. To select bicycle crashes, use the expression "bike" = true. The example selects one point.
6. Save a local QGIS project. You can style and explore the vector layer offline.

These loading and styling actions follow the [QGIS vector-data guide](https://docs.qgis.org/latest/en/docs/user_manual/managing_data_source/opening_data.html). Basemap services are optional for inspecting the local layer.

## Use the file in an existing MapLibre map

After reviewing sharing rights for real records, serve crashes.geojson from your own application's data directory. In an initialized map's load handler:

    map.addSource('city-crashes', {
      type: 'geojson',
      data: '/data/crashes.geojson'
    });
    map.addLayer({
      id: 'city-crashes',
      type: 'circle',
      source: 'city-crashes',
      paint: { 'circle-radius': 6, 'circle-color': '#a31f34' }
    });
    map.setFilter('city-crashes', ['==', ['get', 'bike'], true]);

Place the camera over your city. Use your existing renderer, basemap and hosting choices. The [MapLibre API](https://maplibre.org/maplibre-gl-js/docs/API/classes/Map/) describes loading GeoJSON sources and layers.

## Export your city's real workbook

Follow the [city acquisition guide](city-crash-data.md) to obtain an unrestricted city-filtered XLSX. Keep it under ignored private intake. Record its SHA-256 with shasum -a 256 FILE or PowerShell Get-FileHash FILE -Algorithm SHA256, then run:

    python -m scripts.export_city_crashes private/intake/city.xlsx WORKBOOK_SHA256       private/candidates/city-map --city 'Salt Lake City' --json

Read coverage and excluded before mapping the result. Map features omit missing or invalid positions. The annual statistics include qualifying crashes without positions. The shared population and disclosure fields are defined in the [city point contract](../../data-definitions/crashes/city-crash-points.md). Four decimal coordinate precision is about 11 meters north/south. Exporting prepares local files. Source reuse terms and audience-specific disclosure review govern sharing real points.

## Results for coding agents

Add --json to prepare_city_crashes, export_city_crashes, demo_city_crashes, register_city_crashes or city_crash_history. Success writes one JSON object to stdout with status, inputs, outputs, coverage, excluded and nextCommand. Output paths are absolute. Manifest and ZIP hashes bind the files. nextCommand is an argument array when the workflow has a following command, otherwise null.

Validation and I/O failures write a JSON object with status="error", error and nextCommand=null and exit with code 2. Argument syntax errors use argparse's standard usage error. A nonzero exit requires correction before using any output. Existing directories are retained and never silently overwritten. Default human output is preserved on the older commands.

For an annual candidate, use the existing complete-through review and registration workflow in the [city guide](city-crash-data.md). Geographic candidates and annual city packages have separate shapes. Only the annual registration command updates the Hub ledger and annual crash guide. A local map export has no release, deployment or consumer-adoption side effects.
