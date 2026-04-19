# 📚 Bahria University LMS Assignment Watcher

Automatically checks your LMS for new assignments every hour, downloads them to your Mac, and sends a push notification to your phone.

---

## What It Does

| Feature | Detail |
|---|---|
| **Auto-login** | Logs into the CMS portal, selects your campus, and navigates to the LMS |
| **Scrapes Assignments** | Finds all downloadable files (PDF, DOCX, ZIP, PPTX, XLSX, etc.) |
| **No Duplicates** | Tracks what's already downloaded in a local JSON file |
| **Push Notifications** | Sends alerts to your phone via the free **ntfy** app |
| **Hourly Schedule** | Runs silently in the background using macOS launchd |

---

## Files Included

```
bahria_watcher.py        ← Main Python script
setup.sh                 ← One-time setup script (run this!)
com.bahria.watcher.plist ← launchd job template (setup.sh uses this automatically)
README.md                ← You are here
```

---

## Requirements

- **macOS** (10.15 Catalina or newer recommended)
- **Python 3.9+** — check with `python3 --version` in Terminal
- **Internet connection**
- The **ntfy** app on your iPhone/Android (free — [ntfy.sh](https://ntfy.sh))

---

## Step-by-Step Setup (non-technical friendly)

### 1. Install the ntfy app and create your topic

1. Download **ntfy** from the App Store (iPhone) or Play Store (Android)
2. Open the app and tap **"+"** → Subscribe to a topic
3. Choose any unique topic name, e.g., `bahria-uzair-assignments`  
   ⚠️ Topics are public by default — pick something hard to guess!
4. Keep the app open at least once so it registers for notifications

### 2. Open Terminal

Press **⌘ Space**, type **Terminal**, press Enter.

### 3. Navigate to the script folder

```bash
cd /path/to/where/you/saved/the/scripts
# Example:
cd ~/Desktop/check
```

### 4. Edit setup.sh with your credentials

Open `setup.sh` in any text editor and fill in the three lines near the top:

```bash
LMS_USERNAME="F2023065001"          # ← your student ID
LMS_PASSWORD="mySecretPass123"      # ← your LMS password
NTFY_TOPIC="bahria-uzair-assignments" # ← your ntfy topic name
```

Save the file.

### 5. Run the setup script

```bash
bash setup.sh
```

This will:
- Install all required Python packages
- Download the Chromium browser for automation
- Save your credentials into the script
- Register the hourly launchd job
- Run the watcher once immediately

> **The first run may take 2–3 minutes** as it downloads Chromium (~150 MB).

---

## Where Are My Files?

| Item | Location |
|---|---|
| Downloaded assignments | `~/Downloads/BahriaAssignments/<Course Name>/` |
| Log file | `~/bahria_watcher.log` |
| Downloaded-list tracker | `~/.bahria_downloaded.json` |

---

## Managing the Background Job

### Stop the watcher from running automatically

```bash
launchctl unload ~/Library/LaunchAgents/com.bahria.watcher.plist
```

### Start it again

```bash
launchctl load -w ~/Library/LaunchAgents/com.bahria.watcher.plist
```

### Run it manually right now

```bash
python3 /path/to/bahria_watcher.py
```

### Check the logs

```bash
tail -50 ~/bahria_watcher.log
```

Or open `~/bahria_watcher.log` in any text editor.

---

## Troubleshooting

### "python3 not found"
Install Python from [python.org](https://www.python.org/downloads/) and retry.

### "playwright not found" / "No module named playwright"
Run:
```bash
pip3 install playwright
python3 -m playwright install chromium
```

### No notifications arriving
- Make sure the ntfy app is installed and you subscribed to the **exact** topic name you set in `NTFY_TOPIC`
- Test manually:
  ```bash
  curl -d "Test notification" ntfy.sh/YOUR_TOPIC_NAME
  ```

### Login fails / wrong page
- Double-check your username and password in `bahria_watcher.py`
- The LMS site layout sometimes changes — check `~/bahria_watcher.log` for error details
- Try running with a visible browser to debug (change `headless=True` to `headless=False` in `bahria_watcher.py`)

### "Permission denied" when running setup.sh
```bash
chmod +x setup.sh
bash setup.sh
```

### Changing your password later
Open `bahria_watcher.py` in a text editor and update the `LMS_PASSWORD` line near the top.

---

## Privacy & Security Notes

- Your credentials are stored **only on your local Mac** inside `bahria_watcher.py`
- ntfy topics are public by default — use a random or hard-to-guess topic name
- The script never uploads any data except the notification text to ntfy.sh

---

## How It Works (technical summary)

```
setup.sh runs once
    └── installs Python packages + Playwright Chromium
    └── writes credentials into bahria_watcher.py
    └── installs launchd job → runs every 60 minutes

bahria_watcher.py (each run)
    └── Playwright opens headless Chromium
    └── Logs into lms.bahria.edu.pk
    └── On CMS portal: selects "Islamabad E-8" from 3rd dropdown
    └── Clicks "LMS" button → lands on LMS dashboard
    └── Clicks "Assignments" in sidebar
    └── Finds all links with .pdf/.docx/.zip/.pptx etc. extensions
    └── Checks ~/.bahria_downloaded.json for already-seen URLs
    └── Downloads new files to ~/Downloads/BahriaAssignments/<Course>/
    └── Updates JSON tracker
    └── Sends push notification for each new file
    └── Writes everything to ~/bahria_watcher.log
```

---

*Made with ❤️ for Bahria University students.*
