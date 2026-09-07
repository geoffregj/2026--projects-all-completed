"""
wa_manager.py — reply-only WhatsApp console for two contacts.
Run: python3 wa_manager.py
"""
import os
import json
import threading
import requests
import wa_selenium as wa

CYN, GRN, YLW, RED, B, R = "\033[36m", "\033[32m", "\033[33m", "\033[31m", "\033[1m", "\033[0m"


def _load_self_profile():
    if os.path.exists("self.json"):
        try:
            return json.load(open("self.json"))
        except Exception:
            return {}
    return {}


# ══════════════════════════════════════════════════════════
# REPLY BACKEND — Groq (cloud) or local Ollama, your call
# ══════════════════════════════════════════════════════════
SYSTEM_PROMPT_BASE = (
    "You are texting as a real person having an actual conversation on "
    "WhatsApp — not a customer-support bot answering questions one at a "
    "time. Read the conversation history for real context: what's been "
    "talked about, running jokes, unfinished threads. "
    "Don't just answer what was asked and stop — react like a person "
    "would: add a thought of your own, tease them, bring up something "
    "related. But don't interrogate — ask at most one question per reply, "
    "and only when it naturally follows what they just said, not a new "
    "personal question every message (no stacking 'do you have a "
    "girlfriend / where do you live' back to back — that reads as pushy, "
    "not friendly). Plenty of real texts are just a reaction or comment "
    "with no question at all. "
    "If they haven't replied in a while, that's normal — don't chase them "
    "or ask why they went quiet. "
    "Keep replies short and casual, like a real text, no emoji. "
    "The message shown to you may actually be several consecutive texts "
    "they sent in a row (one per line) — read them together as one thought "
    "and reply once, not line by line. "
    "If a reply genuinely isn't needed (e.g. it's just an emoji/sticker, "
    "already fully wrapped up, or anything you'd say would be redundant), "
    "respond with exactly: SKIP"
)


def _system_prompt():
    profile = _load_self_profile()
    if not profile:
        return SYSTEM_PROMPT_BASE
    return SYSTEM_PROMPT_BASE + "\n\nBackground on who you're texting as:\n" + json.dumps(profile)


def _build_messages(msg, history):
    messages = [{"role": "system", "content": _system_prompt()}]
    for turn in history:
        role = "assistant" if turn["role"] == "me" else "user"
        messages.append({"role": role, "content": turn["text"]})
    messages.append({"role": "user", "content": msg})
    return messages


def _build_gemini_contents(msg, history):
    contents = []
    for turn in history:
        role = "model" if turn["role"] == "me" else "user"
        contents.append({"role": role, "parts": [{"text": turn["text"]}]})
    contents.append({"role": "user", "parts": [{"text": msg}]})
    return contents


def make_reply_fn(backend, api_key=None, model=None):
    if backend == "groq":
        def reply(contact, msg, history):
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model or "openai/gpt-oss-120b", "messages": _build_messages(msg, history)},
                timeout=30,
            )
            return r.json()["choices"][0]["message"]["content"].strip()
        return reply

    if backend == "gemini":
        gmodel = model or "gemini-3.5-flash-lite"
        def reply(contact, msg, history):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{gmodel}:generateContent"
            r = requests.post(
                url,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json={
                    "system_instruction": {"parts": [{"text": _system_prompt()}]},
                    "contents": _build_gemini_contents(msg, history),
                },
                timeout=30,
            )
            data = r.json()
            if "candidates" not in data:
                raise RuntimeError(f"Gemini error: {data}")
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return reply

    def reply_local(contact, msg, history):
        r = requests.post(
            "http://localhost:11434/api/chat",
            json={"model": model or "qwen2.5:7b", "messages": _build_messages(msg, history), "stream": False},
            timeout=60,
        )
        return r.json()["message"]["content"].strip()
    return reply_local


# ══════════════════════════════════════════════════════════
def run_for_contacts(contacts, backend, api_key=None, model=None, interval=20,
                      min_delay=4, max_delay=55):
    driver = wa.start_driver()
    if not wa.wait_for_login(driver):
        return
    reply_fn = make_reply_fn(backend, api_key, model)
    stop_event = threading.Event()
    pause_event = threading.Event()

    t = threading.Thread(
        target=wa.wa_reply_loop,
        args=(driver, reply_fn, contacts),
        kwargs=dict(interval_seconds=interval, min_reply_delay=min_delay,
                    max_reply_delay=max_delay, stop_event=stop_event, pause_event=pause_event),
        daemon=True,
    )
    t.start()

    print(f"\n {B}WA reply loop running{R} for: {', '.join(contacts)}")
    print(" Commands: [p]ause  [r]esume  [q]uit\n")
    while True:
        cmd = input(" wa> ").strip().lower()
        if cmd in ("p", "pause"):
            pause_event.set()
        elif cmd in ("r", "resume"):
            pause_event.clear()
        elif cmd in ("q", "quit"):
            stop_event.set()
            t.join(timeout=interval + 10)
            driver.quit()
            break


def main():
    print(f"{CYN}{'═'*44}{R}\n{B} WA MANAGER — reply-only{R}\n{CYN}{'═'*44}{R}")
    raw = input(" Contact names (comma-separated, exact WA display names): ").strip()
    contacts = [c.strip() for c in raw.split(",") if c.strip()]
    if not contacts:
        print(" Need at least one contact name."); return

    backend = input(" Backend — groq / gemini / local [local]: ").strip().lower() or "local"
    api_key = None
    model = None
    if backend == "groq":
        api_key = input(" Groq API key: ").strip()
    elif backend == "gemini":
        api_key = input(" Gemini API key: ").strip()
        model = input(" Gemini model [gemini-3.5-flash-lite, or gemini-3.1-pro-preview for research/heavier reasoning]: ").strip() or "gemini-3.5-flash-lite"

    raw_delay = input(" Reply delay in seconds, min-max (e.g. 1-1 or 4-55) [4-55]: ").strip()
    try:
        if raw_delay:
            lo, hi = raw_delay.split("-")
            min_delay, max_delay = float(lo), float(hi)
        else:
            min_delay, max_delay = 4, 55
    except ValueError:
        print(" Couldn't parse that, using default 4-55.")
        min_delay, max_delay = 4, 55

    run_for_contacts(contacts, backend, api_key, model=model, min_delay=min_delay, max_delay=max_delay)


if __name__ == "__main__":
    main()
