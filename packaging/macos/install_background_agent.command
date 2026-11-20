#!/bin/bash
set -euo pipefail

LABEL="com.perennisfons.finalert.background"
APP_EXECUTABLE="/Applications/FinAlert.app/Contents/MacOS/FinAlert"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLIST_PATH="$LAUNCH_AGENTS/$LABEL.plist"
DOMAIN="gui/$(id -u)"

if [[ ! -x "$APP_EXECUTABLE" ]]; then
    echo "FinAlert.app is not installed in /Applications."
    echo "Drag FinAlert.app from the DMG into Applications, then run this file again."
    read -r -p "Press Return to close this window..."
    exit 1
fi

mkdir -p "$LAUNCH_AGENTS"

cat > "$PLIST_PATH" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.perennisfons.finalert.background</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Applications/FinAlert.app/Contents/MacOS/FinAlert</string>
        <string>--background</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>30</integer>
</dict>
</plist>
PLIST

plutil -lint "$PLIST_PATH"
launchctl bootout "$DOMAIN" "$PLIST_PATH" >/dev/null 2>&1 || true
launchctl enable "$DOMAIN/$LABEL"
launchctl bootstrap "$DOMAIN" "$PLIST_PATH"

echo "FinAlert background monitoring is installed and running."
echo "Logs: $HOME/Library/Application Support/FinAlert/background.log"
read -r -p "Press Return to close this window..."
