#!/usr/bin/env bash
# Registers crates.io Trusted Publishing (OIDC) for every publishable crate in this workspace.
#
# Usage:
#   CARGO_REGISTRY_TOKEN=<token> ./scripts/setup-trusted-publishing.sh [options]
#
# Options:
#   --owner        GitHub org/user owning the repo  (default: affinidi)
#   --repo         GitHub repository name           (default: affinidi-tdk-rs)
#   --workflow     Workflow filename in .github/workflows/ (default: release.yaml)
#   --environment  GitHub Actions environment name  (default: release)
#   --dry-run      Print what would be done without calling the API
#
# Requires: cargo, jq, curl
# The CARGO_REGISTRY_TOKEN must have the 'publish-new' or 'publish-update' scope.

set -euo pipefail

# ---------- defaults ---------------------------------------------------------
OWNER="affinidi"
REPO="affinidi-tdk-rs"
WORKFLOW="release.yaml"
ENVIRONMENT="release"
DRY_RUN=false
API_BASE="https://crates.io/api/v1"

# ---------- arg parsing ------------------------------------------------------
while [[ $# -gt 0 ]]; do
    case "$1" in
        --owner)       OWNER="$2";       shift 2 ;;
        --repo)        REPO="$2";        shift 2 ;;
        --workflow)    WORKFLOW="$2";    shift 2 ;;
        --environment) ENVIRONMENT="$2"; shift 2 ;;
        --dry-run)     DRY_RUN=true;     shift   ;;
        *) echo "Unknown option: $1" >&2; exit 1  ;;
    esac
done

# ---------- pre-flight -------------------------------------------------------
if [[ -z "${CARGO_REGISTRY_TOKEN:-}" ]]; then
    echo "Error: CARGO_REGISTRY_TOKEN is not set." >&2
    exit 1
fi

for cmd in cargo jq curl; do
    if ! command -v "$cmd" > /dev/null 2>&1; then
        echo "Error: required command '$cmd' not found." >&2
        exit 1
    fi
done

# ---------- discover publishable crates --------------------------------------
echo "Discovering publishable crates in workspace..."

mapfile -t CRATES < <(
    cargo metadata --format-version=1 --no-deps \
        | jq -r '.packages[] | select(.publish == null or .publish != []) | .name' \
        | sort
)

if [[ ${#CRATES[@]} -eq 0 ]]; then
    echo "No publishable crates found." >&2
    exit 1
fi

echo "Found ${#CRATES[@]} publishable crate(s):"
printf '  %s\n' "${CRATES[@]}"
echo

# ---------- register each crate ----------------------------------------------
SUCCESS=0
SKIPPED=0
FAILED=0

for CRATE in "${CRATES[@]}"; do
    echo "── $CRATE"

    # Check if a config already exists for this crate
    EXISTING=$(
        curl --silent --show-error --fail \
            --header "Authorization: Bearer ${CARGO_REGISTRY_TOKEN}" \
            --header "Content-Type: application/json" \
            "${API_BASE}/trusted_publishing/github_configs?crate=${CRATE}" \
        | jq '.github_configs | length'
    )

    if [[ "$EXISTING" -gt 0 ]]; then
        echo "   skipped — trusted publisher already configured"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    PAYLOAD=$(jq --null-input \
        --arg crate       "$CRATE" \
        --arg owner       "$OWNER" \
        --arg repo        "$REPO" \
        --arg workflow    "$WORKFLOW" \
        --arg environment "$ENVIRONMENT" \
        '{
            github_config: {
                crate:              $crate,
                repository_owner:   $owner,
                repository_name:    $repo,
                workflow_filename:  $workflow,
                environment:        $environment
            }
        }'
    )

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "   [dry-run] would POST: ${PAYLOAD}"
        SUCCESS=$((SUCCESS + 1))
        continue
    fi

    read -r -p "   Register trusted publisher for '${CRATE}'? [y/N] " REPLY
    if [[ "$REPLY" != "y" ]] && [[ "$REPLY" != "Y" ]]; then
        echo "   skipped by user"
        SKIPPED=$((SKIPPED + 1))
        continue
    fi

    HTTP_STATUS=$(
        curl --silent --output /dev/null --write-out "%{http_code}" \
            --request POST \
            --header "Authorization: Bearer ${CARGO_REGISTRY_TOKEN}" \
            --header "Content-Type: application/json" \
            --data "$PAYLOAD" \
            "${API_BASE}/trusted_publishing/github_configs"
    )

    if [[ "$HTTP_STATUS" == "200" ]] || [[ "$HTTP_STATUS" == "201" ]]; then
        echo "   registered (HTTP ${HTTP_STATUS})"
        SUCCESS=$((SUCCESS + 1))
    else
        echo "   FAILED (HTTP ${HTTP_STATUS})" >&2
        FAILED=$((FAILED + 1))
    fi
done

# ---------- summary ----------------------------------------------------------
echo
echo "Done — registered: ${SUCCESS}, skipped: ${SKIPPED}, failed: ${FAILED}"
[[ "$FAILED" -eq 0 ]]
