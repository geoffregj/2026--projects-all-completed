#!/usr/bin/env python3
"""
ig_selenium.py — Instagram automation via real Chrome browser (Selenium)
Replaces the raw `requests` private-API calls from the Termux build.

WHY SELENIUM ON DESKTOP:
  Instagram's private API (the endpoints the old script hit directly with
  `requests`) is heavily fingerprinted and easy to get flagged/rate-limited
  from a script that never renders a page. A real Chrome instance driven by
  Selenium looks like an actual logged-in browser session — same cookies,
  same JS execution, same network fingerprint a human has — so it's far
  more durable on a PC where there's no need to fake a mobile user-agent.

CAVEAT (be honest with yourself about this):
  Instagram's DOM uses obfuscated class names that rotate. This module
  prefers aria-label / role / svg-title selectors because those are the
  most stable ones IG has, but they WILL occasionally break when IG ships
  a redesign. Run with SELENIUM_DEBUG=1 to dump a screenshot + page source
  snippet to ~/cortana_debug/ whenever a selector lookup fails, so you can
  patch it fast instead of guessing blind.

Install:
    pip install selenium --break-system-packages
    sudo apt install chromium-chromedriver     # or match your Chrome version
"""

import os
import readline  # noqa: F401 — see ig_manager.py for why
import json
import re
import time
import random
from datetime import datetime, timedelta
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, ElementClickInterceptedException,
    StaleElementReferenceException,
)

try:
    import requests as _requests
except ImportError:
    _requests = None

HOME = os.path.expanduser("~")
COOKIE_FILE = os.path.join(HOME, "ig_cookies.json")
DEBUG_DIR = os.path.join(HOME, "cortana_debug")
DEBUG = os.environ.get("SELENIUM_DEBUG", "0") == "1"
ID_CACHE_FILE = os.path.join(HOME, "python", "id_cache.json")

IG_BASE = "https://www.instagram.com"

R="\033[0m"; DIM="\033[2m"
GRN="\033[92m"; RED="\033[91m"; YLW="\033[93m"; CYN="\033[96m"

# Headers for the private API calls used ONLY for the unfollow-by-id step
# (see unfollow_batch). Ported from hunter15.py. We deliberately do NOT use
# raw requests for login or browsing — only for this one POST, riding on
# cookies from an already-authenticated, already-rendering browser session,
# to keep the fingerprint risk this module was built to avoid as low as
# possible while still being reliable.
_API_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://www.instagram.com/",
    "Origin": "https://www.instagram.com",
}


# ══════════════════════════════════════════════════════════
# DRIVER SETUP
# ══════════════════════════════════════════════════════════
def _binary_location():
    """Find whichever Chromium-based browser is actually installed.
    Linux Mint blocks the snap-based chromium-browser package on purpose,
    so we check for real Google Chrome and Brave (both work fine with
    Selenium's Chrome driver since they're both Chromium under the hood)."""
    for path in (
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/usr/bin/brave-browser", "/usr/bin/chromium", "/usr/bin/chromium-browser",
    ):
        if os.path.exists(path):
            return path
    return None


def make_driver(headless=False):
    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    binary = _binary_location()
    if binary:
        opts.binary_location = binary

    # Auto-fetch a chromedriver that matches whichever browser is installed
    # (Google Chrome or Brave) instead of relying on apt, which Mint blocks
    # for the chromium-chromedriver package. Falls back to PATH if
    # webdriver-manager isn't installed.
    driver = None
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        from selenium.webdriver.chrome.service import Service
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=opts)
    except ImportError:
        print(" (tip: pip install webdriver-manager --break-system-packages"
              " to stop having to manage chromedriver by hand)")
        driver = webdriver.Chrome(options=opts)
    except Exception as e:
        print(f" webdriver-manager failed ({e}), falling back to PATH chromedriver...")
        driver = webdriver.Chrome(options=opts)

    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"},
    )
    return driver


def _debug_dump(driver, tag):
    if not DEBUG:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    ts = datetime.now().strftime("%H%M%S")
    try:
        driver.save_screenshot(os.path.join(DEBUG_DIR, f"{tag}_{ts}.png"))
        with open(os.path.join(DEBUG_DIR, f"{tag}_{ts}.html"), "w") as f:
            f.write(driver.page_source[:20000])
    except Exception:
        pass


def _dismiss_popups(driver):
    """Click away 'Save login info' / 'Turn on notifications' dialogs."""
    for label in ("Not Now", "Not now", "Cancel"):
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, f"//button[text()='{label}']"))
            )
            btn.click()
            time.sleep(1)
        except TimeoutException:
            pass


# ══════════════════════════════════════════════════════════
# LOGIN — cookie persistence so you don't 2FA every run
# ══════════════════════════════════════════════════════════
def load_cookies(driver):
    if not os.path.exists(COOKIE_FILE):
        return False
    driver.get(IG_BASE)
    time.sleep(2)
    with open(COOKIE_FILE) as f:
        cookies = json.load(f)
    for c in cookies:
        c.pop("sameSite", None)
        try:
            driver.add_cookie(c)
        except Exception:
            pass
    driver.get(f"{IG_BASE}/")
    time.sleep(2)
    return is_logged_in(driver)


def save_cookies(driver):
    with open(COOKIE_FILE, "w") as f:
        json.dump(driver.get_cookies(), f)
    os.chmod(COOKIE_FILE, 0o600)


