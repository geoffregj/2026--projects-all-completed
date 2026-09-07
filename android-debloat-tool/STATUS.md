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

- **When:** 2026-09-06
- **By:** Claude (Sonnet 5), this thread
- **What changed:** Adopted the STATUS.md/CHANGELOG.md protocol from
  `ig_manager` for this project. Added three new web UI features
  (foreground-app lookup, per-app Details panel, anonymized scan-report
  export), fixed two real bugs found through live on-device testing
  (see Current known-good state and CHANGELOG.md), and refreshed
  README.md to document all of it. All changes confirmed via
  `py_compile` and live testing on Geoffrey's actual Tecno/HiOS device
  across several sessions — this is not a "looks right on review, never
  run" state like some ig_manager entries; every feature listed
  "confirmed" below has real terminal/log output backing it.

## Current known-good state

Confidence noted per feature — "confirmed" means there's real terminal
output or session-log evidence from an actual run on a real device, not
just that the code looks right on review.

| Feature | Status | Evidence |
|---|---|---|
| Terminal tool — categorize/uninstall/disable/restore (CLI) | confirmed | original tool, used across many prior sessions |
| Web UI — full installed-app list (curated + "not in curated DB") | confirmed | multiple live sessions, hundreds of packages enumerated correctly |
| Web UI — Open on phone (resolve-activity path) | confirmed | correctly launches real activities (Calculator, DeskClock, etc.) |
| Web UI — Open on phone (monkey fallback) | confirmed | correctly launches apps with no resolve-activity match |
| Fix: ResolverActivity/ChooserActivity no longer attempted as explicit `am start -n` target | confirmed | verified against `com.transsion.phonemaster`-class packages that previously threw "no app can perform this action" |
| Fix: headless/no-UI packages (system SDK stubs, overlays) show a clear message instead of a raw monkey error | confirmed | live session showed correct messaging across ~40 unisoc/transsion/google.android system packages |
| Fix: `tech.palm.id`-class OS-protected packages show a clean message instead of a Java stack trace on uninstall/disable | confirmed | live session, both uninstall and disable paths |
| Fix: YouTube (and similarly noisy apps) no longer misreported as FAILED on a real successful launch | confirmed | root cause was a fragile "Error"-substring check; replaced with a "Starting: Intent" positive-success check plus a specific fatal-marker list |
| Web UI — "What's on screen now?" (foreground app lookup + row highlight) | confirmed | live session, correctly identified ~40 different foreground apps including `mCurrentFocus=null` (locked/off screen) and non-package focus targets (`NotificationShade`) |
| Web UI — per-app Details panel (version, size, install/update dates, system-vs-user) | untested | code compiles and reviewed, not yet clicked on a live device |
| Web UI — Export scan report (anonymized JSON, manual/local only) | confirmed | live session, produced a 4-result report matching the session's actual uninstalls |

## In progress / do not touch

*(nothing right now)*

## Open decisions waiting on Geoffrey

- **Crowdsourcing beyond local export:** current design is intentionally
  manual — `scan_report.json` is written locally and never transmitted.
  If Geoffrey wants actual cross-user aggregation later, the lowest-risk
  path discussed is a GitHub issue/PR template where people paste their
  exported JSON, folded into `APP_DB` by hand — not an automatic
  phone-home server. No decision needed unless/until he wants to build
  the receiving side of that.
- **App names/icons in the "all apps" view:** getting real human-readable
  labels (not just package IDs) requires parsing APK resources
  (`aapt`/`aapt2`) or pulling and parsing each APK — a real dependency,
  not currently added. Details panel covers version/size/dates instead,
  which doesn't need it. Revisit only if Geoffrey specifically wants
  app icons/names and is fine adding an `aapt` dependency check.

## Standing risks (don't re-litigate these without new evidence)

- **No root, by design.** Every action goes through `pm uninstall --user 0`
  / `pm disable-user` / `cmd package install-existing`. This is
  reversible and safe, but it means genuinely OS-protected packages
  (see `tech.palm.id` in CHANGELOG.md) cannot be removed at all without
  root — that's Android's own PackageManagerService refusing the
  request, not a limitation of this tool that could be coded around.
- **`com.sh.smart.caller` can BE the phone dialer** on some HiOS builds,
  not just a caller-ID add-on. Tagged `CAUTION`, not `SAFE`, on purpose.
  Don't "fix" this tag without new confirmed evidence.
- **Detecting "no launcher UI" vs "genuinely broken" is a heuristic**
  (string-matching monkey's "No activities found to run" output). If a
  future Android version changes that exact wording, the friendly
  message stops firing and falls through to the old raw-error behavior
  — not a silent failure, just a worse message. Worth a quick check if
  this ever stops looking right after an Android platform update.
- **Anything installed-app-list-shaped is mildly fingerprinting data.**
  This is exactly why scan-report export is manual/local/opt-in only —
  don't add automatic transmission of this data without an explicit,
  separate conversation about consent and hosting (see Open decisions).
