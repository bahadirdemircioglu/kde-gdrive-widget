#!/usr/bin/env bash
# Installs the widget from this checkout, or upgrades it if it is already installed.
set -euo pipefail
cd "$(dirname "$0")/.."

scripts/bundle-sync.sh

ID=$(sed -n 's/.*"Id": *"\([^"]*\)".*/\1/p' package/metadata.json)

if [ -x scripts/i18n-build.sh ] && command -v msgfmt >/dev/null; then
    scripts/i18n-build.sh >/dev/null
fi

if kpackagetool6 -t Plasma/Applet -l 2>/dev/null | grep -qx "$ID"; then
    kpackagetool6 -t Plasma/Applet -u package
    echo "Upgraded $ID."
else
    kpackagetool6 -t Plasma/Applet -i package
    echo "Installed $ID. Add \"Google Drive Sync\" from Add Widgets."
fi
echo "If Plasma still shows the old version: systemctl --user restart plasma-plasmashell"
