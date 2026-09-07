# Changelog

Append new entries at the bottom of the relevant section (or start a new
`## Debugging history — <feature>` section for something not covered yet).
Don't edit or delete past entries — this file is a record of what was
already tried and why it did or didn't work, so nobody re-discovers the
same dead end twice. See `STATUS.md` for the current state; this file is
the history that got you there.

## Debugging history — "Open on phone" false failures

**Reported:** clicking "Open on phone" on `com.transsion.phonemaster`-class
packages threw "no app can perform this action" on the phone screen, even
though the tool logged it as attempted. **Root cause:** the web UI's
`resolve-activity` lookup sometimes resolves to a bare
`ResolverActivity`/`ChooserActivity` component. Those aren't real launcher
entry points — they exist to be invoked *as part of* another app's intent
resolution, and calling one directly with `am start -n` throws because
there's nothing for it to resolve. **Fixed:** `open_app()` now skips any
component whose class name matches `ResolverActivity`/`ChooserActivity`
and falls through to the `monkey -p <pkg> -c android.intent.category.LAUNCHER`
launcher-intent fallback instead, which doesn't need to know the specific
activity.

**Follow-up, same feature:** many packages (system SDK stubs, overlays,
background services — e.g. `com.unisoc.wifi`, `com.google.android.webview`,
`com.transsion.theme.icon`) have no launcher activity at all, so even the
monkey fallback fails with "No activities found to run, monkey aborted."
This was being shown to the user as a scary raw error. **Fixed:** detected
that specific monkey output and replaced it with a plain-language message
("no visible screen, this is normal for background/system components, safe
to uninstall/disable directly") instead of the raw tool output. Confirmed
via live session against ~40 real system packages across Unisoc,
Transsion, and Google AOSP-Go prefixes — all correctly got the friendly
message, and several of those same packages uninstalled cleanly right
after, confirming "no UI" and "not removable" are unrelated properties.

**Follow-up #2, same feature — false FAILED on YouTube.** After the fixes
above, `com.google.android.youtube` was still logged as FAILED even though
the shown message (`Starting: Intent { cmp=com.google.android.youtube/
.app.honeycomb.Shell }`) is exactly what a successful launch looks like.
**Root cause:** the success check was `"Error" not in out2 and "Exception"
not in out2 and "Error" not in err2` — a fragile substring match. Something
in YouTube's stderr apparently contains the literal substring "Error" even
on a completely normal launch, and because the display logic was
`out2 or err2`, a non-empty `out2` meant `err2`'s actual content (whatever
tripped the check) was never even shown to the user — a real success
misreported as a failure, with the true diagnostic hidden. **Fixed:**
replaced the heuristic with a positive check (`"starting: intent"` present
in combined stdout+stderr) combined with a short list of specific fatal
markers (`does not exist`, `error type 3`, `securityexception`,
`permission denial`, `unable to resolve`) that only fire on real failure
patterns. On failure, the full combined output is now always shown instead
of silently dropping whichever half happened to be empty.

## Debugging history — Protected-package errors

**Reported:** `tech.palm.id` failed uninstall with
`DELETE_FAILED_INTERNAL_ERROR`, and disable failed with a full Java
`SecurityException: Cannot disable a protected package` stack trace dumped
into the session log. **Root cause:** this is a genuinely OS-protected
package (Transsion's palm-print/biometric auth stub) — Android's own
`PackageManagerService` refuses the change at the OS level, independent of
anything this tool does. No userland workaround exists without root.
**Fixed:** `uninstall()` and `disable()` in `android_debloat_tool.py` now
detect these specific failure signatures (`DELETE_FAILED_INTERNAL_ERROR`,
`protected package`) and return a short, clear message instead of the raw
stack trace, so it's obvious this is an OS-level refusal and not a tool
bug or something worth retrying.

## Feature — Web UI: foreground-app lookup ("What's on screen now?")

Ported the CLI's existing `current_focus()` (option `0`, reads
`dumpsys window`'s `mCurrentFocus` line) into a structured
`foreground_app()` that returns a parsed package name instead of just
printing raw text, plus a new `/api/foreground` endpoint and a header
button. Clicking it identifies whatever's currently on the phone's screen
and, if that package is in the currently-loaded app list, scrolls to and
highlights its row. Handles the edge cases the CLI version didn't need to:
`mCurrentFocus=null` (screen off/locked — shown as-is, not treated as an
error) and non-package focus targets like `NotificationShade` (the
notification shade being focused isn't a package, shown as-is rather than
forced through the package-name parser). Confirmed live across ~40 real
foreground-app switches in one session with zero misidentifications.

## Feature — Web UI: per-app Details panel

Added `app_details()` in `android_debloat_tool.py`, parsing
`dumpsys package <pkg>` for version name/code, first-install and
last-update timestamps, target SDK, and system-vs-user status (via the
`pkgFlags` field), plus APK size via `du -sh` on the resolved code path.
Wired to a new `/api/details?pkg=` endpoint and a per-row "Details"
button in the web UI that toggles an inline panel. Deliberately does NOT
attempt to fetch the human-readable app label or icon — that requires
parsing the APK's `resources.arsc` (what `aapt`/`aapt2` does), which is a
real dependency this project doesn't currently have. Package ID remains
the primary identifier; Details fills in the "tap an app in Settings"
metadata without needing that dependency. Code compiles and was reviewed,
not yet clicked on a live device — mark as confirmed once it has been.

## Feature — Web UI: anonymized scan-report export

Added `export_session_report()` and a `/api/export_report` endpoint plus
header button. Parses the existing `debloat_log.txt` for
OPEN/UNINSTALL/DISABLE/RESTORE result lines and compiles them into a JSON
report containing only: package name, action, result, truncated detail
text, curated category/risk if known, Android version (`ro.build.version.
release`), and device *brand* only (`ro.product.brand` — e.g. "Tecno", not
model or serial). Deliberately excludes any device identifier (no serial,
no IMEI, no account info) and deliberately does NOT transmit anything —
it writes a local file and stops. This was a direct design choice after
discussing "collect data from users and send it somewhere for future
users": an automatic phone-home in a tool people run specifically to
*reduce* what's tracking them would undermine the tool's own purpose and
create real liability (a server to secure, a privacy policy needed,
consent that a background upload can't obtain). The manual/local-only
version lets a user choose to share their own file (e.g. pasting it into
a GitHub issue) without the tool ever doing that on their behalf.
Confirmed live — a real session produced a 4-result report exactly
matching that session's actual uninstalls (Google app, Duo/Tachyon,
MikroTik client, YouTube Music).

## Process note — adopted STATUS.md/CHANGELOG.md protocol (2026-09-06)

This project didn't previously use the STATUS.md/CHANGELOG.md handoff
protocol used on `ig_manager`. Adopted it here at Geoffrey's request so
future sessions (either AI, or Geoffrey picking this back up months
later) have one file to read instead of re-deriving project state from
scratch. Backfilled STATUS.md's "Current known-good state" table from
this changelog's own history rather than guessing, so confidence levels
reflect what's actually been confirmed on a real device versus what's
just been reviewed and compiled.
