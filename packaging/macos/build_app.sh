#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYINSTALLER="$HOME/Library/Application Support/FinAlert/packaging-venv/bin/pyinstaller"

if [[ ! -x "$PYINSTALLER" ]]; then
    echo "PyInstaller not found at: $PYINSTALLER"
    exit 1
fi

mkdir -p "$PROJECT_ROOT/build/specs"

"$PYINSTALLER" \
    --noconfirm \
    --clean \
    --windowed \
    --name FinAlert \
    --osx-bundle-identifier com.perennisfons.finalert \
    --distpath "$PROJECT_ROOT/dist" \
    --workpath "$PROJECT_ROOT/build/pyinstaller" \
    --specpath "$PROJECT_ROOT/build/specs" \
    --icon "$PROJECT_ROOT/assets/FinAlert.icns" \
    --add-data "$PROJECT_ROOT/assets/fin_alert_logo.svg:assets" \
    "$PROJECT_ROOT/main.py"

APP_PATH="$PROJECT_ROOT/dist/FinAlert.app"
if [[ ! -d "$APP_PATH" ]]; then
    echo "Build finished, but the app bundle was not found at: $APP_PATH"
    exit 1
fi

echo "Built: $APP_PATH"