def clean_username(raw):
    """Strip anything that isn't a valid Instagram username character.

    Terminal input can occasionally leak raw control/escape bytes into a
    typed string — e.g. pressing an arrow key sends ESC[A/B/C/D, and if the
    terminal isn't fully absorbing that into line-editing, those bytes ride
    along invisibly. .strip() only trims whitespace, so this catches the
    rest. Instagram usernames are letters, digits, periods, underscores
    only, max 30 chars.
    """
    import re
    return re.sub(r"[^A-Za-z0-9_.]", "", raw).strip(".")[:30].lower()


def is_logged_in(driver):
    try:
        driver.find_element(By.XPATH, "//a[@href='/direct/inbox/']")
        return True
    except NoSuchElementException:
        try:
            driver.find_element(By.XPATH, "//*[@aria-label='Home']")
            return True
        except NoSuchElementException:
            return False


def login(username=None, password=None, headless=False):
    """
    Returns a logged-in driver, or None on failure.
    Tries saved cookies first; falls back to interactive login (asks for
    2FA in the terminal same as the old version did).
    """
    driver = make_driver(headless=headless)
    if load_cookies(driver):
        print(" ✓ Restored Instagram session from cookies.")
        return driver

    if not username:
        username = input(" Instagram username: ").strip()
    if not password:
        password = __import__("getpass").getpass(" Instagram password: ")

    driver.get(f"{IG_BASE}/accounts/login/")
    wait = WebDriverWait(driver, 15)
    try:
        user_field = wait.until(EC.presence_of_element_located((By.NAME, "username")))
        pass_field = driver.find_element(By.NAME, "password")
        user_field.clear(); user_field.send_keys(username)
        pass_field.clear(); pass_field.send_keys(password)
        pass_field.send_keys(Keys.RETURN)
    except TimeoutException:
        _debug_dump(driver, "login_form_not_found")
        print(" Could not find login form — Instagram may have changed the page.")
        return None

    time.sleep(4)

    # 2FA prompt
    try:
        code_field = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.NAME, "verificationCode"))
        )
        code = input(" 2FA code: ").strip()
        code_field.send_keys(code)
        code_field.send_keys(Keys.RETURN)
        time.sleep(4)
    except TimeoutException:
        pass

    _dismiss_popups(driver)

    if is_logged_in(driver):
        save_cookies(driver)
        print(" ✓ Logged in and cookies saved.")
        return driver

    _debug_dump(driver, "login_failed")
    print(" Login failed — check credentials, or Instagram is showing a challenge.")
    print(" If a 'suspicious login' / captcha page opened, solve it manually")
    print(" in the browser window, then press Enter here to retry the check.")
    input(" Press Enter once resolved (or Ctrl+C to abort)... ")
    if is_logged_in(driver):
        save_cookies(driver)
        return driver
    return None


# ══════════════════════════════════════════════════════════
# SHARED — opening the followers/following dialog reliably
# ══════════════════════════════════════════════════════════
def _find_scrollable(driver, dialog_xpath="//div[@role='dialog']"):
    """Find the real scrollable list container inside the dialog via the
    DOM itself (scrollHeight > clientHeight) instead of guessing at an
    inline style string, which breaks the instant IG changes markup."""
    try:
        dialog = driver.find_element(By.XPATH, dialog_xpath)
    except NoSuchElementException:
        return None
    try:
        candidates = driver.execute_script(
            "return Array.from(arguments[0].querySelectorAll('*')).filter("
            "  el => el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 100"
            ");",
            dialog,
        )
    except Exception:
        return None
    return candidates[0] if candidates else None


def _find_stat_link(driver, username, what):
    """Try several selector strategies for the 'X following'/'X followers'
    stat, most-specific first — IG's own-profile stat elements aren't
    reliably plain <a href> across accounts/rollouts."""
    candidates = [
        (By.XPATH, f"//a[contains(@href,'/{username}/{what}/')]"),
        (By.XPATH, f"//*[@role='link'][contains(@href,'/{username}/{what}/')]"),
        (By.XPATH, f"//a[contains(@href,'/{what}/')]"),
        (By.XPATH, f"//header//*[contains(text(),'{what}')]/ancestor-or-self::*[@role='link' or self::a][1]"),
    ]
    for by, xpath in candidates:
        try:
            el = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, xpath)))
            return el
        except TimeoutException:
            continue
    return None


def open_profile_list_dialog(driver, username, what):
    """Open the followers/following modal for `username`. Tries a cold
    direct nav first (fast path); if IG doesn't actually render the modal
    from that (common — it's SPA-routed), falls back to loading the profile
    and clicking the real stat link, which triggers the client-side router.
    Returns True/False.
    """
    driver.get(f"{IG_BASE}/{username}/{what}/")
    _dismiss_popups(driver)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        return True
    except TimeoutException:
        pass

    # fallback: load profile like a human, click the stat link
    driver.get(f"{IG_BASE}/{username}/")
    _dismiss_popups(driver)
    time.sleep(1.5)
    link = _find_stat_link(driver, username, what)
    if link is None:
        _debug_dump(driver, f"{what}_dialog_missing")
        return False
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", link)
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        return True
    except TimeoutException:
        _debug_dump(driver, f"{what}_dialog_missing")
        return False


