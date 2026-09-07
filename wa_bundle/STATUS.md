# Status

**Confirmed working (live, on real WhatsApp Web):**
- Login / persistent session
- Search + open chat by contact name
- Read incoming messages via `tail-in` + `copyable-text` selectors
- Multi-message batching (collects all new messages since last reply, not
  just the latest one)
- Send reply with emoji stripped (BMP-only limitation)
- History-aware replies with `SKIP` support
- Configurable reply delay (prompted at startup, `min-max` seconds)
- Crash protection around the reply-backend call (any of the 3 backends)
- Verified end-to-end on "Karanja felister2", "Cynthia", "Slyvia" —
  multiple successful round-trip replies logged across sessions

**Backends:**
- `local` (Ollama, `qwen2.5:7b` default) — tested live, working
- `groq` (`openai/gpt-oss-120b` default) — code path in place, not yet
  run live this session
- `gemini` (`gemini-3.5-flash-lite` default, `gemini-3.1-pro-preview` for
  heavier reasoning) — added this session based on current docs, NOT yet
  run live. Verify a first reply comes back correctly before leaving it
  unattended — Gemini's request/response shape is different enough from
  the other two backends that a subtle bug is more likely here than in
  the well-tested paths.

**Not yet built** (discussed, prioritized, not implemented):
1. Startup selector self-test — open a chat, confirm search/message-row/
   compose-box selectors all resolve, fail loud at launch instead of
   silent mid-loop. Flagged as highest priority next.
2. Quiet hours — stay silent overnight regardless of activity.
3. Config file for contacts/backend/delay so you don't retype every run.
4. Reply preview/approval mode.
5. `h <name>` console command to peek at a contact's history without
   opening `wa_log.json` directly.

**Known fragile point:** every WhatsApp Web selector in `wa_selenium.py`
was fixed by inspecting the real DOM live, not from documentation — expect
these to break again on WhatsApp's next redesign. See CHANGELOG for the
fastest fix path when that happens (inspect element → paste HTML, don't
re-guess).

**If picking this back up cold:** delete `wa_log.json` if the shape looks
wrong before re-running — it's `{"seen": {...}, "history": {...}}`; an
older flat `{contact: msg}` file won't parse into that cleanly.
