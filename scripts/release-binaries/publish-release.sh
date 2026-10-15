#!/usr/bin/env bash
#
# Publish the GitHub Release for TAG with every *.tar.gz archive and SHA256SUMS
# in the current directory attached.
#
# The release is created as a draft with every file attached and published
# last, so nobody sees a release with missing archives. A rerun replaces a
# leftover draft but never touches a published release. A tag that contains
# `-`, such as v1.4.0-rc.1, becomes a pre-release.
#
# Run it from the directory that holds the archives and SHA256SUMS.
#
# Requires on PATH: gh.
# Requires env:     TAG, GH_REPO, GH_TOKEN (consumed by gh, needs contents: write).
#
# Used by .github/workflows/release-binaries.yaml. It is a standalone script
# rather than an inline `run:` block so it can be run and tested locally.

set -euo pipefail

: "${TAG?TAG must be set}"
: "${GH_REPO?GH_REPO must be set}"

if is_draft="$(gh release view "${TAG}" --json isDraft --jq .isDraft 2>/dev/null)"; then
  if [ "${is_draft}" != "true" ]; then
    echo "::error::Release ${TAG} is already published. Delete it or push a new tag."
    exit 1
  fi
  gh release delete "${TAG}" --yes
fi
prerelease_args=()
if [[ "${TAG}" == *-* ]]; then
  prerelease_args=(--prerelease)
fi
gh release create "${TAG}" --draft --verify-tag --title "${TAG}" --generate-notes \
  "${prerelease_args[@]}" -- *.tar.gz SHA256SUMS
gh release edit "${TAG}" --draft=false
