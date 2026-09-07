#!/usr/bin/env python3
"""
Android Debloat Tool
A "WinUtil for Android" — remove/disable/restore OEM bloatware over adb,
without root. Built around real findings from a Tecno/Transsion (HiOS) device,
but the core engine works on any adb-connected Android phone.

Requires: adb installed and on PATH, USB debugging enabled on the phone,
device authorized (run `adb devices` once and accept the prompt on-phone).

Usage:
    python3 android_debloat_tool.py
"""

import subprocess
import sys
import shutil
import datetime
import json
import os
import platform
import re

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "debloat_log.txt")

# ---------------------------------------------------------------------------
# Curated package database
# ---------------------------------------------------------------------------
# risk levels:
#   "safe"      - confirmed removable, no functional loss for most users
#   "caution"   - removable but may break a feature you actually use
#   "protected" - never touch; can break calls/network/radio/security
#
# category groups apps for menu display.

APP_DB = {
    "AI / Assistant bloat": {
        "com.transsion.ella": {"risk": "safe", "note": "Voice assistant onboarding shell (real pkg is aivoiceassistant)"},
        "com.transsion.aivoiceassistant": {"risk": "safe", "note": "Ella voice assistant — actual app package"},
        "com.transsion.aisupportercore": {"risk": "safe", "note": "Backend companion to the voice assistant"},
        "com.transsion.aiwriting": {"risk": "safe", "note": "AI writing assistant"},
        "com.transsion.aiassistantlifestyle": {"risk": "safe", "note": "'Life' AI lifestyle app"},
        "com.transsion.kolun.aiservice": {"risk": "caution", "note": "Core AI service — some phone features may depend on it"},
        "com.transsion.aicore.main": {"risk": "caution", "note": "AI core model manager"},
        "com.transsion.aicore.llm": {"risk": "caution", "note": "On-device LLM component"},
        "com.transsion.aicore.ocr": {"risk": "caution", "note": "OCR engine — may be used by camera/gallery text scan"},
        "com.transsion.aicore.cv": {"risk": "caution", "note": "Computer vision core"},
    },
    "Ad-driven app stores / installers": {
        "com.transsnet.store": {"risk": "safe", "note": "Palm Store — pushes ads/installs from apps like MovieBox. Removing can break in-app 'Install' buttons that hardcode this package."},
        "tech.palm.id": {"risk": "caution", "note": "Palm ID — account/auth service tied to Palm Store"},
    },
    "Fake VPN / proxy bloat": {
        "secure.unblock.unlimited.proxy.snap.hotspot.shield": {"risk": "safe", "note": "Bundled free VPN, generally untrustworthy, redundant if you use a real VPN"},
    },
    "Caller-ID / contact-harvesting": {
        "com.sh.smart.caller": {"risk": "caution", "note": "WARNING: on some HiOS builds this IS the phone dialer app, not just caller-ID. Confirmed to break calling on this device. Verify with 'Check what handles calls' before removing."},
    },
    "'Booster' / cleaner nagware": {
        "com.transsion.phonemaster": {"risk": "safe", "note": "Fake cleaner/booster, mostly ads and bogus junk-file warnings"},
        "com.transsion.batterylab": {"risk": "safe", "note": "Battery 'optimizer' nagware"},
        "com.transsion.spacesaversdk": {"risk": "safe", "note": "Storage 'optimizer' nagware"},
    },
    "Telemetry / tracking": {
        "com.transsion.uxdetector": {"risk": "safe", "note": "Usage/UX telemetry tracker"},
        "com.transsion.statisticalsales": {"risk": "safe", "note": "Sales/usage statistics reporting"},
        "com.idea.questionnaire": {"risk": "safe", "note": "Carrier survey/telemetry tool"},
    },
    "Redundant OEM duplicates": {
        "com.gallery20": {"risk": "caution", "note": "AI Gallery — redundant only if you use Google Photos"},
        "com.transsion.chromecustomization": {"risk": "safe", "note": "Chrome tweaker — pointless if you use another browser"},
        "com.transsion.calculator": {"risk": "caution", "note": "OEM calculator — redundant if you use another"},
        "com.transsion.deskclock": {"risk": "caution", "note": "OEM clock app — redundant if you use another"},
        "com.transsion.notebook": {"risk": "caution", "note": "OEM notepad — redundant if you use another"},
        "com.transsion.fmradio": {"risk": "caution", "note": "FM radio app, only useful if your phone has a radio chip you use"},
    },
    "Misc / app-locker / unclear": {
        "com.xui.xhide": {"risk": "safe", "note": "App-hiding/locker utility, not something most people asked for"},
        "com.hoffnung": {"risk": "caution", "note": "Unclear generic-named app — inspect before removing"},
        "com.splendapps.checkmate": {"risk": "caution", "note": "Unclear third-party app — inspect before removing"},
    },
    "PROTECTED — never touch": {
        "com.android.server.telecom": {"risk": "protected", "note": "Core call-handling framework"},
        "com.android.providers.telephony": {"risk": "protected", "note": "SMS/MMS/cellular data provider"},
        "com.android.phone": {"risk": "protected", "note": "Telephony service"},
        "com.mediatek.engineermode": {"risk": "protected", "note": "Radio/modem engineering mode — can brick cellular"},
        "com.google.android.gms": {"risk": "protected", "note": "Google Play Services — breaks most apps if removed"},
        "com.google.android.gsf": {"risk": "protected", "note": "Google Services Framework"},
        "com.android.vending": {"risk": "protected", "note": "Google Play Store"},
        "com.transsion.hilauncher": {"risk": "protected", "note": "Your home screen launcher — clearing its cache resets layout, don't uninstall"},
    },
}

