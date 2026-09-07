# Status

**If you're an AI picking up work on this project: read this whole file
before touching any code.** If you're about to make a change, update the
relevant section below as part of *that same delivery* — not as an
afterthought, not "next time." An out-of-date STATUS.md is worse than no
STATUS.md, because it makes a stale state look current.

**If you're Geoffrey starting a new session (with any AI):** paste this
file in first, before describing what you want done. That's the whole
protocol — one file, pasted at the start of a session, instead of
re-uploading zips and hoping both threads end up seeing the same state.

---

## Last updated

- **When:** 2026-09-07 (later same day)
- **By:** Claude (Sonnet 5), this thread
- **What changed:** Code review pass on the other thread's additions
  (`TodayUsageActivity`, `UsageRingView`, `UsageStatsHelper`,
  `UnlockCounter`) plus this fork's own `AppLockSettings`/`UsageCheckReceiver`.
  Found and fixed one real bug affecting both: `AppLockSettings.rollOverIfNewDay()`
  and `UnlockCounter` both used `java.time.LocalDate`, but `minSdk` is 24
  and `build.gradle` has no core library desugaring enabled — `java.time`
  needs API 26+ without it, so both would have thrown
  `NoClassDefFoundError` the first time either ran on a real API 24/25
  device. Replaced with a `Calendar`-based day-id
  (`YEAR*1000 + DAY_OF_YEAR`), matching the `Calendar` usage already
  established elsewhere in this fork (`UsageCheckReceiver`,
  `UsageStatsHelper`) rather than adding a new dependency. Everything
  else reviewed (constraint chains, manifest registration, brace/paren
  balance, exemption-list logic, ring-view math, unlock-receiver
  registration) checked out clean — see below for the couple of
  non-bug improvement notes.
- **Previous entry:** Packaging pass, ported from `ig_manager`'s
  convention: replaced the upstream marketing `README.md` with a
  fork-specific one, added `.gitignore`.
- **Earlier entry:** Added a "Today's Usage" screen (`TodayUsageActivity` +
  `UsageRingView`) — a ring chart of today's per-app foreground time (top 7
  apps + "Other"), total time, and a screen-unlock counter, in the style of
  Android's own Digital Wellbeing ring. Built to add **zero** new
  always-on background cost: the ring/legend/unlock-count only compute
  when the screen is opened (`UsageStatsHelper` is a one-shot query, not a
  new poll), and unlock counting piggybacks on `ACTION_USER_PRESENT`
  registered from the accessibility service's existing
  `onServiceConnected()` — no new service, no new alarm, no wake lock.
  **Not yet built or run** — this sandbox has no network access to
  Google's Maven repo (`dl.google.com`) or `services.gradle.org`, so
  Gradle couldn't actually compile it here. Reviewed by hand (imports,
  brace/paren balance, XML constraint chain, manifest registration) but
  needs a real Android Studio build + on-device run before it's trusted.

## Current known-good state

Confidence noted per feature — "confirmed" means there's a real build/run
that actually exercised it, not just that the code looks right on review.
Everything below is carried over from the upstream README as claims;
**nothing has been independently verified in this thread yet** — treat
"per upstream" as "unverified by us."

| Feature | Status | Evidence |
|---|---|---|
| Builds from source (Gradle) | untested | never built in this thread — no network access to Google's Maven repo here |
| Device Owner provisioning | per upstream, untested | upstream README claim only |
| True app blocking (prevents launch) | per upstream, untested | upstream README claim only |
| Suspend/hide apps from launcher + Settings | per upstream, untested | upstream README claim only |
| Safe Mode blocking | per upstream, untested | upstream README claim only |
| Uninstall protection / auth-gated removal | per upstream, untested | upstream README claim only |
| ADB emergency recovery (`settings put secure ...`) | per upstream, untested | upstream README claim only |
| Samsung Knox-tripped devices | known-broken (documented) | upstream explicitly states provisioning fails here |
| Daily 5hr/2hr-social usage limit (`UsageCheckReceiver`) | per prior session, untested here | pre-existing "timed" feature, not touched this delivery |
| Today's Usage ring screen (new) | code-reviewed only, not built/run | added this delivery — see below |
| Unlock counter (new) | code-reviewed only, not built/run | added this delivery — see below |
| Teal/blue theme + fixed dark-mode colors (new) | code-reviewed only, not built/run | added this delivery — see below |

