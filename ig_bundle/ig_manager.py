#!/usr/bin/env python3
"""
ig_manager.py — Standalone Instagram management console (Selenium / desktop)

Runs on its own — `python3 ig_manager.py` — separate from the Cortana chat
loop, so you can drive Instagram directly without going through Groq at all.
It also still works as a module Cortana can import, same as ig_selenium.py.

╔══════════════════════════════════════════════════════════╗
║  LOGIN — pick whichever fits how you actually log in       ║
╠══════════════════════════════════════════════════════════╣
║  1. Reuse your real Chrome profile  (BEST — no login step) ║
║     Selenium launches Chrome pointed at your actual        ║
║     ~/.config/google-chrome profile. If you're already     ║
║     logged into Instagram there — via password, passkey,   ║
║     a security key, or a synced Google passkey — that      ║
║     session is just... already open. Nothing to automate.  ║
║  2. Cookie import                                           ║
║     Export cookies from a browser extension (Cookie-Editor, ║
║     EditThisCookie — JSON format) after logging in however  ║
║     you like, point this at the file, done.                 ║
║  3. Interactive login                                       ║
║     Opens a blank Chrome window at the IG login page and    ║
║     waits — type your password, tap your security key,      ║
║     approve a passkey prompt, whatever Instagram offers      ║
║     you. Script just polls until it detects you're in.       ║
║  4. Saved session (from a previous run of this script)      ║
╠══════════════════════════════════════════════════════════╣
║  MANAGEMENT — beyond unfollow/DM/comments (still in         ║
║  ig_selenium.py and reused here):                            ║
║    - Direct follower/following scrape (no manual IG data    ║
║      export needed — this reads the live lists off the      ║
║      profile page itself)                                    ║
║    - Growth snapshot log (CSV, one row per day)              ║
║    - Profile audit (bio, counts, verified, link)             ║
║    - Bulk like posts from a hashtag or a profile's grid      ║
║    - Save / unsave a post                                    ║
║    - Hashtag research (top + recent post counts & captions)  ║
║    - Notifications digest                                    ║
║    - Multi-account switcher (config-driven)                  ║
╚══════════════════════════════════════════════════════════╝

pip install selenium --break-system-packages
"""

import os
import readline  # noqa: F401 — no direct use, but importing it makes input()
                  # understand arrow keys / line editing. Without this,
                  # pressing an arrow key at any input() prompt sends the
                  # raw escape bytes (^[[A etc.) straight into the string.
import csv
import json
import re
import time
import random
import threading
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException, StaleElementReferenceException,
)

# Reuse the driver-agnostic action functions from the first module instead
# of duplicating unfollow / seed-follow / DM / comment / story logic.
import ig_selenium

HOME = os.path.expanduser("~")
ACCOUNTS_FILE = os.path.join(HOME, "ig_accounts.json")   # multi-account config
GROWTH_LOG = os.path.join(HOME, "ig_growth_log.csv")
DEBUG_DIR = os.path.join(HOME, "cortana_debug")
DEBUG = os.environ.get("SELENIUM_DEBUG", "0") == "1"

IG_BASE = "https://www.instagram.com"

R="\033[0m"; B="\033[1m"; DIM="\033[2m"
CYN="\033[96m"; YLW="\033[93m"; GRN="\033[92m"; RED="\033[91m"; WHT="\033[97m"; BLU="\033[94m"



# ══════════════════════════════════════════════════════════
# ACCOUNT CONFIG (multi-account switcher)
# ══════════════════════════════════════════════════════════
def load_accounts():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            return json.load(open(ACCOUNTS_FILE))
        except Exception:
            pass
    return {}

def save_accounts(data):
    json.dump(data, open(ACCOUNTS_FILE, "w"), indent=2)
    os.chmod(ACCOUNTS_FILE, 0o600)

def register_account(name, cookie_file=None, chrome_profile_dir=None, chrome_profile_name=None):
    accounts = load_accounts()
    accounts[name] = {
        "cookie_file": cookie_file,
        "chrome_profile_dir": chrome_profile_dir,
        "chrome_profile_name": chrome_profile_name,
        "registered_at": datetime.now().isoformat(),
    }
    save_accounts(accounts)
    return accounts[name]


# ══════════════════════════════════════════════════════════
# LOGIN METHOD 1 — reuse your real Chrome profile
# ══════════════════════════════════════════════════════════
def login_with_chrome_profile(profile_dir=None, profile_name="Default", headless=False):
    """
    profile_dir: e.g. os.path.expanduser('~/.config/google-chrome')
                 (the *parent* dir, not the 'Default'/'Profile 1' folder itself)
    profile_name: which profile inside that dir — 'Default', 'Profile 1', etc.

    This makes Chrome BE your everyday browser. Whatever got you logged into
    Instagram there — password, passkey, security key, synced session —
    is already sitting in that profile's cookie jar. No login flow to
    automate at all.

    Caveat: you can't have your real Chrome open on the same profile at the
    same time (Chrome locks the profile dir). Close it first.
    """
    if profile_dir is None:
        # sane default locations depending on which browser is actually installed
        candidates = [
            os.path.expanduser("~/.config/google-chrome"),
            os.path.expanduser("~/.config/BraveSoftware/Brave-Browser"),
            os.path.expanduser("~/.config/chromium"),
        ]
        profile_dir = next((c for c in candidates if os.path.exists(c)), candidates[0])

    opts = Options()
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument(f"--profile-directory={profile_name}")
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--disable-notifications")
    binary = ig_selenium._binary_location()
    if binary:
        opts.binary_location = binary
    try:
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        except ImportError:
            driver = webdriver.Chrome(options=opts)
    except Exception as e:
        print(f" {RED}Could not launch with that profile: {e}{R}")
        print(f" {YLW}Most common cause: your real Chrome is still open on this profile.")
        print(f" Close Chrome completely (check for background processes too) and retry.{R}")
        return None

    driver.get(f"{IG_BASE}/")
    time.sleep(3)
    if ig_selenium.is_logged_in(driver):
        print(f" {GRN}✓ Already logged in via your Chrome profile — nothing to do.{R}")
        return driver
    print(f" {YLW}Chrome opened but Instagram isn't logged in on this profile.{R}")
    print(f" Log in normally in the window that just opened (password, passkey, whatever).")
    input(" Press Enter once you're logged in... ")
    if ig_selenium.is_logged_in(driver):
        print(f" {GRN}✓ Logged in.{R}")
        return driver
    print(f" {RED}Still not detecting a logged-in session.{R}")
    return driver  # hand it back anyway, might just be a selector miss


