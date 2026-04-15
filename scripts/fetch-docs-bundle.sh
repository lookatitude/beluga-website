#!/usr/bin/env bash
# Fetch docs-bundle.tar.gz (godoc HTML + framework report bodies) from
# the beluga-ai repo's latest release and splice it into the website
# source tree before a build.
#
# The bundle ships two things:
#   godoc/    — Go API reference HTML (drop into public/godoc/)
#   reports/  — raw CHANGELOG.md / SECURITY.md / CODE-QUALITY.md bodies
#               (spliced into existing stubs under
#                src/content/docs/docs/contributing/project-reports/,
#                preserving each stub's frontmatter)
#
# Usage:
#   scripts/fetch-docs-bundle.sh              # latest release
#   scripts/fetch-docs-bundle.sh v2.3.1        # specific tag
#
# Requirements:
#   - gh CLI authenticated with read access to lookatitude/beluga-ai
#   - awk, tar, sha256sum
#
# Failure handling:
#   This script is intentionally soft-fail. If no release exists, the
#   release is missing docs-bundle.tar.gz, the checksum doesn't match,
#   or the extract fails, it prints a warning and exits 0 so content-only
#   website builds (blog posts, feature pages) are never blocked by an
#   in-progress or broken framework release. The build then runs without
#   godoc pages and with placeholder report bodies — the same state as a
#   local dev build that skips this script entirely.

set -euo pipefail

REPO="${BELUGA_AI_REPO:-lookatitude/beluga-ai}"
TAG="${1:-}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPORTS_DIR="$ROOT/src/content/docs/docs/contributing/project-reports"

cd "$ROOT"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

warn() { printf 'warning: %s\n' "$*" >&2; }

soft_fail() {
  warn "$1"
  warn "continuing without docs bundle: godoc pages will 404 and project-report stubs will keep their placeholder bodies"
  mkdir -p public/godoc
  exit 0
}

if [ -z "$TAG" ]; then
  if ! TAG=$(gh release view --repo "$REPO" --json tagName --jq .tagName 2>/dev/null); then
    soft_fail "no release found in ${REPO} (or gh CLI failed)"
  fi
fi

echo "Fetching docs bundle from ${REPO}@${TAG}..."

if ! gh release download "$TAG" \
     --repo "$REPO" \
     --pattern "docs-bundle.tar.gz" \
     --pattern "docs-bundle.tar.gz.sha256" \
     --dir "$TMP" \
     --clobber; then
  soft_fail "release ${REPO}@${TAG} is missing docs-bundle.tar.gz"
fi

if ! (cd "$TMP" && sha256sum --check docs-bundle.tar.gz.sha256); then
  soft_fail "checksum mismatch for docs-bundle.tar.gz from ${REPO}@${TAG}"
fi

if ! tar -xzf "$TMP/docs-bundle.tar.gz" -C "$TMP"; then
  soft_fail "failed to extract docs-bundle.tar.gz from ${REPO}@${TAG}"
fi

# --- godoc ----------------------------------------------------------------
rm -rf public/godoc
mkdir -p public/godoc
if [ -d "$TMP/godoc" ]; then
  cp -R "$TMP/godoc/." public/godoc/
fi

# --- reports: splice raw body into existing stub's frontmatter ------------
splice_report() {
  local slug="$1"
  local src="$TMP/reports/${slug}.md"
  local dst="$REPORTS_DIR/${slug}.md"

  if [ ! -f "$src" ]; then
    echo "  reports/${slug}.md  missing in bundle (skip)"
    return 0
  fi
  if [ ! -f "$dst" ]; then
    echo "  reports/${slug}.md  stub missing at ${dst} (skip)"
    return 0
  fi

  # Extract the frontmatter block (first `---` fence to second `---` fence).
  local frontmatter
  frontmatter=$(awk '
    BEGIN { in_fm=0; count=0 }
    /^---[[:space:]]*$/ {
      count++
      print
      if (count == 2) { exit }
      in_fm=1
      next
    }
    in_fm { print }
  ' "$dst")

  {
    printf '%s\n\n' "$frontmatter"
    cat "$src"
  } > "$dst"

  echo "  reports/${slug}.md  spliced ($(wc -c < "$src") bytes)"
}

splice_report changelog
splice_report security
splice_report code-quality

echo "docs bundle from ${TAG} installed."
echo "  public/godoc:  $(find public/godoc -type f 2>/dev/null | wc -l) files"
