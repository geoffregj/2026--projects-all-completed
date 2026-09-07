# ig-manager

A standalone, menu-driven Instagram console (`ig_manager.py`) for managing a
personal account without Instagram's official app: live follower/following
analysis, unfollowing non-followers, DM and comment auto-reply via an LLM
(Groq, local Ollama, or Gemini), story posting, growth tracking, and more.

`cortana_mint.py` is a separate, older all-in-one personal assistant
(device control, M-PESA SMS parsing, music/PDF tools) that happens to share
the same underlying `ig_selenium.py` browser-automation module. The two
don't call each other — you can use either independently.

**Read this before running anything on your own account:**
automating Instagram (unfollow batches, auto-follow, auto-DM, auto-comment,
bulk-like) violates Instagram's Terms of Service. This is true regardless of
which internal method is used — driving a real browser isn't inherently
"safe," it's just a different kind of automated behavior Instagram can still
detect. Accounts can be rate-limited, checkpointed, or banned. Use on an
account you're willing to lose, not your only one.

## What's here

| File | What it does |
|---|---|
| `ig_manager.py` | Standalone console — run this directly (`python3 ig_manager.py`). Menu-driven: analyze followers, unfollow, seed-follow, DM/comment auto-reply, story posting, growth log, profile audit, bulk like, hashtag research, notifications digest. |
| `ig_selenium.py` | Shared library `ig_manager.py` imports for the actual browser actions (login, cookies, unfollow, DM read/send, comments, stories). Not meant to be run on its own. |
| `cortana_mint.py` | Separate, older all-in-one assistant. Independent of `ig_manager.py` — shares `ig_selenium.py` only. |
| `self.example.json` | Template for a personal-profile file you copy to `self.json`, fill in, and point the Gemini reply backend at — it gets folded into every DM reply as background context. |

## Setup

```bash
git clone <this repo>
cd ig-manager
python3 -m venv .
source bin/activate
pip install -r requirements.txt
python3 ig_manager.py
```

First run: pick a login method (reusing your real Chrome profile, importing
a cookies JSON export, logging in interactively, or reusing a previously
saved session). If you want LLM-generated DM/comment replies, you'll be
prompted for a backend (Groq, local Ollama, or Gemini) and its API key on
first use — Gemini's key gets cached to `~/.ig_manager_gemini.json` (mode
600) afterward so you don't retype it every run.

## Secrets — none of these are in this repo, keep it that way

`self.json`, `ig_cookies.json`, `~/.ig_manager_gemini.json`, and every
`*_log.json` / `instagram_results.json` file are all in `.gitignore`
already. They all contain either your actual Instagram session, your API
keys, or real message content from real people. If any API key or password
ever shows up on-screen (screenshot, terminal paste, anywhere) — treat it
as burned and regenerate it immediately. Caching a key locally only stops
*future* exposure, it doesn't undo one that already happened.

## More detail

- **`CHANGELOG.md`** — the actual debugging history: every bug that was
  hit, why, and what the fix was. Worth reading before touching a function
  that's already listed there, so you don't re-break something that was
  already fixed for a specific reason.
- **`STATUS.md`** — current known-good state and what (if anything) is
  mid-flight. Read this first if you're picking this project back up after
  a break, or handing it to a second AI session to work on in parallel —
  see that file for why it exists.
