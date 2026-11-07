from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PACKAGE_ROOT.parent
REGISTRY_PATH = PACKAGE_ROOT / "source-registry.yml"
SCHEMA_DIR = PACKAGE_ROOT / "schemas"
DEFAULT_DATA_ROOT = REPO_ROOT / ".danger-zone-data"
DEFAULT_PRIVATE_DATA_ROOT = REPO_ROOT / ".danger-zone-private"

WGS84_EPSG = 4326
ANALYSIS_EPSG = 26912

# Conservative Provo-area envelope. Network matching separates city records
# from nearby records returned by statewide services.
PROVO_AREA_BBOX = (-111.75, 40.18, -111.55, 40.35)