# ══════════════════════════════════════════════════════════
# UNFOLLOW
# ══════════════════════════════════════════════════════════
def _api_session_from_driver(driver):
    """Build a requests.Session() authenticated with the same cookies the
    already-logged-in Selenium browser is using. Returns (session, user_id)
    or (None, None) if requests isn't installed or a required cookie is
    missing (falls back to DOM clicking in that case).

    Forwards the FULL cookie jar (not just sessionid/csrftoken/ds_user_id).
    Some endpoints — notably /accounts/current_user/ used for owner
    verification — are stricter than the friendship endpoints and will
    silently reject a session missing things like `mid`/`datr`/`rur`,
    which previously produced false "logged-in account doesn't match"
    warnings even when the session was genuinely correct."""
    if _requests is None:
        return None, None
    all_cookies = driver.get_cookies()
    cookie_map = {c["name"]: c["value"] for c in all_cookies}
    sessionid = cookie_map.get("sessionid")
    csrftoken = cookie_map.get("csrftoken")
    user_id = cookie_map.get("ds_user_id")
    if not (sessionid and csrftoken and user_id):
        return None, None
    s = _requests.Session()
    s.headers.update(_API_HEADERS)
    try:
        real_ua = driver.execute_script("return navigator.userAgent;")
        if real_ua:
            s.headers["User-Agent"] = real_ua
    except Exception:
        pass  # fall back to the hardcoded UA in _API_HEADERS if this ever fails
    s.headers["X-CSRFToken"] = csrftoken
    for c in all_cookies:
        try:
            s.cookies.set(c["name"], c["value"], domain=".instagram.com")
        except Exception:
            continue
    return s, user_id


def verify_api_session_owner(session):
    """Returns the authenticated account's own username (lowercased), or
    None if it can't be verified. The friendship-list-by-id endpoints below
    always operate on whoever owns the session's cookies — NOT on whatever
    username string gets passed in elsewhere — so anything using them for
    full-list analysis must confirm it's actually your own account first,
    or it'll silently hand back your own lists mislabeled as someone else's.

    2026-08-19: this consistently returns HTTP 400 with body
    {"message":"useragent mismatch","status":"fail"} for this account, even
    after forwarding the driver's real User-Agent above — ruling out the UA
    string itself as the cause. Leading theory: TLS/network-level
    fingerprinting (JA3/JA4-style) distinguishing Python's `requests` from
    real Chrome at the handshake level, independent of header content.
    Treated as a dead end for this endpoint specifically — not something
    more header changes are expected to fix."""
    try:
        r = session.get(f"{IG_BASE}/api/v1/accounts/current_user/?edit=true", timeout=10)
        if r.status_code == 200:
            return (r.json().get("user", {}).get("username") or "").lower()
        body_preview = r.text[:300].replace("\n", " ")
        print(f" {DIM}(owner-verify call returned HTTP {r.status_code} — "
              f"treating as unverified, not necessarily a real mismatch){R}")
        print(f" {DIM}(response body: {body_preview}){R}")
    except Exception as e:
        print(f" {DIM}(owner-verify call errored: {e} — treating as unverified){R}")
    return None


def fetch_full_friendship_list(session, user_id, kind):
    """Fetch your COMPLETE followers or following list via the private API
    (kind='following' or 'followers'), ~200 per page — the same endpoint
    family unfollow_batch already uses successfully, just without filtering
    to a target subset. Only valid for the account that owns `session` (see
    verify_api_session_owner). Returns a set of usernames, or None if the
    very first page fails outright (caller should fall back to DOM scroll)."""
    assert kind in ("following", "followers")
    usernames = set()
    next_page = None
    page = 1
    while True:
        url = f"{IG_BASE}/api/v1/friendships/{user_id}/{kind}/?count=200"
        if next_page:
            url += f"&max_id={next_page}"
        try:
            r = session.get(url, timeout=20)
        except Exception as e:
            print(f" ⚠ network error fetching {kind} page {page}: {e}")
            return usernames if usernames else None
        if r.status_code == 429:
            print(f" ⚠ rate limited fetching {kind} — waiting 60s...")
            time.sleep(60)
            continue
        if r.status_code != 200:
            print(f" ⚠ unexpected status {r.status_code} fetching {kind} page {page}")
            return usernames if usernames else None
        try:
            data = r.json()
            users = data.get("users", [])
        except Exception:
            return usernames if usernames else None
        for u in users:
            uname = (u.get("username") or "").lower()
            if uname:
                usernames.add(uname)
        print(f" {kind}: page {page} — {len(usernames)} so far")
        next_page = data.get("next_max_id")
        if not next_page or not users:
            break
        page += 1
        time.sleep(random.uniform(2, 4))  # polite pause between pages
    return usernames


