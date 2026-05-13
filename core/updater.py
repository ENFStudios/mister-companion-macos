import platform
import re
import subprocess
import sys
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import requests

from core.app_info import APP_VERSION, GITHUB_OWNER, GITHUB_REPO


@dataclass
class UpdateInfo:
    update_available: bool
    current_version: str
    latest_version: str
    release_url: str
    release_name: str


def normalize_version(version: str) -> tuple[int, int, int]:
    if not version:
        return (0, 0, 0)

    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version)
    if not match:
        return (0, 0, 0)

    return tuple(int(part) for part in match.groups())


def check_for_update(timeout: int = 10) -> UpdateInfo:
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MiSTer-Companion-Updater",
        },
    )
    response.raise_for_status()

    data = response.json()

    latest_version = data.get("tag_name", "") or data.get("name", "")
    release_url = data.get("html_url", "")
    release_name = data.get("name", latest_version)

    current_tuple = normalize_version(APP_VERSION)
    latest_tuple = normalize_version(latest_version)

    return UpdateInfo(
        update_available=latest_tuple > current_tuple,
        current_version=APP_VERSION,
        latest_version=latest_version,
        release_url=release_url,
        release_name=release_name,
    )


def is_windows() -> bool:
    return platform.system().lower() == "windows"


def get_app_folder() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parent.parent


def get_mc_updater_path() -> Path:
    return get_app_folder() / "MC-Updater.exe"


def get_update_now_path() -> Path:
    return get_app_folder() / "updatenow.txt"


def mc_updater_available() -> bool:
    if not is_windows():
        return False

    return get_mc_updater_path().exists()


def launch_mc_updater() -> bool:
    if not is_windows():
        return False

    updater_path = get_mc_updater_path()

    if not updater_path.exists():
        return False

    update_now_path = get_update_now_path()
    update_now_path.write_text("", encoding="utf-8")

    subprocess.Popen(
        [str(updater_path)],
        cwd=str(updater_path.parent),
        shell=False,
    )

    return True


def open_release_page(url: str):
    if url:
        webbrowser.open(url)


def is_macos() -> bool:
    return platform.system().lower() == "darwin"


def get_current_app_path() -> Path | None:
    """Return the .app bundle path when running as a bundled app, else None."""
    if not getattr(sys, "frozen", False):
        return None
    # sys.executable: .../MiSTer Companion.app/Contents/MacOS/MiSTer Companion
    return Path(sys.executable).resolve().parent.parent.parent


def get_release_dmg_url(timeout: int = 10) -> tuple[str, str] | None:
    """Fetch latest release from GitHub and return (download_url, filename) for the DMG asset."""
    url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
    response = requests.get(
        url,
        timeout=timeout,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MiSTer-Companion-Updater",
        },
    )
    response.raise_for_status()
    for asset in response.json().get("assets", []):
        name = asset.get("name", "")
        if name.endswith(".dmg"):
            return asset["browser_download_url"], name
    return None


def download_dmg(url: str, dest_path: Path, progress_callback=None) -> None:
    """Stream-download a DMG to dest_path. progress_callback(bytes_done, total_bytes)."""
    response = requests.get(
        url,
        stream=True,
        timeout=60,
        headers={"User-Agent": "MiSTer-Companion-Updater"},
    )
    response.raise_for_status()
    total = int(response.headers.get("content-length", 0))
    done = 0
    with open(dest_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=256 * 1024):
            if chunk:
                f.write(chunk)
                done += len(chunk)
                if progress_callback:
                    progress_callback(done, total)


def launch_macos_update(dmg_path: Path, app_path: Path) -> bool:
    """Write a shell script that mounts the DMG, replaces the .app, and relaunches. Run detached."""
    if not is_macos():
        return False

    install_dir = app_path.parent
    app_name = app_path.name

    script = f"""#!/bin/bash
sleep 3
VOLUME=$(hdiutil attach "{dmg_path}" -nobrowse -noautoopen 2>/dev/null | grep /Volumes | awk -F'\\t' '{{print $NF}}')
if [ -z "$VOLUME" ]; then
    osascript -e 'display alert "Update Failed" message "Could not mount the update disk image."'
    exit 1
fi
rm -rf "{install_dir}/{app_name}"
cp -R "$VOLUME/{app_name}" "{install_dir}/"
hdiutil detach "$VOLUME" -quiet 2>/dev/null
open "{install_dir}/{app_name}"
rm -- "$0"
"""

    script_path = Path("/tmp/mistercompanion_update.sh")
    script_path.write_text(script)
    script_path.chmod(0o755)

    subprocess.Popen(
        ["/bin/bash", str(script_path)],
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return True