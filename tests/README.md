# Regression tests

From the repository root

```sh
BWP_SOURCE_REPO=/absolute/path/to/bikewalk-provo python3 -B -m unittest discover -s tests/hub -t .
PYTHONPATH=.:pipelines/crashes/src python -B -m unittest discover -s tests/crashes -t .
```

The hub group uses the standard library. The crash group requires the pinned crash environment and Node for public-map validation. Retained-input cases report skips when private holdings are absent. Keep those skips visible in verification results.
