"""
wa_selenium.py — WhatsApp Web browser automation (reply-only).
Same shape as ig_selenium.py's dm_reply_loop, ported to web.whatsapp.com.
"""
import os
import json
import time
import random
import threading

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

CYN, GRN, YLW, RED, DIM, B, R = (
    "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"
)

PROFILE_DIR = os.path.expanduser("~/.wa_manager_profile")


# ══════════════════════════════════════════════════════════
# SESSION
# ══════════════════════════════════════════════════════════
def start_driver(profile_dir=None, headless=False):
    """
    Persistent Chrome profile so you scan the QR once. Reuse this same
    profile_dir across runs and you stay logged in.
    """
    profile_dir = profile_dir or PROFILE_DIR
    os.makedirs(profile_dir, exist_ok=True)

    opts = Options()
    opts.add_argument(f"--user-data-dir={profile_dir}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--start-maximized")
    if headless:
        opts.add_argument("--headless=new")

    driver = webdriver.Chrome(options=opts)
    driver.get("https://web.whatsapp.com")
    return driver


def wait_for_login(driver, timeout=120):
    """Blocks until the chat list loads (QR scanned) or times out."""
    try:
        WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, '//div[@id="pane-side"]'))
        )
        print(f" {GRN}Logged in — chat list loaded.{R}")
        return True
    except TimeoutException:
        print(f" {RED}Timed out waiting for QR scan / login.{R}")
        return False


_SEARCH_XPATHS = [
    '//input[@aria-label="Search or start a new chat"]',
    '//input[@role="textbox"][@data-tab="3"]',
    '//div[@contenteditable="true"][@data-tab="3"]',
]


def _find_search_box(driver, timeout):
    for xp in _SEARCH_XPATHS:
        try:
            return WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp))
            )
        except TimeoutException:
            continue
    return None


def open_chat(driver, contact_name, timeout=15):
    """Opens a chat by contact/display name shown in WhatsApp."""
    search = _find_search_box(driver, timeout)
    if search is None:
        print(f" {RED}Couldn't find the search box (WhatsApp Web layout may have changed).{R}")
        return False

    try:
        search.click()
        search.send_keys(Keys.CONTROL + "a")
        search.send_keys(contact_name)
        time.sleep(1.5)

        # Loose match first (contains), exact as fallback — title attrs
        # sometimes carry trailing whitespace/status emoji.
        candidates = driver.find_elements(
            By.XPATH, f'//span[contains(@title, "{contact_name}")]'
        )
        if not candidates:
            print(f" {RED}Couldn't open chat with '{contact_name}' — no match in search results.{R}")
            search.send_keys(Keys.ESCAPE)
            return False

        candidates[0].click()
        time.sleep(1)
        search.send_keys(Keys.ESCAPE)
        return True
    except (TimeoutException, NoSuchElementException) as e:
        print(f" {RED}Couldn't open chat with '{contact_name}': {e}{R}")
        return False


# ══════════════════════════════════════════════════════════
# READ — last incoming message in the currently open chat
# ══════════════════════════════════════════════════════════
def load_existing_history(driver, max_messages=20):
    """
    Reads the last max_messages messages already in the open chat (both
    incoming and outgoing) so the bot starts with real prior context
    instead of a blank slate. Called once per contact, the first time
    its chat is opened in a session with no saved history yet.
    """
    try:
        containers = driver.find_elements(By.XPATH, '//div[@data-testid="msg-container"]')
        turns = []
        for row in containers[-max_messages:]:
            is_in = bool(row.find_elements(By.XPATH, './/span[@data-testid="tail-in"]'))
            is_out = bool(row.find_elements(By.XPATH, './/span[@data-testid="tail-out"]'))
            if not (is_in or is_out):
                continue
            texts = row.find_elements(By.XPATH, './/div[contains(@class,"copyable-text")]')
            if not texts:
                continue
            t = texts[-1].text.strip()
            if not t:
                continue
            turns.append({"role": "them" if is_in else "me", "text": t})
        return turns
    except Exception:
        return []


def get_new_incoming_messages(driver, last_seen=None, max_batch=15):
    """
    Walks incoming messages newest-first, collecting text until it hits
    either an outgoing message (tail-out — you already replied past that
    point) or `last_seen` (the last thing this loop already handled).
    Returns them in chronological order (oldest of the batch first).

    On a cold start (last_seen=None) it only grabs the single newest
    incoming message, same as before — otherwise reconnecting to an old
    chat would treat the whole history as "new".
    """
    try:
        containers = driver.find_elements(By.XPATH, '//div[@data-testid="msg-container"]')
        batch = []
        for row in reversed(containers):
            if row.find_elements(By.XPATH, './/span[@data-testid="tail-out"]'):
                break  # hit your own message — nothing further back is new
            if not row.find_elements(By.XPATH, './/span[@data-testid="tail-in"]'):
                continue
            texts = row.find_elements(By.XPATH, './/div[contains(@class,"copyable-text")]')
            if not texts:
                continue
            t = texts[-1].text.strip()
            if not t:
                continue
            if last_seen is not None and t == last_seen:
                break
            batch.append(t)
            if last_seen is None:
                break  # cold start: just the latest one
            if len(batch) >= max_batch:
                break
        batch.reverse()
        return batch
    except Exception:
        return []


