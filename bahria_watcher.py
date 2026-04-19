"""
Bahria University LMS Assignment Watcher
-----------------------------------------
Monitors the LMS for unsubmitted assignments, downloads new ones,
and sends push notifications via ntfy.sh.

Supports both local execution (macOS launchd) and GitHub Actions.
"""

import asyncio
import base64
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright


# ---------------------------------------------------------------------------
# Configuration — values are overridden by environment variables when set
# (GitHub Actions injects these from repository secrets)
# ---------------------------------------------------------------------------

LMS_USERNAME = os.environ.get("LMS_USERNAME", "YOUR_USERNAME")
LMS_PASSWORD = os.environ.get("LMS_PASSWORD", "YOUR_PASSWORD")
NTFY_TOPIC   = os.environ.get("NTFY_TOPIC",   "YOUR_NTFY_TOPIC")
CAMPUS_NAME  = os.environ.get("CAMPUS_NAME",  "Islamabad E-8 Campus")

# ---------------------------------------------------------------------------
# Paths — download directory shifts to the workspace on GitHub Actions
# so files can be uploaded as workflow artifacts
# ---------------------------------------------------------------------------

_IN_CI = bool(os.environ.get("GITHUB_ACTIONS"))

DOWNLOAD_DIR = (
    Path(os.environ.get("GITHUB_WORKSPACE", ".")) / "downloads"
    if _IN_CI
    else Path.home() / "Downloads" / "BahriaAssignments"
)
LOG_FILE   = Path.home() / "bahria_watcher.log"
STATE_FILE = Path.home() / ".bahria_downloaded.json"

# Build a direct link to this CI run so the phone notification is actionable
_CI_RUN_URL = ""
if _IN_CI:
    _server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    _repo   = os.environ.get("GITHUB_REPOSITORY", "")
    _run    = os.environ.get("GITHUB_RUN_ID", "")
    if _repo and _run:
        _CI_RUN_URL = f"{_server}/{_repo}/actions/runs/{_run}"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LMS_URL  = "https://lms.bahria.edu.pk"
NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

DOWNLOADABLE_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".zip", ".pptx",
    ".ppt", ".xlsx", ".xls", ".rar", ".7z", ".txt",
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  [%(levelname)-7s]  %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("bahria_watcher")


# ---------------------------------------------------------------------------
# State persistence
# ---------------------------------------------------------------------------

def load_state() -> dict:
    """Return the set of already-processed download URLs from disk."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            log.warning("State file unreadable — starting fresh.")
    return {}


def save_state(state: dict) -> None:
    """Persist the processed-URL registry to disk."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------

def send_notification(title: str, body: str, priority: str = "default") -> None:
    """Post a push notification to the configured ntfy topic."""
    try:
        r = httpx.post(
            NTFY_URL,
            content=body.encode("utf-8"),
            headers={
                "Title":        title,
                "Priority":     priority,
                "Tags":         "books",
                "Content-Type": "text/plain; charset=utf-8",
            },
            timeout=10,
        )
        r.raise_for_status()
        log.info(f"Notification sent: {title}")
    except Exception as exc:
        log.error(f"Notification failed: {exc}")


# ---------------------------------------------------------------------------
# File utilities
# ---------------------------------------------------------------------------

def sanitize(name: str) -> str:
    """Strip characters that are invalid in file or directory names."""
    return re.sub(r'[\\/*?:"<>|]', "_", name).strip()


def resolve_filename(url: str, title: str, row_text: str) -> str:
    """
    Extract a human-readable filename from a Download.php?k=<base64> URL.

    The 'k' parameter decodes to a comma-separated record whose fields include
    the original filename (e.g. 'Assignment-1-27012026.docx'). Falls back to
    the assignment title or a timestamp if decoding fails.
    """
    try:
        k = parse_qs(urlparse(url).query).get("k", [None])[0]
        if k:
            decoded = base64.b64decode(k + "==").decode("utf-8", errors="ignore")
            for part in reversed(decoded.split(",")):
                part = part.strip()
                if re.search(r"\.(pdf|docx?|pptx?|xlsx?|zip|rar|7z|txt)$",
                             part, re.I):
                    return sanitize(part)
    except Exception:
        pass

    if title and len(sanitize(title)) > 3:
        return sanitize(title) + ".pdf"

    m = re.search(r"[\w\-]+\.(pdf|docx?|pptx?|xlsx?|zip|rar)", row_text, re.I)
    if m:
        return sanitize(m.group(0))

    return f"assignment_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"


