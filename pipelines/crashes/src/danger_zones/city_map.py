"""Minimized GeoJSON projection of the shared city nonmotorist population."""
from collections import Counter
import math

from .research_reports import crash_modes, SEVERITY_LABELS

FIELDS = {
    "source": ("string", "Source system, always utah-crash-portal."),
    "source_id": ("string", "State crash ID. Feature IDs qualify it with the source system."),
    "city": ("string", "State-assigned city, matched exactly to the workbook filter."),
    "date": ("string", "Source event date in America/Denver, YYYY-MM-DD."),
    "severity": ("string", "Crash severity. Unknown stays Unknown, independently of person injuries."),
    "bike": ("boolean", "Bicycle involvement under the shared annual rule."),
    "ped": ("boolean", "Pedestrian involvement under the shared annual rule."),
    "other": ("boolean", "Other nonmotorist conveyance involvement under the shared annual rule."),
}


def project(observations, city):
    excluded = Counter(dict(otherCity=0, noMotorVehicle=0, noNonmotorist=0,
                            missingCoordinates=0, invalidCoordinates=0))
    features = []
    qualifying = 0
    for observation in sorted(observations, key=lambda row: int(row["sourceRecordId"])):
        crash = observation["metadata"]["crash"]
        if crash["City_Geo"] != city:
            excluded["otherCity"] += 1
            continue
        vehicles = float(crash.get("numberOfVehicles") or 0)
        if not math.isfinite(vehicles):
            raise ValueError("Invalid number of motor vehicles")
        if vehicles < 1:
            excluded["noMotorVehicle"] += 1
            continue
        modes = crash_modes(observation)
        if not modes:
            excluded["noNonmotorist"] += 1
            continue
        qualifying += 1
        raw = [crash.get("longitude"), crash.get("latitude")]
        if any(value is None or isinstance(value, str) and not value.strip() for value in raw):
            excluded["missingCoordinates"] += 1
            continue
        try:
            coordinates = [float(value) for value in raw]
        except (TypeError, ValueError):
            excluded["invalidCoordinates"] += 1
            continue
        if (any(isinstance(value, bool) for value in raw)
                or not all(math.isfinite(value) for value in coordinates)
                or not -180 <= coordinates[0] <= 180 or not -90 <= coordinates[1] <= 90):
            excluded["invalidCoordinates"] += 1
            continue
        source, identifier = observation["sourceKey"], observation["sourceRecordId"]
        properties = dict(source=source, source_id=identifier, city=city,
                          date=observation["observedAt"].split("T")[0],
                          severity=SEVERITY_LABELS.get(str(crash.get("crashSeverity")), "Unknown"),
                          **{mode: mode in modes for mode in ("bike", "ped", "other")})
        features.append(dict(type="Feature", id=source + ":" + identifier,
                             geometry=dict(type="Point", coordinates=[round(v, 4) for v in coordinates]),
                             properties=properties))
    assert len(features) + sum(excluded.values()) == len(observations)
    return dict(type="FeatureCollection", features=features), dict(excluded), qualifying