# ══════════════════════════════════════════════════════════
# LOGIN METHOD 2 — cookie import (from Cookie-Editor / EditThisCookie export)
# ══════════════════════════════════════════════════════════
def login_with_cookie_file(cookie_json_path, headless=False):
    """
    Export format expected: the standard array-of-objects JSON that
    Cookie-Editor / EditThisCookie produce, e.g.:
      [{"name":"sessionid","value":"...","domain":".instagram.com", ...}, ...]
    Get this by logging into instagram.com in your normal browser (any way
    you like), opening the extension, and exporting cookies for the site.
    """
    if not os.path.exists(cookie_json_path):
        print(f" {RED}Cookie file not found: {cookie_json_path}{R}")
        return None

    driver = ig_selenium.make_driver(headless=headless)
    driver.get(IG_BASE)
    time.sleep(2)

    cookies = json.load(open(cookie_json_path))
    added = 0
    for c in cookies:
        cookie = {
            "name": c.get("name"),
            "value": c.get("value"),
            "domain": c.get("domain", ".instagram.com"),
            "path": c.get("path", "/"),
        }
        if not cookie["name"] or cookie["value"] is None:
            continue
        try:
            driver.add_cookie(cookie)
            added += 1
        except Exception:
            pass

    driver.get(f"{IG_BASE}/")
    time.sleep(2)
    if ig_selenium.is_logged_in(driver):
        print(f" {GRN}✓ Logged in from {added} imported cookies.{R}")
        ig_selenium.save_cookies(driver)  # normalize into our own cookie store too
        return driver
    print(f" {YLW}Cookies imported ({added}) but login not detected — they may be stale.{R}")
    return driver


# ══════════════════════════════════════════════════════════
# LOGIN METHOD 3 — fully interactive (covers passkeys / security keys)
# ══════════════════════════════════════════════════════════
def login_interactive(headless=False):
    """
    Opens the login page and just waits. However Instagram lets you get in —
    password, passkey prompt, security key tap, 'Login with Google' if you
    have that linked — do it in the window. We only poll for success.
    """
    driver = ig_selenium.make_driver(headless=headless)
    driver.get(f"{IG_BASE}/accounts/login/")
    print(f" {CYN}Log in however you normally would in the window that just opened.{R}")
    print(f" {DIM}(password, passkey, security key, linked Google login — all fine){R}")
    input(" Press Enter once you're logged in... ")
    ig_selenium._dismiss_popups(driver)
    if ig_selenium.is_logged_in(driver):
        ig_selenium.save_cookies(driver)
        print(f" {GRN}✓ Logged in and session saved.{R}")
        return driver
    print(f" {RED}Not detecting a logged-in session yet.{R}")
    retry = input(" Try again? (y/n): ").strip().lower()
    if retry == "y":
        input(" Press Enter once you're really logged in... ")
        if ig_selenium.is_logged_in(driver):
            ig_selenium.save_cookies(driver)
            return driver
    return driver


# ══════════════════════════════════════════════════════════
# LOGIN METHOD 4 — saved session (delegate to ig_selenium's cookie store)
# ══════════════════════════════════════════════════════════
def login_saved_session(headless=False):
    driver = ig_selenium.make_driver(headless=headless)
    if ig_selenium.load_cookies(driver):
        print(f" {GRN}✓ Restored saved session.{R}")
        return driver
    print(f" {YLW}No valid saved session found.{R}")
    return None


# ══════════════════════════════════════════════════════════
# MANAGEMENT — direct follower/following scrape (no manual export needed)
# ══════════════════════════════════════════════════════════
def _find_scrollable(driver, dialog_xpath="//div[@role='dialog']"):
    """Find the real scrollable list container inside the dialog by asking
    the DOM directly (scrollHeight > clientHeight) instead of guessing at an
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


def _poll_and_collect(driver, dialog_xpath, seen, max_wait, poll=0.25):
    """Poll every `poll` seconds for up to `max_wait`. Parses every
    rendered row into `seen` (mutated in place) on each poll and returns
    as soon as `seen` actually grows — so the same DOM query does both
    jobs (checking AND parsing) instead of the caller re-querying and
    re-parsing everything again from scratch on its next loop pass.
    Returns (grew: bool, rows: list)."""
    waited = 0.0
    rows = []
    while waited < max_wait:
        time.sleep(poll)
        waited += poll
        before = len(seen)
        try:
            rows = driver.find_elements(By.XPATH, f"{dialog_xpath}//a[contains(@href,'/')]")
        except StaleElementReferenceException:
            rows = []
        for r in rows:
            try:
                href = r.get_attribute("href") or ""
                uname = href.rstrip("/").split("/")[-1]
                if uname and "/" not in uname:
                    seen.add(uname)
            except StaleElementReferenceException:
                continue
        if len(seen) > before:
            return True, rows
    return False, rows


def _prime_full_scroll(driver, dialog_xpath="//div[@role='dialog']",
                        max_scrolls=400, stagnant_limit=6, pause=0.4):
    """Fast blind first pass: jumps straight to scrollHeight repeatedly,
    NOT parsing anything, until the container's scrollHeight stops
    growing. Theory: if Instagram's connections list is backed by a
    client-side data cache, this forces every batch to be fetched over
    the network once, so the real collection pass afterward isn't
    waiting on network latency, only on Instagram's own re-render."""
    scroll_box = _find_scrollable(driver, dialog_xpath)
    if scroll_box is None:
        return
    last_height = -1
    stagnant = 0
    scrolls = 0
    while stagnant < stagnant_limit and scrolls < max_scrolls:
        try:
            height = driver.execute_script("return arguments[0].scrollHeight;", scroll_box)
            driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_box
            )
        except StaleElementReferenceException:
            scroll_box = _find_scrollable(driver, dialog_xpath)
            if scroll_box is None:
                return
            continue
        time.sleep(pause)
        scrolls += 1
        if height == last_height:
            stagnant += 1
        else:
            stagnant = 0
            last_height = height
    try:
        driver.execute_script("arguments[0].scrollTop = 0;", scroll_box)
    except StaleElementReferenceException:
        pass
    time.sleep(0.5)


