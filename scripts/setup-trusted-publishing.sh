#!/usr/bin/env bash
# Registers crates.io Trusted Publishing (OIDC) for every publishable crate in workspace
#
# Usage:  ./scripts/setup-trusted-publishing.sh [--dry-run] [repo-path]
#
# Prompts for your crates.io API token (masked) and detects the GitHub
# owner/repo from the Git remote.  Workflow and environment are fixed to
# release.yaml / release.
#
# Requires: cargo, jq, curl, git

set -euo pipefail

API_BASE="https://crates.io/api/v1"
API_TP="${API_BASE}/trusted_publishing"
DRY_RUN=false
REPO_PATH="."

# ---------- arg parsing ------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        -*)        echo "Unknown option: $1" >&2; exit 1 ;;
        *)         REPO_PATH="$1"; shift ;;
    esac
done

# ---------- pre-flight -------------------------------------------------------
for cmd in cargo jq curl git; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "Error: '$cmd' not found." >&2; exit 1; }
done

read -r -s -p "Enter crates.io API token: " TOKEN; echo
[[ -n "$TOKEN" ]] || { echo "Error: token cannot be empty." >&2; exit 1; }

# Resolve owner/repo from git remote (SSH or HTTPS)
REMOTE=$(git -C "$REPO_PATH" remote get-url origin 2>/dev/null) \
    || { echo "Error: no 'origin' remote in '${REPO_PATH}'." >&2; exit 1; }
REMOTE="${REMOTE#*github.com?}"   # strip everything up to and including github.com: or /
REMOTE="${REMOTE%.git}"
OWNER="${REMOTE%%/*}"
REPO="${REMOTE#*/}"
[[ -n "$OWNER" && -n "$REPO" ]] \
    || { echo "Error: cannot parse owner/repo from remote." >&2; exit 1; }

echo "Repository: ${OWNER}/${REPO}"

# ---------- helpers ----------------------------------------------------------
crates_io() { curl --silent --show-error -H "Authorization: Bearer ${TOKEN}" -H "Content-Type: application/json" "$@"; }

# ---------- discover publishable crates --------------------------------------
echo "Discovering publishable crates…"
mapfile -t CRATES < <(
    cargo metadata --format-version=1 --no-deps --manifest-path "${REPO_PATH}/Cargo.toml" \
        | jq -r '.packages[] | select(.publish == null or .publish != []) | .name' \
        | sort
)
[[ ${#CRATES[@]} -gt 0 ]] || { echo "No publishable crates found." >&2; exit 1; }

echo "Found ${#CRATES[@]} crate(s):"
printf '  %s\n' "${CRATES[@]}"
echo

# Build the repo-level part of the payload once
BASE=$(jq --null-input \
    --arg owner "$OWNER" --arg repo "$REPO" \
    --arg wf "release.yaml" --arg env "release" \
    '{repository_owner:$owner, repository_name:$repo, workflow_filename:$wf, environment:$env}')

# ---------- register each crate ----------------------------------------------
SUCCESS=0 SKIPPED=0 FAILED=0

for CRATE in "${CRATES[@]}"; do
    echo "── $CRATE"

    # Crate existence determines the endpoint (also the JSON response key)
    if [[ $(crates_io --output /dev/null --write-out "%{http_code}" "${API_BASE}/crates/${CRATE}") == "200" ]]; then
        ENDPOINT="github_configs";         KIND="active"
    else
        ENDPOINT="pending_github_configs"; KIND="pending (new crate)"
    fi

    EXISTING=$(crates_io "${API_TP}/${ENDPOINT}?crate=${CRATE}" | jq ".${ENDPOINT} | length")
    if [[ "$EXISTING" -gt 0 ]]; then
        echo "   skipped — already configured"; (( SKIPPED++ )); continue
    fi

    PAYLOAD=$(jq --null-input --arg crate "$CRATE" --argjson base "$BASE" \
        '{github_config: ($base + {crate: $crate})}')

    if [[ "$DRY_RUN" == true ]]; then
        echo "   [dry-run] would POST ${KIND}: ${PAYLOAD}"; (( SUCCESS++ )); continue
    fi

    read -r -p "   Register ${KIND} trusted publisher for '${CRATE}'? [y/N] " REPLY
    if [[ ! "$REPLY" =~ ^[yY]$ ]]; then
        echo "   skipped by user"; (( SKIPPED++ )); continue
    fi

    HTTP=$(crates_io --output /dev/null --write-out "%{http_code}" --request POST --data "$PAYLOAD" "${API_TP}/${ENDPOINT}")
    if [[ "$HTTP" =~ ^20[01]$ ]]; then
        echo "   registered ${KIND} (HTTP ${HTTP})"; (( SUCCESS++ ))
    else
        echo "   FAILED (HTTP ${HTTP})" >&2; (( FAILED++ ))
    fi
done

# ---------- summary ----------------------------------------------------------
echo
echo "Done — registered: ${SUCCESS}, skipped: ${SKIPPED}, failed: ${FAILED}"
[[ "$FAILED" -eq 0 ]]