def _fetch_following_ids(session, user_id, targets_set, cache_path=ID_CACHE_FILE):
    """Bulk-fetch numeric user IDs for accounts you follow, ~200 per page,
    instead of a per-target DOM search. Ported from hunter15.py. Caches to
    disk so repeat runs don't re-fetch people we already have an ID for."""
    cached = {}
    if os.path.exists(cache_path):
        try:
            cached = json.load(open(cache_path))
        except Exception:
            cached = {}
    already = {u: cached[u] for u in targets_set if u in cached}
    need = targets_set - set(already)
    if not need:
        print(f" All {len(already)} target IDs already cached.")
        return already

    id_map = dict(cached)
    next_page = None
    page = 1
    while True:
        url = f"{IG_BASE}/api/v1/friendships/{user_id}/following/?count=200"
        if next_page:
            url += f"&max_id={next_page}"
        try:
            r = session.get(url, timeout=20)
        except Exception as e:
            print(f" ⚠ network error fetching following page {page}: {e}")
            break
        if r.status_code == 429:
            print(" ⚠ rate limited fetching following list — waiting 60s...")
            time.sleep(60)
            continue
        if r.status_code != 200:
            print(f" ⚠ unexpected status {r.status_code} fetching following page {page} — "
                  f"falling back to DOM clicking for remaining accounts.")
            break
        try:
            data = r.json()
            users = data.get("users", [])
        except Exception:
            break
        for u in users:
            uname = (u.get("username") or "").lower()
            uid = str(u.get("pk") or u.get("id") or "")
            if uname and uid:
                id_map[uname] = uid
        print(f" page {page}: {len(users)} accounts scanned "
              f"({sum(1 for u in targets_set if u in id_map)}/{len(targets_set)} targets found so far)")
        json.dump(id_map, open(cache_path, "w"))
        next_page = data.get("next_max_id")
        if not next_page or not users:
            break
        page += 1
        time.sleep(random.uniform(3, 6))  # polite pause between pages

    return {u: id_map[u] for u in targets_set if u in id_map}


def _unfollow_by_id(session, user_id):
    """Returns (status, detail) — status is 'ok', 'rate_limited',
    'checkpoint', or 'error'; detail carries the raw response text on
    anything but 'ok', for logging/diagnosis instead of a bare label.

    'checkpoint' means Instagram returned HTTP 200 (or another success-
    shaped response) but the JSON body shows the unfollow didn't actually
    take — a soft block, not a per-account failure.

    2026-08-19: confirmed in practice that the destroy endpoint can also
    return a full HTML page (a login/checkpoint interstitial) instead of
    any JSON at all — that lands in 'error' here (r.json() throws), not
    'checkpoint', since there's no parseable body to inspect. Distinct
    from the JSON-shaped soft-block case above: this looks like the same
    systemic write-action rejection already confirmed on other endpoints
    this session (current_user, DM), not an account-specific checkpoint —
    which is why the caller treats 'error' as fallback-worthy (try a real
    browser click instead) while 'checkpoint' still means stop the batch.
    """
    try:
        r = session.post(
            f"{IG_BASE}/api/v1/friendships/destroy/{user_id}/",
            data={"user_id": user_id}, timeout=15,
        )
    except Exception as e:
        return "error", str(e)

    if r.status_code == 429:
        return "rate_limited", None
    if r.status_code == 403:
        return "checkpoint", r.text[:300]
    if r.status_code != 200:
        return "error", r.text[:300]

    try:
        data = r.json()
    except Exception:
        # Not valid JSON at all — e.g. a full HTML page. Real, distinct
        # failure mode, not the same as a JSON-shaped soft block.
        return "error", r.text[:300]

    if data.get("status") != "ok":
        detail = str(data)[:300]
        return ("checkpoint", detail) if "checkpoint" in str(data).lower() else ("error", detail)
    if data.get("friendship_status", {}).get("following") is True:
        return "checkpoint", str(data)[:300]
    return "ok", None


def _dom_unfollow_one(driver, username, dialog_xpath="//div[@role='dialog']"):
    """Shared click sequence for unfollowing one account through the real
    browser — used both by the per-target fallback in unfollow_batch's API
    path (when a destroy call fails) and by the original all-or-nothing
    DOM path below (when no API session could be built at all), so the
    click logic isn't duplicated in two places. Assumes the following
    dialog is already open on `driver`. Returns (status, detail):
    "ok" / "not_found" / "button_not_found" / "stale" / "blocked" / "error"

    The search box lookup is scoped to inside the open dialog
    specifically (`{dialog_xpath}//input[@placeholder='Search']`), not a
    bare `input[placeholder='Search']` — Instagram's own global left-nav
    search box has the same placeholder text, and a bare selector matches
    whichever one comes first in document order. Confirmed in practice:
    every target came back "not found" even for an account manually
    verified to still be followed, consistent with typing landing in the
    wrong search box entirely.
    """
    try:
        search_box = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.XPATH, f"{dialog_xpath}//input[@placeholder='Search']")
            )
        )
        search_box.clear()
        search_box.send_keys(username)
        time.sleep(1.5)

        row_xpath = f"{dialog_xpath}//a[contains(@href, '/{username}/')]"
        try:
            row_link = WebDriverWait(driver, 6).until(
                EC.presence_of_element_located((By.XPATH, row_xpath))
            )
        except TimeoutException:
            return "not_found", None

        try:
            row_li = row_link.find_element(By.XPATH, "./ancestor::li[1]")
        except NoSuchElementException:
            row_li = row_link.find_element(By.XPATH, "./ancestor::div[.//button][1]")

        unfollow_btn = None
        for btn_xpath in (
            ".//button[text()='Following' or text()='Requested']",
            ".//button[contains(text(),'Following') or contains(text(),'Requested')]",
            ".//button",
        ):
            try:
                unfollow_btn = row_li.find_element(By.XPATH, btn_xpath)
                break
            except NoSuchElementException:
                continue

        if unfollow_btn is None:
            return "button_not_found", None

        unfollow_btn.click()
        time.sleep(1)
        confirm = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//button[text()='Unfollow' or contains(text(),'Unfollow')]",
            ))
        )
        confirm.click()
        return "ok", None
    except StaleElementReferenceException:
        return "stale", None
    except ElementClickInterceptedException:
        return "blocked", None
    except Exception as e:
        return "error", str(e)


