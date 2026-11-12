# BikeWalk Provo Data Hub

The Data Hub receives transportation data, maintains shared definitions and publishes reviewed, versioned files. Projects and Streets Watch independently adopt verified snapshots.

Start with the [contributor quick start and reuse terms](CONTRIBUTING.md) to build a synthetic dataset in a fresh clone. Anyone may submit a pull request. Other contributors need approval from @brycepj before merging. The owner can merge or push directly. Report sensitive findings privately to [contact@bikewalkprovo.org](mailto:contact@bikewalkprovo.org).

## Where do I find something?

| I want to… | Start here |
|---|---|
| Understand the system and its responsibilities | [System design](docs/system-design.md) and [ownership](docs/ownership.md) |
| Update data, publish a release or recover a workspace | [Operations guides](docs/operations/README.md) |
| Find a command and its inputs, effects and prerequisites | [Scripts index](scripts/README.md) |
| Understand a dataset's scope and limitations | [Dataset guides](docs/datasets/README.md) |
| Inspect mappings, protocols, source definitions or schemas | [Data definitions](data-definitions/README.md) |
| Find approved data and manifest pins | [Releases](releases/README.md) |
| Develop the crash-processing library | [Crash pipeline](pipelines/crashes/README.md) |
| Find a past decision or migration record | [Documentation map](docs/README.md) |
| Work with received inputs and local candidates | [Private workspace guide](docs/operations/private-workspace.md) |

[Public catalog](https://bikewalk-provo-data-hub.vercel.app/catalog.json) · [Agent instructions](AGENTS.md)

## Dataset usage

| Dataset | Usage guide | Released data |
|---|---|---|
| Annual transportation counts | [Guide](docs/datasets/annual-transportation-counts.md) | [Release pin](releases/baseline-pins/counts-1.0.1.json) · [Published ZIP](https://bikewalk-provo-data-hub.vercel.app/downloads/annual-transportation-counts/1.0.1/annual-transportation-counts-1.0.1.zip) |
| Safe Routes to School | [Guide](docs/datasets/safe-routes-to-school.md) | [Repository packages](releases/datasets/safe-routes-to-school/) |
| Active transportation crashes | [Guide](docs/datasets/annual-at-crash-aggregates.md) | [Repository packages](releases/datasets/annual-at-crash-aggregates/) |
| Provo bicycle traffic stress | [Guide](docs/datasets/provo-bicycle-traffic-stress.md) | [Repository packages](releases/datasets/provo-bicycle-traffic-stress/) |

## Build and check

From the repository root, with the full canonical BikeWalk Git history available locally

```sh
export BWP_SOURCE_REPO=/absolute/path/to/bikewalk-provo
python3 -B -m unittest discover -s tests/hub -t .
python3 -B -m scripts.build_catalog "$BWP_SOURCE_REPO" build/new-staging
```

Use a fresh output directory. Publication uploads only the generated `public/` directory and `vercel.json` after the [staging and promotion checks](docs/operations/maintainer-guide.md). Local `private/`, `build/` and configuration overrides are ignored by Git. Retain original inputs and recovery archives in authorized private storage.

Every available catalog release also provides a complete ZIP download: one folder containing its data and all manifest-listed supporting files. The catalog's `download` object provides the path, size and SHA-256; existing manifest and individual resource URLs remain unchanged.

`update_crashes.py` and `adopt_routes.py` preserve the entry points used by existing consumers. Maintained commands live in `scripts/`.

- [Provo intersections](data-definitions/provo-intersections/README.md) documents signal records and partial timing coverage.
