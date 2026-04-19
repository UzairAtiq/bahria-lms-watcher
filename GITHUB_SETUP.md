# GitHub Setup Guide — Bahria LMS Watcher

Follow these steps **exactly once**. After that, the watcher runs every hour automatically, even with your laptop off.

---

## Step 1 — Create a GitHub account (skip if you have one)

Go to **https://github.com** → Sign up → Verify email.

---

## Step 2 — Create a new **private** repository

1. Click the **+** icon (top-right) → **New repository**
2. Fill in:
   - **Repository name:** `bahria-lms-watcher`
   - **Visibility:** ✅ **Private** ← important, your credentials will be here as secrets
   - Leave everything else unchecked
3. Click **Create repository**

---

## Step 3 — Push your code to GitHub

GitHub will show you a URL like:
```
https://github.com/YOUR_USERNAME/bahria-lms-watcher.git
```

Copy that URL, then open Terminal on your Mac and run:

```bash
cd ~/Desktop/check

# Replace the URL below with YOUR repository URL
git remote add origin https://github.com/YOUR_USERNAME/bahria-lms-watcher.git
git push -u origin main
```

It will ask for your GitHub username and password.
> ⚠️ GitHub no longer accepts passwords — use a **Personal Access Token** instead.
> Create one at: **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)**
> Give it `repo` and `workflow` scopes. Use that token as your "password".

---

## Step 4 — Add your credentials as GitHub Secrets

This is how GitHub Actions gets your LMS password **without storing it in the code**.

1. Go to your repo on GitHub
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret** and add each of these:

| Secret Name | Value |
|---|---|
| `LMS_USERNAME` | `01-136242-029` |
| `LMS_PASSWORD` | `123asd90@90#90` |
| `NTFY_TOPIC` | `bahria-assignments-uzair` |
| `CAMPUS_NAME` | `Islamabad E-8 Campus` |

---

## Step 5 — Enable GitHub Actions

1. Go to your repo → click the **Actions** tab
2. If prompted, click **"I understand my workflows, go ahead and enable them"**
3. You should see **"Bahria LMS Assignment Watcher"** listed

---

## Step 6 — Run it manually to test

1. Click on **"Bahria LMS Assignment Watcher"** in the Actions tab
2. Click **"Run workflow"** → **"Run workflow"** (green button)
3. Watch it run — should take about 60–90 seconds
4. If new assignments are found, you'll get a notification on your phone

---

## How to download assignment files

When the watcher finds new assignments:

1. Go to your repo → **Actions** tab
2. Click the latest workflow run
3. Scroll down to **Artifacts**
4. Click **assignments-XX** to download a zip of all new assignment files

Your phone notification will also include a direct link to that page.

---

## Schedule info

The workflow runs **every hour** (`0 * * * *` cron).

> **Note:** GitHub Actions cron jobs can sometimes be delayed by 5–15 minutes during peak times — this is normal.

---

## How state is preserved between runs

The downloaded-URLs list is stored in `~/.bahria_downloaded.json` on the runner and **cached between runs** using GitHub's cache system. This means:

- Run 1: Finds 5 assignments → downloads → caches state
- Run 2: Restores state → sees those 5 are already done → only downloads new ones
- Your phone only gets notified for genuinely new assignments ✅

---

## Stopping / pausing the watcher

Go to your repo → **Actions** → **"Bahria LMS Assignment Watcher"** → **"..."** → **Disable workflow**.

To re-enable: same path → **Enable workflow**.

---

## Updating your password

If your LMS password changes:
1. Go to **Settings → Secrets → Actions**
2. Click `LMS_PASSWORD` → **Update** → enter new password → Save

No code changes needed.
