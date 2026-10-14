#!/usr/bin/env bash
#
# Report the highest glibc version a release binary needs, and fail when it is
# newer than MAX_GLIBC.
#
# Reads the dynamic symbols of target/<TARGET>/release/<BINARY> with objdump
# (aarch64-linux-gnu-objdump for the aarch64 target) and takes the highest
# GLIBC_x.y version among them. A static binary needs no glibc at run time and
# always passes. An empty MAX_GLIBC only reports the version.
#
# Run it from the root of the workspace, after the release build.
#
# Requires on PATH: objdump, or aarch64-linux-gnu-objdump for the aarch64 target.
# Requires env:     TARGET, BINARY.
# Optional env:     MAX_GLIBC.
#
# Used by .github/workflows/release-binaries.yaml. It is a standalone script
# rather than an inline `run:` block so it can be run and tested locally.

set -euo pipefail

: "${TARGET?TARGET must be set}"
: "${BINARY?BINARY must be set}"
MAX_GLIBC="${MAX_GLIBC:-}"

objdump=objdump
if [ "${TARGET}" = "aarch64-unknown-linux-gnu" ]; then
  objdump=aarch64-linux-gnu-objdump
fi
# objdump exits 1 with "not a dynamic object" for a static binary,
# which needs no glibc at run time.
if ! symbols="$("${objdump}" -T "target/${TARGET}/release/${BINARY}" 2>&1)"; then
  if ! grep -q 'not a dynamic object' <<< "${symbols}"; then
    printf '%s\n' "${symbols}"
    echo "::error::${objdump} could not read the symbols of ${BINARY} for ${TARGET}"
    exit 1
  fi
  symbols=""
fi
needed="$(grep -o 'GLIBC_[0-9.]*' <<< "${symbols}" | sort -uV | tail -n 1 || true)"
if [ -z "${needed}" ]; then
  echo "${BINARY} for ${TARGET} needs no glibc symbols"
  exit 0
fi
needed="${needed#GLIBC_}"
echo "${BINARY} for ${TARGET} needs glibc ${needed}"
if [ -z "${MAX_GLIBC}" ]; then
  exit 0
fi
lowest="$(printf '%s\n%s\n' "${needed}" "${MAX_GLIBC}" | sort -V | head -n 1)"
if [ "${lowest}" != "${needed}" ]; then
  echo "::error::${BINARY} for ${TARGET} needs glibc ${needed}, newer than max-glibc ${MAX_GLIBC}"
  exit 1
fi
