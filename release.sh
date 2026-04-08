#!/usr/bin/env bash
#
# Build all configured language packs and publish a GitHub release.
#
# Usage:
#   ./release.sh              # build all languages, release
#   ./release.sh fra spa      # build only these, release
#   ./release.sh --skip-build # release existing packs without rebuilding

set -euo pipefail
cd "$(dirname "$0")"

LANGUAGES=(fra spa deu ita por)
SKIP_BUILD=false

# Parse args
if [[ "${1:-}" == "--skip-build" ]]; then
  SKIP_BUILD=true
  shift
elif [[ $# -gt 0 ]]; then
  LANGUAGES=("$@")
fi

# Build
if [[ "$SKIP_BUILD" == false ]]; then
  for lang in "${LANGUAGES[@]}"; do
    echo "==> Building $lang..."
    uv run python build.py --lang "$lang"
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
