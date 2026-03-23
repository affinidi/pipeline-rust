# pipeline-rust

pipeline for Affinidi rust projects

## How to use

1. add file to `.github/workflows/checks.yaml`

```yaml
name: checks

on:
  pull_request_target:
    types:
      - opened
      - synchronize

jobs:
  rust-pipeline:
    uses: affinidi/pipeline-rust/.github/workflows/checks.yaml@main
    secrets: inherit
    with:
      auditIgnore: "RUSTSEC-2022-0040,RUSTSEC-2023-0071,RUSTSEC-2024-0373"
```

2. add file to `.github/workflows/release.yaml`

```yaml
name: "release"

on:
  push:
    branches:
      - main

jobs:
  rust-pipeline:
    uses: affinidi/pipeline-rust/.github/workflows/release.yaml@main
    secrets: inherit
    with:
      auditIgnore: "RUSTSEC-2022-0040,RUSTSEC-2023-0071,RUSTSEC-2024-0373"
```

## Publishing new crate

The release pipeline uses [crates.io Trusted Publishing](https://crates.io/docs/trusted-publishing) — no `CARGO_REGISTRY_TOKEN` secret needed once configured.

Run once per repository or when adding new crate (requires a crates.io API token):

```bash
git clone https://github.com/affinidi/pipeline-rust
cd pipeline-rust
cp ./scripts/setup-trusted-publishing.sh ../repo-rs/
 CARGO_REGISTRY_TOKEN=<token> ./scripts/setup-trusted-publishing.sh --owner <org> --repo <repo>
```

Use `--dry-run` to preview without making changes.
