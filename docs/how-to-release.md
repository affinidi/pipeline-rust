# How to release

For a repository set up as in the README, "Adopting release branches". The
examples release `0.4`.

| Task | Who | How |
|---|---|---|
| Cut `release/0.4` | admin or maintainer | Actions → **Cut a release** |
| Next rc, GA or patch | anyone with write access opens it; review merges it | Actions → **Prepare a release** |
| Backport a fix | anyone who can label PRs | label the merged PR `backport release/0.4` |

Every step opens a PR, and merging it is what takes effect.

## Cut a release

A cut creates `release/0.4` at `0.4.0-rc.0` and moves `main` to `0.5.0`.

1. Actions → **Cut a release** → **Run workflow**, from `main`:
   - `name`: `0.4`
   - `from`: `origin/nightly`, the newest `main` commit on which all of CI
     passed. Before `nightly` exists, `origin/main`. To move `nightly` first,
     run **Nightly**.
   - `dry-run`: ticked
2. Read the log. It prints both commits and ends with `dry run: nothing pushed`.
3. Run it again with `dry-run` cleared. It:
   - pushes `release/0.4`, which **Tag a release** tags `v0.4.0-rc.0`
     (a prerelease; nothing is published to crates.io);
   - opens the `release-cut/0.4` PR, which moves `main` to `0.5.0` and closes
     `main`'s `## Unreleased` changelog section under `## 0.4.0`;
   - creates the `backport release/0.4` label.
4. Review and merge `release-cut/0.4`. If the log warned that `CHANGELOG.md`
   was not split, move the shipped entries under `## 0.4.0` in that PR first.
5. Add `0.4` to the schedule in `RELEASES.md`.

The cut refuses:

| Message | Meaning |
|---|---|
| `run the cut from main, not <ref>` | Start **Cut a release** with `main` as the branch. |
| `<login> may not cut a release` | Whoever started the run needs the admin or maintain role. |
| `<rev> (<sha>) is not on main` | Cut from a commit `main` has, normally `origin/nightly`. |
| `release/0.4 already exists` | That release is cut already. Prepare its next version instead. |

## Release candidate, GA, patch

1. Actions → **Prepare a release** → **Run workflow**, from `release/0.4`,
   with `kind`:

   | `kind` | `RELEASE` moves | Also |
   |---|---|---|
   | `rc` | `0.4.0-rc.N` → `0.4.0-rc.N+1` | |
   | `ga` | `0.4.0-rc.N` → `0.4.0` | `## Unreleased` becomes `## 0.4.0 (date)` |
   | `patch` | `0.4.N` → `0.4.N+1` | every crate moves to `0.4.N+1`; a changelog section lists the commits since `v0.4.N` |

2. It opens the `release-prep/0.4/<version>` PR, titled
   `chore(release): v<version>`. Review `RELEASE`, the changelog and, for a
   patch, the versions.
3. Merge it. That is the release: **Tag a release** tags `v<version>` and
   opens its GitHub Release, and for a GA or patch **Publish crates**
   publishes to crates.io.

The prep refuses:

| Message | Meaning |
|---|---|
| `<version> is GA; an rc comes before GA. Use patch.`, `<version> is already GA. Use patch.` | After GA, only patches. |
| `<version> is a release candidate; use rc or ga first.` | A patch comes after GA. |
| `CHANGELOG.md has no ## Unreleased section to release` | GA releases the `## Unreleased` section; add one. |
| `nothing has changed since v<version>` | Backport something first. |
| `tag v<version> is missing` | **Tag a release** didn't run for the last release; rerun it. |

## Backport a fix

1. Merge the fix into `main`.
2. Label the merged PR `backport release/0.4`, one label per release branch.
   A `backport-<pr>-to-release/0.4` PR opens. If the cherry-pick conflicts, it
   opens as a draft with the conflict committed: resolve it on that branch.
   A conflict in `CHANGELOG.md` is expected; drop that hunk, since a patch's
   changelog comes from commit subjects.
3. Review and merge the backport, then prepare an `rc` or `patch`.

Only when the code no longer exists on `main` does a fix go straight into
`release/0.4`: a maintainer labels that PR `release-direct`, and its
description says why. A label anyone else added fails `branch rules`; a
maintainer removes it and adds it again.

## Without the release bot

A repository moving to the release bot may still cut and prepare from a
maintainer's machine. This is transitional, and it needs
`maintainer-releases: "true"` on `release-branch-rules`, so that a cut or prep
PR from an admin or maintainer counts. Where a ruleset lets only the release
bot and admins create `release/*` branches, only an admin can cut.

From a clean checkout of the repository, with Python 3.11 or later, cargo,
`gh` signed in, push access, and pipeline-rust checked out next to it at the
commit the workflows pin:

```sh
S=../pipeline-rust/scripts/release-branch
```

Cut. The same checks apply, except the role check: who may push the branch
decides.

```sh
git fetch origin
python3 $S/cut-release.py 0.4 --dry-run    # builds both commits, pushes nothing
python3 $S/cut-release.py 0.4              # --from origin/main before nightly exists
```

Then steps 4 and 5 of [Cut a release](#cut-a-release).

Release candidate, GA or patch:

```sh
git switch release/0.4 && git pull --ff-only
python3 $S/prepare-release.py --kind rc --pr-body ../body.md    # or ga, patch
v=$(cat RELEASE)
git switch -c "release-prep/0.4/$v"
git add -A && git commit -s -m "chore(release): v$v"
git push origin HEAD
gh pr create --base release/0.4 --title "chore(release): v$v" --body-file ../body.md
```

Then step 3 of [Release candidate, GA, patch](#release-candidate-ga-patch).
