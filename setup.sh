#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
#  Bahria University LMS Watcher — macOS Setup Script
#  Run once:  bash setup.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─────────────────────────────────────────────
#  CONFIGURATION  ← Fill these in before running
# ─────────────────────────────────────────────

LMS_USERNAME="01-136242-029"       # e.g. F2023065001
LMS_PASSWORD="123asd90@90#90"       # your LMS password
NTFY_TOPIC="bahria-assignments-uzair"       # e.g. bahria-uzair-assignments
CAMPUS_NAME="Islamabad E-8 Campus"

# ─────────────────────────────────────────────
#  DERIVED PATHS
# ─────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHER_SCRIPT="$SCRIPT_DIR/bahria_watcher.py"
PLIST_LABEL="com.bahria.watcher"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
LOG_FILE="$HOME/bahria_watcher.log"
VENV_DIR="$SCRIPT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python3"   # will point into the venv after Step 1

# ─────────────────────────────────────────────
#  HELPER FUNCTIONS
# ─────────────────────────────────────────────

info()    { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
success() { echo -e "\033[1;32m[OK]\033[0m    $*"; }
warn()    { echo -e "\033[1;33m[WARN]\033[0m  $*"; }
error()   { echo -e "\033[1;31m[ERROR]\033[0m $*" >&2; exit 1; }

# ─────────────────────────────────────────────
#  STEP 0: Sanity checks
# ─────────────────────────────────────────────

info "Checking prerequisites …"

[[ "$LMS_USERNAME" == "YOUR_USERNAME_HERE" ]] && \
    error "Please edit setup.sh and fill in LMS_USERNAME, LMS_PASSWORD, and NTFY_TOPIC before running."

command -v python3 &>/dev/null || error "python3 not found. Install it from https://www.python.org"

PYTHON_VERSION=$(python3 -c "import sys; print(sys.version_info.major, sys.version_info.minor)")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | awk '{print $1}')
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | awk '{print $2}')

if [[ $PYTHON_MAJOR -lt 3 || ($PYTHON_MAJOR -eq 3 && $PYTHON_MINOR -lt 9) ]]; then
    error "Python 3.9+ required. Found: $PYTHON_MAJOR.$PYTHON_MINOR"
fi

success "Python $PYTHON_MAJOR.$PYTHON_MINOR found at $PYTHON_BIN"

# ─────────────────────────────────────────────
#  STEP 1: Create virtual environment + install deps
# ─────────────────────────────────────────────

info "Creating virtual environment at $VENV_DIR …"
if [[ ! -d "$VENV_DIR" ]]; then
    python3 -m venv "$VENV_DIR"
fi
source "$VENV_DIR/bin/activate"
success "Virtual environment ready."

info "Installing Python packages into venv …"
pip install --quiet --upgrade pip
pip install --quiet \
    playwright \
    httpx \
    beautifulsoup4 \
    lxml

success "Python packages installed."

# ─────────────────────────────────────────────
#  STEP 2: Install Playwright browsers
# ─────────────────────────────────────────────

info "Installing Playwright Chromium browser …"
"$PYTHON_BIN" -m playwright install chromium
success "Playwright Chromium ready."

# ─────────────────────────────────────────────
#  STEP 3: Inject credentials into the watcher script
# ─────────────────────────────────────────────

info "Writing credentials into bahria_watcher.py …"

# Use Python so we don't worry about special characters in passwords
"$PYTHON_BIN" - <<PYEOF
import re, pathlib

script = pathlib.Path("$WATCHER_SCRIPT").read_text(encoding="utf-8")

replacements = {
    r'LMS_USERNAME\s*=\s*".*?"': 'LMS_USERNAME   = "$LMS_USERNAME"',
    r'LMS_PASSWORD\s*=\s*".*?"': 'LMS_PASSWORD   = "$LMS_PASSWORD"',
    r'NTFY_TOPIC\s*=\s*".*?"':   'NTFY_TOPIC     = "$NTFY_TOPIC"',
    r'CAMPUS_NAME\s*=\s*".*?"':  'CAMPUS_NAME    = "$CAMPUS_NAME"',
}

for pattern, replacement in replacements.items():
    script = re.sub(pattern, replacement, script)

pathlib.Path("$WATCHER_SCRIPT").write_text(script, encoding="utf-8")
print("Credentials written successfully.")
PYEOF

success "Credentials saved to bahria_watcher.py."

# ─────────────────────────────────────────────
#  STEP 4: Create download & log directories
# ─────────────────────────────────────────────

info "Creating directories …"
mkdir -p "$HOME/Downloads/BahriaAssignments"
touch "$LOG_FILE"
success "Directories ready."

# ─────────────────────────────────────────────
#  STEP 5: Create launchd plist (runs every hour)
# ─────────────────────────────────────────────

info "Creating launchd plist at $PLIST_PATH …"

# Unload existing job if present (ignore errors)
launchctl unload "$PLIST_PATH" 2>/dev/null || true

cat > "$PLIST_PATH" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_LABEL}</string>

    <key>ProgramArguments</key>
    <array>
        <string>${PYTHON_BIN}</string>
        <string>${WATCHER_SCRIPT}</string>
    </array>

    <key>StartInterval</key>
    <integer>3600</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>

    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>HOME</key>
        <string>${HOME}</string>
    </dict>

    <key>WorkingDirectory</key>
    <string>${SCRIPT_DIR}</string>
</dict>
</plist>
PLIST

success "plist written."

# ─────────────────────────────────────────────
#  STEP 6: Load the launchd job
# ─────────────────────────────────────────────

info "Registering launchd job …"
launchctl load -w "$PLIST_PATH"
success "Job registered. It will run every hour automatically."

# ─────────────────────────────────────────────
#  STEP 7: Run once immediately
# ─────────────────────────────────────────────

info "Running the watcher once right now …"
echo ""
"$PYTHON_BIN" "$WATCHER_SCRIPT"
echo ""
success "First run complete. Check $LOG_FILE for details."

echo ""
echo "══════════════════════════════════════════════════════"
echo "  ✅  Setup complete!"
echo ""
echo "  • The watcher runs every hour via launchd."
echo "  • Assignments are saved to:  ~/Downloads/BahriaAssignments/"
echo "  • Logs are written to:       ~/bahria_watcher.log"
echo "  • Push notifications go to:  ntfy topic '$NTFY_TOPIC'"
echo ""
echo "  To stop the watcher:"
echo "    launchctl unload ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo ""
echo "  To start it again:"
echo "    launchctl load -w ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo "══════════════════════════════════════════════════════"
