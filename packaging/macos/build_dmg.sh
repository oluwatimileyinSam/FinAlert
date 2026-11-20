#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
APP_PATH="$PROJECT_ROOT/dist/FinAlert.app"
AGENT_INSTALLER="$PROJECT_ROOT/packaging/macos/install_background_agent.command"
DMG_PATH="$PROJECT_ROOT/dist/FinAlert.dmg"

if [[ ! -d "$APP_PATH" ]]; then
    echo "FinAlert.app not found. Build it first."
    exit 1
fi

if [[ ! -x "$AGENT_INSTALLER" ]]; then
    echo "Background-agent installer is missing or not executable."
    exit 1
fi

mkdir -p "$PROJECT_ROOT/build" "$PROJECT_ROOT/dist"
STAGING_DIR="$(mktemp -d "$PROJECT_ROOT/build/dmg-staging.XXXXXX")"
trap 'rm -rf "$STAGING_DIR"' EXIT

ditto "$APP_PATH" "$STAGING_DIR/FinAlert.app"
ditto "$AGENT_INSTALLER" "$STAGING_DIR/Install Background Agent.command"
ln -s /Applications "$STAGING_DIR/Applications"

hdiutil create \
    -volname "FinAlert" \
    -srcfolder "$STAGING_DIR" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

echo "Built clean DMG: $DMG_PATH"