def _scroll_and_collect(driver, dialog_xpath="//div[@role='dialog']", max_scrolls=250,
                         stagnant_limit=14, prime_first=True, label="", max_duration=480):
    """
    Full reconstruction, 2026-08-19 — see STATUS.md/CHANGELOG.md for the
    round-by-round history. Summary of everything folded in here:
      - stagnant_limit raised 6->14, pause ceiling grows 1.2s->~4s while
        stagnant (undercount fix — 884 vs 917 real).
      - Polling instead of a flat sleep (_poll_and_collect), parsing and
        checking in the same DOM query instead of two passes per scroll.
      - Optional priming pass (_prime_full_scroll, on by default): a fast
        blind scroll to the bottom before the real collection pass, on the
        theory Instagram's connections list is backed by a client-side
        cache and priming pays the network cost up front.
      - `label` (e.g. "following"/"followers"), prefixed onto every
        progress line — needed once two scrapes run in parallel (1T) and
        interleave in one terminal.
      - Aggressive post-priming poll tightening was tried and REVERTED —
        caused a confirmed 20+ minute hang (likely throttling response to
        rapid-fire polling: a slow trickle of new rows was enough to keep
        resetting the stagnation counter without ever tripping it).
      - `max_duration` (default 480s/8min): a hard wall-clock cap,
        independent of the stagnation-count logic, so a slow-trickle
        scenario can never hang indefinitely again regardless of cause.
      - Progress heartbeat is time-based (~every 6s) instead of count-
        boundary-based — the old `len(seen) % 100 < 20` gate could go
        silent for very long stretches depending on what range a list's
        true final count happened to land in, which looked identical to
        a hang even when the scrape was working fine.
    """
    import time as _time
    _start = _time.monotonic()

    if prime_first:
        print(f" {DIM}[{label or '?'}] ...priming (fast blind scroll to load everything first){R}")
        _prime_full_scroll(driver, dialog_xpath)

    seen = set()
    stagnant = 0
    scrolls = 0
    scroll_box = _find_scrollable(driver, dialog_xpath)

    try:
        rows = driver.find_elements(By.XPATH, f"{dialog_xpath}//a[contains(@href,'/')]")
    except StaleElementReferenceException:
        rows = []
    for r in rows:
        try:
            href = r.get_attribute("href") or ""
            uname = href.rstrip("/").split("/")[-1]
            if uname and "/" not in uname:
                seen.add(uname)
        except StaleElementReferenceException:
            continue
    if seen:
        print(f" {DIM}[{label or '?'}] ...{len(seen)} so far{R}")
    _last_print = _time.monotonic()

    while (stagnant < stagnant_limit and len(seen) < 20000 and scrolls < max_scrolls
           and _time.monotonic() - _start < max_duration):
        if scroll_box is None:
            scroll_box = _find_scrollable(driver, dialog_xpath)

        try:
            if scroll_box is not None:
                driver.execute_script(
                    "arguments[0].scrollTop += Math.max(arguments[0].clientHeight * 0.85, 400);",
                    scroll_box,
                )
            elif rows:
                driver.execute_script("arguments[0].scrollIntoView({block:'end'});", rows[-1])
            else:
                break
        except StaleElementReferenceException:
            scroll_box = None

        scrolls += 1
        # Reverted from a tightened (0.12s/~1.7s) post-priming timing —
        # see docstring above. Original, safer numbers, always.
        max_wait = 1.2 + min(stagnant * 0.4, 2.8)
        grew, rows = _poll_and_collect(driver, dialog_xpath, seen, max_wait)
        if grew:
            stagnant = 0
        else:
            stagnant += 1
        now = _time.monotonic()
        if now - _last_print >= 6.0:
            print(f" {DIM}[{label or '?'}] ...{len(seen)} so far{R}")
            _last_print = now

    elapsed = _time.monotonic() - _start
    if elapsed >= max_duration:
        print(f" {YLW}[{label or '?'}] (stopped — hit the {max_duration}s absolute time "
              f"limit with {len(seen)} accounts found. This means it was still finding "
              f"SOME new rows right up to the cutoff without ever going fully stagnant — "
              f"possibly a slow trickle rather than a real end-of-list. Worth a retry, "
              f"and worth mentioning if it happens repeatedly.){R}")
    elif stagnant >= stagnant_limit and scrolls < max_scrolls:
        print(f" {DIM}[{label or '?'}] (stopped after {stagnant_limit} stagnant scrolls — "
              f"{len(seen)} accounts found. If this looks short, Instagram's "
              f"own header count is an approximation too; some gap can be "
              f"normal.){R}")
    return seen

