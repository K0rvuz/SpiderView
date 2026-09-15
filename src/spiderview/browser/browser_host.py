from __future__ import annotations

from PySide6.QtCore import QUrl, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


class BrowserHost(QWidget):
    """
    Browser embutido do SpiderView.

    Por enquanto usa Qt WebEngine.
    Futuramente essa implementação pode ser trocada por WebView2,
    WKWebView, WebKitGTK etc. sem alterar o canvas.
    """

    closeRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.browser = QWebEngineView()

        self.back_button = QToolButton()
        self.back_button.setText("←")

        self.forward_button = QToolButton()
        self.forward_button.setText("→")

        self.reload_button = QToolButton()
        self.reload_button.setText("↻")

        self.stop_button = QToolButton()
        self.stop_button.setText("✕")

        self.close_button = QToolButton()
        self.close_button.setText("Fechar")

        self.address_bar = QLineEdit()
        self.address_bar.setPlaceholderText("https://...")

        self.status_label = QLabel()

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        toolbar = QHBoxLayout()

        toolbar.setContentsMargins(6, 6, 6, 0)
        toolbar.setSpacing(4)

        toolbar.addWidget(self.back_button)
        toolbar.addWidget(self.forward_button)
        toolbar.addWidget(self.reload_button)
        toolbar.addWidget(self.stop_button)

        toolbar.addSpacing(6)

        toolbar.addWidget(
            self.address_bar,
            stretch=1,
        )

        toolbar.addWidget(self.status_label)

        toolbar.addSpacing(6)

        toolbar.addWidget(self.close_button)

        root = QVBoxLayout(self)

        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        root.addLayout(toolbar)

        root.addWidget(
            self.browser,
            stretch=1,
        )

    def _connect_signals(self) -> None:
        self.back_button.clicked.connect(
            self.browser.back
        )

        self.forward_button.clicked.connect(
            self.browser.forward
        )

        self.reload_button.clicked.connect(
            self.browser.reload
        )

        self.stop_button.clicked.connect(
            self.browser.stop
        )

        self.close_button.clicked.connect(
            self.closeRequested.emit
        )

        self.address_bar.returnPressed.connect(
            self._navigate_from_address_bar
        )

        self.browser.urlChanged.connect(
            self._on_url_changed
        )

        self.browser.loadProgress.connect(
            self._on_load_progress
        )

        self.browser.loadFinished.connect(
            self._on_load_finished
        )

    def open_url(self, url: str) -> None:
        url = url.strip()

        if not url:
            return

        if "://" not in url:
            url = f"https://{url}"

        self.browser.setUrl(
            QUrl(url)
        )

    def _navigate_from_address_bar(self) -> None:
        self.open_url(
            self.address_bar.text()
        )

    def _on_url_changed(
        self,
        url: QUrl,
    ) -> None:
        self.address_bar.setText(
            url.toString()
        )

    def _on_load_progress(
        self,
        progress: int,
    ) -> None:
        self.status_label.setText(
            f"{progress}%"
        )

    def _on_load_finished(
        self,
        success: bool,
    ) -> None:
        if success:
            self.status_label.setText("")
        else:
            self.status_label.setText(
                "Erro"
            )