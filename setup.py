from setuptools import setup

APP = ["main.py"]
DATA_FILES = [
    ("assets", ["assets/icon.png"]),
]

OPTIONS = {
    "iconfile": "assets/icon.icns",
    "argv_emulation": False,
    "plist": {
        "CFBundleName": "MiSTer Companion",
        "CFBundleDisplayName": "MiSTer Companion",
        "CFBundleIdentifier": "io.github.anime0t4ku.mistercompanion",
        "CFBundleVersion": "3.5.1",
        "CFBundleShortVersionString": "3.5.1",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "NSRequiresAquaSystemAppearance": False,
        "NSHumanReadableCopyright": "Original by Anime0t4ku. macOS port by ENF Studios.",
    },
    "packages": [
        "PyQt6",
        "paramiko",
        "requests",
        "websocket",
        "psutil",
        "cryptography",
        "cffi",
        "nacl",
        "charset_normalizer",
        "idna",
        "urllib3",
        "certifi",
    ],
    "includes": [
        "_cffi_backend",
        "core",
        "core.app_paths",
        "core.config",
        "core.connection",
        "core.flasher",
        "core.scripts_actions",
        "core.theme",
        "core.zaplauncher_db",
        "core.zapscripts",
        "ui",
    ],
    "excludes": [
        "tkinter",
        "test",
        "unittest",
        "pydoc",
    ],
}

setup(
    app=APP,
    name="MiSTer Companion",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
