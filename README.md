# Excalibur — Monitor Manager

A single-file Windows desktop utility that puts a **radial menu on your mouse's X2 (back) button** to manage a multi-monitor setup instantly: move the active window to another monitor, or switch your whole display layout with saved profiles.

![tech](https://img.shields.io/badge/Python-3.10+-3776AB) ![tech](https://img.shields.io/badge/PySide6-Qt-41CD52) ![tech](https://img.shields.io/badge/Windows-CCD_API-0078D6)

## What it does

Press the mouse's **X2 button** and a radial menu appears with three actions:

1. **Move Window** — send the currently focused window to another monitor.
2. **Monitor Profiles** — apply a saved profile that turns specific screens on/off (e.g. a "gaming" profile that leaves only your main display active), each bound to its own global hotkey.
3. **Configuration** — create, edit, or delete those profiles from a small GUI.

Profiles are stored as JSON next to the script, so they're easy to read and share.

## Why it's technically interesting

The core is real low-level Windows systems programming, not a wrapper around a helper app:

- **Display switching via the Windows CCD API** (Connecting and Configuring Displays), called directly through `ctypes`. The script declares the full set of Win32 structures itself — `DISPLAYCONFIG_PATH_INFO`, `DISPLAYCONFIG_TARGET_MODE`, `LUID`, `DISPLAYCONFIG_VIDEO_SIGNAL_INFO`, and friends — and uses `QueryDisplayConfig` / `SetDisplayConfig` to change the monitor topology programmatically.
- **Custom radial menu** hand-drawn with Qt's `QPainter` (`PySide6`), on a frameless, translucent, always-on-top overlay.
- **Global mouse & keyboard hooks** via `pynput`, so the menu and profile hotkeys work from anywhere, over any application.
- **Live window control** with `pygetwindow` + `screeninfo` to find monitors and reposition windows across them.

## Requirements

Windows, Python 3.10+.

```bash
pip install PySide6 pynput pygetwindow screeninfo
```

## Run

```bash
python Excalibur_Monitor.py
```

The X2 mouse button now opens the radial menu. Profiles live in `excalibur_perfis.json` in the same folder (a sample "gaming" profile is included).

## Files

```
Excalibur_Monitor.py    single-file app (GUI + CCD display manager + hooks)
excalibur_perfis.json   saved monitor profiles (sample included)
```

---

Built by **Winicius Guimarães** · [github.com/winiciusguimaraes-betaTester](https://github.com/winiciusguimaraes-betaTester)
