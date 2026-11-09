"""Run inside Brokenspoke Analyzer 3.3.0 against a dedicated configured database."""

import json, os, subprocess
from pathlib import Path
from importlib.resources import files
from sqlalchemy import text
from brokenspoke_analyzer.core import compute, ingestor, runner
from brokenspoke_analyzer.core.database import dbcore

url = os.environ["DATABASE_URL"]
engine = dbcore.create_psycopg_engine(url)
scripts = Path(str(files("brokenspoke_analyzer.scripts")._paths[0]))
geom = json.loads(Path("/tmp/inputs/boundary.json").read_text())["features"][0][
    "geometry"
]
with engine.begin() as conn:
    conn.execute(
        text(
            "CREATE TABLE neighborhood_boundary AS SELECT ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:g),4326),32612) geom"
        ),
        {"g": json.dumps(geom)},
    )
    box = conn.execute(
        text(
            "SELECT ST_Extent(ST_Transform(ST_Buffer(geom,3000),4326))::text FROM neighborhood_boundary"
        )
    ).scalar()
bounds = box[4:-1].replace(" ", ",")
osm = Path(os.environ.get("BWP_MODEL_XML", "/tmp/provo.osm"))
subprocess.run(
    [
        "osmium",
        "extract",
        "-b",
        bounds,
        "-s",
        "complete_ways",
        "/tmp/inputs/utah.osm.pbf",
        "-o",
        str(osm),
    ],
    check=True,
)
for schema, prefix, config in [
    ("received", "neighborhood_", "highway"),
    ("scratch", "neighborhood_cycwys_", "cycleway"),
]:
    runner.run_osm2pgrouting(
        url, schema, prefix, scripts / f"mapconfig_{config}.xml", osm
    )
ingestor.rename_neighborhood_tables(engine)
runner.run_osm2pgsql(url, 32612, scripts / "pfb.style", osm, number_processes=2)
compute.features(engine, scripts / "sql", 32612, 2680)
compute.stress(engine, scripts / "sql", 25, int(os.environ.get("BWP_CITY_SPEED", "25")))
for table, fields in [
    (
        "neighborhood_ways",
        "road_id,osm_id,name,intersection_from,intersection_to,one_way,ft_seg_stress,tf_seg_stress,ft_int_stress,tf_int_stress",
    ),
    ("neighborhood_ways_intersections", "int_id,legs,osm_id"),
]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT {fields},ST_AsGeoJSON(ST_Transform(geom,4326),9) AS geometry FROM {table} ORDER BY 1"
            )
        ).mappings()
        features = []
        for row in rows:
            props = dict(row)
            geometry = json.loads(props.pop("geometry"))
            features.append(dict(type="Feature", properties=props, geometry=geometry))
        Path("/tmp/outputs", table + ".geojson").write_text(
            json.dumps(
                dict(type="FeatureCollection", features=features), separators=(",", ":")
            )
        )
