# Crash-processing library

The existing danger_zones namespace remains stable. Install the exact pinned dependencies into a dedicated Python 3.11+ environment from the repository root

```sh
python -m pip install -e ./pipelines/crashes
PYTHONPATH=.:pipelines/crashes/src python -B -m unittest discover -s tests/crashes -t .
```

`src/danger_zones/` contains maintained source adapters and shared rules. Its configuration locates the hub root and the resources in data-definitions/crashes. Field-catalog references to src/ resolve against this pipeline, and references/ resolve against the definition directory. Historical callers can supply their frozen reference root explicitly.

Run routine updates through `python -m scripts.update_crashes`. Use the library module directly for isolated recovery with explicit roots. Consult [operations](../../docs/operations/README.md), [definitions](../../data-definitions/README.md) and [tests](../../tests/README.md).
