# Changelog

Append new entries at the bottom of the relevant section (or start a new
`## Debugging history — <feature>` section for something not covered yet).
Don't edit or delete past entries — this file is a record of what was
already tried and why it did or didn't work, so nobody re-discovers the
same dead end twice. See `STATUS.md` for the current state; this file is
the history that got you there.

## Debugging history — Two sessions converged on the same bug (2026-08-19)

Geoffrey uploaded a zip mid-thread that turned out to be a different
branch of work than this thread's own accumulated state — behind in most
ways (missing `1T`, priming, `max_duration`, most of the unfollow
debugging this thread had already done) but ahead in one specific way: a
separate session had already improved `_unfollow_by_id()` with a
cross-validated check (verifying the response's own
`friendship_status.following` field, not just a top-level `status` flag)
that this thread hadn't written. Reconciled rather than picking one
wholesale over the other:
- Kept the other session's smarter check-and-cross-validate logic.
- Added what it was still missing: response detail capture for
  diagnosis, a per-target DOM-click fallback specifically for plain
  'error' results (an HTML/non-JSON response is treated as fallback-
  worthy — same systemic write-rejection pattern as `current_user`/DM —
  while a 'checkpoint' result still stops the batch, since that's a
  genuine account-level soft block a browser click would likely also
  hit), and the search-box scoping fix — this uploaded copy's existing
  all-or-nothing DOM fallback had the exact same unscoped-selector bug
  already found and fixed elsewhere in this thread.
- Reapplied everything else this thread had built that the upload was
  missing (see the "Priming pass"/"parallel analyze"/"absolute wall-clock
  cap" entries below — all unchanged in substance, just re-threaded onto
  this base).

Lesson for future sessions: when picking up a zip mid-project, diff
`STATUS.md`'s "Last updated" timestamp/round-number against what you'd
expect, not just against your own memory of prior turns — the two can
drift independently, and the version in front of you might be either
behind OR ahead of what you last worked on, sometimes both at once in
different files.

## Debugging history — Groq reply backend

