#!/usr/bin/env bash
# setup.sh — One-time setup for Bahria LMS Watcher (macOS)
# Creates a Python venv, installs dependencies, injects credentials,
# registers an hourly launchd job, and runs the watcher once.

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — fill these in before running
# ---------------------------------------------------------------------------

LMS_USERNAME="YOUR_USERNAME"
LMS_PASSWORD="YOUR_PASSWORD"
NTFY_TOPIC="YOUR_NTFY_TOPIC"
CAMPUS_NAME="Islamabad E-8 Campus"

# ---------------------------------------------------------------------------
# Derived paths
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHER="$SCRIPT_DIR/bahria_watcher.py"
VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python3"
PLIST_ID="com.bahria.watcher"
PLIST="$HOME/Library/LaunchAgents/${PLIST_ID}.plist"
LOG="$HOME/bahria_watcher.log"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

info()  { echo -e "\033[1;34m[INFO]\033[0m  $*"; }
ok()    { echo -e "\033[1;32m[ OK ]\033[0m  $*"; }
err()   { echo -e "\033[1;31m[ERR ]\033[0m  $*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

[[ "$LMS_USERNAME" == "YOUR_USERNAME" ]] && \
    err "Edit setup.sh and set LMS_USERNAME, LMS_PASSWORD, and NTFY_TOPIC first."

command -v python3 &>/dev/null || err "python3 not found."

PY_VER=$(python3 -c "import sys; print(sys.version_info.major, sys.version_info.minor)")
MAJOR=$(echo "$PY_VER" | awk '{print $1}')
MINOR=$(echo "$PY_VER" | awk '{print $2}')
(( MAJOR >= 3 && MINOR >= 9 )) || err "Python 3.9+ required."
ok "Python $MAJOR.$MINOR"

# ---------------------------------------------------------------------------
# Virtual environment
# ---------------------------------------------------------------------------

info "Setting up virtual environment..."
[[ -d "$VENV" ]] || python3 -m venv "$VENV"
source "$VENV/bin/activate"
ok "Venv ready: $VENV"

info "Installing packages..."
pip install --quiet --upgrade pip
pip install --quiet playwright httpx beautifulsoup4 lxml
ok "Packages installed."

info "Installing Playwright Chromium..."
"$PYTHON" -m playwright install chromium
ok "Chromium ready."

# ---------------------------------------------------------------------------
# Inject credentials
# ---------------------------------------------------------------------------

info "Writing credentials into watcher script..."
"$PYTHON" - <<PYEOF
import re, pathlib

script = pathlib.Path("$WATCHER").read_text(encoding="utf-8")
for pat, val in [
    (r'LMS_USERNAME\s*=\s*os\.environ\.get\("LMS_USERNAME",\s*".*?"\)', 'LMS_USERNAME = os.environ.get("LMS_USERNAME", "$LMS_USERNAME")'),
    (r'LMS_PASSWORD\s*=\s*os\.environ\.get\("LMS_PASSWORD",\s*".*?"\)', 'LMS_PASSWORD = os.environ.get("LMS_PASSWORD", "$LMS_PASSWORD")'),
    (r'NTFY_TOPIC\s*=\s*os\.environ\.get\("NTFY_TOPIC",\s*".*?"\)',     'NTFY_TOPIC   = os.environ.get("NTFY_TOPIC",   "$NTFY_TOPIC")'),
    (r'CAMPUS_NAME\s*=\s*os\.environ\.get\("CAMPUS_NAME",\s*".*?"\)',   'CAMPUS_NAME  = os.environ.get("CAMPUS_NAME",  "$CAMPUS_NAME")'),
]:
    script = re.sub(pat, val, script)
pathlib.Path("$WATCHER").write_text(script, encoding="utf-8")
print("Credentials written.")
PYEOF
ok "Credentials saved."

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

mkdir -p "$HOME/Downloads/BahriaAssignments"
touch "$LOG"
ok "Directories ready."

# ---------------------------------------------------------------------------
# launchd job (runs every hour)
# ---------------------------------------------------------------------------

info "Registering launchd job..."
launchctl unload "$PLIST" 2>/dev/null || true

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
    "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key>             <string>${PLIST_ID}</string>
    <key>ProgramArguments</key>  <array>
        <string>${PYTHON}</string>
        <string>${WATCHER}</string>
    </array>
    <key>StartInterval</key>     <integer>3600</integer>
    <key>RunAtLoad</key>         <true/>
    <key>StandardOutPath</key>   <string>${LOG}</string>
    <key>StandardErrorPath</key> <string>${LOG}</string>
    <key>EnvironmentVariables</key> <dict>
        <key>PATH</key> <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>HOME</key> <string>${HOME}</string>
    </dict>
    <key>WorkingDirectory</key>  <string>${SCRIPT_DIR}</string>
</dict></plist>
PLIST

launchctl load -w "$PLIST"
ok "launchd job registered (runs every hour)."

# ---------------------------------------------------------------------------
# First run
# ---------------------------------------------------------------------------

info "Running watcher now..."
"$PYTHON" "$WATCHER"

echo ""
echo "────────────────────────────────────────────────────"
echo "  Setup complete."
echo ""
echo "  Assignments saved to : ~/Downloads/BahriaAssignments/"
echo "  Log file             : $LOG"
echo "  ntfy topic           : $NTFY_TOPIC"
echo ""
echo "  To stop:   launchctl unload $PLIST"
echo "  To start:  launchctl load -w $PLIST"
echo "────────────────────────────────────────────────────"
