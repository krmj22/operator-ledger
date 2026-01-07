#!/bin/bash

# LaunchD Setup Helper Script
# Install or uninstall operator LaunchD agents
# Supports: ingestion (weekly), github-sync (daily), cache-monitor

set -euo pipefail

# Auto-detect project root (one level up from scripts directory)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Service configuration
SERVICE="${1:-}"
case "${SERVICE}" in
    ingestion)
        LABEL="com.kylejensen.operator-ingestion"
        DESCRIPTION="Transcript ingestion (weekly)"
        ;;
    github-sync)
        LABEL="com.operator.github-sync"
        DESCRIPTION="GitHub commit sync (daily)"
        ;;
    cache-monitor)
        LABEL="com.operator.cache-monitor"
        DESCRIPTION="Cache monitoring"
        ;;
    ledger-audit)
        LABEL="com.operator.ledger-audit"
        DESCRIPTION="Ledger gap detection (weekly)"
        ;;
    *)
        echo "Error: Invalid service '${SERVICE}'"
        echo "Usage: $0 {ingestion|github-sync|cache-monitor|ledger-audit} {install|uninstall|status}"
        echo ""
        echo "Services:"
        echo "  ingestion    - Weekly transcript ingestion (Mondays 9am)"
        echo "  github-sync  - Daily GitHub commit sync (2am)"
        echo "  cache-monitor - Cache monitoring service"
        echo "  ledger-audit - Weekly ledger gap detection (Sundays 9am)"
        exit 1
        ;;
esac

PLIST_DEST="${HOME}/Library/LaunchAgents/${LABEL}.plist"

# Ensure OPERATOR_DATA_DIR is set (only for ingestion service)
if [ "${SERVICE}" = "ingestion" ] && [ -z "${OPERATOR_DATA_DIR:-}" ]; then
    echo "Warning: OPERATOR_DATA_DIR environment variable not set"
    echo "Please set it in your shell profile (e.g., ~/.zshrc):"
    echo "  export OPERATOR_DATA_DIR=\"/path/to/your/transcripts\""
    echo ""
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

function show_usage() {
    echo "Usage: $0 {ingestion|github-sync|cache-monitor|ledger-audit} {install|uninstall|status}"
    echo ""
    echo "Commands:"
    echo "  install   - Copy plist to LaunchAgents and load it"
    echo "  uninstall - Unload and remove the LaunchD agent"
    echo "  status    - Check if the agent is loaded"
    exit 1
}

function install_agent() {
    echo "Installing ${DESCRIPTION} LaunchD agent..."
    echo "Project root: ${PROJECT_ROOT}"

    # Ensure LaunchAgents directory exists
    mkdir -p "${HOME}/Library/LaunchAgents"

    # Ensure logs directory exists
    mkdir -p "${PROJECT_ROOT}/ledger/logs"

    # Generate service-specific plist
    if [ "${SERVICE}" = "github-sync" ]; then
        generate_github_sync_plist
    elif [ "${SERVICE}" = "ingestion" ]; then
        generate_ingestion_plist
    elif [ "${SERVICE}" = "cache-monitor" ]; then
        generate_cache_monitor_plist
    elif [ "${SERVICE}" = "ledger-audit" ]; then
        generate_ledger_audit_plist
    fi

    echo "✓ Generated plist at ${PLIST_DEST}"

    # Load the agent
    launchctl load "${PLIST_DEST}"
    echo "✓ Loaded LaunchD agent"

    echo ""
    echo "Agent installed successfully!"
    echo "Run 'launchctl list | grep ${LABEL}' to check status"
}

function generate_github_sync_plist() {
    cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${PROJECT_ROOT}/ledger/scripts/sync_github_commits.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <!-- Run daily at 2:00 AM -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>2</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${PROJECT_ROOT}/ledger/logs/github_sync.log</string>

    <key>StandardErrorPath</key>
    <string>${PROJECT_ROOT}/ledger/logs/github_sync_error.log</string>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF
}

