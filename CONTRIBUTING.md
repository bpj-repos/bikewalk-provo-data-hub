# Contributing and reuse

Anyone with repository access can propose a change. Fork the repository, work on a branch, run the checks below, and open a pull request describing the change and how you tested it. Once the repository is public, anyone can clone it for another project or submit a PR. Other contributors need Bryce's explicit approval on GitHub (@brycepj) before merging. Bryce can merge and push directly to main, and his own PRs require no approval. Maintainers review release pins and deployment separately.

## Try the synthetic counts example

With Python 3.12, from a fresh clone:

    python3 -m scripts.build_demo_counts build build/demo
    python3 -m scripts.build_demo_counts validate build/demo
    python3 -m unittest -v tests.hub.test_release

Open the series.csv under build/demo/datasets to see how an observed zero differs from a missing survey session. Use a fresh output directory for each build. To run the broader suites, create a virtual environment, install ./pipelines/crashes with pip, put Node on PATH, and follow the [test guide](tests/README.md). Private-input cases report skips.

Use invented records or an approved public release for examples and tests. Keep source deliveries, diagnostic output, crash narratives, identifying details, keys and local paths out of commits, issues and attachments. For a suspected disclosure, follow [private reporting](SECURITY.md). For a change in what a record means, identify the dataset, current pin, proposed rule and affected consumers. Preserve old release bytes.

## Reuse in another project

Copy, modify and redistribute original BikeWalk Provo code and associated original documentation under the [MIT license](LICENSE). Include its copyright and license notice. Code contributions are offered under the same terms.

Dataset permissions come from each version's datapackage.json, source notices and dataset contract. The approved counts product has a CC0 dedication. For crash, Safe Routes and citywide stress packages, check the specific version's reuse and attribution text and each named provider's terms. Synthetic counts carry their own demonstration notice. Upstream manuals, HTML and GIS reference captures, third-party material in frozen evidence and private inputs retain their source terms. Consult the source steward when redistribution permission is undocumented. A fork should use its own deployment account and private inputs.
