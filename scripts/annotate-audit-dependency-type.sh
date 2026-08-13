#!/usr/bin/env bash
#
# Annotate open RustSec audit issues with direct/transitive dependency info.
#
# actions-rust-lang/audit (https://github.com/actions-rust-lang/audit) creates one GitHub
# issue per RustSec finding, titled "<RUSTSEC-id>: <title>" or "Crate <name> <version>".
# Its issue body is built purely from `cargo audit`'s JSON, which only describes the flagged
# crate itself -- it has no concept of "who depends on it", so there is no existing input to
# make it show that. This script re-runs `cargo audit --json`, cross-references each finding
# against `cargo tree -i <pkg> --depth 1` to see what depends on it one level up, and comments
# on the matching open issue with whether it's a direct dependency of this workspace or a
# transitive one (and, if transitive, the immediate parents).
#
# A hidden HTML-comment marker makes this idempotent: each issue is annotated exactly once,
# not re-commented on every (daily) scheduled run.
#
# Requires on PATH: cargo, cargo-audit (installed by the actions-rust-lang/audit step), jq, gh.
# Requires env:     GH_TOKEN (consumed by gh).
#
# It is deliberately a standalone script rather than an inline `run:` block so it can be
# executed and tested locally, independently of the workflow.

set -euo pipefail

# Hidden marker embedded in every comment we post; we look for it before commenting so each
# issue is annotated only once.
MARKER="<!-- affinidi-dependency-type-annotation -->"

cargo audit --json > audit-report.json || true

if ! jq -e . audit-report.json >/dev/null 2>&1; then
  echo "No valid cargo-audit JSON report produced, skipping annotation."
  exit 0
fi

MEMBERS=$(cargo metadata --no-deps --format-version=1 | jq -r '.packages[].name' | sort -u)

jq -c '
  (.vulnerabilities.list // [])
  + (.warnings.unmaintained // [])
  + (.warnings.unsound // [])
  + (.warnings.yanked // [])
' audit-report.json | jq -c '.[]?' | while read -r entry; do
  ADVISORY_ID=$(echo "$entry" | jq -r '.advisory.id // empty')
  PKG_NAME=$(echo "$entry" | jq -r '.package.name')
  PKG_VER=$(echo "$entry" | jq -r '.package.version')
  TITLE_PREFIX="${ADVISORY_ID:-Crate $PKG_NAME $PKG_VER}"

  PARENTS=$(cargo tree -i "${PKG_NAME}@${PKG_VER}" --depth 1 -e normal,build,dev --prefix none 2>/dev/null \
    | tail -n +2 | awk '{print $1}' | sort -u)

  DIRECT="no"
  for p in $PARENTS; do
    if echo "$MEMBERS" | grep -qx "$p"; then
      DIRECT="yes"
    fi
  done

  PARENTS_LIST=$(echo "$PARENTS" | paste -sd ',' - | sed 's/,/, /g')

  if [ "$DIRECT" = "yes" ]; then
    NOTE="**Dependency type:** Direct dependency — declared in this workspace's own \`Cargo.toml\`."
  else
    NOTE="**Dependency type:** Transitive dependency — pulled in via: \`${PARENTS_LIST:-unknown}\`. Not declared directly in this workspace's \`Cargo.toml\`."
  fi

  echo "::group::${TITLE_PREFIX}"
  echo "$NOTE"
  echo "::endgroup::"

  # TITLE_PREFIX and MARKER are passed to jq as --arg data, never spliced into the filter
  # program text, so a crafted crate name or advisory id cannot inject jq syntax.
  ISSUE_NUM=$(gh issue list --search "${TITLE_PREFIX} in:title" --state open --json number,title \
    | jq -r --arg prefix "$TITLE_PREFIX" '[.[] | select(.title | startswith($prefix))][0].number // empty')

  if [ -n "$ISSUE_NUM" ]; then
    ALREADY=$(gh issue view "$ISSUE_NUM" --json comments \
      | jq -r --arg m "$MARKER" '[.comments[].body | select(contains($m))] | length')
    if [ "$ALREADY" -gt 0 ]; then
      echo "Issue #${ISSUE_NUM} already annotated, skipping comment."
    else
      gh issue comment "$ISSUE_NUM" --body "${NOTE}"$'\n\n'"${MARKER}"
    fi
  else
    echo "No matching open issue found for ${TITLE_PREFIX}, skipping comment."
  fi
done