def unfollow_batch(driver, my_username, targets, max_batch=20, log_path="unfollow_log.json"):
    """
    Unfollows the given usernames. Prefers Instagram's private API (fast,
    ID-based, no DOM guessing) using cookies from the already-logged-in
    browser; falls back to clicking through the following dialog if no
    API session could be built at all, AND per-target the instant an
    individual API destroy call fails with 'error' (not 'checkpoint' —
    a checkpoint means stop the whole batch, since it indicates an
    account-level soft block that DOM-clicking in the same session would
    likely also hit; 'error', especially an HTML-not-JSON response, looks
    like the same systemic write-action rejection seen elsewhere this
    session and is worth trying to route around via a real browser click).
    """
    log = []
    if os.path.exists(log_path):
        try:
            log = json.load(open(log_path))
        except Exception:
            log = []

    if not my_username:
        print(" No username given — can't open a following list for nobody.")
        return 0, 0, len(targets)

    batch = targets[:max_batch]

    # ── Preferred: API-based unfollow ───────────────────────────────────
    session, user_id = _api_session_from_driver(driver)
    if session is not None:
        print(" Using API-based unfollow (reusing your browser's login cookies)...")
        targets_set = set(batch)
        id_map = _fetch_following_ids(session, user_id, targets_set)
        done = skipped = errors = 0
        total = len(id_map)
        i = 0
        dom_dialog_open = False
        for username in batch:
            uid = id_map.get(username)
            if not uid:
                print(f" ⚠ @{username} — not in your following list (already gone)")
                skipped += 1
                log.append({"username": username, "status": "not_found",
                            "timestamp": datetime.now().isoformat()})
                json.dump(log, open(log_path, "w"), indent=2)
                continue
            i += 1
            result, detail = _unfollow_by_id(session, uid)
            if result == "ok":
                print(f" ✔ [{i}/{total}] @{username}")
                done += 1
                log.append({"username": username, "uid": uid, "status": "unfollowed",
                            "timestamp": datetime.now().isoformat()})
            elif result == "rate_limited":
                print(f" ⚠ @{username} — rate limited, backing off 90s")
                log.append({"username": username, "status": "rate_limited",
                            "timestamp": datetime.now().isoformat()})
                json.dump(log, open(log_path, "w"), indent=2)
                time.sleep(90)
                continue
            elif result == "checkpoint":
                print(f" 🛑 @{username} — Instagram accepted the request but the"
                      f" unfollow didn't actually take (still shows as following)."
                      f" This is a soft block on the session, not a per-account issue.")
                log.append({"username": username, "uid": uid, "status": "silent_block",
                            "detail": detail, "timestamp": datetime.now().isoformat()})
                json.dump(log, open(log_path, "w"), indent=2)
                print(" 🛑 Stopping batch — continuing would just log more fake"
                      " 'successes'. Log into instagram.com in a real browser,")
                print("    clear any checkpoint/challenge prompt, then re-run.")
                break
            else:
                # 'error' — API destroy call failed (often an HTML response,
                # not JSON at all). Fall back to a real browser click for
                # THIS ONE target instead of just logging an API error.
                if not dom_dialog_open:
                    print(f" {DIM}[{i}/{total}] API unfollow failing — switching to "
                          f"browser-click fallback for the rest of this batch{R}")
                    if open_profile_list_dialog(driver, my_username, "following"):
                        dom_dialog_open = True
                        time.sleep(2)
                    else:
                        print(f" {RED}Could not open the following list in-browser either "
                              f"— logging remaining failures as errors.{R}")
                if dom_dialog_open:
                    dom_status, dom_detail = _dom_unfollow_one(driver, username)
                    if dom_status == "ok":
                        print(f" ✔ [{i}/{total}] @{username} (via browser click)")
                        done += 1
                        log.append({"username": username, "uid": uid, "status": "unfollowed",
                                    "via": "dom_fallback",
                                    "timestamp": datetime.now().isoformat()})
                    elif dom_status == "not_found":
                        print(f" ⚠ @{username} — not found via browser search either")
                        skipped += 1
                        log.append({"username": username, "status": "not_found_dom",
                                    "timestamp": datetime.now().isoformat()})
                    else:
                        print(f" ✗ @{username} — API error: {detail} | "
                              f"browser fallback also failed: {dom_status} {dom_detail or ''}")
                        errors += 1
                        log.append({"username": username, "uid": uid, "status": "error",
                                    "detail": detail, "dom_status": dom_status,
                                    "timestamp": datetime.now().isoformat()})
                else:
                    print(f" ✗ @{username} — API error: {detail}")
                    errors += 1
                    log.append({"username": username, "uid": uid, "status": "error",
                                "detail": detail, "timestamp": datetime.now().isoformat()})
            json.dump(log, open(log_path, "w"), indent=2)
            time.sleep(random.uniform(25, 55))  # keep it human-paced regardless of API speed
        return done, skipped, errors

    # ── Fallback: click through the following dialog ────────────────────
    print(" Could not build an API session from cookies (requests not installed, "
          "or a cookie was missing) — falling back to clicking through the UI.")
    if not open_profile_list_dialog(driver, my_username, "following"):
        print(f" Could not open the following list for @{my_username}.")
        print(" Check: is that the right username? Is the account private")
        print(" and you're not logged in as it? Run with SELENIUM_DEBUG=1")
        print(" and check ~/cortana_debug/ for a screenshot of what loaded.")
        return 0, 0, len(targets)

    time.sleep(2)
    done = skipped = errors = 0
    batch = targets[:max_batch]
    print(f"\n Unfollowing {len(batch)} accounts...\n")

    for username in batch:
        status, detail = _dom_unfollow_one(driver, username)
        if status == "ok":
            print(f" ✔ @{username}")
            done += 1
            log.append({"username": username, "status": "unfollowed",
                        "timestamp": datetime.now().isoformat()})
        elif status == "not_found":
            print(f" ⚠ @{username} — not in search results, skipping")
            skipped += 1
            log.append({"username": username, "status": "not_found",
                        "timestamp": datetime.now().isoformat()})
        elif status == "button_not_found":
            print(f" ✗ @{username} — row found but no follow-button matched (markup changed?)")
            errors += 1
            log.append({"username": username, "status": "button_not_found",
                        "timestamp": datetime.now().isoformat()})
            _debug_dump(driver, f"unfollow_button_missing_{username}")
        elif status == "stale":
            print(f" ⚠ @{username} — page changed mid-click, will retry next run")
            skipped += 1
            log.append({"username": username, "status": "stale",
                        "timestamp": datetime.now().isoformat()})
        elif status == "blocked":
            print(f" ✗ @{username} — click blocked, skipping")
            errors += 1
        else:
            print(f" ✗ @{username} — {detail}")
            errors += 1
            _debug_dump(driver, f"unfollow_error_{username}")

        json.dump(log, open(log_path, "w"), indent=2)
        time.sleep(random.uniform(25, 55))  # keep it human-paced even without API rate limits

    return done, skipped, errors