# ══════════════════════════════════════════════════════════
# SEND — human-like typing + send
# ══════════════════════════════════════════════════════════
def send_reply(driver, text, typing_delay_range=(0.03, 0.09)):
    # ChromeDriver's send_keys only supports BMP characters — emoji etc.
    # (U+10000 and above) crash it. Strip them rather than lose the whole send.
    text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)

    box = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located(
            (By.XPATH, '//footer//div[@contenteditable="true"][@data-tab="10"]')
        )
    )
    box.click()
    for ch in text:
        box.send_keys(ch)
        time.sleep(random.uniform(*typing_delay_range))
    box.send_keys(Keys.ENTER)


# ══════════════════════════════════════════════════════════
# REPLY LOOP — mirrors ig_selenium.dm_reply_loop
# ══════════════════════════════════════════════════════════
def wa_reply_loop(driver, reply_fn, allowed_contacts, interval_seconds=20,
                   min_reply_delay=4, max_reply_delay=55, log_path="wa_log.json",
                   pause_event=None, stop_event=None):
    """
    Polls each contact in allowed_contacts every interval_seconds. On a new
    incoming message not seen before, waits a random human-like delay
    (< max_reply_delay seconds) then replies via reply_fn(message_text) -> str.

    allowed_contacts: list of exact WhatsApp display names — ONLY these are
    ever touched. Nothing here scans your whole inbox.
    """
    if pause_event is None:
        pause_event = threading.Event()
    if stop_event is None:
        stop_event = threading.Event()

    seen = {}
    history = {}   # contact -> list of {"role": "them"/"me", "text": ...}
    if os.path.exists(log_path):
        try:
            data = json.load(open(log_path))
            seen = data.get("seen", {})
            history = data.get("history", {})
        except Exception:
            seen, history = {}, {}

    round_n = 0
    for contact in allowed_contacts:
        if not history.get(contact):
            if open_chat(driver, contact):
                seeded = load_existing_history(driver)
                if seeded:
                    history[contact] = seeded[-20:]
                    print(f" {DIM}{contact}: seeded {len(seeded)} messages of prior chat history.{R}")

    while not stop_event.is_set():
        if pause_event.is_set():
            print(f" {YLW}[paused] WA loop idle...{R}")
            while pause_event.is_set() and not stop_event.is_set():
                time.sleep(1)
            continue

        round_n += 1
        replied = 0
        for contact in allowed_contacts:
            if stop_event.is_set():
                break
            try:
                if not open_chat(driver, contact):
                    continue
                batch = get_new_incoming_messages(driver, last_seen=seen.get(contact))
                if not batch:
                    print(f" {DIM}{contact}: nothing new.{R}")
                    continue

                msg = "\n".join(batch)
                delay = random.uniform(min_reply_delay, max_reply_delay)
                tag = f"{len(batch)} new msgs" if len(batch) > 1 else "new msg"
                print(f" {CYN}{tag} from {contact} — replying in {delay:.0f}s{R}")
                time.sleep(delay)

                convo = history.get(contact, [])
                try:
                    reply_text = reply_fn(contact, msg, convo)
                except Exception as e:
                    print(f" {RED}{contact}: reply backend error ({e}) — skipping this round.{R}")
                    continue
                seen[contact] = batch[-1]

                if not reply_text or reply_text.strip().upper() == "SKIP":
                    print(f" {DIM}{contact}: model chose to skip.{R}")
                else:
                    send_reply(driver, reply_text)
                    convo.append({"role": "them", "text": msg})
                    convo.append({"role": "me", "text": reply_text})
                    history[contact] = convo[-20:]  # cap history length
                    replied += 1
            except Exception as e:
                print(f" {RED}Error on {contact}: {e}{R}")

        json.dump({"seen": seen, "history": history}, open(log_path, "w"))
        print(f" {DIM}Round {round_n}: replied to {replied}. Next check in {interval_seconds}s.{R}")

        slept = 0
        while slept < interval_seconds:
            if stop_event.is_set() or pause_event.is_set():
                break
            time.sleep(1)
            slept += 1

    print(f" {DIM}WA loop stopped after {round_n} round(s).{R}")