**Build target:** `compileSdk 36`, `minSdk 24`, `targetSdk 35`, Java 11,
package `com.jarm.applock`. Pulled from `AppSourceCode/AppLock/app/build.gradle`
— not run, just read.

**Prebuilt APK:** `ReleaseApk/base.apk` + `.idsig` are included in this
bundle as shipped by upstream. Not reproduced from this source tree in
this thread — if a rebuild ever produces a different APK, note that here.

## In progress / do not touch

- **New Today's Usage feature needs a real build + device run before it's
  trusted.** Files: `UsageStatsHelper.java`, `UnlockCounter.java`,
  `UsageRingView.java`, `TodayUsageActivity.java`, plus edits to
  `AccSrvForBootstrapAndLock.java` (one added line registering the unlock
  receiver), `SettingsActivity.java` (new button wiring), `settings_activity.xml`
  (new button + adjusted constraint chain), `AndroidManifest.xml` (new
  activity entry). Whoever builds this first: report back pass/fail and
  update the table above with real evidence, don't just flip it to
  "confirmed" on the assumption it compiles.

## Open decisions waiting on Geoffrey

- **What this project is for.** Upstream ships this as a general-purpose
  app locker. Confirm whether Geoffrey wants it as-is, or is planning to
  fork/modify it (e.g. rename package, add features, integrate with
  something else) — that changes whether "stay in sync with upstream" or
  "diverge and own it" is the right default going forward.
- **License/attribution.** Upstream `LICENSE` is MIT, copyright Jesús
  Alberto Developer. If this becomes a public fork, keep the upstream
  license/attribution intact per MIT terms rather than re-licensing as
  original work.
- **Notification count** (shown in the reference Digital Wellbeing
  screenshot alongside unlocks) was deliberately left out of this
  delivery — it needs a `NotificationListenerService`, which is a
  continuously-bound system component with real RAM/battery cost and its
  own manually-granted permission, unlike the unlock counter's one-shot
  broadcast. Add it only if Geoffrey actually wants that trade-off.
- **Ring/legend colors** are a fixed 8-color palette cycled by rank —
  now loosely coordinated with the app's teal/blue brand color (both
  landed in this thread), but not derived from it programmatically.
  Revisit together if that mismatch ever becomes noticeable.
- **Theme now defines real color tokens** (`color_primary`,
  `color_on_primary`, etc. in `values/colors.xml` and
  `values-night/colors.xml`) instead of the old commented-out
  placeholders. Anyone touching `themes.xml` again should keep editing
  the `colors.xml` values rather than hardcoding new colors directly in
  `themes.xml` — that's what let this fix apply to every toolbar at once
  instead of needing 15 separate edits.

## Standing risks (don't re-litigate these without new evidence)

- **Device Owner is a powerful, hard-to-undo state.** Upstream's own
  disclaimer says misconfiguration carries some risk of bricking a
  device, and that it cannot protect against factory reset or
  recovery/bootloader reflashing. Test on a spare/non-primary device
  before trusting it on a daily driver.
- **Knox-tripped Samsung devices cannot provision Device Owner** on stock
  firmware — this is a Samsung platform limitation upstream explicitly
  calls out, not a bug in this app.
- **ADB recovery depends on ADB already being trusted** ("Always allow"
  + no timeout) *before* you get locked out — if that wasn't set up in
  advance, the documented recovery commands won't help after the fact.
- **This is third-party code (MIT-licensed), not something written from
  scratch in these sessions.** Before making claims about what it does or
  doesn't do, read the actual `.java` source in
  `AppSourceCode/AppLock/app/src/main/java/com/jarm/applock/` rather than
  trusting the README description — same standard applied to any
  upstream dependency.
