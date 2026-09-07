# Android Debloat Tool

A "WinUtil for Android" — remove, disable, or restore OEM/carrier
bloatware over `adb`, no root required. No GUI, no Android Studio
needed to *run* it — just Python 3 and `adb`.

Built from real findings on a Tecno Spark 40 (Transsion / HiOS), but the
engine works on any adb-connected Android phone. Contributions welcome —
see [CONTRIBUTING.md](CONTRIBUTING.md) to add packages for other
OEMs (Xiaomi/MIUI, Samsung/One UI, Oppo/ColorOS, etc).

## Quick start

**Terminal version:**
```bash
python3 android_debloat_tool.py
```

**Browser version (WinUtil-style checkbox UI):**
```bash
python3 webui.py
```
Opens `http://127.0.0.1:8765` in your browser automatically. Same
engine, same `APP_DB`, zero extra dependencies (stdlib `http.server`,
no Flask/pip install needed) — it just gives you a visual list of
*every* installed app on the phone (not only the curated ones), with
an **Open on phone** button per app so you can launch it and confirm
what it actually is before uninstalling/disabling anything. Apps not
in the curated database are auto-checked against known core
Android/Google package patterns and locked as protected if they match;
everything else is flagged `NOT CURATED` and requires a typed `YES`
confirmation before any destructive action, same as `caution`-tier
curated apps.

The web UI also has:
- **"What's on screen now?"** — reads the phone's actual foreground
  app (same trick as the CLI's option `0`) and jumps to/highlights
  that app in the list, if it's loaded. Useful when an icon's on-screen
  name doesn't match what you'd expect its package to be.
- **Details** (per app) — version, size, install/update dates, target
  SDK, and system-vs-user, pulled straight from `dumpsys package`. Note:
  this doesn't show the app's human-readable name/icon — that needs
  APK resource parsing (`aapt`), which isn't a dependency here. Package
  ID stays the primary identifier.
- **Export scan report** — writes an anonymized `scan_report.json`
  (package/action/result/Android version/device brand — no serial, no
  IMEI, no account info) next to the log file. This is manual and
  local only; nothing is ever sent anywhere automatically. If you want
  to contribute results for other users, share the file yourself (e.g.
  paste it into a GitHub issue).

Either way: no `pip install`, no dependencies beyond `adb` — everything
used is Python's standard library. If `adb` isn't installed or your
phone isn't authorized, the tool detects that and walks you through
fixing it step by step (it knows your OS and gives exact commands).

## What it does

- Lists known bloatware/telemetry/ad-injection apps by category
- Tags each one `SAFE`, `CAUTION`, or `PROTECTED` based on real testing
- Lets you uninstall (`pm uninstall --user 0`), disable
  (`pm disable-user`), or restore (`cmd package install-existing`) —
  all reversible, no root, no data wipe
- Refuses to touch anything tagged `PROTECTED` (core telephony, Play
  Services, your launcher) even if you try
- Logs every action with a timestamp to `debloat_log.txt`
- Has a built-in "what app is this?" tool (option `0`) that reads the
  foreground app's real package name — useful for identifying apps
  whose on-screen name doesn't match their package (see Ella below)

## Repo layout

```
android-debloat-tool/
├── android_debloat_tool.py   # terminal tool — single file, stdlib only
├── webui.py                  # browser UI — imports APP_DB + adb helpers
│                              # from android_debloat_tool.py, same log file
├── README.md                 # this file
├── SETUP.md                  # adb/USB debugging setup for end users
├── CONTRIBUTING.md           # how to add packages / new OEM support
├── STATUS.md                 # current project state — read this first
│                              # if you're an AI picking up this project
├── CHANGELOG.md               # append-only debugging/feature history
├── debloat_log.txt           # created on first run, gitignored, shared
│                              # by both the terminal tool and the web UI
└── scan_report.json          # created by "Export scan report" in the
                               # web UI, gitignored, local/anonymized only
```

## Known gotchas (found the hard way, documented so nobody repeats them)

- **`com.transsion.ella` is a decoy.** The real "Ella" voice assistant
  package is `com.transsion.aivoiceassistant`. Uninstalling `.ella`
  alone does nothing visible — the icon stays and the app still opens.
  Always confirm with option `0` (open the app, then check its real
  package) before assuming a name maps to the package you expect.
- **`com.sh.smart.caller` can BE the phone dialer**, not just a
  caller-ID add-on, on some HiOS builds. Confirmed to break outgoing
  calls on this device. That's why it's tagged `CAUTION` and not
  `SAFE` in the database.
- **Removing an ad-driven app store (e.g. `com.transsnet.store` / Palm
  Store) can break in-app "Install" buttons** in apps like MovieBox, if
  their ad SDK hardcodes an explicit intent to that package instead of
  a generic `market://` intent. Expect silent failures or a crash in
  the calling app, not a graceful fallback to Play Store. This is how
  Android intent resolution works, not a tool bug.
- **Launcher icons can go stale after uninstall.** This is cosmetic —
  it means the launcher's icon cache hasn't refreshed, not that the
  removal failed. Dragging the dead icon to "Remove" is safer than
  `pm clear`-ing the launcher, which resets your whole home screen
  layout.

## Safety model

Every removal goes through `pm uninstall --user 0`, which unlinks the
app from your user profile without deleting the underlying system APK.
Nothing here requires root, and everything is reversible with the
`restore` action — as long as you haven't since done a factory reset
or system update that actually purges it.

`PROTECTED` packages (telecom, telephony provider, Play Services, your
launcher, etc.) are hardcoded to be refused by the tool itself, not
just flagged — see `APP_DB` in the script.

## License

MIT — see [LICENSE](LICENSE). Do whatever you want with it, just don't
blame me if you remove something you shouldn't have. Read the risk tag.
