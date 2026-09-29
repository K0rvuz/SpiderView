from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFontDatabase, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


def parse_headers(raw: str) -> dict[str, str]:
    """
    Accept either a JSON object or one `Header: value` entry per line.
    """

    text = raw.strip()

    if not text:
        return {}

    if text.startswith("{"):
        parsed = json.loads(text)

        if not isinstance(parsed, dict):
            raise ValueError("Headers em JSON precisam ser um objeto.")

        return {
            str(key).strip(): str(value)
            for key, value in parsed.items()
            if str(key).strip()
        }

    headers: dict[str, str] = {}

    for line_number, line in enumerate(
        text.splitlines(),
        start=1,
    ):
        line = line.strip()

        if not line:
            continue

        if ":" not in line:
            raise ValueError(
                f"Linha {line_number}: use 'Header: valor'."
            )

        name, value = line.split(":", 1)

        name = name.strip()
        value = value.strip()

        if not name:
            raise ValueError(
                f"Linha {line_number}: nome do header vazio."
            )

        headers[name] = value

    return headers


def format_console_value(result: Any) -> str:
    if not isinstance(result, dict):
        return str(result)

    value_type = str(
        result.get("type", "")
        or ""
    )

    value = result.get("value")

    if value_type == "undefined":
        return "undefined"

    if value_type in {
        "null",
        "number",
        "boolean",
        "bigint",
        "function",
        "symbol",
    }:
        return str(value)

    if value_type == "string":
        return str(value)

    if value_type == "json":
        try:
            return json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
            )
        except (TypeError, ValueError):
            return str(value)

    return str(value)


def _pretty_response_body(
    body: str,
    content_type: str,
) -> str:
    if not body:
        return ""

    if "json" not in content_type.lower():
        return body

    try:
        parsed = json.loads(body)
    except (TypeError, ValueError):
        return body

    return json.dumps(
        parsed,
        ensure_ascii=False,
        indent=2,
    )


class ConsoleInput(QPlainTextEdit):
    executeRequested = Signal()

    def keyPressEvent(self, event) -> None:
        if (
            event.key()
            in {
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter,
            }
            and bool(
                event.modifiers()
                & Qt.KeyboardModifier.ControlModifier
            )
        ):
            self.executeRequested.emit()
            event.accept()
            return

        super().keyPressEvent(event)


