from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import (
    QUrl,
    Signal,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import (
    QWebEnginePage,
    QWebEngineScript,
)
from PySide6.QtWebEngineWidgets import (
    QWebEngineView,
)


EVENT_PREFIX = "__SPIDERVIEW_EVENT__:"


INSTRUMENTATION_JS = r"""
(() => {

    if (window.__spiderview_installed__) {
        return;
    }

    window.__spiderview_installed__ = true;


    // --------------------------------------------------------------
    // Event sender
    // --------------------------------------------------------------

    function emit(payload) {

        try {

            console.log(
                "__SPIDERVIEW_EVENT__:"
                + JSON.stringify(payload)
            );

        } catch (error) {

            // SpiderView nunca deve interferir
            // no funcionamento normal da página.

        }
    }


    // --------------------------------------------------------------
    // Helpers
    // --------------------------------------------------------------

    function cleanText(value) {

        if (!value) {
            return "";
        }

        return String(value)
            .replace(/\s+/g, " ")
            .trim()
            .slice(0, 180);
    }


    function elementLabel(element) {

        if (!element) {
            return "";
        }

        const candidates = [
            element.getAttribute?.("aria-label"),
            element.getAttribute?.("title"),
            element.innerText,
            element.textContent,
            element.getAttribute?.("name"),
            element.getAttribute?.("value"),
        ];

        for (const candidate of candidates) {

            const text = cleanText(candidate);

            if (text) {
                return text;
            }
        }

        return "";
    }


    function absoluteUrl(value) {

        if (!value) {
            return "";
        }

        try {

            return new URL(
                value,
                window.location.href
            ).href;

        } catch (error) {

            return "";
        }
    }


    // --------------------------------------------------------------
    // Click
    // --------------------------------------------------------------

    document.addEventListener(
        "click",

        (event) => {

            let element = event.target;

            if (!(element instanceof Element)) {
                return;
            }

            element = element.closest(
                [
                    "a",
                    "button",
                    "input[type='submit']",
                    "input[type='button']",
                    "[role='button']",
                    "[onclick]"
                ].join(",")
            );

            if (!element) {
                return;
            }

            let targetUrl = "";

            if (
                element.tagName
                && element.tagName.toLowerCase() === "a"
            ) {

                targetUrl = absoluteUrl(
                    element.getAttribute("href")
                );
            }

            emit({
                kind: "click",

                label: elementLabel(
                    element
                ),

                target_url: targetUrl,

                source_url:
                    window.location.href,

                tag:
                    element.tagName
                    ? element.tagName.toLowerCase()
                    : "",
            });

        },

        true
    );


    // --------------------------------------------------------------
    // Form submit
    // --------------------------------------------------------------

    document.addEventListener(
        "submit",

        (event) => {

            const form = event.target;

            if (!(form instanceof HTMLFormElement)) {
                return;
            }

            const submitter = event.submitter;

            const action = absoluteUrl(
                form.getAttribute("action")
                || window.location.href
            );

            const method = (
                form.getAttribute("method")
                || "GET"
            ).toUpperCase();

            emit({
                kind: "submit",

                label: elementLabel(
                    submitter
                ),

                target_url: action,

                source_url:
                    window.location.href,

                method: method,
            });

        },

        true
    );


    // --------------------------------------------------------------
    // History API
    // --------------------------------------------------------------

    function wrapHistory(
        functionName,
        eventName
    ) {

        const original =
            history[functionName];

        if (typeof original !== "function") {
            return;
        }

        history[functionName] = function() {

            const previousUrl =
                window.location.href;

            const result =
                original.apply(
                    this,
                    arguments
                );

            emit({
                kind: eventName,

                source_url:
                    previousUrl,

                url:
                    window.location.href,

                title:
                    document.title || "",
            });

            return result;
        };
    }


    wrapHistory(
        "pushState",
        "history_push"
    );

    wrapHistory(
        "replaceState",
        "history_replace"
    );


    // --------------------------------------------------------------
    // Browser history
    // --------------------------------------------------------------

    window.addEventListener(
        "popstate",

        () => {

            emit({
                kind: "history_pop",

                url:
                    window.location.href,

                title:
                    document.title || "",
            });
        }
    );


    // --------------------------------------------------------------
    // Hash navigation
    // --------------------------------------------------------------

    window.addEventListener(
        "hashchange",

        () => {

            emit({
                kind: "hash_change",

                url:
                    window.location.href,

                title:
                    document.title || "",
            });
        }
    );


    // --------------------------------------------------------------
    // fetch()
    // --------------------------------------------------------------

    const originalFetch = window.fetch;

    if (typeof originalFetch === "function") {

        window.fetch = async function(input, init) {

            const startedAt = performance.now();

            const sourceUrl =
                window.location.href;

            let requestUrl = "";
            let method = "GET";

            try {

                if (
                    typeof Request !== "undefined"
                    && input instanceof Request
                ) {

                    requestUrl =
                        input.url || "";

                    method = (
                        init?.method
                        || input.method
                        || "GET"
                    ).toUpperCase();

                } else {

                    requestUrl = absoluteUrl(
                        String(input ?? "")
                    );

                    method = (
                        init?.method
                        || "GET"
                    ).toUpperCase();
                }

            } catch (error) {

                requestUrl = "";
                method = "GET";
            }

            try {

                const response =
                    await originalFetch.apply(
                        this,
                        arguments
                    );

                const durationMs =
                    performance.now()
                    - startedAt;

                let contentType = "";

                try {

                    contentType =
                        response.headers.get(
                            "content-type"
                        ) || "";

                } catch (error) {

                    contentType = "";
                }

                emit({
                    kind: "fetch",

                    source_url:
                        sourceUrl,

                    request_url:
                        requestUrl,

                    url:
                        response.url
                        || requestUrl,

                    method:
                        method,

                    status:
                        response.status,

                    ok:
                        response.ok,

                    content_type:
                        contentType,

                    duration_ms:
                        Math.round(
                            durationMs * 100
                        ) / 100,

                    error:
                        "",
                });

                return response;

            } catch (error) {

                const durationMs =
                    performance.now()
                    - startedAt;

                emit({
                    kind: "fetch",

                    source_url:
                        sourceUrl,

                    request_url:
                        requestUrl,

                    url:
                        requestUrl,

                    method:
                        method,

                    status:
                        null,

                    ok:
                        false,

                    content_type:
                        "",

                    duration_ms:
                        Math.round(
                            durationMs * 100
                        ) / 100,

                    error:
                        cleanText(
                            error?.message
                            || String(error)
                        ),
                });

                throw error;
            }
        };
    }


    // --------------------------------------------------------------
    // XMLHttpRequest
    // --------------------------------------------------------------

    const originalXhrOpen =
        XMLHttpRequest.prototype.open;

    const originalXhrSend =
        XMLHttpRequest.prototype.send;

    XMLHttpRequest.prototype.open = function(
        method,
        url
    ) {

        this.__spiderview_request__ = {
            method:
                String(
                    method || "GET"
                ).toUpperCase(),

            request_url:
                absoluteUrl(
                    String(url || "")
                ),

            source_url:
                window.location.href,
        };

        return originalXhrOpen.apply(
            this,
            arguments
        );
    };


    XMLHttpRequest.prototype.send = function() {

        const xhr = this;

        const info = (
            xhr.__spiderview_request__
            || {
                method: "GET",
                request_url: "",
                source_url:
                    window.location.href,
            }
        );

        const startedAt =
            performance.now();

        const finish = () => {

            const durationMs =
                performance.now()
                - startedAt;

            let contentType = "";

            try {

                contentType =
                    xhr.getResponseHeader(
                        "content-type"
                    ) || "";

            } catch (error) {

                contentType = "";
            }

            const status =
                Number.isFinite(
                    xhr.status
                )
                ? xhr.status
                : 0;

            emit({
                kind: "xhr",

                source_url:
                    info.source_url,

                request_url:
                    info.request_url,

                url:
                    xhr.responseURL
                    || info.request_url,

                method:
                    info.method,

                status:
                    status,

                ok:
                    status >= 200
                    && status < 400,

                content_type:
                    contentType,

                duration_ms:
                    Math.round(
                        durationMs * 100
                    ) / 100,

                error:
                    status === 0
                    ? "Network error or request blocked"
                    : "",
            });
        };

        xhr.addEventListener(
            "loadend",
            finish,
            {
                once: true,
            }
        );

        try {

            return originalXhrSend.apply(
                this,
                arguments
            );

        } catch (error) {

            const durationMs =
                performance.now()
                - startedAt;

            emit({
                kind: "xhr",

                source_url:
                    info.source_url,

                request_url:
                    info.request_url,

                url:
                    info.request_url,

                method:
                    info.method,

                status:
                    null,

                ok:
                    false,

                content_type:
                    "",

                duration_ms:
                    Math.round(
                        durationMs * 100
                    ) / 100,

                error:
                    cleanText(
                        error?.message
                        || String(error)
                    ),
            });

            throw error;
        }
    };

})();
"""


class SpiderWebPage(QWebEnginePage):
    """
    Página customizada do Qt WebEngine.

    Intercepta somente mensagens reservadas ao SpiderView
    vindas da instrumentação JavaScript.
    """
    IGNORED_CONSOLE_MESSAGES = (
    "Error with Permissions-Policy header: Unrecognized feature:",
    "Failed to create WebGPU Context Provider",
    "OTS parsing error:",
    "Failed to parse audio contentType:",
    "Failed to parse video contentType:",
    )
    browserEvent = Signal(object)

    def javaScriptConsoleMessage(
        self,
        level,
        message: str,
        line_number: int,
        source_id: str,
    ) -> None:

        # --------------------------------------------------------------
        # Eventos internos do SpiderView
        # --------------------------------------------------------------

        if message.startswith(
            EVENT_PREFIX
        ):

            raw = message[
                len(EVENT_PREFIX):
            ]

            try:

                payload = json.loads(
                    raw
                )

            except json.JSONDecodeError:

                return

            if isinstance(
                payload,
                dict,
            ):

                self.browserEvent.emit(
                    payload
                )

            return

        # --------------------------------------------------------------
        # Ruído conhecido do Chromium / páginas
        # --------------------------------------------------------------

        for ignored in self.IGNORED_CONSOLE_MESSAGES:

            if ignored in message:
                return

        # Alguns sites imprimem mensagens estilizadas/invisíveis
        # no console. Não são úteis para o SpiderView.
        if (
            "font-size:0"
            in message
            and "color:transparent"
            in message
        ):
            return

        # --------------------------------------------------------------
        # Console normal
        # --------------------------------------------------------------

        super().javaScriptConsoleMessage(
            level,
            message,
            line_number,
            source_id,
        )


class BrowserHost(QWidget):
    """
    Browser embutido do SpiderView.
    """

    closeRequested = Signal()

    navigationFinished = Signal(
        str,   # url
        str,   # title
        bool,  # success
        str,   # origin
    )

    # click / submit
    interactionDetected = Signal(
        object
    )

    # pushState / replaceState
    spaNavigationDetected = Signal(
        object
    )

    # fetch / XMLHttpRequest
    apiRequestDetected = Signal(
        object
    )

    def __init__(
        self,
        parent=None,
    ):

        super().__init__(parent)

        # --------------------------------------------------------------
        # Browser
        # --------------------------------------------------------------

        self.browser = QWebEngineView()

        self.page = SpiderWebPage(
            self.browser
        )

        self.browser.setPage(
            self.page
        )

        self._install_instrumentation()

        # --------------------------------------------------------------
        # Navigation state
        # --------------------------------------------------------------

        self._navigation_origin = "page"

        # --------------------------------------------------------------
        # Buttons
        # --------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Address
        # --------------------------------------------------------------

        self.address_bar = QLineEdit()

        self.address_bar.setPlaceholderText(
            "https://..."
        )

        self.status_label = QLabel()

        self._build_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # Instrumentation
    # ------------------------------------------------------------------

    def _install_instrumentation(
        self,
    ) -> None:

        script = QWebEngineScript()

        script.setName(
            "SpiderView instrumentation"
        )

        script.setInjectionPoint(
            QWebEngineScript.InjectionPoint.DocumentCreation
        )

        script.setWorldId(
            QWebEngineScript.ScriptWorldId.MainWorld
        )

        script.setRunsOnSubFrames(
            False
        )

        script.setSourceCode(
            INSTRUMENTATION_JS
        )

        self.page.scripts().insert(
            script
        )

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:

        toolbar = QHBoxLayout()

        toolbar.setContentsMargins(
            6,
            6,
            6,
            0,
        )

        toolbar.setSpacing(4)

        toolbar.addWidget(
            self.back_button
        )

        toolbar.addWidget(
            self.forward_button
        )

        toolbar.addWidget(
            self.reload_button
        )

        toolbar.addWidget(
            self.stop_button
        )

        toolbar.addSpacing(6)

        toolbar.addWidget(
            self.address_bar,
            stretch=1,
        )

        toolbar.addWidget(
            self.status_label
        )

        toolbar.addSpacing(6)

        toolbar.addWidget(
            self.close_button
        )

        root = QVBoxLayout(
            self
        )

        root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        root.setSpacing(4)

        root.addLayout(
            toolbar
        )

        root.addWidget(
            self.browser,
            stretch=1,
        )

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:

        self.back_button.clicked.connect(
            self._go_back
        )

        self.forward_button.clicked.connect(
            self._go_forward
        )

        self.reload_button.clicked.connect(
            self._reload
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

        self.page.browserEvent.connect(
            self._on_browser_event
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_url(
        self,
        url: str,
        origin: str = "programmatic",
    ) -> None:

        url = url.strip()

        if not url:
            return

        qurl = QUrl.fromUserInput(
            url
        )

        if not qurl.isValid():
            return

        self._navigation_origin = origin

        self.browser.setUrl(
            qurl
        )

    def current_url(self) -> str:

        return (
            self.browser
            .url()
            .toString()
        )

    def current_title(self) -> str:

        return (
            self.browser
            .title()
            .strip()
        )

    def focus_address_bar(self) -> None:

        self.address_bar.setFocus()

        self.address_bar.selectAll()

    def capture_preview(
        self,
        path: str | Path,
    ) -> bool:

        path = Path(
            path
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        pixmap = self.browser.grab()

        if pixmap.isNull():
            return False

        return pixmap.save(
            str(path),
            "PNG",
        )

    # ------------------------------------------------------------------
    # Navigation commands
    # ------------------------------------------------------------------

    def _navigate_from_address_bar(
        self,
    ) -> None:

        self.open_url(
            self.address_bar.text(),
            origin="address",
        )

    def _go_back(self) -> None:

        self._navigation_origin = (
            "history"
        )

        self.browser.back()

    def _go_forward(self) -> None:

        self._navigation_origin = (
            "history"
        )

        self.browser.forward()

    def _reload(self) -> None:

        self._navigation_origin = (
            "reload"
        )

        self.browser.reload()

    # ------------------------------------------------------------------
    # Browser instrumentation event
    # ------------------------------------------------------------------

    def _on_browser_event(
        self,
        payload: dict,
    ) -> None:

        kind = str(
            payload.get(
                "kind",
                "",
            )
        )

        if kind in {
            "click",
            "submit",
        }:

            self.interactionDetected.emit(
                payload
            )

            return

        if kind in {
            "history_push",
            "history_replace",
        }:

            self.spaNavigationDetected.emit(
                payload
            )

            return

        if kind in {
            "fetch",
            "xhr",
        }:

            self.apiRequestDetected.emit(
                payload
            )

            return

    # ------------------------------------------------------------------
    # Browser events
    # ------------------------------------------------------------------

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

            self.status_label.setText(
                ""
            )

        else:

            self.status_label.setText(
                "Erro"
            )

        url = (
            self.browser
            .url()
            .toString()
        )

        title = (
            self.browser
            .title()
            .strip()
        )

        if not title:
            title = url

        origin = (
            self._navigation_origin
        )

        self._navigation_origin = (
            "page"
        )

        self.navigationFinished.emit(
            url,
            title,
            success,
            origin,
        )