def _diag_on_dialog_fail(driver, username, what):
    """Always-on (no SELENIUM_DEBUG needed) breadcrumb so a failed run
    still tells you *why* instead of just '0 accounts found'."""
    try:
        url = driver.current_url
    except Exception:
        url = "?"
    try:
        title = driver.title
    except Exception:
        title = "?"
    try:
        body_snip = driver.find_element(By.TAG_NAME, "body").text.strip().replace("\n", " ")[:180]
    except Exception:
        body_snip = "?"

    print(f" {RED}Could not open {what} list for @{username}.{R}")
    print(f" {DIM}landed on: {url}{R}")
    print(f" {DIM}page title: {title}{R}")
    print(f" {DIM}visible text: {body_snip}{R}")

    if "/login" in url or "challenge" in url:
        print(f" {YLW}→ Session got bounced to a login/challenge page. Cookies are"
              f" stale or the account got a checkpoint — log in fresh (option 3){R}")
    elif f"/{username}/{what}/" not in url:
        print(f" {YLW}→ Direct nav to the {what} URL didn't stick — IG served the"
              f" plain profile page instead of the dialog. This usually means"
              f" the modal only opens via client-side routing, not a cold page load.{R}")
    else:
        print(f" {YLW}→ URL looks right but no dialog rendered — IG likely changed"
              f" the markup. Run with SELENIUM_DEBUG=1 for a screenshot to re-check selectors.{R}")

    # Always dump HTML/screenshot on failure, not just when SELENIUM_DEBUG=1 —
    # a failed run is exactly when you want the evidence.
    was_debug = ig_selenium.DEBUG
    ig_selenium.DEBUG = True
    ig_selenium._debug_dump(driver, f"{what}_dialog_missing")
    ig_selenium.DEBUG = was_debug
    print(f" {DIM}(saved screenshot + html to ~/cortana_debug/ regardless of SELENIUM_DEBUG){R}")


def _find_stat_link(driver, username, what):
    """IG's own-profile stat links aren't reliably plain <a href> anymore —
    try several selector strategies, most-specific first, and return the
    first clickable element found (or None)."""
    candidates = [
        # classic anchor with matching href
        (By.XPATH, f"//a[contains(@href,'/{username}/{what}/')]"),
        # any element (div/span/a) explicitly role='link' with matching href
        (By.XPATH, f"//*[@role='link'][contains(@href,'/{username}/{what}/')]"),
        # anchor whose href just ends in /following/ or /followers/ (relative nav quirks)
        (By.XPATH, f"//a[contains(@href,'/{what}/')]"),
        # last resort: the header stat <li>/<span> containing the word itself,
        # walk up to nearest ancestor that's actually clickable
        (By.XPATH, f"//header//*[contains(text(),'{what}')]/ancestor-or-self::*[@role='link' or self::a][1]"),
    ]
    for by, xpath in candidates:
        try:
            el = WebDriverWait(driver, 4).until(EC.presence_of_element_located((by, xpath)))
            return el, xpath
        except TimeoutException:
            continue
    return None, None


def _open_list_via_profile_click(driver, username, what):
    """Fallback: load the profile page like a human, then click the
    'X following' / 'X followers' stat link so IG's SPA router opens the
    dialog the way it expects, instead of cold-loading /username/following/.
    Returns (success, reason) so the caller can tell you exactly which
    step failed instead of a single generic timeout."""
    driver.get(f"{IG_BASE}/{username}/")
    ig_selenium._dismiss_popups(driver)
    time.sleep(1.5)  # let the header fully render before hunting for stats

    link, matched_xpath = _find_stat_link(driver, username, what)
    if link is None:
        return False, f"no clickable '{what}' stat link found on the profile page (all selectors missed)"

    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", link)
        time.sleep(0.3)
        # JS click sidesteps 'element click intercepted' from tooltips/overlays
        # (e.g. the 'Add a note' bubble near the avatar) that a native click hits.
        driver.execute_script("arguments[0].click();", link)
    except Exception as e:
        return False, f"found the '{what}' link ({matched_xpath}) but click failed: {e}"

    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
        return True, None
    except TimeoutException:
        return False, f"clicked the '{what}' link ({matched_xpath}) but no dialog appeared — IG may be showing an inline panel instead of a modal now"


def scrape_following(driver, username):
    if not username:
        print(f" {RED}No username given.{R}")
        return set()
    driver.get(f"{IG_BASE}/{username}/following/")
    ig_selenium._dismiss_popups(driver)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
    except TimeoutException:
        print(f" {DIM}[following] Direct nav didn't open the dialog — retrying via profile click...{R}")
        ok, reason = _open_list_via_profile_click(driver, username, "following")
        if not ok:
            print(f" {YLW}[following] Fallback also failed: {reason}{R}")
            _diag_on_dialog_fail(driver, username, "following")
            return set()
    time.sleep(2)
    return _scroll_and_collect(driver, label="following")

def scrape_followers(driver, username):
    if not username:
        print(f" {RED}No username given.{R}")
        return set()
    driver.get(f"{IG_BASE}/{username}/followers/")
    ig_selenium._dismiss_popups(driver)
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']"))
        )
    except TimeoutException:
        print(f" {DIM}[followers] Direct nav didn't open the dialog — retrying via profile click...{R}")
        ok, reason = _open_list_via_profile_click(driver, username, "followers")
        if not ok:
            print(f" {YLW}[followers] Fallback also failed: {reason}{R}")
            _diag_on_dialog_fail(driver, username, "followers")
            return set()
    time.sleep(2)
    return _scroll_and_collect(driver, label="followers")


def _build_and_save_analysis(following, followers, results_path="instagram_results.json"):
    """Shared by analyze_live and analyze_live_parallel."""
    res = {
        "not_following_back": sorted(following - followers),
        "you_dont_follow":    sorted(followers - following),
        "mutual":             sorted(following & followers),
        "following_count":    len(following),
        "followers_count":    len(followers),
        "generated_at":       datetime.now().isoformat(),
    }
    json.dump(res, open(results_path, "w"), indent=2)
    return res


