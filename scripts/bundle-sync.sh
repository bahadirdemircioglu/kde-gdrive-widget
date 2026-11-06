#!/usr/bin/env bash
# Copies the sync scripts (sync/ is the single source) into the plasmoid, so the widget can
# run the setup on a machine where nothing is installed yet.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=package/contents/code/sync
rm -rf "$DEST"
mkdir -p "$DEST"
for f in gdrive-setup gdrive-sync gdrive-syncd gdrive-status gdrive-nfc gdrive_common.py gdrive-lib.sh; do
    install -m 644 "sync/$f" "$DEST/$f"
done
