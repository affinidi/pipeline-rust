#!/usr/bin/env bash
#
# Check that the pushed tag is `v<version>` of the package that owns the binary.
#
# Finds the workspace package with a [[bin]] target named BINARY (restricted to
# PACKAGE when it is set) through `cargo metadata`, and fails unless exactly one
# package matches and GITHUB_REF_NAME equals `v` plus its version. Writes the
# owning package and its version as `package=` and `version=` lines to
# GITHUB_OUTPUT, or to stdout when GITHUB_OUTPUT is unset.
#
# Run it from the root of the workspace.
#
# Requires on PATH: cargo, jq.
# Requires env:     BINARY, GITHUB_REF_TYPE, GITHUB_REF_NAME.
# Optional env:     PACKAGE, GITHUB_OUTPUT.
#
# Used by .github/workflows/release-binaries.yaml. It is a standalone script
# rather than an inline `run:` block so it can be run and tested locally.

set -euo pipefail

: "${BINARY?BINARY must be set}"
: "${GITHUB_REF_TYPE?GITHUB_REF_TYPE must be set}"
: "${GITHUB_REF_NAME?GITHUB_REF_NAME must be set}"
PACKAGE="${PACKAGE:-}"

if [ "${GITHUB_REF_TYPE}" != "tag" ]; then
  echo "::error::Release binaries are built from a version tag, got ${GITHUB_REF_TYPE} ${GITHUB_REF_NAME}"
  exit 1
fi
matches="$(cargo metadata --no-deps --format-version 1 --locked \
  | jq -r --arg bin "${BINARY}" --arg pkg "${PACKAGE}" \
    '.packages[]
     | select($pkg == "" or .name == $pkg)
     | select(any(.targets[]; .name == $bin and (.kind | index("bin"))))
     | "\(.name) \(.version)"')"
if [ -z "${matches}" ]; then
  if [ -n "${PACKAGE}" ]; then
    echo "::error::Package ${PACKAGE} has no binary named ${BINARY}"
  else
    echo "::error::No workspace package has a binary named ${BINARY}"
  fi
  exit 1
fi
if [ "$(printf '%s\n' "${matches}" | grep -c .)" -ne 1 ]; then
  echo "::error::More than one package has a binary named ${BINARY}: ${matches//$'\n'/, }. Set the package input to pick one."
  exit 1
fi
read -r owner version <<< "${matches}"
if [ "${GITHUB_REF_NAME}" != "v${version}" ]; then
  echo "::error::Tag ${GITHUB_REF_NAME} does not match ${owner} version ${version}, expected v${version}"
  exit 1
fi
{
  echo "package=${owner}"
  echo "version=${version}"
} >> "${GITHUB_OUTPUT:-/dev/stdout}"
