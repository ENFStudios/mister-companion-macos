import os
import subprocess
import sys

from core.open_helpers import open_local_folder, open_smb_share


def open_mister_share(ip, username="root", password="1"):
    if not ip:
        raise ValueError("No MiSTer IP address is available.")

    if sys.platform == "darwin":
        username = username or "root"
        password = password or "1"
        home = os.path.expanduser("~")

        for share in ["sdcard", "usb0"]:
            mount_point = os.path.join(home, f"MiSTer_{share}")
            subprocess.run(["mkdir", "-p", mount_point], capture_output=True)
            subprocess.run(
                ["mount_smbfs", f"//{username}:{password}@{ip}/{share}", mount_point],
                capture_output=True,
            )

        subprocess.Popen(["open", os.path.join(home, "MiSTer_sdcard")])
        return

    open_smb_share(ip)