# ══════════════════════════════════════════════════════════
# DM AUTO-REPLY
# ══════════════════════════════════════════════════════════
_TIME_AGO_RE = re.compile(r"(\d+\s*[smhdw]|\bago\b)", re.IGNORECASE)

def _looks_like_note_bubble(el):
    """The broadest fallback selector (any button-role element with an
    avatar image) matches Instagram's Notes tray just as well as real
    conversation rows — both are clickable divs containing an <img>, and
    notes render first in the page, so the scan was locking onto them and
    never reaching real threads ('clicking it didn't navigate anywhere').
    Real inbox rows show a trailing time-ago suffix ('2h', '57m', '9h',
    '1d'); note bubbles just show a name or 'Your note'. Not a DOM
    property — a text heuristic based on what's actually visible."""
    try:
        text = el.text.strip()
    except Exception:
        return False
    return bool(text) and not _TIME_AGO_RE.search(text)


def _find_dm_rows(driver):
    """Instagram's inbox list doesn't reliably expose conversation rows as
    plain <a href="/direct/t/..."> — try several structural selectors,
    most specific first, and use whichever actually finds something."""
    for xpath in (
        "//a[contains(@href,'/direct/t/')]",
        "//div[@role='listbox']//div[@role='listitem']",
        "//div[@role='listitem']//div[@role='button']",
        "//div[@role='listitem']",
        "//div[@role='row']",
        "//div[@role='button'][.//img]",  # last resort — rows generally have an avatar
    ):
        try:
            els = driver.find_elements(By.XPATH, xpath)
        except Exception:
            continue
        if not els:
            continue
        # Only the broad last-resort selector is ambiguous with the notes
        # tray — the more specific ones above it don't match notes at all,
        # so only filter when we actually fell through to that one.
        if xpath == "//div[@role='button'][.//img]":
            filtered = [e for e in els if not _looks_like_note_bubble(e)]
            if filtered:
                return filtered, xpath + " (notes filtered out)"
            continue  # everything matched looked like a note — try nothing left, fall through
        return els, xpath
    return [], None


