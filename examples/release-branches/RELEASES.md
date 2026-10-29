# Releases

A release is named by its `major.minor` version (`0.4`, `0.5`, …). It is cut
from `nightly`, stabilised and patched on its own branch for as long as it is
supported, and published from there. Every crate in the workspace carries the
release's version. The release workflows run the `release-*` actions of
[affinidi/pipeline-rust](https://github.com/affinidi/pipeline-rust) (README,
"Release branches").

## Branches

```
feature/*  ──PR──▶  main  ──(nightly.yml: last fully green commit)──▶  nightly
                                                                         │
                          release/0.4 ◀── Cut a release ─────────────────┘
```

| Branch | What it is |
|---|---|
| `main` | Every PR lands here first. Carries the *next* release's version and publishes nothing. |
| `nightly` | The newest `main` commit on which every CI job passed. Releases are cut from here. |
| `release/<major.minor>` | One release, from its cut to its end of life. Takes backported fixes only. |

## Versions and tags

`[workspace.package] version` in the root `Cargo.toml` is every crate's
version, and every internal dependency requires exactly that version. Nobody
edits it by hand: the cut and prep workflows move it, and the `release guards`
check fails a tree where the versions disagree. On a release branch, the
`RELEASE` file names the current release; its tag is `v` + `RELEASE`.

| Step | How | `RELEASE` | Tag | crates.io |
|---|---|---|---|---|
| Cut | Actions → **Cut a release** on `main`, name `0.4` | `0.4.0-rc.0` | `v0.4.0-rc.0` (prerelease) | no |
| Next candidate | Actions → **Prepare a release** on `release/0.4`, kind `rc`; merge its PR | `0.4.0-rc.N` | `v0.4.0-rc.N` | no |
| GA | the same, kind `ga` | `0.4.0` | `v0.4.0` | `0.4.0` |
| Patch | the same, kind `patch` | `0.4.N` | `v0.4.N` | `0.4.N` |

Only an admin or maintainer may cut. The cut also opens a PR that moves `main`
to the next minor and starts a new `## Unreleased` section in `CHANGELOG.md`;
merge it. Merging a prep PR is the release: it is tagged, and a GA or patch is
published to crates.io.

## Schedule

| Release | Branch | GA | Latest | Status |
|---|---|---|---|---|
| 0.4 | `release/0.4` | TBD | — | in development |

## What goes on a release branch

Fix on `main` first. Then label the merged PR `backport release/<major.minor>`,
one label per branch, and a backport PR opens on that branch. Only when the
code no longer exists on `main` does a maintainer label a PR into the release
branch `release-direct`, and its description says why. The `branch rules`
check enforces this.

## New crate

Trusted Publishing publishes only to a crate that already exists. A crate
owner publishes its first version by hand, then adds this repository, workflow
`publish.yml` and environment `release` as its trusted publisher on crates.io.
