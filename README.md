# MiSTer Companion — macOS Port

> **Original author:** [Anime0t4ku](https://github.com/Anime0t4ku) · upstream project: [Anime0t4ku/mister-companion](https://github.com/Anime0t4ku/mister-companion)

A macOS build of MiSTer Companion, the cross-platform GUI utility for managing and maintaining a MiSTer FPGA system over SSH.

This port provides a native `.app` bundle and DMG installer for Apple Silicon Macs, with macOS-specific adjustments for user-data locations, terminology, and file-sharing integration.

---

## Download

| Platform | File | Link |
|---|---|---|
| macOS (Apple Silicon, arm64) | `MiSTer Companion-4.0.8.dmg` | **[Download v4.0.8](https://github.com/ENFStudios/mister-companion-macos/releases/latest)** |

Older versions remain on the [releases page](https://github.com/ENFStudios/mister-companion-macos/releases).

---

![Screenshot](assets/screenshot.png)

---

## System Requirements

- **Apple Silicon Mac** (M1 and newer)
- **macOS 11 Big Sur** or later.
- A MiSTer FPGA reachable over the local network via SSH.

---

## Installation (DMG)

The DMG is signed with an Apple Developer ID and notarized by Apple.

1. Download `MiSTer Companion-<version>.dmg` from the Releases page.
2. Open the DMG. A window opens showing the app icon and an `Applications` shortcut — drag **MiSTer Companion** onto `Applications`.
3. Eject the DMG.
4. Launch the app — on first run macOS shows the standard *"downloaded from the Internet"* dialog; click **Open** to confirm.

### Where user data is stored

After a DMG install, all user data is stored under:

    ~/Library/Application Support/MiSTer Companion/

The layout is:

    ~/Library/Application Support/MiSTer Companion/
    ├── config.json                  # saved devices, last selected device, preferences
    ├── MiSTerSettings/              # MiSTer.ini backups (created by the MiSTer Settings tab)
    │   └── <device-name>/
    │       └── MiSTer-<timestamp>.ini
    └── SaveManager/                 # everything related to the SaveManager tab
        ├── backups/                 # timestamped save backups per device
        │   └── <device-name>/
        │       └── <timestamp>/
        │           ├── saves/
        │           └── savestates/  # optional
        └── sync/                    # Local Sync Folder — merged newest saves across devices

Notes:
- `config.json` holds your saved SSH device profiles (IP, user, password) — back it up if you want to keep your device list portable.
- To reveal the folder in Finder, open Finder → **Go → Go to Folder…** and paste `~/Library/Application Support/MiSTer Companion/`.
- If you previously ran the app from source and accumulated data in `MiSTerSettings/` and `SaveManager/` next to the repo, it is migrated into this folder automatically on first launch of the bundled build.

---

## Running From Source

Requirements:

- Python 3.10 or newer (tested up to 3.13)
- PyQt6, paramiko, requests, websocket-client, psutil

All dependencies install as prebuilt arm64 wheels, so you normally **do not** need Xcode Command Line Tools. If pip falls back to building a package from source, run `xcode-select --install` once and retry.

Set up a virtualenv and install dependencies:

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

For a fully reproducible install (pinned versions matching the DMG build), use the lock file instead:

    pip install -r requirements-lock.txt

Run:

    python main.py

In source mode, user data is stored next to the repository (`./MiSTerSettings`, `./SaveManager`) instead of in `~/Library/Application Support/`, which is convenient during development.

---

## Building the `.app` and DMG

Additional requirements:

- `py2app` (`pip install py2app`)
- `create-dmg` (`brew install create-dmg`)

Build the bundle:

    source .venv/bin/activate
    rm -rf build dist
    python setup.py py2app

Build the DMG:

    ./build_dmg.sh

The DMG is written to `dist/MiSTer Companion-<version>.dmg`. The build script also cleans stale Launch Services entries left behind by previously mounted DMG volumes, so double-clicking `dist/MiSTer Companion.app` keeps working after multiple builds.

### Gatekeeper Override (no Apple Developer ID)

If you build the DMG yourself without a paid Apple Developer ID, the result is only ad-hoc signed and macOS Gatekeeper will block the first launch. On **macOS 15 Sequoia and newer**, the dialog only offers **Done** and **Move to Bin**; the Control-click → Open shortcut has also been removed by Apple. To approve the app:

1. Double-click **MiSTer Companion** once so macOS registers it as blocked, then dismiss the warning.
2. Open **System Settings → Privacy & Security**.
3. Scroll to the bottom — you should see *"MiSTer Companion" was blocked to protect your Mac.*
4. Click **Open Anyway** and authenticate with Touch ID or your password.
5. On the next launch, confirm **Open** in the final dialog.

From then on you can start it normally via double-click, Dock, or Spotlight. *On macOS 14 Sonoma and earlier* the Control-click → Open shortcut still works.

---

## Features

MiSTer Companion uses a tabbed interface to organize functionality.

### Flash SD
- Download the latest Mr. Fusion release directly from within the app
- Download the latest SuperStationONE SD Installer release directly from within the app
- Detect removable drives
- Flash SD cards without external tools
- Hardcoded block for macOS internal boot disks plus type-to-confirm safety

### Connection
- Connect to a MiSTer over SSH
- Save and manage multiple device profiles
- Scan the local network for MiSTer devices
- Automatic reconnect after a remote reboot
- Global UI scale selector (75 %–125 %) for Retina and external displays

### Device
- View SD card and USB storage usage
- Enable or disable Remote Access (SMB) on the MiSTer
- Open the MiSTer network share directly in Finder
- Reboot the MiSTer remotely

### MiSTer Settings
- Easy Mode for common MiSTer.ini tweaks
- Advanced Mode editor for the full MiSTer.ini
- Automatic backups before applying changes
- Restore from backups or defaults

### Scripts
- Install and configure common MiSTer scripts: `update_all`, `zaparoo`, `migrate_sd`, `cifs_mount` / `cifs_umount`, `auto_time`, `dav_browser`, `ftp_save_sync`, `static_wallpaper`
- Live SSH output while scripts run

### ZapScripts
- Browse the full Zaparoo media library and launch games directly from the app
- Trigger scripts via the Zaparoo Core API: `update_all`, `migrate_sd`, `Insert-Coin`
- Open the Bluetooth or OSD menu, cycle wallpaper, return to the MiSTer home screen
- Launch and Controls are disabled automatically if Zaparoo is not installed

### SaveManager
- Create timestamped backups of MiSTer saves (with optional savestates)
- Per-device retention
- Restore backups to any connected MiSTer
- Sync saves between multiple MiSTer systems
- Local Sync Folder for merging newest save files

### Wallpapers
- Install wallpaper packs via a JSON database system
- Multiple wallpaper sources supported (Ranny, PCN, OT4KU and more)
- Automatic update detection
- Built-in SSH output log

### Extras
- Install and manage the **Zaparoo Launcher/UI Beta** on MiSTer
- Install and update **RetroAchievement Cores** (switches automatically to a dedicated MiSTer_RA.ini)
- Install extras like **3S-ARM** and **Sonic Mania**
- All operations run live with SSH output and optional reboot prompts

### RetroAchievements Viewer
- View your recent achievement unlocks directly within the app
- Requires a RetroAchievements account

### Offline Mode
- Flash SD, MiSTer Settings, and script operations work without a live MiSTer — directly on a mounted SD card

---

## Tips

### How to switch INI files on MiSTer

1. Go to the MiSTer main screen
2. Press **Left arrow** on keyboard or gamepad
3. The Info/Config screen opens — at the bottom you'll see the INI selector
4. Available INIs are listed by the name after the underscore:
    - `MiSTer.ini` → shown as **"Main"**
    - `MiSTer_RA.ini` → shown as **"RA"**
    - `MiSTer_CRT.ini` → shown as **"CRT"**
    - etc.
5. Select the one you want → MiSTer reloads with that config

Useful after installing **RetroAchievement Cores** from the Extras tab — that adds a `MiSTer_RA.ini` you switch to via the steps above.

---

## Known Limitations

- **Apple Silicon only.** An Intel build is not provided; building one from source on an Intel Mac is untested.
- **No auto-update mechanism.** New versions must be downloaded and installed manually.

---

## Credits

Original author: **[Anime0t4ku](https://github.com/Anime0t4ku)** — see [UPSTREAM_README.md](UPSTREAM_README.md) for the upstream project description.

macOS port maintained by **[ENF Studios](https://github.com/ENFStudios)**.

This repository is a macOS-focused fork/port and is **not** affiliated with or endorsed by the upstream project.

---

## License

GNU General Public License v2.0 (GPL-2.0), matching the upstream project. See [LICENSE](LICENSE) for the full text.
