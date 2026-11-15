#!/usr/bin/env python3
"""Prepare the next rc, GA or patch on a release branch (RELEASES.md).

    prepare-release.py --kind rc|ga|patch [--pr-body FILE] [--main-changelog FILE]

Run by `release-prep.yml` from a checkout of `release/<major.minor>`; it
edits the tree and the workflow commits it as a `chore(release): v…` PR on a
`release-prep/<major.minor>/<version>` branch. Merging that PR is the
release: `release-tag.yml` tags `v<RELEASE>`, and
`publish.yml` publishes the crates for a GA or patch.

  rc     0.42.0-rc.N -> 0.42.0-rc.N+1   RELEASE only.
  ga     0.42.0-rc.N -> 0.42.0          RELEASE; CHANGELOG `## Unreleased`
                                        becomes `## 0.42.0 (date)`; with
                                        --main-changelog, main's `## 0.42.0 …`
                                        heading gets the same date.
  patch  0.42.N      -> 0.42.N+1        the workspace version (lockstep: every
                                        crate and internal requirement);
                                        RELEASE; a CHANGELOG section listing
                                        the commits since the last tag.

A patch's entries come from the commit subjects since the previous tag, not
from cherry-picked CHANGELOG hunks: a backport's hunk lands in main's
`## Unreleased`, which does not exist on a GA'd branch, so resolve such a
conflict by dropping the hunk. Commit subjects are conventional, so they read
as entries.

main keeps its own copy of a release's notes: the cut closes main's
`## Unreleased` as `## 0.42.0 (unreleased)`. --main-changelog names main's
CHANGELOG.md in a separate checkout (release-prep.yml uses a worktree of
origin/main); at GA it is rewritten in place so its `## 0.42.0 …` heading is
the very heading the release branch gets, and the action opens a PR to main
with it. Headings from older cuts (`## 0.42.0 (release/0.42)`) are dated the
same way. A main without the heading (the cut PR not merged yet, or the
notes moved by hand) is left alone with a warning: the GA does not wait on it.
"""

import argparse
import datetime
import pathlib
import sys

from release_lib import (
    ROOT,
    date_heading,
    git,
    insert_section,
    parse_release,
    release_heading,
    set_version,
    unreleased_split,
    version_heading,
    workspace_version,
)


def commits_since(tag):
    if git("rev-parse", "-q", "--verify", f"refs/tags/{tag}", check=False).returncode:
        return None
    out = git("log", "--no-merges", "--format=%s", f"{tag}..HEAD").stdout.splitlines()
    return [s for s in out if not s.startswith("chore(release)")]


def date_main(path, version, date):
    """Give main's `## <version> …` heading the GA's date; warn, never fail, when it can't."""
    main_log = pathlib.Path(path)
    if not main_log.exists():
        print(f"WARNING: {path} does not exist; main's changelog not dated", file=sys.stderr)
        return
    # newline="" keeps the file's line endings: a CRLF changelog is not rewritten wholesale.
    with open(main_log, newline="") as f:
        text = f.read()
    if len(version_heading(version).findall(text)) > 1:
        print(
            f"WARNING: main's CHANGELOG.md has more than one `## {version}` heading; dating the first", file=sys.stderr
        )
    dated = date_heading(text, version, date)
    if dated is None:
        print(
            f"WARNING: main's CHANGELOG.md has no `## {version}` heading (is the release-cut PR merged?); "
            f"add `{release_heading(version, date)}` there by hand",
            file=sys.stderr,
        )
    elif dated == text:
        print(f"main's CHANGELOG.md already reads `{release_heading(version, date)}`")
    else:
        with open(main_log, "w", newline="") as f:
            f.write(dated)
        print(f"main's CHANGELOG.md: `## {version}` heading dated {date}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", required=True, choices=["rc", "ga", "patch"])
    ap.add_argument("--pr-body", help="write the PR description here")
    ap.add_argument(
        "--main-changelog", help="at GA, date this version's heading in main's CHANGELOG.md (a separate checkout)"
    )
    args = ap.parse_args()

    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    release_file = ROOT / "RELEASE"
    if not release_file.exists():
        sys.exit("no RELEASE file: run this on a release/<major.minor> branch")
    current = release_file.read_text().strip()
    major, minor, patch, rc = parse_release(current)
    if branch not in ("HEAD", f"release/{major}.{minor}"):
        sys.exit(f"RELEASE says {current}, but this is {branch}")
    crates = workspace_version(ROOT)
    if crates != f"{major}.{minor}.{patch}":
        sys.exit(f"RELEASE says {current} but the workspace is at {crates}; fix the branch first")

    today = datetime.date.today().isoformat()
    changelog = ROOT / "CHANGELOG.md"
    if not changelog.exists():
        sys.exit("no CHANGELOG.md at the repository root")
    text = changelog.read_text()
    since = commits_since(f"v{current}")

    if args.kind == "rc":
        if rc is None:
            sys.exit(f"{current} is GA; an rc comes before GA. Use `patch`.")
        target = f"{major}.{minor}.{patch}-rc.{rc + 1}"
    elif args.kind == "ga":
        if rc is None:
            sys.exit(f"{current} is already GA. Use `patch`.")
        target = f"{major}.{minor}.{patch}"
        parts = unreleased_split(text)
        if not parts:
            sys.exit("CHANGELOG.md has no `## Unreleased` section to release")
        before, body, after = parts
        changelog.write_text(f"{before}{release_heading(target, today)}\n{body}{after}")
        if args.main_changelog:
            date_main(args.main_changelog, target, today)
    else:
        if rc is not None:
            sys.exit(f"{current} is a release candidate; use `rc` or `ga` first.")
        if since is None:
            sys.exit(f"tag v{current} is missing: did the release-tag action run for it?")
        if not since:
            sys.exit(f"nothing has changed since v{current}")
        target = f"{major}.{minor}.{patch + 1}"
        set_version(ROOT, target)
        entries = "".join(f"- {s}\n" for s in since)
        parts = unreleased_split(text)
        if parts:
            # A backport brought its own `## Unreleased` notes: they are this patch's.
            before, body, after = parts
            text = f"{before}{release_heading(target, today)}\n{body.rstrip()}\n\n### Commits\n\n{entries}\n{after}"
        else:
            text = insert_section(text, f"{release_heading(target, today)}\n\n{entries}\n")
        changelog.write_text(text)

    release_file.write_text(f"{target}\n")
    print(f"{current} -> {target}")

    if args.pr_body:
        lines = [f"Prepares **v{target}** on `release/{major}.{minor}` (was `v{current}`).", ""]
        lines.append(f"Merging this PR is the release: it is tagged `v{target}` on merge.")
        if "-rc." not in target:
            lines.append("Its crates are then published to crates.io at this version.")
        if since:
            lines += ["", f"Changes since `v{current}`:", ""] + [f"- {s}" for s in since]
        with open(args.pr_body, "w") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
