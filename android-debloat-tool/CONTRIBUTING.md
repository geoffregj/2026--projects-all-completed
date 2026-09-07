# Contributing

The whole tool is built around one data structure, `APP_DB`, near the
top of `android_debloat_tool.py`. Everything else (menus, uninstall
logic, protection checks) is generic and reads from it — so extending
the tool almost always means adding to this dictionary, not writing new
code.

## Adding a package

Find (or create) the right category, then add an entry:

```python
"Some Category Name": {
    "com.example.somepackage": {
        "risk": "safe",       # "safe" | "caution" | "protected"
        "note": "One sentence: what it is, and WHY it's tagged this way.",
    },
},
```

### Choosing a risk tag — be honest, not optimistic

- **`safe`** — you've confirmed (on a real device, not guessed) that
  removing it causes no functional loss for a typical user.
- **`caution`** — removable, but it might be load-bearing for someone
  (a feature they use, a dependency another app needs). The tool will
  force a typed `YES` confirmation before touching these. When in
  doubt, use this tag, not `safe`.
- **`protected`** — never remove, full stop. Reserved for things that
  can break calling, networking, security, or bootability. The tool
  hardcodes a refusal for these regardless of what a user selects.

### Write the note like a warning label, not a description

Bad: `"Ella voice assistant"` — doesn't tell anyone anything they
couldn't get from the package name.

Good: `"Voice assistant onboarding shell (real pkg is
aivoiceassistant)"` — tells you the actual gotcha: this package name is
a decoy for the real one.

If you found something the hard way (bricked a feature, broke calling,
caused a crash elsewhere), put that in the note. The whole point of
this database is to save the next person from repeating your mistake.

## Adding support for a new OEM (Xiaomi, Samsung, Oppo, etc.)

1. Get the real package name the same way this project did: open the
   app on the device, then run the tool's option `0` (or manually:
   `adb shell dumpsys window | grep mCurrentFocus`). Don't guess from
   the display name — see the Ella gotcha in the main README for why.
2. Test uninstall on your own device first (`pm uninstall --user 0
   <package>`) and confirm nothing broke before tagging it `safe`.
3. Add a new top-level category if it's OEM-specific (e.g. `"Xiaomi /
   MIUI bloat"`), so users on other OEMs aren't shown irrelevant
   entries.
4. Send a PR (or however this project's maintainer wants contributions
   — check the repo's current instructions) with what you found and
   how you verified it.

## Adding new tool features

The core functions (`uninstall`, `disable`, `restore`, `is_installed`,
`is_disabled`) are thin wrappers around `adb shell pm ...` commands —
if you're adding a new action, follow that same pattern: one function,
returns `(ok: bool, output: str)`, logs via `log()`.

Keep the tool dependency-free (stdlib only) unless there's a strong
reason not to — the whole point is that someone can clone this and run
it immediately with nothing but Python and adb.
