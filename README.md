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

## Choosing the runner

`checks.yaml`, `checks-no-test.yaml` and `checks-test-only.yaml` take an
optional `runs-on` input (default `ubuntu-24.04`). It applies to the jobs that
compile the workspace: cargo check, clippy, test, coverage, verify-publish and
deprecation-check. fmt, audit and cargo-deny always run on the default runner.

Use it to move those jobs to a larger GitHub-hosted runner. Falling back to the
default when a repository variable is unset keeps the caller working before the
runner exists:

```yaml
jobs:
  rust-pipeline:
    uses: affinidi/pipeline-rust/.github/workflows/checks.yaml@main
    secrets: inherit
    with:
      runs-on: ${{ vars.CI_RUNNER_LARGE || 'ubuntu-24.04' }}
```

Larger runners are billed even for public repositories, and the runner's group
must allow the calling repository.

`release.yaml` takes the same `runs-on` input for its publish job, plus
`build-jobs` (default `0`, cargo's default of one job per CPU). Lower it when
verifying a large crate exhausts the runner's memory and the job is killed
mid-publish:

```yaml
jobs:
  rust-pipeline:
    uses: affinidi/pipeline-rust/.github/workflows/release.yaml@main
    secrets: inherit
    with:
      runs-on: ${{ vars.CI_RUNNER_LARGE || 'ubuntu-24.04' }}
      build-jobs: 2
```

## Publishing new crate

The release pipeline uses [crates.io Trusted Publishing](https://crates.io/docs/trusted-publishing) — no `CARGO_REGISTRY_TOKEN` secret needed once configured.

Run once per repository or when adding new crate (requires a crates.io API token):

```bash
git clone https://github.com/affinidi/pipeline-rust
cd pipeline-rust
# or 
curl https://raw.githubusercontent.com/affinidi/pipeline-rust/refs/main/scripts/setup-trusted-publishing.sh | bash
./scripts/setup-trusted-publishing.sh ~/path/to-repo-rs/ --dry-run
```

Use `--dry-run` to preview without making changes.
