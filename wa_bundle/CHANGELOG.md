# Changelog

## Session 1 — initial build + live debugging against real WhatsApp Web

- Built `wa_selenium.py` / `wa_manager.py` from scratch, modeled on
  ig-manager's `dm_reply_loop` (persistent-profile session, allowlist-only
  polling, pause/resume/stop via threading.Event).
- **Search box selector broke twice**: WhatsApp Web's search box is a real
  `<input role="textbox" aria-label="Search or start a new chat">`, not the
  `contenteditable div[data-tab="3"]` guessed initially. Fixed once the
  actual element HTML was inspected.
- **Incoming-message detection broke twice**:
  - First guess (`div.message-in` class) never matched — WhatsApp Web uses
    hashed atomic CSS classes now, not literal ones.
  - Second guess (`data-id` starting with `false_`) also didn't match this
    build's `data-id` format.
  - Fixed using `data-testid="msg-container"` rows + a descendant
    `span[data-testid="tail-in"]` to flag incoming, with text pulled from
    `div.copyable-text` (a literal class WhatsApp keeps stable for its own
    copy-to-clipboard feature).
- **Send crash**: `ChromeDriver only supports characters in the BMP` —
  model-generated emoji broke `send_keys`. Fixed by stripping any character
  with `ord(ch) > 0xFFFF` before typing.
- **No memory / no skip logic**: original `reply_fn(msg) -> str` had no
  history and always replied. Reworked `wa_log.json` to store
  `{"seen": {...}, "history": {...}}`, `reply_fn` signature changed to
  `(contact, msg, history) -> str | None`, last 20 turns per contact fed
  back as context, model can return `SKIP` to withhold a reply.
- Added `self.json` / `self.example.json` support — profile folded into
  system prompt, mirrors ig-manager's pattern.

**Lesson for next session**: none of these selectors were verified against
a live page before shipping — they were best-guesses based on typical
WhatsApp Web structure, and WhatsApp's hashed CSS + shifting attributes
broke most of them on first run. Fastest path to a fix each time was
"right-click the real element → Inspect → Copy element → paste here" —
skip the guessing round next time a selector breaks and go straight to
that.

## Session 2 — multi-message batching, Gemini backend, config, hardening

- **Multi-message batching**: contact was sending several messages back to
  back and the bot only ever saw the newest one. `get_last_incoming_message`
  replaced with `get_new_incoming_messages(driver, last_seen)`, which walks
  backward collecting every incoming message since the last one replied to,
  stopping at your own last outgoing message (tail-out) or a 15-message cap.
  Batch is joined with newlines and handed to the model as one block; system
  prompt updated to say "this may be several consecutive texts, reply once."
  Cold start (no `last_seen` yet) still only grabs the single latest message
  so reconnecting to an old chat doesn't treat the whole history as new.
- **Configurable reply delay**: was hardcoded 4–55s. `wa_manager.py` now
  prompts for `min-max` at startup (e.g. `1-1` for testing, `4-55` default).
  Flagged to Geoffrey: near-instant replies (1s) are the single strongest
  bot tell — fine for a quick test, not for anything left running.
- **Gemini backend added** as a third option alongside groq/local. Verified
  live against current docs before building (2.5 series retiring Oct 16
  2026, so NOT used as default): `x-goog-api-key` header is the current
  auth method (not the old `?key=` query param), endpoint is
  `v1beta/models/{model}:generateContent`. Default model
  `gemini-3.5-flash-lite` (cheap, current, 1M-token context on every tier
  now, not just top models). `gemini-3.1-pro-preview` offered as the
  heavier-reasoning option for research-flavored replies. Gemini's message
  format differs from OpenAI-style (`contents` array with `user`/`model`
  roles instead of `messages` with `user`/`assistant`, separate
  `system_instruction` field) — handled in `_build_gemini_contents`.
- **Crash protection**: `reply_fn` call wrapped in try/except inside the
  loop. An API hiccup (rate limit, timeout, malformed response) on any
  backend now logs and skips that round instead of killing the whole
  reply thread. Message is NOT marked as seen on failure, so it retries
  next round instead of silently being dropped.
- **`self.json` populated from real usage**: extracted texting-style
  patterns (word length, punctuation habits, common words/slang, emoji
  frequency) from an actual WhatsApp chat export via word-frequency /
  regex analysis — deliberately NOT the literal conversation content,
  since that shouldn't be baked verbatim into a file the AI reads to
  generate messages.

**Not yet built** (discussed, not implemented): config file for
contacts/backend so you don't retype them every run, reply preview/approval
mode, quiet hours, startup selector self-test, `h <name>` console command
to peek at history. Self-test and quiet-hours were flagged as the two worth
doing next.
