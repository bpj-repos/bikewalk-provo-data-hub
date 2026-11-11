"""Create a small invented city workbook and run the real GeoJSON exporter offline."""
import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import Workbook

from danger_zones.field_inventory import read_catalog
from scripts.city_cli import run
from scripts.export_city_crashes import ROOT, export


def demo(output):
    output = output.resolve()
    if output.exists() or not output.is_relative_to(ROOT / "private"):
        raise ValueError("Use a fresh output directory under private/")
    catalog = read_catalog()
    book = Workbook()
    book.remove(book.active)
    crashes = [
        dict(Crash_ID="1", City_Geo="Example City", numberOfVehicles=1,
             crashDateandTime="2025-03-04 09:30:00", latitude=40.23, longitude=-111.66, crashSeverity="2"),
        dict(Crash_ID="2", City_Geo="Example City", numberOfVehicles=1,
             crashDateandTime="2025-04-05 10:00:00", latitude=40.2305, longitude=-111.6605, crashSeverity="5"),
        dict(Crash_ID="3", City_Geo="Example City", numberOfVehicles=1,
             crashDateandTime="2025-06-01 12:00:00", latitude=None, longitude=None),
        dict(Crash_ID="4", City_Geo="Example City", numberOfVehicles=1,
             crashDateandTime="2025-07-01 12:00:00", latitude=40.231, longitude=-111.66),
    ]
    filters = {"City": "Example City", "Counties": "All", "Agency": "All", "Vehicle Types": "All",
               "Crash Severity": "1,2,3,4,5", "Date Selection": "Jan 01, 2025 to Dec 31, 2025 for 2025",
               "Age Range": "All Ages Included", "Days": "Mon, Tue, Wed, Thu, Fri, Sat, Sun",
               "Hours": "12:00 AM to 11:59 PM", "Months": "All Months",
               "Number of Vehicles": "All Vehicle Counts Included"}
    rows = dict(Crashes=crashes, Persons=[dict(Crash_ID=str(i), personType=kind)
                                        for i, kind in [(1, "4"), (2, "3"), (3, "4"), (4, "1")]],
                Vehicles=[], Rollups=[], Filters=[dict(Filter=k, Value=v) for k, v in filters.items()])
    for name, records in rows.items():
        sheet = book.create_sheet(name)
        fields = list(catalog["tables"]["portal." + name.lower()]["fields"])
        sheet.append(fields)
        for record in records:
            sheet.append([record.get(field) for field in fields])
    output.mkdir(parents=True)
    workbook = output / "synthetic.xlsx"
    book.save(workbook)
    digest = hashlib.sha256(workbook.read_bytes()).hexdigest()
    (output / "source.json").write_text(json.dumps(dict(synthetic=True, city="Example City",
                                                      file=workbook.name, sha256=digest), indent=2) + "\n")
    return export(workbook, digest, output / "map", "Example City", synthetic=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser, lambda args: demo(args.output))
