# applock-timed

A fork of [`jesusalbertodeveloper/AppLock`](https://github.com/jesusalbertodeveloper/AppLock)
(MIT-licensed) — a Device Owner API app locker for Android — extended into
a personal digital-wellbeing tool: hardcoded daily usage limits (5h for all
apps combined, 2h for apps auto-detected as social media) enforced by a
periodic background check instead of upstream's manual-lock-only design,
plus a "Today's Usage" ring screen and unlock counter modeled on Android's
own Digital Wellbeing.

The point of the fork: Android's built-in Digital Wellbeing can always be
turned off from Settings in two taps. This can't — it's provisioned as
Device Owner, so uninstalling or disabling it requires either the app's own
authenticated recovery path or ADB, not a Settings toggle.

**Read `STATUS.md` before touching any code.** It has the actual
build/test confidence per feature — most of what's below is upstream's
claims plus this fork's additions, not independently re-verified here.

## What's here

| File/dir | What it does |
|---|---|
| `AppSourceCode/AppLock/` | The Android Studio project — open this folder directly in Android Studio. |
| `AppLockSettings.java` | Core data model: original explicit lock/suspend/hide lists (upstream) + this fork's daily-limit counters and thresholds. |
| `UsageCheckReceiver.java` | This fork's addition — fires every 30 min via `AlarmManager`, reads today's per-app time from `UsageStatsManager`, suspends/unsuspends packages via `DevicePolicyManager`. No continuously-running service. |
| `AppCategoryHelper.java` | This fork's addition — auto-detects social media apps via `ApplicationInfo.category`, no hardcoded package list, no network call. |
| `TodayUsageActivity.java` / `UsageRingView.java` / `UsageStatsHelper.java` / `UnlockCounter.java` | This fork's addition — the Digital-Wellbeing-style ring screen. One-shot query on open, not a new background poll. |
| `AccSrvForBootstrapAndLock.java` | Upstream's accessibility service, still used for the original manual-lock feature and the four recovery `ContentObserver`s (emergency remove, safe mode toggle, password reset, self-healing re-enable). |
| `ReleaseApk/base.apk` | Prebuilt APK as shipped by upstream. Not rebuilt from this source tree yet — see `STATUS.md`. |
| `DISCLAIMER.md`, `PRIVACY_POLICY.md`, `LICENSE` | Upstream's, unmodified. MIT license — keep attribution intact per its terms if this is ever shared further. |

## Setup

This isn't a Play Store install — it's provisioned as Device Owner via ADB,
which only works on a device with **zero accounts** signed in.

```bash
# 1. Remove every account on the device first (Settings > Users & accounts)
#    - Device Owner provisioning refuses to run otherwise.

# 2. Build in Android Studio, or use the prebuilt ReleaseApk/base.apk
adb install -t base.apk

# 3. Provision as Device Owner
adb shell dpm set-device-owner com.jarm.applock/.DeviceAdminReceiverForDeviceOwner

# 4. This fork's addition - grant usage-stats access (not covered by
#    Device Owner provisioning alone, needs its own one-time grant)
adb shell appops set com.jarm.applock android:get_usage_stats allow

# 5. Set ADB as a trusted host: check "Always allow", disable ADB timeout
#    (Android 11+) - do this *before* you might need emergency recovery,
#    not after.

# 6. Open the app once manually after install - sideloaded apps stay in
#    Android's "stopped state" until first opened, which blocks the
#    BOOT_COMPLETED receiver from re-arming the 30-min check after a reboot.

# 7. Sign back into accounts now that Device Owner status is set - it
#    persists, it doesn't require staying account-free.
```

Full upstream installation notes, Samsung Knox limitations, and the
"important Android messages (not bugs)" section live in `DISCLAIMER.md`
and the git history of the original repo.

## Secrets — keep these out of version control

There's no `.gitignore` in the upstream repo as downloaded, so this fork
adds one. The one thing that actually matters here: **the signing
keystore/key used for the first install must be reused for every future
`adb install -r`** — losing it means every update requires the full
remove-and-reprovision-Device-Owner flow again, not a simple reinstall.
Back it up somewhere that isn't this repo.

## Recovery

If something goes wrong: `STATUS.md`'s "standing risks" section has the
full picture, and the upstream README's "Recovery Options (ADB Shell)"
block (still accurate, untouched by this fork) has the actual commands —
`settings put secure applock_emergency_remove 1` is the one that matters
most, it clears Device Owner status and this app's saved data in one step.

## More detail

- **`STATUS.md`** — current state, what's confirmed vs. untested, open
  decisions, standing risks. Read this first in any new session.
- **`CHANGELOG.md`** — the actual history of what was added/changed and
  why, in the order it happened.
