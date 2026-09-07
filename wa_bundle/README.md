# wa-manager

A standalone, reply-only WhatsApp console (`wa_manager.py`) for auto-replying
to specific contacts via an LLM (local Ollama, Groq, or Gemini), with
per-contact rolling conversation history, multi-message batching, and
human-like reply timing.

**Read this before running anything on your own number:**
automating WhatsApp violates its Terms of Service — accounts can be
rate-limited or banned. This is scoped to a small allowlist of named
contacts with human-timed replies specifically to keep it low-signature,
not because it's risk-free. Don't run this on a number you can't afford
to lose.

## What's here

| File | What it does |
|---|---|
| `wa_manager.py` | Standalone console — run directly (`python3 wa_manager.py`). Prompts for contact names and reply backend. |
| `wa_selenium.py` | Shared library `wa_manager.py` imports for browser actions (session, chat search/open, read last incoming message, send). |
| `self.example.json` | Template for a personal-profile file you copy to `self.json` — folded into every AI reply as background context so replies sound like you. |

## Setup

```bash
python3 -m venv .
source bin/activate
pip install -r requirements.txt
python3 wa_manager.py
```

First run: a persistent Chrome profile opens web.whatsapp.com — scan the QR
once, and you stay logged in on future runs (same profile dir). You'll then
be prompted for contact names, a backend (`local`/`groq`/`gemini`), and a
reply delay range in seconds (`min-max`, default `4-55`).

## Backends

| Backend | Default model | Notes |
|---|---|---|
| `local` | `qwen2.5:7b` (Ollama) | Free, private, CPU-only on this machine — slower. |
| `groq` | `openai/gpt-oss-120b` | Needs API key. Fast cloud inference. |
| `gemini` | `gemini-3.5-flash-lite` | Needs API key. Cheap, 1M-token context. Use `gemini-3.1-pro-preview` for heavier reasoning/research-style replies. |

## Storage / state

- `self.json` — your profile, folded into the system prompt. Never in git.
- `wa_log.json` — per contact: last-seen message (dedup) + rolling last-20-turn
  history (model context / tuning data). Never in git.

## Known-good behavior

- Only touches contacts you name explicitly — no full-inbox scanning.
- Collects multiple consecutive incoming messages into one batch before
  replying, instead of only reacting to the newest one.
- Model can return `SKIP` instead of a reply when nothing needs saying.
- Emoji stripped before typing (ChromeDriver can't send non-BMP characters).
- Reply-backend call is wrapped in try/except — an API hiccup skips that
  round instead of crashing the loop.
- Reply delay is configurable at startup (near-instant delays are the
  strongest bot tell — fine for testing, not for anything left running).
- Selectors target stable hooks (`data-testid`, `copyable-text`) rather than
  WhatsApp's hashed atomic-CSS classes, which change across builds — but
  they *will* break again on a future WhatsApp Web redesign. If replies
  silently stop, right-click the relevant element → Inspect → Copy element,
  and update the selector in `wa_selenium.py`.

## More detail

- **`CHANGELOG.md`** — debugging history, what broke and why.
- **`STATUS.md`** — current known-good state.
