#!/usr/bin/env bash
# Install/reinstall the daily sourcing launchd job (default: 08:00 local).
# Usage:
#   ./scripts/install_daily_launchd.sh            # 08:00
#   ./scripts/install_daily_launchd.sh 07 30       # custom HH MM

set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.gabriel.jobfit.dailysourcing"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"

HOUR="${1:-08}"
MINUTE="${2:-00}"

mkdir -p "$ROOT/out/tracking"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${ROOT}/scripts/daily_sourcing_run.sh</string>
        <string>--with-linkedin</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>${HOUR}</integer>
        <key>Minute</key>
        <integer>${MINUTE}</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>${ROOT}/out/tracking/launchd.log</string>
    <key>StandardErrorPath</key>
    <string>${ROOT}/out/tracking/launchd.err.log</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

echo "Installed: $PLIST"
echo "Runs daily at ${HOUR}:${MINUTE} local time."
launchctl list | grep "$LABEL" || echo "Warning: job not showing in launchctl list yet."
