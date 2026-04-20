import shutil
import sys
from pathlib import Path


APP_NAME = "MiSTer Companion"

LEGACY_DATA_DIRS = ("MiSTerSettings", "SaveManager")


def _is_frozen_darwin() -> bool:
    return getattr(sys, "frozen", False) and sys.platform == "darwin"


def _source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    if _is_frozen_darwin():
        return Path(sys.executable).resolve().parent.parent / "Resources"
    return _source_root()


def user_data_dir() -> Path:
    if _is_frozen_darwin():
        path = Path.home() / "Library" / "Application Support" / APP_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path
    return _source_root()


def _has_content(path: Path) -> bool:
    return path.exists() and path.is_dir() and any(path.iterdir())


def migrate_legacy_data_dirs() -> None:
    target_root = user_data_dir()
    cwd = Path.cwd()

    for name in LEGACY_DATA_DIRS:
        legacy = (cwd / name).resolve()
        target = (target_root / name).resolve()

        if legacy == target:
            continue
        if not _has_content(legacy):
            continue
        if target.exists() and any(target.iterdir()):
            continue

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(target))