def dm_check_and_reply(driver, reply_fn, avoid_fn, log_path="dm_log.json",
                        max_threads=15, safety_limit=200, allowed_senders=None):
    """
    reply_fn(context, message, history) -> str   — plug in your Groq call
    avoid_fn(text) -> bool                        — plug in avoid-topics check
    allowed_senders: optional iterable of usernames (case-insensitive). If
                      given, only threads whose sender is in this set get a
                      reply — everything else is left alone (not logged as
                      skipped, so it's picked up again once the sender is
                      added back to the allow-list).

    Drives the real UI (clicks the real row, types into the real message
    box, clicks the real send) instead of calling Instagram's private API,
    so it doesn't carry a fingerprinted header. Slower, but every step
    prints what it's actually finding so a zero-thread or zero-reply run
    tells you why instead of silently doing nothing. Rows are found by
    role/structure rather than href, since IG doesn't reliably expose
    plain <a href="/direct/t/..."> anymore; we click a row, then read
    driver.current_url afterward to get the thread's real URL.
    """
    allow_set = {s.strip().lstrip("@").lower() for s in allowed_senders} if allowed_senders else None
    log = {}
    if os.path.exists(log_path):
        try:
            log = json.load(open(log_path))
        except Exception:
            log = {}

    driver.get(f"{IG_BASE}/direct/inbox/")
    _dismiss_popups(driver)

    try:
        WebDriverWait(driver, 12).until(lambda d: _find_dm_rows(d)[0])
    except TimeoutException:
        print(f" {RED}No DM thread rows appeared within 12s (tried several selectors).{R}")
        print(f" {DIM}landed on: {driver.current_url}{R}")
        print(f" {DIM}page title: {driver.title}{R}")
        was_debug = DEBUG
        globals()["DEBUG"] = True
        _debug_dump(driver, "inbox_no_threads")
        globals()["DEBUG"] = was_debug
        print(f" {DIM}(saved screenshot + html to ~/cortana_debug/ regardless of SELENIUM_DEBUG){R}")
        return 0

    rows, matched_selector = _find_dm_rows(driver)
    n_threads = min(len(rows), max_threads)
    print(f" {DIM}Inbox: {len(rows)} row(s) found via `{matched_selector}` "
          f"(checking first {n_threads}).{R}")

    replied = 0
    seen_hrefs = set()
    consecutive_failures = 0
    backoff_seconds = 30

    for i in range(n_threads):
        if len(seen_hrefs) >= safety_limit:
            break

        # Re-navigate and re-fetch rows fresh each loop: once we click into
        # a thread the earlier row elements go stale, and indices can shift
        # if the list re-sorts after a reply.
        driver.get(f"{IG_BASE}/direct/inbox/")
        _dismiss_popups(driver)
        try:
            WebDriverWait(driver, 8).until(lambda d: len(_find_dm_rows(d)[0]) > i)
        except TimeoutException:
            print(f" {YLW}Row {i}: inbox didn't re-render with enough rows — stopping.{R}")
            break
        rows, _ = _find_dm_rows(driver)
        if i >= len(rows):
            break
        row = rows[i]

        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
            time.sleep(0.2)
            driver.execute_script("arguments[0].click();", row)
        except Exception as e:
            print(f" {YLW}Row {i}: click failed ({e}) — skipping.{R}")
            continue

        try:
            WebDriverWait(driver, 8).until(lambda d: d.current_url != f"{IG_BASE}/direct/inbox/")
        except TimeoutException:
            print(f" {YLW}Row {i}: clicking it didn't navigate anywhere — skipping.{R}")
            continue

        href = driver.current_url
        seen_hrefs.add(href)
        _dismiss_popups(driver)

        try:
            WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH, "//div[@dir='auto']"))
            )
        except TimeoutException:
            print(f" {YLW}{href}: no message bubbles rendered — skipping.{R}")
            continue

        try:
            sender = driver.title.split("•")[0].strip() or "unknown"
        except Exception:
            sender = "unknown"

        if allow_set is not None and sender.strip().lstrip("@").lower() not in allow_set:
            print(f" {DIM}{sender}: not on the allow-list — skipping.{R}")
            continue

        try:
            bubbles = driver.find_elements(By.XPATH, "//div[@dir='auto']")
            tail = bubbles[-10:]  # look at more than 5 raw bubbles since we filter empties next
            texts = []
            elems = []
            for b in tail:
                t = b.text.strip()
                if t:
                    texts.append(t)
                    elems.append(b)
            texts, elems = texts[-5:], elems[-5:]

            # Instagram doesn't label which side sent which bubble in the
            # DOM (no reliable class/aria-label for this), but visually
            # your own messages are right-aligned and theirs are
            # left-aligned — the same pattern every chat UI uses. Cluster
            # by horizontal position instead of guessing a fixed pixel
            # threshold, so it adapts to window size/layout.
            recent = []
            if elems:
                try:
                    lefts = driver.execute_script(
                        "return arguments[0].map(el => el.getBoundingClientRect().left);", elems
                    )
                    mid = (max(lefts) + min(lefts)) / 2
                    for text, left in zip(texts, lefts):
                        role = "assistant" if left > mid else "user"
                        recent.append({"role": role, "content": text})
                except Exception:
                    # Position lookup failed for some reason — fall back to
                    # untagged text rather than losing the message entirely.
                    recent = [{"role": "unknown", "content": t} for t in texts]

            # Reply to the last message actually from them, not just the
            # last bubble on screen — if your own message happens to be
            # the most recent one (e.g. you replied outside the bot,
            # nothing new since), there's nothing new to respond to.
            their_msgs = [h["content"] for h in recent if h["role"] in ("user", "unknown")]
            last_text = their_msgs[-1] if their_msgs else ""
        except Exception as e:
            print(f" {YLW}{href}: error reading bubbles: {e}{R}")
            recent = []
            last_text = ""

        if not last_text:
            print(f" {DIM}{href}: last message in thread is already yours — nothing new to reply to.{R}")
            continue

        print(f" {DIM}{sender}: " + " | ".join(
            f"{'You' if h['role']=='assistant' else 'Them'}: {h['content'][:30]}" for h in recent
        ) + f"{R}")

        key = f"{href}:{hash(last_text)}"
        if key in log:
            print(f" {DIM}{sender}: already replied to this message — skipping.{R}")
            continue
        if avoid_fn(last_text):
            print(f" {DIM}{sender}: matched an avoided topic — skipping.{R}")
            log[key] = {"skipped": True}
            json.dump(log, open(log_path, "w"), indent=2)
            continue

        try:
            reply = reply_fn(f"IG DM from {sender}", last_text, recent)
        except Exception as e:
            print(f" {RED}{sender}: reply generation failed: {e}{R}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print(f" {YLW}Multiple reply-generation failures — backing off {backoff_seconds}s.{R}")
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 600)
            continue

        # The persona is instructed to reply with exactly "SKIP" when a
        # reply genuinely isn't warranted (emoji/sticker-only message,
        # thread already wrapped up, anything redundant). Honor that
        # instead of forcing a reply into every single DM. Ported from
        # wa_manager (2026-09-03).
        if not reply or reply.strip().upper() == "SKIP":
            print(f" {DIM}{sender}: model chose to skip — no reply sent.{R}")
            log[key] = {"status": "skipped_by_model"}
            json.dump(log, open(log_path, "w"), indent=2)
            continue

        # IG has used a few different markups for the reply box over time —
        # try each, most specific first, instead of betting on a single
        # exact placeholder string that a locale/UI change can break.
        box = None
        for by, xpath in [
            (By.XPATH, "//textarea[@placeholder='Message...']"),
            (By.XPATH, "//textarea[contains(@placeholder,'Message')]"),
            (By.XPATH, "//div[@contenteditable='true'][contains(@aria-label,'Message')]"),
            (By.XPATH, "//div[@role='textbox'][@contenteditable='true']"),
        ]:
            try:
                box = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, xpath)))
                break
            except TimeoutException:
                continue

        if box is None:
            print(f" {RED}{sender}: couldn't find the reply box (tried 4 selectors).{R}")
            was_debug = DEBUG
            globals()["DEBUG"] = True
            _debug_dump(driver, "dm_box_missing")
            globals()["DEBUG"] = was_debug
            log[key] = {"status": "failed"}
            json.dump(log, open(log_path, "w"), indent=2)
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print(f" {YLW}Multiple send failures — backing off {backoff_seconds}s.{R}")
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 600)
            continue

        try:
            # ChromeDriver's send_keys() only supports characters in the
            # Basic Multilingual Plane — most colorful emoji (😀 😂 👍 etc.)
            # live outside it and make send_keys throw instead of typing,
            # which silently kills the whole reply. Strip those before
            # typing rather than losing the reply entirely.
            safe_reply = "".join(ch for ch in reply if ord(ch) <= 0xFFFF)
            if safe_reply != reply:
                print(f" {DIM}Stripped non-BMP characters (likely emoji) that "
                      f"ChromeDriver can't type.{R}")
            if not safe_reply.strip():
                print(f" {YLW}{sender}: reply was emoji-only after stripping — skipping send.{R}")
                log[key] = {"status": "skipped_emoji_only"}
                json.dump(log, open(log_path, "w"), indent=2)
                continue

            box.click()
            box.send_keys(safe_reply)
            box.send_keys(Keys.RETURN)
            print(f" {GRN}✔ Replied to {sender}: {safe_reply[:50]}{R}")
            log[key] = {"sender": sender, "message": last_text, "reply": safe_reply,
                        "sent_at": datetime.now().isoformat(), "status": "sent"}
            replied += 1
            consecutive_failures = 0
            backoff_seconds = 30
            time.sleep(random.uniform(6, 12))
        except Exception as e:
            print(f" {RED}{sender}: error sending reply: {e}{R}")
            log[key] = {"status": "failed"}
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print(f" {YLW}Multiple send failures — backing off {backoff_seconds}s.{R}")
                time.sleep(backoff_seconds)
                backoff_seconds = min(backoff_seconds * 2, 600)

        json.dump(log, open(log_path, "w"), indent=2)

    print(f" {DIM}DM scan complete. Replied: {replied}, scanned: {len(seen_hrefs)}.{R}")
    return replied


