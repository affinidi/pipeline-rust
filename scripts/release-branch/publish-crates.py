#!/usr/bin/env python3
"""Publish a lockstep workspace to crates.io from a release branch.

    publish-crates.py gate                  should this push publish at all?
    publish-crates.py plan                  print the publish order and what is pending
    publish-crates.py publish [--dry-run]   publish every pending crate, in order
    publish-crates.py check-all             fail unless every crate is on crates.io

Run from the root of the repository being released (the release-publish
action does). `gate` publishes only when RELEASE exists, names a GA or patch
version (`X.Y.Z`; a release candidate publishes nothing) and equals the
workspace version; a mismatch fails rather than publishing the wrong thing.

Trusted Publishing only: no registry token is read from anywhere. For each
crate, `publish` verify-builds it (`cargo package`, the long part, with no
token in existence), then mints a fresh crates.io token from the job's OIDC
identity, uploads with `cargo publish --no-verify` (seconds), and revokes the
token. A token lives 30 minutes, so minting once up front lets a long release
outlive it; minting per crate cannot. A failed upload is retried on a new
token. The job needs `permissions: id-token: write`.

Order: a topological sort of the publishable workspace members over their
normal and build dependencies on each other, with dev-dependency edges
honoured wherever they do not form a cycle (cargo keeps a versioned
dev-dependency in the published manifest, so it must resolve when the
dependent is verified). Ties break on name, so the order is deterministic.

"Already published" is read from the crates.io sparse index, so a re-run
resumes where a previous run stopped. A crate missing from crates.io is an
error: a Trusted Publishing token cannot create a crate, so an owner publishes
its first version by hand and adds the repository's publishing workflow as
its trusted publisher.

--dry-run uploads nothing and mints no token. A crate missing from crates.io
counts as pending, and each crate is packaged together with the crates before
it, since they are not on crates.io to resolve against.

Outputs go to $GITHUB_OUTPUT when set (stdout otherwise).
"""

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from release_lib import ROOT, publishable_crates, workspace_version  # noqa: E402

INDEX = "https://index.crates.io"
TRUSTED_PUBLISHING = "https://crates.io/api/v1/trusted_publishing/tokens"
USER_AGENT = "pipeline-rust release-publish (https://github.com/affinidi/pipeline-rust)"
INDEX_WAIT_SECONDS = 15 * 60
UPLOAD_ATTEMPTS = 3


def output(**kv):
    if "reason" in kv and os.environ.get("GITHUB_ACTIONS"):
        print(f"::notice::{kv['reason']}")
    path = os.environ.get("GITHUB_OUTPUT")
    lines = "".join(f"{k}={v}\n" for k, v in kv.items())
    if path:
        with open(path, "a") as f:
            f.write(lines)
    print(lines, end="")


def cargo(*args, check=True, env=None):
    print(f"$ cargo {' '.join(args)}", flush=True)
    out = subprocess.run(["cargo", *args], cwd=ROOT, env=env)
    if check and out.returncode:
        sys.exit(f"cargo {' '.join(args)} failed (exit {out.returncode})")
    return out.returncode


def metadata():
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def publishable(pkg):
    # cargo metadata: null = anywhere, [] = publish = false, [..] = named registries.
    return pkg["publish"] is None or "crates-io" in pkg["publish"]


def publish_order():
    """[(name, version)] in an order every dependency precedes its dependents."""
    meta = metadata()
    members = set(meta["workspace_members"])
    pkgs = {p["name"]: p for p in meta["packages"] if p["id"] in members and publishable(p)}

    hard, soft = {n: set() for n in pkgs}, {n: set() for n in pkgs}
    for name, pkg in pkgs.items():
        for dep in pkg["dependencies"]:
            if dep["name"] not in pkgs or dep["name"] == name:
                continue
            (soft if dep["kind"] == "dev" else hard)[name].add(dep["name"])

    def reaches(graph, start, goal):
        seen, stack = set(), [start]
        while stack:
            n = stack.pop()
            if n == goal:
                return True
            if n not in seen:
                seen.add(n)
                stack.extend(graph[n])
        return False

    edges = {n: set(d) for n, d in hard.items()}
    for name in sorted(soft):
        for dep in sorted(soft[name]):
            if not reaches(edges, dep, name):  # adding name -> dep makes no cycle
                edges[name].add(dep)

    order, done = [], set()
    while len(order) < len(pkgs):
        ready = sorted(n for n in pkgs if n not in done and edges[n] <= done)
        if not ready:
            sys.exit(f"dependency cycle among {sorted(set(pkgs) - done)}")
        order.append(ready[0])
        done.add(ready[0])
    return [(n, pkgs[n]["version"]) for n in order]


def index_path(name):
    n = name.lower()
    if len(n) <= 2:
        return f"{len(n)}/{n}"
    if len(n) == 3:
        return f"3/{n[0]}/{n}"
    return f"{n[:2]}/{n[2:4]}/{n}"


def published_versions(name):
    """Set of versions on crates.io, or None when the crate does not exist."""
    url = f"{INDEX}/{index_path(name)}"
    for attempt in range(5):
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache"})
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode()
            return {json.loads(line)["vers"] for line in body.splitlines() if line.strip()}
        except urllib.error.HTTPError as e:
            if e.code in (403, 404, 410):
                return None
            err = e
        except (urllib.error.URLError, TimeoutError) as e:
            err = e
        time.sleep(5 * (attempt + 1))
    sys.exit(f"could not read the crates.io index for {name}: {err}")