function generate_ingestion_plist() {
    cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <!-- Job Label (must be unique) -->
    <key>Label</key>
    <string>${LABEL}</string>

    <!-- Program to run -->
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${PROJECT_ROOT}/ledger/scripts/daily_ingestion.sh</string>
    </array>

    <!-- Working directory -->
    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <!-- Run every Monday at 9:00 AM -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>1</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <!-- Standard output log -->
    <key>StandardOutPath</key>
    <string>${PROJECT_ROOT}/ledger/logs/launchd_stdout.log</string>

    <!-- Standard error log -->
    <key>StandardErrorPath</key>
    <string>${PROJECT_ROOT}/ledger/logs/launchd_stderr.log</string>

    <!-- Don't run on load -->
    <key>RunAtLoad</key>
    <false/>

    <!-- Environment variables -->
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>OPERATOR_DATA_DIR</key>
        <string>${OPERATOR_DATA_DIR:-}</string>
    </dict>

    <!-- Don't keep alive -->
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF
}

function generate_cache_monitor_plist() {
    # Use existing cache-monitor plist template
    if [ -f "${SCRIPT_DIR}/com.operator.cache-monitor.plist" ]; then
        # Replace placeholders with actual paths
        sed "s|\${PROJECT_ROOT}|${PROJECT_ROOT}|g" \
            "${SCRIPT_DIR}/com.operator.cache-monitor.plist" > "${PLIST_DEST}"
    else
        echo "Error: Template plist not found: ${SCRIPT_DIR}/com.operator.cache-monitor.plist"
        exit 1
    fi
}

function generate_ledger_audit_plist() {
    cat > "${PLIST_DEST}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${PROJECT_ROOT}/scripts/ledger-audit.sh</string>
    </array>

    <key>WorkingDirectory</key>
    <string>${PROJECT_ROOT}</string>

    <!-- Run every Sunday at 9:00 AM -->
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>9</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>${PROJECT_ROOT}/ledger/logs/audit-latest.log</string>

    <key>StandardErrorPath</key>
    <string>${PROJECT_ROOT}/ledger/logs/audit-latest.log</string>

    <key>RunAtLoad</key>
    <false/>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
    </dict>

    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
EOF
}

function uninstall_agent() {
    echo "Uninstalling ${DESCRIPTION} LaunchD agent..."

    # Unload if loaded
    if launchctl list | grep -q "${LABEL}"; then
        launchctl unload "${PLIST_DEST}" 2>/dev/null || true
        echo "✓ Unloaded LaunchD agent"
    else
        echo "Agent was not loaded"
    fi

    # Remove plist
    if [ -f "${PLIST_DEST}" ]; then
        rm "${PLIST_DEST}"
        echo "✓ Removed plist from LaunchAgents"
    else
        echo "Plist was not installed"
    fi

    echo ""
    echo "Agent uninstalled successfully!"
}

function check_status() {
    echo "Checking ${DESCRIPTION} agent status..."
    echo "Project root: ${PROJECT_ROOT}"
    echo ""

    if [ -f "${PLIST_DEST}" ]; then
        echo "✓ Plist installed at: ${PLIST_DEST}"
    else
        echo "✗ Plist not installed"
    fi

    if launchctl list | grep -q "${LABEL}"; then
        echo "✓ Agent is loaded"
        echo ""
        launchctl list | grep "${LABEL}"
    else
        echo "✗ Agent is not loaded"
    fi

    echo ""
    if [ "${SERVICE}" = "ingestion" ]; then
        echo "OPERATOR_DATA_DIR: ${OPERATOR_DATA_DIR:-not set}"
        echo ""
        echo "Recent ingestion logs:"
        ls -lt "${PROJECT_ROOT}/ledger/logs/ingestion_*.log" 2>/dev/null | head -5 || echo "No logs found"
    elif [ "${SERVICE}" = "github-sync" ]; then
        echo "Recent sync logs:"
        tail -20 "${PROJECT_ROOT}/ledger/logs/github_sync.log" 2>/dev/null || echo "No logs found"
    elif [ "${SERVICE}" = "ledger-audit" ]; then
        echo "Recent audit log:"
        tail -30 "${PROJECT_ROOT}/ledger/logs/audit-latest.log" 2>/dev/null || echo "No logs found"
    fi
}

# Main
if [ $# -lt 2 ]; then
    show_usage
fi

COMMAND="${2}"

case "${COMMAND}" in
    install)
        install_agent
        ;;
    uninstall)
        uninstall_agent
        ;;
    status)
        check_status
        ;;
    *)
        show_usage
        ;;
esac