def dm_reply_loop(driver, reply_fn, avoid_fn, interval_seconds=60, allowed_senders=None,
                   log_path="dm_log.json", max_threads=15, pause_event=None, stop_event=None):
    """
    Repeatedly calls dm_check_and_reply every `interval_seconds`, until
    stop_event is set. Meant to be run on a background thread while the
    main thread (in ig_manager.py) listens for pause/resume/stop commands.

    pause_event: threading.Event — while set(), the loop skips scanning
                 and just sleeps in short ticks, so a pause takes effect
                 almost immediately instead of waiting out the full
                 interval. Safe to leave None to run un-pausable.
    stop_event:  threading.Event — once set(), the loop exits after the
                 current scan (or current pause) finishes.
    """
    import threading
    if pause_event is None:
        pause_event = threading.Event()
    if stop_event is None:
        stop_event = threading.Event()

    round_n = 0
    while not stop_event.is_set():
        if pause_event.is_set():
            print(f" {YLW}[paused] DM loop idle — waiting to resume...{R}")
            while pause_event.is_set() and not stop_event.is_set():
                time.sleep(1)
            continue

        round_n += 1
        who = f"anyone in {sorted(allowed_senders)}" if allowed_senders else "anyone"
        print(f" {CYN}── DM loop round {round_n} (replying to: {who}) ──{R}")
        try:
            n = dm_check_and_reply(driver, reply_fn, avoid_fn, log_path=log_path,
                                    max_threads=max_threads, allowed_senders=allowed_senders)
            print(f" {DIM}Round {round_n}: replied to {n} thread(s). "
                  f"Next check in {interval_seconds}s.{R}")
        except Exception as e:
            print(f" {RED}DM loop round {round_n} errored: {e} — continuing after backoff.{R}")

        # Sleep in 1s ticks (rather than one long time.sleep) so pause/stop
        # commands from the control thread take effect right away instead
        # of waiting out the full interval.
        slept = 0
        while slept < interval_seconds:
            if stop_event.is_set() or pause_event.is_set():
                break
            time.sleep(1)
            slept += 1

    print(f" {DIM}DM loop stopped after {round_n} round(s).{R}")