# ---------------------------------------------------------------------------
# adb helpers
# ---------------------------------------------------------------------------

def guided_adb_install():
    system = platform.system()
    print("\n'adb' isn't installed or isn't on your PATH.")
    print("You do NOT need Android Studio for this — adb ships on its own")
    print("as 'platform-tools', a tiny download with no IDE attached.\n")

    if system == "Linux":
        print("Detected: Linux")
        if shutil.which("apt"):
            print("  Run:   sudo apt update && sudo apt install android-tools-adb")
        elif shutil.which("dnf"):
            print("  Run:   sudo dnf install android-tools")
        elif shutil.which("pacman"):
            print("  Run:   sudo pacman -S android-tools")
        else:
            print("  No known package manager detected — download platform-tools directly:")
            print("  https://developer.android.com/tools/releases/platform-tools")
            print("  Unzip it, then either move 'adb' to /usr/local/bin or add the")
            print("  unzipped folder to your PATH.")
    elif system == "Darwin":
        print("Detected: macOS")
        print("  Easiest: install Homebrew (https://brew.sh) if you don't have it, then:")
        print("  Run:   brew install android-platform-tools")
    elif system == "Windows":
        print("Detected: Windows")
        print("  Download platform-tools (zip, no installer, no Android Studio needed):")
        print("  https://developer.android.com/tools/releases/platform-tools")
        print("  Unzip it somewhere permanent (e.g. C:\\platform-tools), then add that")
        print("  folder to your PATH: Settings > System > About > Advanced system")
        print("  settings > Environment Variables > Path > New > paste the folder.")
    else:
        print(f"Unrecognized OS ({system}). Grab platform-tools manually:")
        print("  https://developer.android.com/tools/releases/platform-tools")

    print("\nAfter installing, close and reopen your terminal, then run this script again.")
    sys.exit(1)


def guided_phone_setup():
    print("\nNo authorized device found. On your PHONE, do this once:")
    print("  1. Settings -> About phone -> tap 'Build number' 7 times")
    print("     (this unlocks Developer options — you'll see a toast counting down)")
    print("  2. Settings -> Developer options -> turn on 'USB debugging'")
    print("  3. Plug the phone into this computer with a USB cable")
    print("  4. A popup will appear ON THE PHONE screen asking")
    print("     'Allow USB debugging?' — check 'Always allow from this computer'")
    print("     and tap Allow. (If you don't see it, unlock the phone screen —")
    print("     it sometimes hides behind the lock screen.)")
    print("\nThen run this script again.")
    sys.exit(1)


