import sys
from PyQt6.QtWidgets import QApplication

from core.app_paths import migrate_legacy_data_dirs
from core.config import load_config
from core.theme import apply_theme
from ui.main_window import MainWindow


def main():
    migrate_legacy_data_dirs()

    app = QApplication(sys.argv)

    config = load_config()
    apply_theme(app, config.get("theme_mode", "auto"))

    window = MainWindow(app)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()