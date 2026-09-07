# Status

**If you're an AI picking up work on this project: read this whole file
before touching any code.** If you're about to make a change, update the
relevant section below as part of *that same delivery* — not as an
afterthought, not "next time." An out-of-date STATUS.md is worse than no
STATUS.md, because it makes a stale state look current.

**If you're Geoffrey starting a new session (with either AI):** paste this
file in first, before describing what you want done. That's the whole
protocol — one file, pasted at the start of a session, instead of
re-uploading zips and hoping both threads end up seeing the same state.

---

## Last updated

- **When:** 2026-08-19 (reconciliation — this uploaded copy had drifted
  from the thread's own working copy)
- **By:** Claude (Sonnet 5), this thread
- **What changed:** Geoffrey uploaded a zip that turned out to be behind
  this thread's own accumulated work (no `1T`, no priming, no
  `max_duration`, none of the unfollow debugging) — BUT ahead in one real
  way: `_unfollow_by_id` already had a smarter body-check than this
  thread had written, including cross-validating the response's own
  `friendship_status.following` field to catch a sneaky case where
  Instagram reports `"status":"ok"` while that same field still shows
  `following: true`. That version's own docstring dates it after this
  thread's timeline, meaning a separate session/surface did real,
  independent work on this exact bug.

  Reconciled rather than overwritten: kept that smarter check-and-
  cross-validate logic, and layered in what it was still missing —
  response detail capture on the plain 'error' path (needed for
  diagnosis, not just checkpoint), a per-target browser-click fallback
  (`_dom_unfollow_one`) for 'error' results specifically (an HTML/non-
  JSON response looks like the same systemic write-action rejection seen
  on other endpoints this session, worth trying to route around — a
  'checkpoint' result still stops the batch entirely, since that's a
  genuine account-level soft block a browser click would likely also
  hit), and the search-box scoping fix (this file's existing all-or-
  nothing DOM fallback had the exact same unscoped-selector bug already
  found and fixed in this thread — Instagram's global nav search box
  shares the same placeholder text as the dialog's own internal one).

  Also reapplied everything else this thread had already built that this
  upload was missing: analyze's `1T` parallel option, the priming pass,
  time-based progress heartbeat, the `max_duration` safety net, and the
  UA-forwarding + response-body-logging fixes on the owner-verification
  path. **Genuinely untested in this merged form** — next real runs of
  both analyze and unfollow are what confirm the reconciliation held
  together correctly, not just that it compiles.

- **Earlier — 2026-08-19 (this thread's own prior rounds):** see
  CHANGELOG.md for the full round-by-round history — UA-mismatch
  investigation, DOM-scroll priming/speed work, the false-success
  unfollow bug and its fixes, all still applicable and now folded into
  this reconciled copy.

- **Earlier — 2026-08-19 (this upload's own prior state, before
  reconciliation):** Sped up the DOM-scroll fallback (`_scroll_and_collect`)
  without weakening the undercount fix from earlier today. It previously
  slept a flat fixed pause after every scroll regardless of how fast the
  next batch actually rendered — on a big list that's minutes of pure
  unused waiting. Added `_wait_for_new_rows()`, which polls every 0.25s
  and moves on the instant new rows appear; the old pause value is now
  only a ceiling for genuinely slow batches, not a fixed cost paid every
  time. Not yet run against a live account.

- **Earlier — 2026-08-19 (first patch of the day):** Fixed
  `_scroll_and_collect()`'s undercounting bug — it was declaring the
  follower/following list "done" after only 6 consecutive empty scrolls
  at a flat 1.2s pace, which a slow-loading batch can trigger by mistake
  (confirmed: 884 found vs 917 shown on a real following list).
  `stagnant_limit` raised to a configurable `14`, and the inter-scroll
  pause ceiling now grows with consecutive stagnant rounds (1.2s -> ~4s)
  instead of staying flat. This only affects the DOM-scroll *fallback*
  path — the API fast-path (`fetch_full_friendship_list`, landed
  2026-08-18) doesn't have this failure mode and is used first whenever a
  valid API session can be built.

- **Earlier — 2026-08-08:** Fixed the Groq backend — `llama-3.3-70b-versatile` was
  deprecated by Groq on 2026-06-17, which is what was actually causing
  "Groq connection errors" (not a real connectivity issue). Default
  changed to `openai/gpt-oss-20b`, added the same HTTPError-body-surfacing
  treatment Gemini already had, added conversation history support (Groq's
  reply_fn was the only backend still ignoring `hist`), and gave it the
  same persisted-key treatment as Gemini (`.ig_manager_gemini.json`, now
  shared across both backends under different keys). Fixed a real bug this
  surfaced: `_save_gemini_config` did a full overwrite instead of a merge,
  which would have silently wiped Groq's saved key the next time Gemini
  was used — fixed to merge. Added menu option 12 (update saved
  API keys/config) instead of requiring manual file deletion to change
  one. Changed the Ollama backend's default model from `qwen2.5-coder:7b`
  to `llama3.1:8b` — confirmed firsthand that the coder variant produces
  noticeably worse casual-conversation replies, so it shouldn't be the
  default suggestion anymore (still usable if explicitly chosen, just not
  what a blank Enter gives you).

## Current known-good state

Confidence noted per feature — "confirmed" means there's real terminal
output from an actual run, not just that the code looks right on review.

| Feature | Status | Evidence |
|---|---|---|
| Login (all 4 methods) | confirmed | used repeatedly across sessions |
| Analyze followers/following (option 1) | confirmed (DOM path, ~98-99% complete with priming); API fast-path **not viable** — see standing risks | multiple confirmed runs this thread, including a validated 891/852 vs real ~917/854 |
| Analyze followers/following (option 1T, parallel two-window) | untested | just added, never actually run |
| Unfollow (option 2) | **broken via API — confirmed, not suspected; DOM fallback exists but untested end-to-end in this merged form** | API destroy returns HTML/non-JSON responses (same systemic pattern as current_user/DM); per-target + all-or-nothing DOM fallbacks both scoped-search-fixed, neither run since the fix |
| Seed-follow (option 3) | untested | fixed alongside unfollow's dialog-open bug, never actually run |
| DM auto-reply (option 4, Gemini) | confirmed | 8 real Gemini-generated replies sent successfully |
| DM auto-reply (option 4, Groq) | untested (post-fix) | model was deprecated and erroring before this fix; new model/error-handling/history support never actually run |
| DM auto-reply (option 4, Ollama) | untested | never reported as run |
| Comment auto-reply (option 5) | untested | hardened to match DM's robustness, never actually run |
| Update saved config (option 12) | untested | just added, never actually run |
| Story posting, growth log, profile audit, bulk like, hashtag research, notifications digest | untested | never reported as run in either thread |
| Analyze — API fast-path full cookie forwarding fix (2026-08-18) | untested | code looks right on review, never actually run |
| DM auto-reply loop / pause-resume (2026-08-18) | untested | code looks right on review, never actually run |
| Analyze — DOM-scroll undercount fix (2026-08-19) | untested | code looks right on review, never actually run |

## In progress / do not touch

*(nothing right now — if you start something that will take more than one
message to finish, list it here with which file/function, so the other
thread doesn't collide with it)*

## Open decisions waiting on Geoffrey

- **License:** defaulted to MIT in this delivery. Confirm or change
  `LICENSE`.
- **Gemini rate limits:** hitting 429s on `gemini-3.6-flash` free tier.
  Check https://aistudio.google.com/rate-limit for actual current quota —
  neither AI thread can see this from here.

## Standing risks (don't re-litigate these without new evidence)

- API write actions (destroy/friendships, likely others) return HTML or
  non-JSON responses on this account/session — the same systemic
  rejection pattern already confirmed on `current_user`/DM, now also
  confirmed on unfollow's destroy call. Reads (fetching the following-
  list ID map) work fine over the same session; it's specifically writes
  that get walled off. Both DOM fallback paths (per-target and all-or-
  nothing) now share `_dom_unfollow_one()` with a scoped search-box
  lookup — the earlier bare-selector version was silently typing into
  Instagram's own global nav search box instead of the dialog's internal
  one, which is why "not found" appeared for accounts confirmed still
  followed. Not yet confirmed the scoped fix actually gets someone
  unfollowed end-to-end — that's the next real test.
- Automating Instagram violates its ToS regardless of method (DOM-clicking
  vs private API). This is a known, accepted risk, not an open question.
- The `X-IG-App-ID: 936619743392459` header gets Instagram's private
  **DM/inbox** endpoints rejected with "useragent mismatch" — confirmed on
  this account, on two independent code paths (`cortana_mint.py`'s login
  flow and an earlier `ig_manager.py` DM attempt). DM/comment reply
  therefore drives the real browser, not the API.
- The same header, on the **friendships** endpoints (unfollow, follower/
  following lists), has *not* shown the same rejection across repeated use
  — currently treated as lower-risk for those specific endpoints only.
  This is observed behavior, not a guarantee; if it starts failing, that's
  new evidence, revisit it then.
- Any API key or password that's appeared on-screen (screenshot or pasted
  terminal output) should be treated as burned. This has happened at least
  twice (an Instagram password, a Gemini key) — check `CHANGELOG.md` for
  specifics before assuming an old warning is stale.

- **2026-09-03:** Fixed a silent-failure bug in `_unfollow_by_id()` — it
  only checked HTTP status code (200 = "ok"), never the response body.
  Instagram can return HTTP 200 with a body indicating the unfollow didn't
  actually apply (soft block / checkpoint), and the old code logged these
  as "unfollowed" while the account stayed followed. Now parses the JSON
  body, checks `status == "ok"`, and re-confirms `friendship_status.following`
  is actually `False` before reporting success. Added a new `"checkpoint"`
  result that stops the batch immediately (instead of burning through the
  whole target list logging fake successes) and tells the user to clear
  any Instagram challenge/checkpoint before re-running. Not yet run against
  a live account — same "code looks right on review" caveat as other
  recent unrun patches.

- **2026-09-04 — Three-way merge + feature trim.** Reconciled three
  divergent branches that had drifted from the same 2026-08-19 ancestor
  with no cross-awareness of each other's work:
  - This thread's unfollow silent-fail fix (checkpoint detection, body
    verification) — already present in the branch used as merge base.
  - The reconciled branch's unfollow-side work: `1T` parallel analyze,
    priming pass, `max_duration` safety cap, `_dom_unfollow_one` fallback
    for non-JSON write responses.
  - A separate parallel branch's DM/comment reply work: `_REPLY_PERSONA_BASE`
    (ported from wa_manager) and the `SKIP` sentinel, letting the model
    decline to reply instead of forcing one into every message. Ported
    into this branch's `_prompt_reply_backend` (all 3 backends: Gemini,
    Ollama, Groq) and wired the `SKIP` check into `dm_check_and_reply`.
  - User-directed feature trim: removed everything except analyze (1/1T),
    unfollow (2), DM auto-reply (4/4L), and config update (12). Removed
    from the menu and deleted their now-dead functions entirely: seed-follow
    (3), comment auto-reply (5), post story (6), growth snapshot (7),
    profile audit (8), bulk like (9), hashtag research (10), notifications
    digest (11) — plus `save_post()`, which was already dead code (defined,
    never wired to any menu option).
  - Verified: `ast.parse` succeeds on both files, no dangling references
    to any removed function anywhere in the codebase.
  - **Not yet run against a live account** — same "code looks right on
    review, not confirmed by an actual run" caveat as prior unrun patches.
    Standing risk from the prior entry (API write actions returning
    non-JSON / HTML) is still unresolved and should be checked before
    running option 2 or 4 for real.

- **2026-09-04 (later same day) — Fixed a real crash from the merge above.**
  `dm_check_and_reply` (option 4) crashed on first use: `NameError:
  _find_dm_rows is not defined`. Root cause: the earlier feature-trim step
  removed `seed_follow` by cutting from its start to the start of
  `dm_check_and_reply`, but `_find_dm_rows` — plus its own dependencies
  `_looks_like_note_bubble` and the `_TIME_AGO_RE` regex, plus the
  "DM AUTO-REPLY" section header — were sitting in that gap and got
  deleted along with it. This is exactly the kind of bug the "code looks
  right on review, not confirmed by a real run" caveat is warning about —
  it passed `ast.parse` cleanly since a NameError only surfaces at
  runtime, not at parse time. Restored all four pieces from the
  pre-trim source and re-verified this time with `pyflakes` (proper
  scope-aware undefined-name checking) instead of just `ast.parse` —
  zero undefined-name errors now. Also fixed a second, unrelated,
  pre-existing bug pyflakes caught in the same pass: `CYN` was used in
  `dm_reply_loop`'s round-separator print but only ever defined in
  ig_manager.py, not in ig_selenium.py itself — would have crashed the
  DM loop (4L) on its first completed round. Still not run against a
  live account.