def analyze_live_parallel(username, results_path="instagram_results.json", headless=False):
    """Same result as analyze_live, but scrapes following and followers at
    the same time on two independent Chrome windows (each restoring the
    saved session via cookies), instead of one after the other — Selenium
    only has one command channel per driver, so two threads sharing one
    driver would interleave and corrupt each other's dialog state. Skips
    the API fast-path entirely and goes straight to DOM scroll on both
    windows, since that path is a confirmed dead end for this account."""
    results = {}
    errors = {}

    def _run(kind, scrape_fn):
        d = None
        try:
            d = ig_selenium.make_driver(headless=headless)
            if not ig_selenium.load_cookies(d):
                errors[kind] = "could not restore saved session in second window"
                return
            results[kind] = scrape_fn(d, username)
        except Exception as e:
            errors[kind] = str(e)
        finally:
            if d is not None:
                try:
                    d.quit()
                except Exception:
                    pass

    print(f" {CYN}Scraping following and followers for @{username} in parallel "
          f"(two windows)...{R}")
    t_following = threading.Thread(target=_run, args=("following", scrape_following))
    t_followers = threading.Thread(target=_run, args=("followers", scrape_followers))
    t_following.start()
    t_followers.start()
    t_following.join()
    t_followers.join()

    if "following" in errors:
        print(f" {RED}Following scrape failed: {errors['following']}{R}")
    if "followers" in errors:
        print(f" {RED}Followers scrape failed: {errors['followers']}{R}")

    following = results.get("following", set())
    followers = results.get("followers", set())
    print(f" {DIM}{len(following)} following, {len(followers)} followers found.{R}")
    return _build_and_save_analysis(following, followers, results_path)


def analyze_live(driver, username, results_path="instagram_results.json"):
    """Same output shape as the old ig_parse_export(), but scraped live —
    no manual 'Download your data' export from Instagram needed anymore.

    Tries the private API first — same working pattern as unfollow_batch
    (paginated, ~200/page, no scrolling needed) — falling back to the
    DOM-scroll scrape per-list if the API session can't be built, or if
    it doesn't actually belong to @username (the friendship-list-by-id
    endpoints always return whoever owns the session's cookies, so this
    is only safe to use when analyzing your own account)."""
    session, user_id = ig_selenium._api_session_from_driver(driver)
    use_api = False
    if session is not None:
        owner = ig_selenium.verify_api_session_owner(session)
        if owner == username.lower():
            use_api = True
        else:
            print(f" {DIM}(logged-in account doesn't match @{username} — using browser scroll instead){R}")

    if use_api:
        print(f" {CYN}Fetching following for @{username} via API (fast path)...{R}")
        following = ig_selenium.fetch_full_friendship_list(session, user_id, "following")
        if following is None:
            print(f" {YLW}API fetch failed for following — falling back to browser scroll.{R}")
            following = scrape_following(driver, username)
        print(f" {DIM}{len(following)} accounts found.{R}")

        print(f" {CYN}Fetching followers for @{username} via API (fast path)...{R}")
        followers = ig_selenium.fetch_full_friendship_list(session, user_id, "followers")
        if followers is None:
            print(f" {YLW}API fetch failed for followers — falling back to browser scroll.{R}")
            followers = scrape_followers(driver, username)
        print(f" {DIM}{len(followers)} accounts found.{R}")
    else:
        print(f" {CYN}Scraping following for @{username}...{R}")
        following = scrape_following(driver, username)
        print(f" {DIM}{len(following)} accounts found.{R}")
        print(f" {CYN}Scraping followers for @{username}...{R}")
        followers = scrape_followers(driver, username)
        print(f" {DIM}{len(followers)} accounts found.{R}")

    return _build_and_save_analysis(following, followers, results_path)


# ══════════════════════════════════════════════════════════
# MANAGEMENT — growth tracking (one CSV row per day)
# ══════════════════════════════════════════════════════════

GEMINI_CONFIG_FILE = os.path.join(HOME, ".ig_manager_gemini.json")

def _load_gemini_config():
    if os.path.exists(GEMINI_CONFIG_FILE):
        try:
            return json.load(open(GEMINI_CONFIG_FILE))
        except Exception:
            return {}
    return {}

def _save_gemini_config(api_key, model, self_profile_path):
    # chmod 600 — same treatment as ig_cookies.json in ig_selenium.py.
    # This is plaintext on disk, not encrypted — fine for a personal
    # machine, not fine to back up unencrypted or commit anywhere.
    # Merge rather than overwrite — this file also holds Groq's saved
    # key/model under different keys, and a full overwrite here would
    # silently wipe those the next time Gemini gets used.
    data = _load_gemini_config()
    data.update({"api_key": api_key, "model": model, "self_profile_path": self_profile_path})
    json.dump(data, open(GEMINI_CONFIG_FILE, "w"))
    os.chmod(GEMINI_CONFIG_FILE, 0o600)


def _update_saved_config():
    """Menu option to re-enter and overwrite saved keys/paths, instead of
    making the person go delete the config file by hand to change one."""
    saved = _load_gemini_config()
    print(f"\n{CYN} Update saved config ({GEMINI_CONFIG_FILE}){R}")
    print(" Leave any field blank to keep its current saved value.")

    def _masked(key):
        v = saved.get(key, "")
        return f"...{v[-4:]}" if len(v) > 4 else "(not set)"

    print(f"\n {DIM}Gemini key: {_masked('api_key')} | model: {saved.get('model', '(not set)')}{R}")
    new_gemini_key = input(" New Gemini API key: ").strip()
    new_gemini_model = input(" New Gemini model: ").strip()
    new_profile_path = input(" New self.json path: ").strip()
    if new_gemini_key:
        saved["api_key"] = new_gemini_key
    if new_gemini_model:
        saved["model"] = new_gemini_model
    if new_profile_path:
        saved["self_profile_path"] = new_profile_path

    print(f"\n {DIM}Groq key: {_masked('groq_api_key')} | model: {saved.get('groq_model', '(not set)')}{R}")
    new_groq_key = input(" New Groq API key: ").strip()
    new_groq_model = input(" New Groq model: ").strip()
    if new_groq_key:
        saved["groq_api_key"] = new_groq_key
    if new_groq_model:
        saved["groq_model"] = new_groq_model

    json.dump(saved, open(GEMINI_CONFIG_FILE, "w"))
    os.chmod(GEMINI_CONFIG_FILE, 0o600)
    print(f" {GRN}Saved.{R}")


