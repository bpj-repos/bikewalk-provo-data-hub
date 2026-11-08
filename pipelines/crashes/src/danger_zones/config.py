from __future__ import annotations

from pathlib import Path


HUB_ROOT = Path(__file__).resolve().parents[4]
PIPELINE_ROOT = HUB_ROOT / "pipelines/crashes"
DEFINITIONS_ROOT = HUB_ROOT / "data-definitions/crashes"
PACKAGE_ROOT = DEFINITIONS_ROOT
REPO_ROOT = HUB_ROOT
REGISTRY_PATH = PACKAGE_ROOT / "source-registry.yml"
SCHEMA_DIR = PACKAGE_ROOT / "schemas"


def workspace_paths():
    import json
    paths = {"workspace": "private/active/crashes", "collection": "private/active/crashes/collection",
             "geography": "private/active/crashes/geography", "mappings": "private/active/crashes/path-map.json"}
    local = HUB_ROOT / "config/paths.local.json"
    if local.exists():
        configured = json.loads(local.read_text())
        if set(configured) - paths.keys():
            raise ValueError("Unknown workspace path setting")
        paths.update(configured)
    return {name: (HUB_ROOT / value).resolve() for name, value in paths.items()}


WORKSPACE_PATHS = workspace_paths()
DEFAULT_DATA_ROOT = WORKSPACE_PATHS["geography"]
DEFAULT_PRIVATE_DATA_ROOT = WORKSPACE_PATHS["collection"]

WGS84_EPSG = 4326
ANALYSIS_EPSG = 26912

# Conservative Provo-area envelope. Network matching separates city records
# from nearby records returned by statewide services.
PROVO_AREA_BBOX = (-111.75, 40.18, -111.55, 40.35)
