#!/usr/bin/env bash
set -euo pipefail

APP_NAME="MiSTer Companion"
VERSION="4.0.8"
BUNDLE_ID="com.enfstudios.mistercompanion"
APP_PATH="dist/${APP_NAME}.app"
DMG_NAME="${APP_NAME}-${VERSION}.dmg"
DMG_PATH="dist/${DMG_NAME}"
LSREGISTER="/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister"

if [[ ! -d "${APP_PATH}" ]]; then
    echo "error: ${APP_PATH} not found. Run 'python setup.py py2app' first." >&2
    exit 1
fi

rm -f "${DMG_PATH}"

create-dmg \
    --volname "${APP_NAME}" \
    --volicon "assets/icon.icns" \
    --window-pos 200 120 \
    --window-size 600 380 \
    --icon-size 128 \
    --icon "${APP_NAME}.app" 150 180 \
    --app-drop-link 450 180 \
    --hide-extension "${APP_NAME}.app" \
    --no-internet-enable \
    "${DMG_PATH}" \
    "${APP_PATH}"

echo "built: ${DMG_PATH}"
ls -lh "${DMG_PATH}"

if [[ -x "${LSREGISTER}" ]]; then
    "${LSREGISTER}" -dump 2>/dev/null \
        | awk -v bid="${BUNDLE_ID}" '
            /^path:/ { p = $0; sub(/^path:[[:space:]]+/, "", p); sub(/[[:space:]]+\(0x[0-9a-f]+\)$/, "", p); next }
            /^identifier:/ { id = $2; if (id == bid && p ~ /^\/Volumes\//) print p }
        ' \
        | while IFS= read -r stale; do
            if [[ ! -e "${stale}" ]]; then
                "${LSREGISTER}" -u "${stale}" >/dev/null 2>&1 || true
                echo "unregistered stale: ${stale}"
            fi
        done
    "${LSREGISTER}" -f "${APP_PATH}" >/dev/null 2>&1 || true
    xattr -cr "${APP_PATH}" 2>/dev/null || true
fi