class BrowserConsolePanel(QWidget):
    """
    Browser Console + API Lab.

    The panel deliberately executes in the same JavaScript context as the
    embedded browser. Cookies, origin, CORS and page state therefore behave
    like a request made by the page itself.
    """

    MAX_CAPTURED_REQUESTS = 500

    def __init__(
        self,
        browser_host,
        parent=None,
    ):
        super().__init__(parent)

        self.browser_host = browser_host
        self._command_history: list[str] = []

        self.tabs = QTabWidget()

        self._build_console_tab()
        self._build_api_lab_tab()
        self._build_requests_tab()
        self._build_history_tab()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tabs)

        self._connect_browser()

    # ------------------------------------------------------------------
    # Build UI
    # ------------------------------------------------------------------

    def _build_console_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        hint = QLabel(
            "JavaScript no contexto da página. "
            "Ctrl+Enter executa; Promises são aguardadas automaticamente. "
            "Se a página bloquear eval por CSP, use o API Lab para requests."
        )
        hint.setWordWrap(True)

        self.console_output = QPlainTextEdit()
        self.console_output.setReadOnly(True)
        self.console_output.document().setMaximumBlockCount(2500)

        fixed_font = QFontDatabase.systemFont(
            QFontDatabase.SystemFont.FixedFont
        )
        self.console_output.setFont(fixed_font)

        self.console_input = ConsoleInput()
        self.console_input.setFont(fixed_font)
        self.console_input.setPlaceholderText(
            "Ex.: await fetch('/api/users').then(r => r.json())"
        )
        self.console_input.setMaximumHeight(120)

        button_row = QHBoxLayout()

        self.execute_button = QPushButton("Executar")
        self.clear_console_button = QPushButton("Limpar")

        button_row.addStretch(1)
        button_row.addWidget(self.clear_console_button)
        button_row.addWidget(self.execute_button)

        layout.addWidget(hint)
        layout.addWidget(self.console_output, 1)
        layout.addWidget(self.console_input)
        layout.addLayout(button_row)

        self.tabs.addTab(tab, "Console")

        self.console_input.executeRequested.connect(
            self._execute_console
        )
        self.execute_button.clicked.connect(
            self._execute_console
        )
        self.clear_console_button.clicked.connect(
            self.console_output.clear
        )

    def _build_api_lab_tab(self) -> None:
        tab = QWidget()
        root = QVBoxLayout(tab)
        root.setContentsMargins(8, 8, 8, 8)

        hint = QLabel(
            "Requisições saem do WebView e reaproveitam a sessão do navegador. "
            "As regras normais de CORS continuam valendo."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()

        method_url = QWidget()
        method_url_layout = QHBoxLayout(method_url)
        method_url_layout.setContentsMargins(0, 0, 0, 0)

        self.api_method = QComboBox()
        self.api_method.addItems(
            [
                "GET",
                "POST",
                "PUT",
                "PATCH",
                "DELETE",
                "OPTIONS",
                "HEAD",
            ]
        )

        self.api_url = QLineEdit()
        self.api_url.setPlaceholderText(
            "/api/resource ou https://host/api/resource"
        )

        method_url_layout.addWidget(self.api_method)
        method_url_layout.addWidget(self.api_url, 1)

        form.addRow("Request", method_url)

        self.api_headers = QPlainTextEdit()
        self.api_headers.setPlaceholderText(
            "Content-Type: application/json\n"
            "Accept: application/json\n\n"
            "ou {\"Content-Type\": \"application/json\"}"
        )
        self.api_headers.setMaximumHeight(110)
        form.addRow("Headers", self.api_headers)

        self.api_body = QPlainTextEdit()
        self.api_body.setPlaceholderText(
            '{\n  "example": true\n}'
        )
        self.api_body.setMaximumHeight(150)
        form.addRow("Body", self.api_body)

        request_widget = QWidget()
        request_layout = QVBoxLayout(request_widget)
        request_layout.setContentsMargins(0, 0, 0, 0)
        request_layout.addLayout(form)

        button_row = QHBoxLayout()
        self.send_api_button = QPushButton("Enviar")
        self.clear_api_button = QPushButton("Limpar resposta")
        button_row.addStretch(1)
        button_row.addWidget(self.clear_api_button)
        button_row.addWidget(self.send_api_button)
        request_layout.addLayout(button_row)

        self.api_response = QPlainTextEdit()
        self.api_response.setReadOnly(True)
        self.api_response.setPlaceholderText(
            "Status, headers e body aparecerão aqui."
        )

        splitter = QSplitter(
            Qt.Orientation.Vertical
        )
        splitter.addWidget(request_widget)
        splitter.addWidget(self.api_response)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self.tabs.addTab(tab, "API Lab")

        self.send_api_button.clicked.connect(
            self._send_api_request
        )
        self.clear_api_button.clicked.connect(
            self.api_response.clear
        )

    def _build_requests_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        hint = QLabel(
            "Selecione para inspecionar. "
            "Duplo clique ou 'Repetir no API Lab' carrega método, URL, "
            "headers e body capturados. Credenciais ficam apenas em memória."
        )
        hint.setWordWrap(
            True
        )

        self.requests_table = QTableWidget(
            0,
            6,
        )
        self.requests_table.setHorizontalHeaderLabels(
            [
                "Method",
                "Status",
                "Type",
                "Origin",
                "Time",
                "URL",
            ]
        )
        self.requests_table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.requests_table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.requests_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        header = self.requests_table.horizontalHeader()

        for column in range(5):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.ResizeToContents,
            )

        header.setSectionResizeMode(
            5,
            QHeaderView.ResizeMode.Stretch,
        )

        self.request_inspector = QPlainTextEdit()
        self.request_inspector.setReadOnly(
            True
        )
        self.request_inspector.setPlaceholderText(
            "Selecione uma request para ver headers, body e response headers."
        )

        splitter = QSplitter(
            Qt.Orientation.Vertical
        )
        splitter.addWidget(
            self.requests_table
        )
        splitter.addWidget(
            self.request_inspector
        )
        splitter.setStretchFactor(
            0,
            2
        )
        splitter.setStretchFactor(
            1,
            1
        )

        self.replay_request_button = QPushButton(
            "Repetir no API Lab"
        )
        self.replay_request_button.setEnabled(
            False
        )

        self.clear_requests_button = QPushButton(
            "Limpar requests"
        )

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(
            self.replay_request_button
        )
        row.addWidget(
            self.clear_requests_button
        )

        layout.addWidget(
            hint
        )
        layout.addWidget(
            splitter,
            1,
        )
        layout.addLayout(
            row
        )

        self.tabs.addTab(
            tab,
            "Requests",
        )

        self.requests_table.itemSelectionChanged.connect(
            self._show_selected_request
        )

        self.requests_table.cellDoubleClicked.connect(
            lambda _row, _column:
                self._replay_selected_request()
        )

        self.replay_request_button.clicked.connect(
            self._replay_selected_request
        )

        self.clear_requests_button.clicked.connect(
            self._clear_requests
        )

    def _build_history_tab(self) -> None:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)

        self.history_output = QPlainTextEdit()
        self.history_output.setReadOnly(True)
        self.history_output.document().setMaximumBlockCount(3000)

        self.clear_history_button = QPushButton(
            "Limpar histórico"
        )
        self.clear_history_button.clicked.connect(
            self.history_output.clear
        )

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.clear_history_button)

        layout.addWidget(self.history_output, 1)
        layout.addLayout(row)

        self.tabs.addTab(tab, "History")

    # ------------------------------------------------------------------
    # Browser integration
    # ------------------------------------------------------------------

    def _connect_browser(self) -> None:
        self.browser_host.javascriptResult.connect(
            self._on_javascript_result
        )

        self.browser_host.consoleMessageDetected.connect(
            self._on_console_message
        )

        self.browser_host.apiLabResult.connect(
            self._on_api_lab_result
        )

        self.browser_host.apiRequestDetected.connect(
            self.record_request
        )

    # ------------------------------------------------------------------
    # Console
    # ------------------------------------------------------------------

    def focus_console(self) -> None:
        self.tabs.setCurrentIndex(0)
        self.console_input.setFocus()

    def _execute_console(self) -> None:
        code = self.console_input.toPlainText().strip()

        if not code:
            return

        self._command_history.append(code)

        self._append_console(
            "> " + code
        )

        self._record_history(
            "console",
            code,
        )

        self.browser_host.execute_javascript(
            code
        )

        self.console_input.clear()

    def _on_javascript_result(
        self,
        payload: dict,
    ) -> None:
        if not isinstance(payload, dict):
            return

        if payload.get("ok"):
            value = format_console_value(
                payload.get("result")
            )
            self._append_console(
                "< " + value
            )
            self._record_history(
                "console-result",
                value,
            )
            return

        error = str(
            payload.get("error", "JavaScript error")
            or "JavaScript error"
        )

        self._append_console(
            "! " + error
        )
        self._record_history(
            "console-error",
            error,
        )

    def _on_console_message(
        self,
        payload: dict,
    ) -> None:
        if not isinstance(payload, dict):
            return

        level = str(
            payload.get("level", "console")
            or "console"
        )
        message = str(
            payload.get("message", "")
            or ""
        )

        if not message:
            return

        self._append_console(
            f"[{level}] {message}"
        )

    def _append_console(
        self,
        text: str,
    ) -> None:
        self.console_output.appendPlainText(
            text
        )
        self.console_output.moveCursor(
            QTextCursor.MoveOperation.End
        )

    # ------------------------------------------------------------------
    # API Lab
    # ------------------------------------------------------------------

    def select_api_lab(self) -> None:
        self.tabs.setCurrentIndex(1)
        self.api_url.setFocus()

    @staticmethod
    def _headers_editor_text(
        headers,
    ) -> str:
        if not isinstance(
            headers,
            dict,
        ):
            return ""

        return "\n".join(
            f"{name}: {value}"
            for name, value
            in headers.items()
        )

    def prefill_request(
        self,
        method: str,
        url: str,
        headers: dict | None = None,
        body: str = "",
    ) -> None:
        method = (
            method.strip().upper()
            or "GET"
        )

        index = self.api_method.findText(
            method
        )

        if index >= 0:
            self.api_method.setCurrentIndex(
                index
            )

        self.api_url.setText(
            url
        )

        if headers is not None:
            self.api_headers.setPlainText(
                self._headers_editor_text(
                    headers
                )
            )

        self.api_body.setPlainText(
            body or ""
        )

        self.select_api_lab()

    def _send_api_request(self) -> None:
        method = self.api_method.currentText()
        url = self.api_url.text().strip()

        if not url:
            self.api_response.setPlainText(
                "Informe uma URL."
            )
            return

        try:
            headers = parse_headers(
                self.api_headers.toPlainText()
            )
        except (
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            self.api_response.setPlainText(
                f"Headers inválidos: {exc}"
            )
            return

        body = self.api_body.toPlainText()

        self.api_response.setPlainText(
            f"Enviando {method} {url}..."
        )

        self._record_history(
            "api-request",
            f"{method} {url}",
        )

        self.browser_host.execute_api_request(
            method=method,
            url=url,
            headers=headers,
            body=body,
        )

    def _on_api_lab_result(
        self,
        payload: dict,
    ) -> None:
        if not isinstance(payload, dict):
            return

        if not payload.get("ok"):
            error = str(
                payload.get(
                    "error",
                    "Request failed",
                )
                or "Request failed"
            )

            self.api_response.setPlainText(
                "ERROR\n\n" + error
            )

            self._record_history(
                "api-error",
                error,
            )
            return

        status = payload.get(
            "status"
        )
        status_text = str(
            payload.get(
                "status_text",
                "",
            )
            or ""
        ).strip()

        final_url = str(
            payload.get(
                "url",
                "",
            )
            or ""
        )

        duration = payload.get(
            "duration_ms"
        )

        headers = payload.get(
            "headers",
            {},
        )

        if not isinstance(
            headers,
            dict,
        ):
            headers = {}

        content_type = str(
            headers.get(
                "content-type",
                "",
            )
            or ""
        )

        body = _pretty_response_body(
            str(
                payload.get(
                    "body",
                    "",
                )
                or ""
            ),
            content_type,
        )

        lines = [
            f"HTTP {status} {status_text}".rstrip(),
        ]

        if duration is not None:
            lines.append(
                f"Time: {duration} ms"
            )

        if final_url:
            lines.append(
                f"URL: {final_url}"
            )

        lines.append("")
        lines.append("Headers:")

        if headers:
            for name, value in headers.items():
                lines.append(
                    f"{name}: {value}"
                )
        else:
            lines.append("(none)")

        lines.append("")
        lines.append("Body:")
        lines.append(
            body or "(empty)"
        )

        if payload.get("truncated"):
            lines.append("")
            lines.append(
                "[response truncated at 2 MB]"
            )

        output = "\n".join(lines)

        self.api_response.setPlainText(
            output
        )

        self._record_history(
            "api-response",
            lines[0],
        )

    # ------------------------------------------------------------------
    # Captured requests
    # ------------------------------------------------------------------

    def _clear_requests(
        self,
    ) -> None:
        self.requests_table.setRowCount(
            0
        )
        self.request_inspector.clear()
        self.replay_request_button.setEnabled(
            False
        )

    def _selected_request_event(
        self,
    ) -> dict | None:
        row = (
            self.requests_table
            .currentRow()
        )

        if row < 0:
            return None

        item = (
            self.requests_table
            .item(
                row,
                0,
            )
        )

        if item is None:
            return None

        raw = item.data(
            Qt.ItemDataRole.UserRole
        )

        if not raw:
            return None

        try:
            event = json.loads(
                str(raw)
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
        ):
            return None

        if not isinstance(
            event,
            dict,
        ):
            return None

        return event

    def _show_selected_request(
        self,
    ) -> None:
        event = (
            self._selected_request_event()
        )

        if event is None:
            self.request_inspector.clear()
            self.replay_request_button.setEnabled(
                False
            )
            return

        self.replay_request_button.setEnabled(
            True
        )

        request_headers = event.get(
            "request_headers",
            {},
        )

        response_headers = event.get(
            "response_headers",
            {},
        )

        request_body = str(
            event.get(
                "request_body",
                "",
            )
            or ""
        )

        method = str(
            event.get(
                "method",
                "GET",
            )
            or "GET"
        ).upper()

        url = str(
            event.get(
                "request_url",
                "",
            )
            or event.get(
                "url",
                "",
            )
            or ""
        )

        status = event.get(
            "status"
        )

        lines = [
            f"{method} {url}",
            "",
            "Request headers:",
            (
                self._headers_editor_text(
                    request_headers
                )
                or "(none captured)"
            ),
            "",
            "Request body:",
            request_body
            or "(empty / not captured)",
            "",
            "Response:",
            (
                str(status)
                if status not in (
                    None,
                    "",
                )
                else "—"
            ),
            "",
            "Response headers:",
            (
                self._headers_editor_text(
                    response_headers
                )
                or "(none exposed)"
            ),
        ]

        error = str(
            event.get(
                "error",
                "",
            )
            or ""
        )

        if error:
            lines.extend(
                [
                    "",
                    "Error:",
                    error,
                ]
            )

        self.request_inspector.setPlainText(
            "\n".join(
                lines
            )
        )

    def _replay_selected_request(
        self,
    ) -> None:
        event = (
            self._selected_request_event()
        )

        if event is None:
            return

        method = str(
            event.get(
                "method",
                "GET",
            )
            or "GET"
        ).upper()

        url = str(
            event.get(
                "request_url",
                "",
            )
            or event.get(
                "url",
                "",
            )
            or ""
        )

        headers = event.get(
            "request_headers",
            {},
        )

        if not isinstance(
            headers,
            dict,
        ):
            headers = {}

        body = str(
            event.get(
                "request_body",
                "",
            )
            or ""
        )

        self.prefill_request(
            method,
            url,
            headers=headers,
            body=body,
        )

        self._record_history(
            "replay",
            f"{method} {url}",
        )

    def record_request(
        self,
        event: dict,
    ) -> None:
        if not isinstance(event, dict):
            return

        method = str(
            event.get(
                "method",
                "GET",
            )
            or "GET"
        ).upper()

        raw_status = event.get(
            "status"
        )

        if raw_status in {
            None,
            "",
            0,
            "0",
        }:
            status = (
                "ERR"
                if event.get("error")
                else "-"
            )
        else:
            status = str(
                raw_status
            )

        kind = str(
            event.get(
                "kind",
                "request",
            )
            or "request"
        )

        request_origin = str(
            event.get(
                "request_origin",
                "page",
            )
            or "page"
        )

        if request_origin == "api_lab":
            origin = "API Lab"
        else:
            origin = "Browser"

        duration = event.get(
            "duration_ms"
        )

        if duration is None:
            duration_label = "-"
        else:
            try:
                duration_label = (
                    f"{float(duration):.1f} ms"
                )
            except (TypeError, ValueError):
                duration_label = str(
                    duration
                )

        url = str(
            event.get(
                "url",
                "",
            )
            or event.get(
                "request_url",
                "",
            )
            or ""
        )

        self.requests_table.insertRow(
            0
        )

        values = [
            method,
            status,
            kind,
            origin,
            duration_label,
            url,
        ]

        event_json = json.dumps(
            event,
            ensure_ascii=False,
            default=str,
        )

        for column, value in enumerate(
            values
        ):
            item = QTableWidgetItem(
                value
            )

            if column == 0:
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    event_json,
                )

            self.requests_table.setItem(
                0,
                column,
                item,
            )

        while (
            self.requests_table.rowCount()
            > self.MAX_CAPTURED_REQUESTS
        ):
            self.requests_table.removeRow(
                self.requests_table.rowCount()
                - 1
            )

        self._record_history(
            "request",
            (
                f"{method} {url} "
                f"[{status}] via {origin}"
            ),
        )

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record_history(
        self,
        category: str,
        message: str,
    ) -> None:
        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        self.history_output.appendPlainText(
            f"[{timestamp}] "
            f"{category}: "
            f"{message}"
        )