# Shared persona for all 3 reply backends (Gemini/Ollama/Groq) — used for
# both DM and comment replies. Ported from wa_manager's prompt, which was
# noticeably better at not reading like a bot: react like a person instead
# of just answering and stopping, don't stack questions, don't chase
# silence, and — the actually load-bearing part — bail out with SKIP when
# a reply genuinely isn't warranted (a sticker/emoji-only comment, a
# thread that's already wrapped up) instead of forcing a reply into
# every single message.
_REPLY_PERSONA_BASE = (
    "You're replying to a real Instagram DM or comment as yourself — not "
    "a customer-support bot answering questions one at a time. Read the "
    "conversation history for real context: what's been talked about, "
    "running jokes, unfinished threads. Don't just answer what was asked "
    "and stop — react like a person would: add a thought of your own, "
    "tease them, bring up something related. But don't interrogate — ask "
    "at most one question per reply, and only when it naturally follows "
    "what they just said, not a new personal question every message. "
    "Plenty of real replies are just a reaction or comment with no "
    "question at all. If they haven't replied in a while, that's normal "
    "— don't chase them or ask why they went quiet. Keep it short and "
    "casual, like a real DM or comment, no emoji — they get stripped "
    "before sending anyway. "
    "If a reply genuinely isn't needed (e.g. it's just an emoji/sticker, "
    "the exchange is already fully wrapped up, or anything you'd say "
    "would be redundant), respond with exactly: SKIP"
)