def download_file(url: str, dest: Path, cookies: dict) -> bool:
    """Stream a file from the LMS to disk using the active session cookies."""
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with httpx.stream("GET", url, cookies=cookies,
                          follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_bytes(8192):
                    f.write(chunk)
        log.info(f"Saved  {dest}")
        return True
    except Exception as exc:
        log.error(f"Download failed ({url[-60:]}): {exc}")
        return False


# ---------------------------------------------------------------------------
# Browser automation helpers
# ---------------------------------------------------------------------------

async def _click_first_visible(page, selectors: list[str],
                                timeout: int = 4_000) -> str | None:
    """Try each selector in order and click the first visible match."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.is_visible(timeout=timeout):
                await loc.click()
                return sel
        except Exception:
            continue
    return None


async def _fill_first_visible(page, selectors: list[str],
                               value: str, timeout: int = 3_000) -> bool:
    """Fill the first visible input that matches any selector."""
    for sel in selectors:
        try:
            field = page.locator(sel).first
            if await field.is_visible(timeout=timeout):
                await field.fill(value)
                return True
        except Exception:
            continue
    return False


async def _scrape_unsubmitted(page) -> list[dict]:
    """
    Parse the assignment table and return only rows where the student
    has not yet submitted (Action column contains a Submit link/button).

    Table columns (0-indexed):
      0  No.  |  1  Title  |  2  Assignment file  |  3  Student submission
      4  Marks  |  5  Returned comments  |  6  Action  |  7  Deadline
    """
    await page.wait_for_load_state("networkidle", timeout=15_000)
    await page.wait_for_timeout(1_500)

    rows = await page.evaluate("""
        () => {
            const out = [];
            document.querySelectorAll('table tbody tr').forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length < 7) return;

                // Col 6: Action — must contain a submit link to be unsubmitted
                const action = cells[6];
                const actionText = action.innerText.trim().toLowerCase();
                const hasSubmit =
                    action.querySelector('a, button, input[type="submit"]') &&
                    (actionText.includes('submit') || actionText.includes('upload'));
                if (!hasSubmit) return;

                // Col 2: professor's assignment file
                const link =
                    cells[2].querySelector('a[href*="Download.php"]') ||
                    cells[2].querySelector('a[href]');
                if (!link) return;

                out.push({
                    href:     link.href,
                    title:    cells[1]?.innerText.trim() ?? '',
                    deadline: cells[7]?.innerText.trim() ?? '',
                    rowText:  row.innerText.trim(),
                });
            });
            return out;
        }
    """)

    return rows


# ---------------------------------------------------------------------------
# Main watcher
# ---------------------------------------------------------------------------

async def run_watcher() -> None:
    """
    Full automation flow:
      login -> campus select -> LMS -> Assignments -> per-course scrape
      -> download new files -> notify
    """
    state = load_state()
    new_items: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            # -- Navigate to LMS landing page
            log.info("Opening LMS portal...")
            await page.goto(LMS_URL, wait_until="networkidle", timeout=60_000)

            # -- Click Student Sign In
            await _click_first_visible(page, [
                "#BodyPH_hlStudent",
                "a:has-text('Student Sign In')",
                "a:has-text('Student')",
            ], timeout=5_000)
            await page.wait_for_load_state("networkidle", timeout=30_000)
            log.info(f"Login form: {page.url}")

            # -- Select campus (value='1' = Islamabad E-8)
            for sel in ["#BodyPH_ddlInstituteID",
                        "select[id*='Institute']",
                        "select[id*='Campus']"]:
                try:
                    dd = page.locator(sel).first
                    if await dd.is_visible(timeout=4_000):
                        try:
                            await dd.select_option(value="1")
                        except Exception:
                            options = await dd.evaluate(
                                "el => Array.from(el.options).map(o => o.text)"
                            )
                            match = next(
                                (o for o in options
                                 if CAMPUS_NAME.lower() in o.lower()), None
                            )
                            if match:
                                await dd.select_option(label=match)
                        log.info("Campus selected.")
                        break
                except Exception:
                    continue

            # -- Fill enrollment number and password
            filled = await _fill_first_visible(
                page,
                ["#BodyPH_tbEnrollment", "input[id*='Enrollment']",
                 "input[name='username']", "input[type='text']:visible"],
                LMS_USERNAME,
            )
            if not filled:
                raise RuntimeError("Could not locate enrollment input field.")

            await _fill_first_visible(
                page,
                ["#BodyPH_tbPassword", "input[id*='Password']",
                 "input[type='password']"],
                LMS_PASSWORD,
            )

            # -- Submit login form and wait for redirect
            login_url = page.url
            await _click_first_visible(page, [
                "#BodyPH_btnLogin", "input[id*='btnLogin']",
                "button[type='submit']", "input[type='submit']",
            ])

            try:
                await page.wait_for_url(
                    lambda u: u != login_url, timeout=15_000
                )
            except PlaywrightTimeout:
                body = await page.inner_text("body")
                if any(kw in body.lower()
                       for kw in ["invalid", "incorrect", "wrong", "error"]):
                    raise RuntimeError(
                        "Login rejected — check LMS_USERNAME and LMS_PASSWORD."
                    )
                await page.wait_for_load_state("networkidle", timeout=20_000)

            log.info(f"Logged in: {page.url}")

            # -- Open LMS from CMS dashboard (link opens in new tab)
            for sel in ["a:has-text('LMS')", "a:has-text('Go to LMS')",
                        "a[href*='lms.bahria']", "a[href*='/LMS']"]:
                try:
                    btn = page.locator(sel).first
                    if not await btn.is_visible(timeout=4_000):
                        continue
                    async with context.expect_page(timeout=10_000) as evt:
                        await btn.click()
                    page = await evt.value
                    await page.wait_for_load_state("networkidle", timeout=30_000)
                    log.info(f"LMS tab: {page.url}")
                    break
                except PlaywrightTimeout:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                    if "login" not in page.url.lower():
                        break
                except Exception:
                    continue

            # Fallback: grab last open tab
            all_pages = context.pages
            if len(all_pages) > 1:
                page = all_pages[-1]
                await page.wait_for_load_state("networkidle", timeout=20_000)

            # -- Click Assignments in the LMS sidebar
            await _click_first_visible(page, [
                "a:has-text('Assignments')",
                "li:has-text('Assignments') a",
                "a[href*='ssignment']",
            ], timeout=5_000)
            await page.wait_for_load_state("networkidle", timeout=30_000)
            log.info(f"Assignments page: {page.url}")

            # -- Read course list from the #courseId dropdown
            courses = await page.evaluate("""
                () => {
                    const sel = document.querySelector('#courseId');
                    if (!sel) return [];
                    return Array.from(sel.options)
                        .filter(o => o.value.trim())
                        .map(o => ({ value: o.value, text: o.text.trim() }));
                }
            """)
            log.info(f"Found {len(courses)} course(s).")

            downloadable: list[dict] = []

            if courses:
                for course in courses:
                    log.info(f"  Checking: {course['text']}")
                    try:
                        await page.select_option(
                            "#courseId", value=course["value"]
                        )
                        rows = await _scrape_unsubmitted(page)
                        if rows:
                            log.info(
                                f"    {len(rows)} unsubmitted assignment(s)."
                            )
                        for r in rows:
                            r["course"] = course["text"]
                        downloadable.extend(rows)
                    except Exception as exc:
                        log.warning(f"    Skipped ({exc})")
            else:
                for r in await _scrape_unsubmitted(page):
                    r["course"] = "General"
                    downloadable.append(r)

            log.info(f"Total unsubmitted: {len(downloadable)}")

            # -- Extract session cookies for httpx downloads
            cookies = {c["name"]: c["value"] for c in await context.cookies()}

            # -- Download files not already in state
            for item in downloadable:
                url      = item["href"]
                course   = item.get("course", "General")
                title    = item.get("title") or "Assignment"
                deadline = item.get("deadline") or "Unknown"
                row_text = item.get("rowText", "")

                if url in state:
                    log.info(f"  Skip (seen): {title}")
                    continue

                filename = resolve_filename(url, title, row_text)
                dest     = DOWNLOAD_DIR / sanitize(course) / filename

                log.info(f"  New: {title!r} | {course} | due {deadline}")
                ok = download_file(url, dest, cookies)

                state[url] = {
                    "title":          title,
                    "deadline":       deadline,
                    "course":         course,
                    "downloaded_at":  datetime.utcnow().isoformat(),
                    "success":        ok,
                    "local_path":     str(dest) if ok else None,
                }
                save_state(state)
                new_items.append(state[url])

        except PlaywrightTimeout as exc:
            log.error(f"Timeout: {exc}")
            send_notification("Bahria Watcher - Timeout",
                              str(exc), priority="high")
        except Exception as exc:
            log.error(f"Error: {exc}", exc_info=True)
            send_notification("Bahria Watcher - Error",
                              str(exc), priority="high")
        finally:
            await browser.close()

    # -- Send one notification per course that had new assignments
    if new_items:
        by_course: dict[str, list] = {}
        for item in new_items:
            by_course.setdefault(item["course"], []).append(item)

        for course, items in by_course.items():
            ok_count = sum(1 for i in items if i["success"])
            lines    = [
                f"Course: {course}",
                f"Downloaded: {ok_count}/{len(items)}",
                "",
            ]
            for i in items[:6]:
                status = "OK" if i["success"] else "FAIL"
                lines.append(f"[{status}] {i['title']}")
                lines.append(f"      Due: {i['deadline']}")
            if len(items) > 6:
                lines.append(f"  ...and {len(items) - 6} more")
            if _CI_RUN_URL:
                lines += ["", f"Artifacts: {_CI_RUN_URL}"]

            send_notification(
                f"New Assignment - {course}",
                "\n".join(lines),
                priority="high",
            )
    else:
        log.info("No new unsubmitted assignments this run.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    log.info("-" * 60)
    log.info("Bahria LMS Watcher")
    log.info(f"Download dir : {DOWNLOAD_DIR}")
    log.info(f"State file   : {STATE_FILE}")
    log.info("-" * 60)
    asyncio.run(run_watcher())
    log.info("Done.")