def check_adb():
    if shutil.which("adb") is None:
        guided_adb_install()

    try:
        result = subprocess.run(["adb", "devices"], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        print("adb didn't respond. Try unplugging and replugging the phone, then rerun.")
        sys.exit(1)

    lines = [l for l in result.stdout.strip().splitlines()[1:] if l.strip()]
    if not lines:
        guided_phone_setup()

    authorized = [l for l in lines if l.strip().endswith("device")]
    unauthorized = [l for l in lines if "unauthorized" in l]

    if unauthorized and not authorized:
        print("\nDevice detected but shows as UNAUTHORIZED.")
        print("Look at your PHONE screen right now — there should be an")
        print("'Allow USB debugging?' popup waiting for you to tap Allow.")
        print("If you don't see it: unlock the phone, unplug and replug the cable.")
        sys.exit(1)

    if not authorized:
        print("Device connected but in an unexpected state:")
        for l in lines:
            print(f"  {l}")
        print("Try unplugging and replugging the USB cable.")
        sys.exit(1)

    print(f"Device connected: {authorized[0].split()[0]}")


def adb_shell(*args):
    result = subprocess.run(["adb", "shell", *args], capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()


def is_installed(pkg):
    out, _ = adb_shell("pm", "list", "packages", "--user", "0")
    return f"package:{pkg}" in out


def is_disabled(pkg):
    out, _ = adb_shell("pm", "list", "packages", "-d")
    return f"package:{pkg}" in out


SYSTEM_PROTECTED_MSG = (
    "This is a system-protected package -- Android itself is refusing the "
    "change (not a bug in this tool). It can't be uninstalled or disabled "
    "without root. Safe to leave alone; leaving it installed doesn't mean "
    "it's actively doing anything visible."
)


def uninstall(pkg):
    out, err = adb_shell("pm", "uninstall", "--user", "0", pkg)
    ok = "Success" in out
    combined = out + err
    if not ok and "DELETE_FAILED_INTERNAL_ERROR" in combined:
        log(f"UNINSTALL {pkg}: FAILED - system-protected (DELETE_FAILED_INTERNAL_ERROR)")
        return False, SYSTEM_PROTECTED_MSG
    log(f"UNINSTALL {pkg}: {'OK' if ok else 'FAILED - ' + combined}")
    return ok, out or err


def disable(pkg):
    out, err = adb_shell("pm", "disable-user", "--user", "0", pkg)
    ok = "new state" in out
    combined = out + err
    if not ok and "protected package" in combined.lower():
        log(f"DISABLE {pkg}: FAILED - system-protected (SecurityException)")
        return False, SYSTEM_PROTECTED_MSG
    log(f"DISABLE {pkg}: {'OK' if ok else 'FAILED - ' + combined}")
    return ok, out or err


def restore(pkg):
    out, err = adb_shell("cmd", "package", "install-existing", pkg)
    ok = "installed for user" in out
    log(f"RESTORE {pkg}: {'OK' if ok else 'FAILED - ' + out + err}")
    return ok, out or err


def log(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a") as f:
        f.write(f"[{ts}] {msg}\n")


def app_details(pkg):
    """Best-effort per-app detail lookup, in the spirit of tapping an app
    in Settings > Apps. Pure adb/dumpsys, no root, no aapt required.

    Note on app names/icons: Android doesn't expose the human-readable
    label or icon over adb without parsing the APK's resources.arsc
    (that's what aapt/aapt2 does). Without pulling every APK and parsing
    it -- slow, and a real dependency -- this shows package id, version,
    install/update dates, size, and system-vs-user, which covers most of
    what people actually check an app for."""
    out, _ = adb_shell("dumpsys", "package", pkg)
    info = {"pkg": pkg}

    def grab(pattern, key, cast=str):
        m = re.search(pattern, out)
        if m:
            try:
                info[key] = cast(m.group(1))
            except ValueError:
                info[key] = m.group(1)

    grab(r"versionName=(\S+)", "version")
    grab(r"versionCode=(\d+)", "version_code", int)
    grab(r"firstInstallTime=([^\n]+)", "first_install")
    grab(r"lastUpdateTime=([^\n]+)", "last_update")
    grab(r"codePath=(\S+)", "code_path")
    grab(r"targetSdk=(\d+)", "target_sdk", int)

    flags_match = re.search(r"pkgFlags=\[([^\]]*)\]", out)
    flags = flags_match.group(1) if flags_match else ""
    info["system_app"] = "SYSTEM" in flags

    if info.get("code_path"):
        size_out, _ = adb_shell("du", "-sh", info["code_path"])
        parts = size_out.split()
        if parts:
            info["size"] = parts[0]

    return info


def export_session_report(log_lines):
    """Build an anonymized, shareable record of this session's outcomes.
    No device identifiers (no serial, no IMEI, no account info) -- just
    package/category/risk/action/result, so results can be compared across
    different phones without exposing anything about the specific device
    or its owner. Entirely local: this never sends anything anywhere on
    its own. Sharing it (e.g. pasting into a GitHub issue) is a manual,
    separate step the user chooses to take."""
    pattern = re.compile(
        r"^(OPEN|UNINSTALL|DISABLE|RESTORE) (\S+): (OK|FAILED)(?: - (.*))?$"
    )
    results = []
    for line in log_lines:
        # strip the "[timestamp] " prefix written by log()
        msg = line.split("] ", 1)[-1].strip()
        m = pattern.match(msg)
        if not m:
            continue
        action, pkg, outcome, detail = m.groups()
        known_meta = None
        known_cat = None
        for cat_name, apps in APP_DB.items():
            if pkg in apps:
                known_meta = apps[pkg]
                known_cat = cat_name
                break
        results.append({
            "pkg": pkg,
            "action": action.lower(),
            "result": outcome.lower(),
            "detail": (detail or "")[:200],
            "category": known_cat,
            "curated_risk": known_meta["risk"] if known_meta else None,
        })

    report = {
        "tool_version": "android-debloat-tool",
        "android_version": None,
        "device_brand": None,
        "results": results,
    }
    out, _ = adb_shell("getprop", "ro.build.version.release")
    if out.strip():
        report["android_version"] = out.strip()
    out, _ = adb_shell("getprop", "ro.product.brand")
    if out.strip():
        report["device_brand"] = out.strip()  # e.g. "Tecno" -- brand only, not model/serial

    return report


def current_focus():
    """Print the package name of whatever's currently on screen — helps
    identify unknown app icons (open the app on the phone first)."""
    out, _ = adb_shell("dumpsys", "window")
    for line in out.splitlines():
        if "mCurrentFocus" in line:
            print(line.strip())
            return
    print("Could not read current focus — is the screen on?")


def foreground_app():
    """Same idea as current_focus() but returns structured data instead of
    printing, so the web UI can show it and cross-reference it against the
    app list. Returns (pkg_or_None, raw_line)."""
    out, _ = adb_shell("dumpsys", "window")
    raw = None
    for line in out.splitlines():
        if "mCurrentFocus" in line or "mFocusedApp" in line:
            raw = line.strip()
            break
    if not raw:
        return None, "Could not read current focus -- is the screen on and unlocked?"
    # Typical line: mCurrentFocus=Window{...u0 com.pkg.name/com.pkg.name.MainActivity ...}
    match = re.search(r"\su0\s([\w.]+)/", raw)
    if not match:
        # Fallback: any dotted identifier that looks like a package
        match = re.search(r"([a-zA-Z][\w]*(?:\.[a-zA-Z][\w]*){2,})/", raw)
    pkg = match.group(1) if match else None
    return pkg, raw


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------

def risk_tag(risk):
    return {"safe": "[SAFE]", "caution": "[CAUTION]", "protected": "[PROTECTED]"}[risk]


def status_tag(pkg):
    if is_installed(pkg):
        return "installed"
    if is_disabled(pkg):
        return "disabled"
    return "removed"


def print_category(name, apps):
    print(f"\n=== {name} ===")
    for i, (pkg, meta) in enumerate(apps.items(), 1):
        st = status_tag(pkg)
        print(f" {i:2d}. {risk_tag(meta['risk']):12s} {pkg:45s} ({st})")
        print(f"      {meta['note']}")


def category_menu():
    cats = list(APP_DB.keys())
    while True:
        print("\n--- Android Debloat Tool ---")
        for i, c in enumerate(cats, 1):
            print(f" {i}. {c}")
        print(" 0. Identify current foreground app (open it on phone first)")
        print(" q. Quit")
        choice = input("Pick a category: ").strip().lower()
        if choice == "q":
            break
        if choice == "0":
            current_focus()
            continue
        try:
            idx = int(choice) - 1
            cat_name = cats[idx]
        except (ValueError, IndexError):
            print("Invalid choice.")
            continue
        app_menu(cat_name, APP_DB[cat_name])


def app_menu(cat_name, apps):
    while True:
        print_category(cat_name, apps)
        print(" u <n>  - uninstall app n")
        print(" d <n>  - disable app n")
        print(" r <n>  - restore app n")
        print(" b      - back")
        cmd = input("Command: ").strip().lower()
        if cmd == "b":
            return
        parts = cmd.split()
        if len(parts) != 2 or parts[0] not in ("u", "d", "r"):
            print("Format: u 3 / d 3 / r 3")
            continue
        try:
            idx = int(parts[1]) - 1
            pkg = list(apps.keys())[idx]
            meta = apps[pkg]
        except (ValueError, IndexError):
            print("Invalid app number.")
            continue

        if meta["risk"] == "protected":
            print("This app is PROTECTED. Refusing to touch it.")
            continue

        if parts[0] == "u":
            if meta["risk"] == "caution":
                confirm = input(f"CAUTION: {meta['note']}\nType YES to uninstall {pkg}: ")
                if confirm != "YES":
                    print("Cancelled.")
                    continue
            ok, out = uninstall(pkg)
        elif parts[0] == "d":
            ok, out = disable(pkg)
        else:
            ok, out = restore(pkg)

        print(("OK: " if ok else "FAILED: ") + out)


if __name__ == "__main__":
    check_adb()
    category_menu()
    print(f"\nSession log saved to {LOG_PATH}")
