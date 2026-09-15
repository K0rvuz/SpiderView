from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "SpiderView"
    )

    app.setOrganizationName(
        "Korvuz"
    )

    window = MainWindow()

    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(
        main()
    )