from __future__ import annotations

import faulthandler
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QtMsgType, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


_CRASH_LOG = None


def _install_crash_logging() -> None:
    global _CRASH_LOG
    log_path = Path.cwd() / "spiderview-crash.log"
    _CRASH_LOG = log_path.open("a", encoding="utf-8", buffering=1)
    _CRASH_LOG.write("\\n\\n=== SpiderView session start ===\\n")
    faulthandler.enable(file=_CRASH_LOG, all_threads=True)

    def exception_hook(exc_type, exc_value, exc_traceback):
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=_CRASH_LOG)
        traceback.print_exception(exc_type, exc_value, exc_traceback, file=sys.stderr)
        _CRASH_LOG.flush()

    sys.excepthook = exception_hook

    def qt_message_handler(message_type, context, message):
        label = getattr(message_type, "name", str(message_type))
        _CRASH_LOG.write(f"[Qt {label}] {message}\\n")
        _CRASH_LOG.flush()
        if message_type in (QtMsgType.QtFatalMsg,):
            sys.stderr.write(f"[Qt {label}] {message}\\n")

    qInstallMessageHandler(qt_message_handler)


def main() -> int:
    _install_crash_logging()
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