**Reported as "Groq connection errors."** Checked Groq's live deprecations
page rather than assuming — `llama-3.3-70b-versatile` (the hardcoded
model) was deprecated 2026-06-17. That's a model-not-found/deprecated
error from Groq, not an actual network/connectivity problem; the vague
error text just looked like one. **Fixed:** default model changed to
`openai/gpt-oss-20b` (Groq's current recommended migration target).
Brought Groq's `reply_fn` up to parity with Gemini's while in there: it
now surfaces the real response body on an HTTP error instead of a bare
status code, and it now actually uses conversation history (`hist`) —
previously it was the only backend silently ignoring it and replying with
zero context.

## Debugging history — DOM-scroll speed (fallback path)

**Reported:** even after the undercount fix above, the scroll fallback
felt slow on large lists — every scroll was sleeping the *entire* fixed
pause (1.2s+) regardless of how fast Instagram actually rendered the next
batch, which dominates total runtime on a big list (150 scrolls x 1.2s ≈
3 minutes, most of it unused idle time). **Fixed:** added
`_wait_for_new_rows()`, which polls every 0.25s and returns as soon as
the raw row count in the dialog grows, instead of always sleeping the
full window. The existing pause value (1.2s baseline, up to ~4s while
stagnant) is now used only as a *ceiling* — a slow batch still gets the
same patience as before (so the undercount fix isn't weakened), but a
normally-loading batch moves on as soon as it's actually ready instead of
waiting out a fixed timer.

## Debugging history — DOM-scroll undercounting (analyze fallback)

**Reported:** scroll-based follower/following scrape (`_scroll_and_collect`,
used when the API fast-path isn't available) came back short — 884 found
vs 917 shown on the profile header for a following list. **Root cause:**
the loop declared "reached the end of the list" after 6 consecutive
scrolls with no new usernames, sleeping a flat 1.2s between each — on a
slower-loading virtualized batch that's ~7s of patience total, which is
easily mistaken for "nothing left" when it's really "still loading."
**Fixed:** `stagnant_limit` raised from a hardcoded `6` to a configurable
default of `14`, and the pause between scrolls now grows with consecutive
stagnant rounds (1.2s up to ~4s) instead of staying flat, giving slow
batches more time to render before being judged empty — while keeping the
original fast 1.2s pace whenever new rows are still showing up. Also
added an on-stop message stating the final count and stagnant-limit
reached, instead of just silently returning. Note: Instagram's own header
count is a cached/approximate figure and can still differ from the
scraped list by a small amount even with this fix — that's expected, not
a bug in this function.

## New features (post-fix)

**7. Fixed false "logged-in account doesn't match" — API fast-path now actually fires for analysis.**
`_api_session_from_driver()` was only forwarding 3 named cookies (`sessionid`, `csrftoken`, `ds_user_id`) out of the Selenium browser's full cookie jar into the `requests` session used for the API fast-path. `unfollow_batch`'s friendship endpoints tolerate that fine, but `verify_api_session_owner()`'s call to `/accounts/current_user/?edit=true` is stricter and was silently rejecting the incomplete session — producing a false "logged-in account doesn't match @username" warning and forcing the slow DOM-scroll fallback on every `analyze_live` run, even when genuinely logged in as the right account. Fixed by forwarding the entire cookie jar instead of cherry-picking three. `verify_api_session_owner()` also now prints the actual HTTP status/exception on failure instead of failing silently, so a real mismatch and a broken session no longer look identical in the logs.

**6. DM auto-reply loop (menu option 4L) — checks every N seconds, pausable, sender allow-list.**
Option 4 was always a one-shot scan. `ig_selenium.dm_reply_loop()` wraps the existing `dm_check_and_reply()` in a timed loop (default 60s, configurable, floor of 15s) run on a background thread, while the main thread drops into a `dm-loop>` prompt taking `p` (pause), `r` (resume), `q` (stop and return to menu). Pause/stop are checked every 1s rather than slept for the full interval, so they take effect almost immediately instead of waiting out the whole cycle. Also added `allowed_senders` to `dm_check_and_reply()` itself — pass a comma-separated username list at the prompt and threads from anyone else are skipped outright (not logged, so they're picked up automatically the moment they're added back to the list); leave it blank to reply to everyone, same as before. Only wired into the DOM-clicking reply path, not the API-based unfollow path — unaffected by the `useragent mismatch` decision that's still open.

**4. Update saved API keys/config from the menu (option 12).**
Previously changing a saved key/model meant manually deleting `~/.ig_manager_gemini.json`. Option 12 now lets you re-enter any field (Gemini key/model, `self.json` path, Groq key/model) and leave the rest untouched by leaving a prompt blank. Fixed a real bug this surfaced along the way: `_save_gemini_config` was doing a full overwrite of the config file rather than merging, which would have silently deleted Groq's saved key the next time the Gemini backend got used (both backends share the same file under different keys). Now merges.

**5. Ollama default model changed from `qwen2.5-coder:7b` to `llama3.1:8b`.**
Confirmed firsthand that the coder-specialized variant produces noticeably worse casual-conversation replies for DMs — it's trained for code, not chat. Still fully usable if you type it in explicitly; it's just no longer what a blank Enter gives you.

**1. Persistent Gemini config — no more retyping the key every run.**
A small file, `~/.ig_manager_gemini.json` (mode 600, same treatment as `ig_cookies.json`), now stores the API key, model, and `self.json` path after the first time you enter them. Precedence: `GEMINI_API_KEY` env var (if set) > saved config file > prompt. Once saved, the key is never printed in full again — only the last 4 characters, so it can't end up in another screenshot. This file is plaintext on disk (not encrypted) — fine for a personal machine, don't back it up unencrypted or commit it anywhere.

**3. Analyze (option 1) now uses the API fast path too.**
Same pattern that already made unfollow fast: `analyze_live` first tries
Instagram's private `friendships/{id}/following|followers` endpoints
(paginated, ~200 accounts/request) instead of scrolling the dialog, which
was taking minutes and would only get slower as follower count grows. Falls
back automatically to the DOM-scroll scrape if an API session can't be
built, or if the logged-in account doesn't match the username being
analyzed (the endpoint always returns the session owner's own list, so
this fast path only applies to analyzing your own account — anything else
correctly falls back rather than silently returning the wrong data).
A small file, `~/.ig_manager_gemini.json` (mode 600, same treatment as `ig_cookies.json`), now stores the API key, model, and `self.json` path after the first time you enter them. Precedence: `GEMINI_API_KEY` env var (if set) > saved config file > prompt. Once saved, the key is never printed in full again — only the last 4 characters, so it can't end up in another screenshot. This file is plaintext on disk (not encrypted) — fine for a personal machine, don't back it up unencrypted or commit it anywhere.

**2. "Who's me vs who's them" in DM history.**
Previously the last-5-messages history sent to Gemini was just raw scraped text with no attribution — Instagram's DOM doesn't label which side sent which bubble. Now each bubble is classified by horizontal position (your own messages render right-aligned, theirs left-aligned — the same convention every chat UI uses), clustering by the midpoint between the leftmost and rightmost bubble rather than a fixed pixel guess, so it adapts to window size. The reply also now targets the last message actually *from them* — if the most recent bubble in the thread is something you already sent, the script correctly recognizes there's nothing new to reply to instead of treating your own last message as an incoming one. The classified `You: ... | Them: ...` breakdown prints to the terminal for each thread so this is visible, not silent.

## Debugging history — DM auto-reply (option 4)

**1. Silently did nothing ("Replied to 0 threads")**
Original code scraped rendered HTML with a fixed `sleep()` and no error output — if the page hadn't loaded or the markup didn't match, it just returned 0 with no explanation.

**2. Tried Instagram's private JSON API instead of scraping HTML**
Both a separate `requests.Session` and later in-browser `fetch()` calls were rejected with `HTTP 400: "useragent mismatch"`, including right after a fresh login — ruling out a stale session. Working theory: the header this route needs (`X-IG-App-ID: 936619743392459`) is extremely widely reused across public IG-scraper tools and likely gets flagged by Instagram's abuse detection on sight. Abandoned — an arms race against Instagram's anti-bot systems, not a code bug.

**3. Back to driving the UI — but the thread list had changed shape**
Switched back to clicking the real message box and send button. First attempt still looked for `//a[contains(@href,'/direct/t/')]`, which Instagram no longer reliably uses for conversation rows.

**4. Row-click fix, but it grabbed the Notes tray instead of real threads**
The broadest fallback row-selector (`div[role='button']` containing an image) matches Instagram's Notes tray just as well as real conversation rows. Result: "clicking it didn't navigate anywhere" — it was clicking note bubbles.

**5. Fixed: filter out note bubbles by their visible text shape**
Real conversation rows show a trailing time-ago suffix (`2h`, `57m`, `9h`, `1d`); note bubbles don't. `_find_dm_rows` filters on that.

## Debugging history — Gemini reply generation

**1. HTTP 404, no explanation.** `urllib.request.urlopen` raised a bare `HTTPError` with the response body swallowed. Fixed: `reply_fn` now catches `HTTPError` and prints Google's actual response body before re-raising.

**2. Root cause of the 404:** `gemini-2.5-flash` is no longer available to *new* API keys/projects. Fixed: default model changed to `gemini-3.6-flash`, the current GA model per Google's docs.

**3. Replies came back empty ("hey!" fallback), `finishReason: MAX_TOKENS`.** `gemini-3.6-flash` does internal reasoning ("thinking") by default, sharing the same `maxOutputTokens` budget as the visible reply.

**3a. First fix attempt was itself wrong.** Set `thinkingConfig: {"thinkingBudget": 0}` — but that's the *Gemini 2.5-series* field. Gemini 3.x models use `thinkingLevel` instead, and sending the wrong one is an `INVALID_ARGUMENT` 400. Google's docs also say Gemini 3 Flash/Flash-Lite don't support disabling thinking at all — `0`/off was never going to work for this model family regardless.

**3b. Actual fix:** the model's major version is parsed from its name and the correct field is picked automatically — `thinkingBudget: 0` for Gemini ≤2.x, `thinkingLevel: "low"` (the minimum available) for Gemini 3.x. `maxOutputTokens` raised to 500.

**4. `ChromeDriver only supports characters in the BMP`.** Most colorful emoji live outside Unicode's Basic Multilingual Plane, and ChromeDriver's `send_keys` throws instead of skipping the character, killing the whole reply. Fixed: reply text is stripped of non-BMP characters before typing, and the system prompt now tells Gemini not to bother generating emoji.

## Standing risks / things to know

- **Automating Instagram (unfollow batches, auto-follow, auto-DM, auto-comment, bulk-like) violates Instagram's Terms of Service.** This whole toolkit runs that risk regardless of which internal method is used — accounts can get rate-limited, checkpointed, or banned.
- **Any API key that's ever appeared on-screen in a debugging screenshot should be treated as burned** — regenerate it. The persisted config file only masks the key in *future* prints; it doesn't retroactively protect a key that's already been shown.
- `self.json` and `~/.ig_manager_gemini.json` both contain personal/sensitive content (your profile, your API key). Neither is included here, and neither should be shared or committed anywhere.
- Instagram's markup can and does change without notice. If DM auto-reply breaks again, run with `SELENIUM_DEBUG=1`, check `~/cortana_debug/` for the dumped screenshot/HTML, and get a screenshot of the actual rendered page before assuming a fix.
- Google's Gemini model names, fields, and default behavior move fast and differ between model generations. If a 400/404 shows up again, the printed error body names the real reason.
- Replies now come from a real generative model responding to real people's real messages, unsupervised. Worth periodically checking `dm_log.json` for what it's actually been sending.

## Debugging history — Unfollow silent failures

**Reported:** unfollow batch logs "✔ Unfollowed" for accounts but they stay
followed. **Root cause:** `_unfollow_by_id()` treated any HTTP 200 as
success without checking the response body. Instagram's `friendships/destroy`
endpoint can return HTTP 200 with a body that says the action didn't apply
(session soft-blocked / checkpoint flag), and the old code had no way to
tell that apart from a real success. **Fixed:** parse the JSON body, require
`status == "ok"`, and re-check `friendship_status.following` is `False`
before reporting success — added a distinct `"checkpoint"` result so this
case is never miscounted as a real success or a real per-account error.
`unfollow_batch()` now stops on the first checkpoint result instead of
continuing to log fake successes for the rest of the batch.

## Three-way branch merge + feature trim (2026-09-04)

Three sessions had independently modified this codebase from the same
2026-08-19 base with no visibility into each other's work: this thread
(unfollow silent-fail fix), a "reconciliation" session (1T parallel
analyze, priming, DOM fallback for unfollow), and a separate session
(DM/comment reply persona + SKIP sentinel, ported from wa_manager).
Merged by reading each branch's actual code rather than trusting any
one branch's changelog — used the unfollow-side branch as the base
(most advanced on that feature) and spliced in the persona/SKIP work
from the DM-side branch.

Also trimmed the menu at the user's request, on the grounds that most
options had never actually been used: kept analyze (1/1T), unfollow (2),
DM auto-reply (4/4L), config update (12). Deleted the functions backing
every removed option (seed_follow, reply_to_comments, post_story,
growth_snapshot, profile_audit, bulk_like, hashtag_research,
notifications_digest) and the already-dead save_post(). profile_counts()
was also removed since it was a helper used only by the two removed
audit/snapshot functions.
