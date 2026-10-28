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

## Linux release binaries

`release-binaries.yaml` builds a binary for x86_64 and aarch64 Linux when a
`v<version>` tag is pushed, smoke tests it on Debian bookworm-slim and attaches
`<binary>-<version>-<target>.tar.gz` archives plus a `SHA256SUMS` file to the
tag's GitHub Release. The tag must match the package version in `Cargo.toml`.

Builds run in a Debian bookworm container, so the binaries need at most glibc
2.36. aarch64 is cross compiled on the standard x86_64 runner.

Add `.github/workflows/release-binaries.yaml` to your repository:

```yaml
name: release-binaries

on:
  push:
    tags:
      - "v*"

permissions:
  contents: read

jobs:
  linux-binaries:
    uses: affinidi/pipeline-rust/.github/workflows/release-binaries.yaml@<commit>
    permissions:
      contents: write  # only the final publish job uses it
    with:
      binary: my-cli
      toolchain: '1.96.0'
      apt-deps: libssl-dev              # -dev packages the build links against, default none
      smoke-test-apt-deps: libssl3 ca-certificates  # run-time packages, default none (bare image)
      max-glibc: '2.34'                 # fail the build if the binary needs a newer glibc
```

| Input | Default | What it does |
|---|---|---|
| `binary` | required | Name of the `[[bin]]` target to ship. Also the archive name prefix. |
| `package` | empty | Package that owns the binary. Needed only when more than one workspace package has a bin of that name. Empty finds the owning package from `cargo metadata`. |
| `toolchain` | `stable` | Rust toolchain used for the build. |
| `targets` | `["x86_64-unknown-linux-gnu", "aarch64-unknown-linux-gnu"]` | JSON list of targets to build. Only these two are supported. |
| `apt-deps` | empty | Debian `-dev` packages the build links against, installed for each target's architecture. |
| `smoke-test-apt-deps` | empty | Debian packages the binary needs at run time, installed in the smoke test image. Binaries that make HTTPS calls with the system's root certificates usually need `ca-certificates`. |
| `smoke-test` | empty | Extra shell commands run after `<binary> --version` and `<binary> --help`, with the binary on `PATH`. |
| `max-glibc` | empty | Highest glibc version the binary may need, for example `2.34`. The build fails if it needs a newer one. Empty skips the check. |
| `runs-on` | `ubuntu-24.04` | Runner for the build jobs. Must be an x86_64 Linux runner with Docker. See [Choosing the runner](#choosing-the-runner). |

The smoke test runs on a bare `debian:bookworm-slim` image with only the
`smoke-test-apt-deps` packages added. `--version` and `--help` make no network
calls, so a missing `ca-certificates` only shows up if `smoke-test` makes an
HTTPS call.

Release rules:

- Push the `v<version>` tag and let the workflow create the release. Do not
  create the release in the GitHub UI, because the run fails when the tag
  already has a published release.
- A published release is never replaced. To ship a fix, push a new tag.
- A tag that contains `-`, such as `v1.4.0-rc.1`, becomes a pre-release.
- Rerunning a failed run replaces the draft release that run left behind.
- The tag must equal `v` plus the version in the owning package's
  `Cargo.toml`, so `v1.4.0` for version `1.4.0`.

## Release branches

An alternative to `release.yaml` for a workspace that versions every crate in
lockstep and supports releases on their own branches. `main` carries the next
version and never publishes; a release is cut to `release/<major.minor>`,
stabilised with release candidates, published at GA and patched by backport.

| Step | Action | `RELEASE` | Tag | crates.io |
|---|---|---|---|---|
| Cut | `release-cut` | `0.4.0-rc.0` | `v0.4.0-rc.0` (prerelease) | no |
| Next candidate | `release-prep`, kind `rc` | `0.4.0-rc.N` | `v0.4.0-rc.N` | no |
| GA | `release-prep`, kind `ga` | `0.4.0` | `v0.4.0` | `0.4.0` |
| Patch | `release-prep`, kind `patch` | `0.4.N` | `v0.4.N` | `0.4.N` |

Merging a prep PR is the release: `release-tag` tags it and `release-publish`
publishes it. The other actions keep the flow honest: `release-guards`
(lockstep versions, CHANGELOG.md and RELEASE agree), `release-branch-rules`
(fixes reach a release branch by backport, only the tooling moves versions),
`release-backport`, `release-nightly` (cuts come from the newest fully green
`main`) and `release-dco`.

They are composite actions under `.github/actions/release-*`; each checks out
the repository itself. The scripts they run are in `scripts/release-branch`
and come with the action at the ref you pin, so nothing is copied into your
repository. They need Python 3.11 or later on the runner.

`release-publish` uses crates.io Trusted Publishing only. It verify-builds
each crate, then mints a token for that crate alone, uploads and revokes it,
so a long release never outlives a 30-minute token. Because the action runs
inside your workflow, the trusted publisher on crates.io names your
repository, your workflow file and its environment:

```yaml
name: Publish crates   # .github/workflows/publish.yml: the trusted publisher names this file

on:
  push:
    branches: ["release/**"]
  workflow_dispatch:

jobs:
  publish:
    if: startsWith(github.ref, 'refs/heads/release/')
    runs-on: ubuntu-24.04
    environment: release
    permissions:
      id-token: write
      contents: read
    steps:
      - uses: affinidi/pipeline-rust/.github/actions/release-publish@<commit>
```

`release-cut`, `release-prep` and `release-backport` need a GitHub App
`token`: what `GITHUB_TOKEN` pushes or opens triggers no workflow, and
`release-branch-rules` accepts a cut, prep or backport PR only from a branch
of the repository opened by that app, since anyone can name a branch. Its
`release-bot` input is the app's login, `affinidi-semantic-release[bot]` by
default.
`maintainer-releases: "true"` also accepts a cut or prep PR opened by a person
with the admin or maintain role, for a repository that still cuts and preps
with local scripts. It is transitional: use the `release-cut` and
`release-prep` workflows instead.
`release-tag` needs one that may create tags under your tag rules.

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

`release-binaries.yaml` takes `runs-on` for its build jobs only; the smoke test
and release jobs stay on `ubuntu-24.04`. It must be an x86_64 Linux runner
with Docker, because the build runs in a Debian bookworm container that builds
x86_64 natively and cross compiles aarch64.

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