def pending(order, dry_run=False):
    out = []
    for name, version in order:
        versions = published_versions(name)
        if versions is None and not dry_run:
            sys.exit(
                f"{name} does not exist on crates.io. A Trusted Publishing token cannot create a "
                "crate: an owner publishes its first version by hand, then adds this repository's "
                "publishing workflow as its trusted publisher."
            )
        if version not in (versions or set()):
            out.append((name, version))
    return out


def http_json(method, url, headers, body=None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers={"User-Agent": USER_AGENT, **headers})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else {}


def mint_token():
    """A crates.io token for this job's OIDC identity, valid 30 minutes."""
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
    if not url or not bearer:
        sys.exit("no OIDC token available: the publishing job needs `permissions: id-token: write`")
    jwt = http_json("GET", f"{url}&audience=crates.io", {"Authorization": f"bearer {bearer}"}).get("value")
    if not jwt:
        sys.exit("the OIDC token request returned no token")
    print(f"::add-mask::{jwt}", flush=True)
    try:
        token = http_json("POST", TRUSTED_PUBLISHING, {"Content-Type": "application/json"}, {"jwt": jwt}).get("token")
    except urllib.error.HTTPError as e:
        sys.exit(
            f"crates.io refused the Trusted Publishing exchange (HTTP {e.code}). Is a trusted publisher "
            "configured for this repository, workflow file and environment on every crate?"
        )
    if not token:
        sys.exit("crates.io returned no token")
    print(f"::add-mask::{token}", flush=True)
    return token


def revoke_token(token):
    try:
        http_json("DELETE", TRUSTED_PUBLISHING, {"Authorization": f"Bearer {token}"})
    except (urllib.error.URLError, TimeoutError):
        print("::warning::could not revoke a Trusted Publishing token; it expires within 30 minutes")


def wait_for_index(name, version):
    deadline = time.monotonic() + INDEX_WAIT_SECONDS
    while time.monotonic() < deadline:
        if version in (published_versions(name) or set()):
            print(f"{name} {version} is in the index")
            return
        print(f"waiting for {name} {version} to reach the index…", flush=True)
        time.sleep(15)
    sys.exit(f"{name} {version} uploaded but not visible in the index after {INDEX_WAIT_SECONDS}s")


def upload(name, version):
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        token = mint_token()
        try:
            rc = cargo("publish", "-p", name, "--locked", "--no-verify", check=False,
                       env={**os.environ, "CARGO_REGISTRY_TOKEN": token})
        finally:
            revoke_token(token)
        # A failed attempt may still have landed (the error came after the upload).
        if rc == 0 or version in (published_versions(name) or set()):
            return
        print(f"::warning::uploading {name} {version} failed (attempt {attempt} of {UPLOAD_ATTEMPTS})")
        time.sleep(30 * attempt)
    sys.exit(f"could not upload {name} {version} after {UPLOAD_ATTEMPTS} attempts")


def cmd_gate(args):
    release = ROOT / "RELEASE"
    if not release.exists():
        output(publish="false", reason="no RELEASE file: not a release branch")
        return 0
    rel = release.read_text().strip()
    ws = workspace_version(ROOT)
    if "-" in rel:
        output(publish="false", reason=f"RELEASE {rel} is a release candidate; crates publish at GA")
        return 0
    if rel != ws:
        print(f"::error::RELEASE says {rel} but the workspace version is {ws}; refusing to publish")
        return 1
    # No cargo needed: the publishable members come straight from the manifests.
    todo = pending([(name, ws) for name in sorted(publishable_crates(ROOT))], dry_run=args.dry_run)
    if not todo:
        output(publish="false", reason=f"every crate is already on crates.io at {ws}")
        return 0
    output(publish="true", reason=f"{len(todo)} crate(s) to publish at {ws}", version=ws)
    return 0


def cmd_plan(args):
    order = publish_order()
    todo = {n for n, _ in pending(order, args.dry_run)}
    for i, (name, version) in enumerate(order, 1):
        print(f"{i}. {name} {version} {'(pending)' if name in todo else '(on crates.io)'}")
    return 0


def cmd_publish(args):
    order = publish_order()
    names = [n for n, _ in order]
    todo = pending(order, args.dry_run)
    if not todo:
        print("nothing left to publish")
        return 0
    for name, version in todo:
        print(f"::group::{name} {version}", flush=True)
        if args.dry_run:
            upto = names[: names.index(name) + 1]
            cargo("package", *[a for n in upto for a in ("-p", n)], "--locked")
            print(f"dry run: would upload {name} {version}")
        else:
            # The verify build: the packaged tarball built against
            # registry-resolved dependencies. No token exists yet.
            cargo("package", "-p", name, "--locked")
            upload(name, version)
            wait_for_index(name, version)
        print("::endgroup::", flush=True)
    return 0


def cmd_check_all(args):
    if args.dry_run:
        print("dry run: nothing was uploaded")
        return 0
    todo = pending(publish_order())
    if todo:
        for name, version in todo:
            print(f"::error::{name} {version} is not on crates.io")
        print("Re-run the publishing workflow: it resumes from the first missing crate.")
        return 1
    print("every publishable crate is on crates.io")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("gate", cmd_gate), ("plan", cmd_plan), ("publish", cmd_publish), ("check-all", cmd_check_all)):
        p = sub.add_parser(name)
        p.add_argument("--dry-run", action="store_true", help="upload nothing, mint no token")
        p.set_defaults(fn=fn)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
