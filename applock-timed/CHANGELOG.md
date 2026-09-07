# Changelog

Append new entries at the bottom of the relevant section (or start a new
`## Debugging history — <feature>` section for something not covered yet).
Don't edit or delete past entries — this file is a record of what was
already tried and why it did or didn't work, so nobody re-discovers the
same dead end twice. See `STATUS.md` for the current state; this file is
the history that got you there.

## Packaging

**1. Self-documenting protocol added (`STATUS.md` + this file), ported
from `ig_manager`.** This project was downloaded from upstream
(`github.com/jesusalbertodeveloper/AppLock`) as a finished, working repo
rather than built up over sessions, so there was no existing debugging
history to preserve here. Going forward, treat this the same as
`ig_manager`: paste `STATUS.md` at the start of a new session instead of
re-uploading the zip, and log real changes/fixes here as they happen —
not before they happen.

**2. `README.md` rewritten fork-specific; `.gitignore` added.** The
`README.md` this repo shipped with was still upstream's original
marketing copy (feature bullet list, generic install steps) — replaced
with a `what's-here` table distinguishing upstream files from this fork's
additions, the actual ADB setup sequence including the `appops` grant
`UsageCheckReceiver` needs (not mentioned anywhere upstream, since
upstream doesn't have that feature), and a secrets note about the signing
key. No `.gitignore` existed anywhere in the downloaded zip; added one
covering build output, `local.properties`, and — the one that actually
matters per `STATUS.md`'s standing risks — the signing keystore/key,
since losing it turns every future update into a full
remove-and-reprovision-Device-Owner cycle instead of a normal
`adb install -r`.

## New features

**1. "Today's Usage" ring screen + unlock counter, modeled on Android's
Digital Wellbeing.** Added `UsageStatsHelper` (one-shot query against
`UsageStatsManager`, top-7-apps-plus-"Other" bucketing — same exemption
list `UsageCheckReceiver` already uses, just not sharing code with it so
the already-working 30-minute check couldn't be affected by this change),
`UsageRingView` (custom `Canvas`-drawn multi-segment ring, no animation
loop), and `TodayUsageActivity` (ring + total time + unlock count +
per-app legend, built with plain `LinearLayout` rows to match the app's
existing style rather than introducing a `RecyclerView` pattern for a
short list). Unlock counting is `UnlockCounter`, a `SharedPreferences`
counter incremented by `ACTION_USER_PRESENT`, registered from
`AccSrvForBootstrapAndLock.onServiceConnected()` (already always-running,
so this adds no new always-on component). Entry point is a new "Today's
Usage" button on the main settings screen, next to "Other Settings".
Deliberately left out: notification count (would need a
`NotificationListenerService` — see `STATUS.md` open decisions for why).
**Not yet built** — no network access to Google's Maven repo in this
sandbox, so this has been reviewed by hand only, not compiled. Build in
Android Studio and confirm before trusting the "confirmed" column in
`STATUS.md`.

## New features

**2. Real brand color + working dark-theme tokens (teal/blue), replacing
the untouched Material3 purple placeholder.** `values/themes.xml` and
`values-night/themes.xml` previously both extended
`Theme.Material3.DayNight.NoActionBar` with every color override
commented out — meaning dark mode used the exact same colorPrimary as
light mode, which is the opposite of what Material's dark-theme guidance
recommends (dark surfaces should get a lighter/desaturated primary, not
the same saturated one). Added `color_primary`/`color_on_primary`/etc. to
`values/colors.xml` (teal/blue, chosen to complement rather than clash
with the red padlock launcher icon) and a `values-night/colors.xml` with
the same names at lighter, less-saturated tones, then wired both into the
respective `themes.xml`. Because every toolbar already referenced
`?attr/colorPrimary` rather than a literal color, this fixes all of them
at once with no per-screen edits needed — except one real bug it
surfaced: 8 screens (`authentication_activity`, `password_setup_activity`,
`setup_complete`, `usb_debugging_authentication_activity`,
`acc_serv_disable_error_screen`, `disclaimer_rejected_screen`,
`privacy_policy_rejected_screen`, `other_settings`) hardcoded their
toolbar title text to near-white (`#FFFFFF`/`#E9E4E4`/`@color/white`).
That was fine against the old dark-teal-only primary, but would have been
nearly unreadable against the new lighter dark-mode primary — fixed all 8
to use `?attr/colorOnPrimary` instead, which is defined per-mode
alongside `colorPrimary` and stays correct automatically. Also reverted
`TodayUsageActivity`'s toolbar from the `colorSurface` workaround back to
`?attr/colorPrimary` now that colorPrimary itself is properly toned per
mode, so it's consistent with every other screen.
**Not yet built/run** — same network limitation as feature 1 above.

## Debugging history

**1. `java.time.LocalDate` would crash on API 24/25 devices — found during
code review, not reported by a run.** `AppLockSettings.rollOverIfNewDay()`
(this fork's daily-limit reset) and `UnlockCounter` (the other thread's
unlock counter) both called `LocalDate.now()`. `minSdk` is 24, and
`build.gradle`'s `compileOptions` has no `coreLibraryDesugaringEnabled` —
`java.time` was added to the Android platform in API 26, so without
desugaring, the first call to either method on a real API 24/25 device
throws `NoClassDefFoundError`. Neither had actually been run yet (both
were mid-development, per `STATUS.md`), so this was never observed as a
crash — caught by code review first. **Fixed:** both replaced with a
`Calendar`-based day id (`YEAR*1000 + DAY_OF_YEAR`), matching the
`Calendar` usage this fork already established elsewhere
(`UsageCheckReceiver`, `UsageStatsHelper`) instead of adding
`desugar_jdk_libs` as a new dependency for one class. Still not built —
same sandbox network limitation noted throughout this file — so "fixed"
here means "the crash-causing API call no longer exists in the source,"
not "confirmed working on-device."
