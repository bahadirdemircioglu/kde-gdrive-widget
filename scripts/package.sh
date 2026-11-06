#!/usr/bin/env bash
# Builds dist/kde-gdrive-widget-<Version>.plasmoid (zip of package/, metadata.json at the root).
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION=$(sed -n 's/.*"Version": *"\([^"]*\)".*/\1/p' package/metadata.json)
OUT="dist/kde-gdrive-widget-${VERSION}.plasmoid"

scripts/i18n-build.sh
scripts/bundle-sync.sh
mkdir -p dist
rm -f "$OUT"
(cd package && zip -qr "../${OUT}" . -x '*.swp' -x '*~')
echo "Packaged ${OUT}"
