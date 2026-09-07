# Setup Guide (for people who've never used adb before)

You do **not** need Android Studio to use this tool. Android Studio is a
full IDE (multi-GB) for *building* Android apps. All this tool needs is
`adb`, a tiny command-line utility that ships on its own as
"platform-tools."

If you already have `adb` working, skip to [Enable USB debugging on
your phone](#2-enable-usb-debugging-on-your-phone).

## 1. Install adb

### Linux
```bash
# Debian/Ubuntu/Mint
sudo apt update && sudo apt install android-tools-adb

# Fedora
sudo dnf install android-tools

# Arch
sudo pacman -S android-tools
```
No package manager, or none of the above worked? Download platform-tools
directly: https://developer.android.com/tools/releases/platform-tools
Unzip it, then either move the `adb` binary to `/usr/local/bin` or add
the unzipped folder to your `PATH`.

### macOS
Install [Homebrew](https://brew.sh) if you don't have it, then:
```bash
brew install android-platform-tools
```

### Windows
Download platform-tools (a zip, no installer):
https://developer.android.com/tools/releases/platform-tools

Unzip it somewhere permanent, e.g. `C:\platform-tools`, then add that
folder to your PATH:
`Settings → System → About → Advanced system settings → Environment
Variables → Path → New → paste the folder path`

### Verify it worked
Close and reopen your terminal, then:
```bash
adb --version
```
You should see something like `Android Debug Bridge version 1.0.41`.
adb has no icon and no GUI — it only runs from a terminal, which is
expected, not a bug.

## 2. Enable USB debugging on your phone

1. **Settings → About phone** → tap **Build number** 7 times. You'll
   see a toast counting down ("You are now N steps from being a
   developer") until it says "You are now a developer!"
2. Go back to **Settings → Developer options** (a new menu that just
   appeared) → turn on **USB debugging**.
3. Plug your phone into the computer with a USB cable.
4. A popup appears **on the phone screen** (not the computer):
   *"Allow USB debugging?"* — check **"Always allow from this
   computer"** and tap **Allow**. If you don't see it, unlock your
   phone's screen — it sometimes hides behind the lock screen — or
   unplug and replug the cable.

## 3. Confirm the connection

```bash
adb devices
```
You should see your device listed with `device` next to it (not
`unauthorized` — if you see that, look at your phone screen for the
popup from step 2.4).

## 4. Run the tool

```bash
python3 android_debloat_tool.py
```
(Requires Python 3, which is preinstalled on Linux/macOS. On Windows,
install from https://python.org if you don't have it — check "Add
python.exe to PATH" during install.)

That's the whole setup. The tool itself will also detect and explain
any of the above if something's still missing when you run it.