def _prompt_reply_backend():
    """Pick which LLM writes DM/comment replies. Groq is fast cloud, but if
    you say it's dumb you probably want your own model — route to a local
    Ollama instance instead (same idea as Sylvia's LAN connection)."""
    print(" Reply backend:")
    print("  1. Groq (cloud, needs API key)")
    print("  2. Local Ollama (localhost or LAN)")
    print("  3. Google Gemini (cloud, needs API key)")
    pick = input(" Choice [1]: ").strip() or "1"

    if pick == "3":
        saved = _load_gemini_config()

        # Precedence: env var > saved config file > ask. Env var stays first
        # since it never touches disk at all.
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        key_source = "env var" if api_key else None
        if not api_key:
            api_key = saved.get("api_key", "").strip()
            if api_key:
                key_source = "saved config"
        if api_key:
            # Never re-print the full key on screen once it's saved —
            # that's exactly how it kept ending up in screenshots.
            masked = f"...{api_key[-4:]}" if len(api_key) > 4 else "***"
            print(f" {DIM}Using Gemini key from {key_source} ({masked}).{R}")
        else:
            api_key = input(" Gemini API key (or set GEMINI_API_KEY env var instead): ").strip()

        default_model = saved.get("model") or "gemini-3.6-flash"
        model = input(f" Gemini model [{default_model}]: ").strip() or default_model

        # Optional "who am I" profile — loaded once, reused for every reply.
        # Free-form JSON: name, bio, tone, facts, boilerplate answers, whatever
        # you want the model to know about you. With a 1M-token window this
        # costs basically nothing to include every call.
        default_profile_path = saved.get("self_profile_path", "")
        prompt_suffix = f" [{default_profile_path}]" if default_profile_path else ""
        profile_path = input(f" Path to self.json profile (blank to skip){prompt_suffix}: ").strip()
        profile_path = profile_path or default_profile_path
        self_profile = {}
        if profile_path and os.path.exists(profile_path):
            try:
                self_profile = json.load(open(profile_path))
                print(f" {DIM}Loaded profile with {len(self_profile)} field(s) from {profile_path}{R}")
            except Exception as e:
                print(f" {YLW}Couldn't parse {profile_path}: {e} — continuing without it.{R}")

        # Persist whatever changed so next run doesn't ask again. Only
        # writes when something's actually different, so hitting Enter
        # through all three prompts doesn't rewrite the file every time.
        if (api_key, model, profile_path) != (saved.get("api_key"), saved.get("model"), saved.get("self_profile_path")):
            _save_gemini_config(api_key, model, profile_path)
            print(f" {DIM}Saved to {GEMINI_CONFIG_FILE} (mode 600) for next run.{R}")

        def reply_fn(ctx, msg, hist):
            # Minimal inline REST call — no dependency on the google-genai
            # SDK, same "fully standalone" approach as the Groq branch above.
            import urllib.request, ssl

            sys_parts = [_REPLY_PERSONA_BASE]
            if self_profile:
                sys_parts.append("Background info about the person you're replying as "
                                  "(use it to answer naturally, don't just recite it):")
                sys_parts.append(json.dumps(self_profile, indent=2))
            system_text = "\n\n".join(sys_parts)

            # hist is the last few message bubbles scraped from the thread
            # (both sides, chronological, no sender labels — DM UI doesn't
            # expose who-said-what cleanly, so treat it as rough context,
            # not a clean transcript).
            convo_text = ""
            if hist:
                lines = []
                for h in hist:
                    if isinstance(h, dict):
                        who = "You" if h.get("role") == "assistant" else "Them"
                        lines.append(f"{who}: {h.get('content', '')}")
                    else:
                        lines.append(f"- {h}")
                convo_text = "Recent messages in this thread, oldest first:\n" + "\n".join(lines)

            user_text = f"{ctx}\n\n{convo_text}\n\nMessage to reply to: {msg}".strip()

            url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
                   f"{model}:generateContent?key={api_key}")
            # Gemini 2.5-series models use thinkingBudget; 3.x-series models
            # use thinkingLevel instead — sending the wrong one is an
            # INVALID_ARGUMENT 400. Pick based on the model's major version
            # so this doesn't break again if a different model gets typed in.
            gen_match = re.match(r"gemini-(\d+)", model)
            gen = int(gen_match.group(1)) if gen_match else 3
            thinking_config = {"thinkingBudget": 0} if gen <= 2 else {"thinkingLevel": "low"}

            payload = json.dumps({
                "contents": [{"parts": [{"text": user_text}]}],
                "systemInstruction": {"parts": [{"text": system_text}]},
                "generationConfig": {
                    # gemini-3.6-flash "thinks" before answering by default, and
                    # those reasoning tokens share the same maxOutputTokens
                    # budget as the visible reply. Google's own docs say
                    # Gemini 3 Flash/Flash-Lite don't support fully disabling
                    # thinking, so "low" is the minimum, not off — budget the
                    # token ceiling accordingly.
                    "thinkingConfig": thinking_config,
                    "maxOutputTokens": 500,
                },
            }).encode()
            req = urllib.request.Request(
                url, data=payload, method="POST",
                headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
                    data = json.loads(r.read())
            except urllib.error.HTTPError as e:
                # A bare "HTTP Error 404: Not Found" tells you nothing — Google's
                # response body almost always names the actual problem (e.g. the
                # model string doesn't exist for this API version/key). Surface
                # that instead of letting it get swallowed into a generic message.
                body = e.read().decode(errors="replace")
                print(f" {RED}Gemini API error {e.code} for model '{model}': {body[:400]}{R}")
                raise
            try:
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
            except (KeyError, IndexError):
                # Common cause: the reply got blocked by a safety filter, or
                # the response was truncated — data['candidates'][0].get('finishReason')
                # tells you which.
                print(f" {YLW}Gemini returned no usable text: {data}{R}")
                return "hey!"

        print(f" {DIM}Using Gemini ({model}){R}")
        return reply_fn

    if pick == "2":
        host = input(" Ollama host [http://localhost:11434]: ").strip() or "http://localhost:11434"
        model = input(" Ollama model [llama3.1:8b]: ").strip() or "llama3.1:8b"
        if "coder" in model.lower():
            print(f" {DIM}Heads up: coder models are trained for code, not conversation —"
                  f" they tend to write stiff, technical, or oddly formal replies for casual"
                  f" DMs. A general chat model (llama3.1, qwen2.5:7b-instruct, mistral) fits"
                  f" this use case better. Your call.{R}")

        def reply_fn(ctx, msg, hist):
            import urllib.request
            messages = [{"role": "system", "content": _REPLY_PERSONA_BASE}]
            # NOTE: this branch previously dropped `hist` entirely and sent
            # only the latest message — Gemini/Groq below both used it
            # correctly. Fixed so Ollama replies have the same conversation
            # continuity as the other two backends.
            if hist:
                for h in hist:
                    if isinstance(h, dict) and h.get("content"):
                        role = "assistant" if h.get("role") == "assistant" else "user"
                        messages.append({"role": role, "content": h["content"]})
            messages.append({"role": "user", "content": f"{ctx}\n\nMessage: {msg}"})
            payload = json.dumps({
                "model": model,
                "messages": messages,
                "stream": False,
            }).encode()
            req = urllib.request.Request(
                f"{host.rstrip('/')}/api/chat",
                data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            # local inference is slower than a cloud API — generous timeout
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())["message"]["content"].strip()

        print(f" {DIM}Using local Ollama @ {host} ({model}){R}")
        return reply_fn

    saved = _load_gemini_config()  # reused generically for any backend's key, not Gemini-only despite the name
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    key_source = "env var" if api_key else None
    if not api_key:
        api_key = saved.get("groq_api_key", "").strip()
        if api_key:
            key_source = "saved config"
    if api_key:
        masked = f"...{api_key[-4:]}" if len(api_key) > 4 else "***"
        print(f" {DIM}Using Groq key from {key_source} ({masked}).{R}")
    else:
        api_key = input(" Groq API key (or set GROQ_API_KEY env var instead): ").strip()
        if api_key and api_key != saved.get("groq_api_key"):
            saved["groq_api_key"] = api_key
            json.dump(saved, open(GEMINI_CONFIG_FILE, "w"))
            os.chmod(GEMINI_CONFIG_FILE, 0o600)
            print(f" {DIM}Saved to {GEMINI_CONFIG_FILE} (mode 600) for next run.{R}")

    default_groq_model = saved.get("groq_model") or "openai/gpt-oss-20b"
    groq_model = input(f" Groq model [{default_groq_model}]: ").strip() or default_groq_model
    if groq_model != saved.get("groq_model"):
        saved["groq_model"] = groq_model
        json.dump(saved, open(GEMINI_CONFIG_FILE, "w"))
        os.chmod(GEMINI_CONFIG_FILE, 0o600)

    def reply_fn(ctx, msg, hist):
        # minimal inline Groq call so this module has zero dependency
        # on cortana_mint.py — fully standalone
        import urllib.request, urllib.error, ssl
        messages = [{"role": "system", "content": _REPLY_PERSONA_BASE}]
        if hist:
            for h in hist:
                if isinstance(h, dict) and h.get("content"):
                    role = "assistant" if h.get("role") == "assistant" else "user"
                    messages.append({"role": role, "content": h["content"]})
        messages.append({"role": "user", "content": msg})
        payload = json.dumps({
            "model": groq_model,
            "messages": messages,
            "max_tokens": 200,
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=20, context=ssl.create_default_context()) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except urllib.error.HTTPError as e:
            # A bare "HTTP Error 4xx" hides the actual reason — Groq's body
            # names it directly (deprecated model, bad key, etc.). Deprecated
            # models are common here: check console.groq.com/docs/deprecations
            # if this fires with a "model has been deprecated" message.
            body = e.read().decode(errors="replace")
            print(f" {RED}Groq API error {e.code} for model '{groq_model}': {body[:400]}{R}")
            raise

    return reply_fn


def _menu_login():
    print(f"\n{CYN} How do you want to log in?{R}")
    print("  1. Reuse my real Chrome profile (close Chrome first)")
    print("  2. Import cookies from a JSON export")
    print("  3. Interactive (password / passkey / security key — do it yourself)")
    print("  4. Use previously saved session")
    choice = input(" Choice: ").strip()
    if choice == "1":
        profile_dir = input(" Chrome profile parent dir [default ~/.config/google-chrome]: ").strip()
        profile_name = input(" Profile name [default 'Default']: ").strip() or "Default"
        return login_with_chrome_profile(profile_dir or None, profile_name)
    if choice == "2":
        path = input(" Path to cookie JSON export: ").strip()
        return login_with_cookie_file(path)
    if choice == "3":
        return login_interactive()
    if choice == "4":
        return login_saved_session()
    print(" Not a valid choice.")
    return None


def _run_dm_loop(driver):
    """
    Menu option: DM auto-reply loop. Checks DMs every N seconds (default
    60) in a background thread, while this thread reads commands so you
    can pause/resume/stop without killing the whole app.
    """
    reply_fn = _prompt_reply_backend()

    raw_interval = input(" Check every how many seconds? [60]: ").strip()
    try:
        interval = max(15, int(raw_interval)) if raw_interval else 60
    except ValueError:
        interval = 60

    raw_allow = input(" Only reply to these usernames (comma-separated, blank = everyone): ").strip()
    allowed = [u for u in (a.strip() for a in raw_allow.split(",")) if u] if raw_allow else None

    pause_event = threading.Event()
    stop_event = threading.Event()

    t = threading.Thread(
        target=ig_selenium.dm_reply_loop,
        args=(driver, reply_fn, lambda text: False),
        kwargs=dict(interval_seconds=interval, allowed_senders=allowed,
                    pause_event=pause_event, stop_event=stop_event),
        daemon=True,
    )
    t.start()

    print(f"\n {B}DM loop running{R} (every {interval}s"
          f"{', only replying to ' + ', '.join(allowed) if allowed else ''}).")
    print(" Commands: [p]ause  [r]esume  [q]uit back to menu\n")

    while True:
        cmd = input(" dm-loop> ").strip().lower()
        if cmd in ("p", "pause"):
            pause_event.set()
            print(f" {YLW}Paused.{R}")
        elif cmd in ("r", "resume"):
            pause_event.clear()
            print(f" {GRN}Resumed.{R}")
        elif cmd in ("q", "quit", "stop"):
            stop_event.set()
            print(" Stopping loop (finishing current step)...")
            t.join(timeout=interval + 10)
            break
        else:
            print(" Commands: p (pause), r (resume), q (quit back to menu)")


def main():
    os.system("clear")
    print(f"{CYN}{'═'*54}{R}")
    print(f"{B}{WHT} IG MANAGER — standalone Instagram console{R}")
    print(f"{CYN}{'═'*54}{R}")

    driver = _menu_login()
    if driver is None:
        print(f" {RED}No session — exiting.{R}")
        return

    username = ""
    while not username:
        raw = input(" Your Instagram username (for scrape/audit calls): ")
        username = ig_selenium.clean_username(raw)
        if not username:
            print(" That's blank (or was just control characters) — type your actual username.")
            continue
        ok = input(f" Using @{username} — correct? (y/n): ").strip().lower()
        if ok != "y":
            username = ""

    while True:
        print(f"\n{BLU}{'─'*54}{R}")
        print(" 1. Analyze followers/following (live scrape, no export needed)")
        print(" 1T. Analyze followers/following (parallel — two windows, faster)")
        print(" 2. Unfollow non-followers")
        print(" 4. DM auto-reply (once)")
        print(" 4L. DM auto-reply (loop, pause/resume, choose who)")
        print(" 12. Update saved API keys / config")
        print(" 0. Quit")
        choice = input(" Choice: ").strip()

        if choice == "0":
            break
        elif choice == "1":
            res = analyze_live(driver, username)
            print(f" Following:{res['following_count']} Followers:{res['followers_count']} "
                  f"Not following back:{len(res['not_following_back'])}")
        elif choice.lower() == "1t":
            res = analyze_live_parallel(username)
            print(f" Following:{res['following_count']} Followers:{res['followers_count']} "
                  f"Not following back:{len(res['not_following_back'])}")
        elif choice == "2":
            targets = json.load(open("instagram_results.json")).get("not_following_back", []) \
                if os.path.exists("instagram_results.json") else []
            if not targets:
                print(" Run analyze first (option 1).")
                continue
            n = int(input(f" How many (of {len(targets)})? ").strip() or "10")
            done, skipped, errors = ig_selenium.unfollow_batch(driver, username, targets, n)
            print(f" Done:{done} Skipped:{skipped} Errors:{errors}")
        elif choice == "4":
            reply_fn = _prompt_reply_backend()
            n = ig_selenium.dm_check_and_reply(driver, reply_fn, lambda text: False)
            print(f" Replied to {n} threads.")
        elif choice.lower() == "4l":
            _run_dm_loop(driver)
        elif choice == "12":
            _update_saved_config()
        else:
            print(" Not a valid choice.")

    driver.quit()
    print(" Session closed.")


if __name__ == "__main__":
    main()
