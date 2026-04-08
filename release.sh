#!/usr/bin/env bash
#
# Build all cross-language packs and publish a GitHub release.
#
# Usage:
#   ./release.sh                        # build all 30 pairs, release
#   ./release.sh eng fra eng spa        # build only these pairs (from-lang target pairs)
#   ./release.sh --skip-build           # release existing packs without rebuilding

set -euo pipefail
cd "$(dirname "$0")"

ALL_LANGS=(eng fra spa deu ita por)
SKIP_BUILD=false
PAIRS=()

# Parse args
if [[ "${1:-}" == "--skip-build" ]]; then
  SKIP_BUILD=true
  shift
elif [[ $# -gt 0 ]]; then
  # Expect pairs as: from_lang1 lang1 from_lang2 lang2 ...
  while [[ $# -ge 2 ]]; do
    PAIRS+=("$1:$2")
    shift 2
  done
  if [[ $# -gt 0 ]]; then
    echo "Error: pairs must be specified as 'from_lang lang' (got odd number of args)" >&2
    exit 1
  fi
fi

# Default: all pairs (6 langs × 5 targets = 30)
if [[ ${#PAIRS[@]} -eq 0 && "$SKIP_BUILD" == false ]]; then
  for from in "${ALL_LANGS[@]}"; do
    for to in "${ALL_LANGS[@]}"; do
      [[ "$from" != "$to" ]] && PAIRS+=("$from:$to")
    done
  done
fi

# Build
if [[ "$SKIP_BUILD" == false ]]; then
  for pair in "${PAIRS[@]}"; do
    from="${pair%%:*}"
    to="${pair##*:}"
    echo "==> Building $from→$to..."
    uv run python build.py --from-lang "$from" --lang "$to"
    echo ""
  done
fi

# Collect assets
assets=()
for db in packs/*.db; do
  [[ -f "$db" ]] && assets+=("$db")
done
assets+=("manifest.json")

echo "==> Assets to release:"
printf "    %s\n" "${assets[@]}"

# Tag
tag="v$(date +%Y.%m.%d)"

# Check if tag already exists today — append a counter if so
existing=$(gh release list --json tagName -q '.[].tagName' 2>/dev/null || true)
if echo "$existing" | grep -qx "$tag"; then
  i=2
  while echo "$existing" | grep -qx "${tag}.${i}"; do
    ((i++))
  done
  tag="${tag}.${i}"
fi

echo "==> Creating release $tag..."
gh release create "$tag" \
  --title "$tag" \
  --notes "Language packs built $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --latest \
  "${assets[@]}"

echo "==> Done! https://github.com/lexaway/lexaway-packs/releases/tag/$tag"
