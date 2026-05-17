from core.open_helpers import open_local_folder, open_smb_share


def open_mister_share(ip, username="root", password="1"):
    open_smb_share(ip)
