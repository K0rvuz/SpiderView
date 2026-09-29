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
CONSOLE_RESULT_PREFIX = "__SPIDERVIEW_CONSOLE_RESULT__:"
API_LAB_RESULT_PREFIX = "__SPIDERVIEW_API_LAB_RESULT__:"


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


    function headersObject(value) {

        const result = {};

        if (!value) {
            return result;
        }

        try {

            const headers = (
                value instanceof Headers
                ? value
                : new Headers(value)
            );

            headers.forEach(
                (headerValue, name) => {

                    result[
                        String(name).toLowerCase()
                    ] = String(headerValue);
                }
            );

        } catch (error) {

            // Request capture must never break the page.

        }

        return result;
    }


    function mergeHeaders(
        base,
        override
    ) {

        return Object.assign(
            {},
            base || {},
            override || {},
        );
    }


    function rawHeadersObject(raw) {

        const result = {};

        for (
            const line
            of String(raw || "").split(
                /\r?\n/
            )
        ) {

            const index = line.indexOf(
                ":"
            );

            if (index <= 0) {
                continue;
            }

            const name = (
                line
                .slice(0, index)
                .trim()
                .toLowerCase()
            );

            const value = (
                line
                .slice(index + 1)
                .trim()
            );

            if (name) {
                result[name] = value;
            }
        }

        return result;
    }


    function bodyPreview(value) {

        if (value == null) {
            return "";
        }

        try {

            if (
                typeof value
                === "string"
            ) {
                return value.slice(
                    0,
                    20000
                );
            }

            if (
                typeof URLSearchParams
                !== "undefined"
                && value
                instanceof URLSearchParams
            ) {
                return value
                    .toString()
                    .slice(
                        0,
                        20000
                    );
            }

            if (
                typeof FormData
                !== "undefined"
                && value
                instanceof FormData
            ) {

                const entries = [];

                for (
                    const [name, item]
                    of value.entries()
                ) {

                    if (
                        typeof File
                        !== "undefined"
                        && item
                        instanceof File
                    ) {

                        entries.push(
                            [
                                name,
                                "[File "
                                + item.name
                                + " · "
                                + item.size
                                + " bytes]",
                            ]
                        );

                    } else {

                        entries.push(
                            [
                                name,
                                String(item),
                            ]
                        );
                    }
                }

                return JSON.stringify(
                    entries
                ).slice(
                    0,
                    20000
                );
            }

            if (
                typeof Blob
                !== "undefined"
                && value
                instanceof Blob
            ) {

                return (
                    "[Blob "
                    + (value.type || "unknown")
                    + " · "
                    + value.size
                    + " bytes]"
                );
            }

            if (
                typeof ArrayBuffer
                !== "undefined"
                && value
                instanceof ArrayBuffer
            ) {

                return (
                    "[ArrayBuffer "
                    + value.byteLength
                    + " bytes]"
                );
            }

            return String(
                value
            ).slice(
                0,
                20000
            );

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

            const requestOrigin = String(
                init?.__spiderview_origin
                || "page"
            );

            let requestUrl = "";
            let method = "GET";
            let requestHeaders = {};
            let requestBody = "";

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

                    requestHeaders = (
                        headersObject(
                            input.headers
                        )
                    );

                    if (
                        method !== "GET"
                        && method !== "HEAD"
                    ) {

                        try {

                            requestBody = (
                                await input
                                .clone()
                                .text()
                            ).slice(
                                0,
                                20000
                            );

                        } catch (error) {

                            requestBody = "";
                        }
                    }

                } else {

                    requestUrl = absoluteUrl(
                        String(input ?? "")
                    );

                    method = (
                        init?.method
                        || "GET"
                    ).toUpperCase();
                }

                requestHeaders = mergeHeaders(
                    requestHeaders,
                    headersObject(
                        init?.headers
                    )
                );

                if (
                    init
                    && Object.prototype
                    .hasOwnProperty.call(
                        init,
                        "body"
                    )
                ) {

                    requestBody = bodyPreview(
                        init.body
                    );
                }

            } catch (error) {

                requestUrl = "";
                method = "GET";
                requestHeaders = {};
                requestBody = "";
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

                const responseHeaders = (
                    headersObject(
                        response.headers
                    )
                );

                const contentType = (
                    responseHeaders[
                        "content-type"
                    ]
                    || ""
                );

                emit({
                    kind: "fetch",

                    source_url:
                        sourceUrl,

                    request_origin:
                        requestOrigin,

                    request_url:
                        requestUrl,

                    url:
                        response.url
                        || requestUrl,

                    method:
                        method,

                    request_headers:
                        requestHeaders,

                    request_body:
                        requestBody,

                    response_headers:
                        responseHeaders,

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

                    request_origin:
                        requestOrigin,

                    request_url:
                        requestUrl,

                    url:
                        requestUrl,

                    method:
                        method,

                    request_headers:
                        requestHeaders,

                    request_body:
                        requestBody,

                    response_headers:
                        {},

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

    const originalXhrSetRequestHeader =
        XMLHttpRequest.prototype.setRequestHeader;


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

            request_origin:
                "page",

            request_headers:
                {},

            request_body:
                "",
        };

        return originalXhrOpen.apply(
            this,
            arguments
        );
    };


    XMLHttpRequest.prototype.setRequestHeader = function(
        name,
        value
    ) {

        const info = (
            this.__spiderview_request__
            || null
        );

        if (info) {

            const key = String(
                name || ""
            ).toLowerCase();

            if (key) {

                const current = (
                    info.request_headers[
                        key
                    ]
                    || ""
                );

                info.request_headers[
                    key
                ] = (
                    current
                    ? current
                        + ", "
                        + String(value)
                    : String(value)
                );
            }
        }

        return originalXhrSetRequestHeader.apply(
            this,
            arguments
        );
    };


    XMLHttpRequest.prototype.send = function(
        body
    ) {

        const xhr = this;

        const info = (
            xhr.__spiderview_request__
            || {
                method: "GET",
                request_url: "",
                source_url:
                    window.location.href,
                request_origin:
                    "page",
                request_headers:
                    {},
                request_body:
                    "",
            }
        );

        info.request_body = bodyPreview(
            body
        );

        const startedAt =
            performance.now();

        const finish = () => {

            const durationMs =
                performance.now()
                - startedAt;

            let responseHeaders = {};

            try {

                responseHeaders = (
                    rawHeadersObject(
                        xhr.getAllResponseHeaders()
                    )
                );

            } catch (error) {

                responseHeaders = {};
            }

            const contentType = (
                responseHeaders[
                    "content-type"
                ]
                || ""
            );

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

                request_origin:
                    info.request_origin
                    || "page",

                request_url:
                    info.request_url,

                url:
                    xhr.responseURL
                    || info.request_url,

                method:
                    info.method,

                request_headers:
                    info.request_headers
                    || {},

                request_body:
                    info.request_body
                    || "",

                response_headers:
                    responseHeaders,

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

                request_origin:
                    info.request_origin
                    || "page",

                request_url:
                    info.request_url,

                url:
                    info.request_url,

                method:
                    info.method,

                request_headers:
                    info.request_headers
                    || {},

                request_body:
                    info.request_body
                    || "",

                response_headers:
                    {},

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
    consoleResult = Signal(object)
    apiLabResult = Signal(object)
    consoleMessageDetected = Signal(object)

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
        # Browser Console / API Lab results
        # --------------------------------------------------------------

        for prefix, signal in (
            (
                CONSOLE_RESULT_PREFIX,
                self.consoleResult,
            ),
            (
                API_LAB_RESULT_PREFIX,
                self.apiLabResult,
            ),
        ):
            if not message.startswith(
                prefix
            ):
                continue

            raw = message[
                len(prefix):
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
                signal.emit(
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

        level_name = getattr(
            level,
            "name",
            str(level),
        )

        self.consoleMessageDetected.emit(
            {
                "level": level_name,
                "message": message,
                "line_number": line_number,
                "source_id": source_id,
            }
        )

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

    # Browser Console
    javascriptResult = Signal(
        object
    )

    consoleMessageDetected = Signal(
        object
    )

    # API Lab
    apiLabResult = Signal(
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

        self._console_request_counter = 0
        self._api_lab_request_counter = 0

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

        self.page.consoleResult.connect(
            self.javascriptResult.emit
        )

        self.page.consoleMessageDetected.connect(
            self.consoleMessageDetected.emit
        )

        self.page.apiLabResult.connect(
            self.apiLabResult.emit
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

    def execute_javascript(
        self,
        code: str,
    ) -> int | None:
        """
        Execute JavaScript in MainWorld and asynchronously return even
        Promise results through javascriptResult.
        """

        code = code.strip()

        if not code:
            return None

        self._console_request_counter += 1

        request_id = (
            self._console_request_counter
        )

        source_json = json.dumps(
            code
        )

        prefix_json = json.dumps(
            CONSOLE_RESULT_PREFIX
        )

        script = r"""
(async () => {
    const requestId = %s;
    const prefix = %s;
    const source = %s;

    function serialize(value) {
        if (value === undefined) {
            return {
                type: "undefined",
                value: "undefined",
            };
        }

        if (value === null) {
            return {
                type: "null",
                value: "null",
            };
        }

        if (
            typeof Response !== "undefined"
            && value instanceof Response
        ) {
            return {
                type: "json",
                value: {
                    type: "Response",
                    url: value.url,
                    status: value.status,
                    statusText: value.statusText,
                    ok: value.ok,
                    redirected: value.redirected,
                },
            };
        }

        if (value instanceof Error) {
            return {
                type: "json",
                value: {
                    name: value.name,
                    message: value.message,
                    stack: value.stack || "",
                },
            };
        }

        const type = typeof value;

        if (
            type === "string"
            || type === "number"
            || type === "boolean"
        ) {
            return {
                type: type,
                value: value,
            };
        }

        if (type === "bigint") {
            return {
                type: "bigint",
                value: value.toString() + "n",
            };
        }

        if (
            type === "function"
            || type === "symbol"
        ) {
            return {
                type: type,
                value: String(value),
            };
        }

        try {
            return {
                type: "json",
                value: JSON.parse(
                    JSON.stringify(value)
                ),
            };
        } catch (error) {
            return {
                type: type,
                value: String(value),
            };
        }
    }

    async function executeSource() {
        try {
            return await eval(source);
        } catch (error) {
            const topLevelAwait = (
                error instanceof SyntaxError
                && /\\bawait\\b/.test(source)
            );

            if (!topLevelAwait) {
                throw error;
            }

            const AsyncFunction = (
                Object.getPrototypeOf(
                    async function() {}
                ).constructor
            );

            try {
                const expressionRunner = (
                    new AsyncFunction(
                        "return await (" + source + ");"
                    )
                );

                return await expressionRunner.call(
                    window
                );
            } catch (expressionError) {
                const statementRunner = (
                    new AsyncFunction(
                        source
                    )
                );

                return await statementRunner.call(
                    window
                );
            }
        }
    }

    try {
        const result = await executeSource();

        console.log(
            prefix
            + JSON.stringify({
                id: requestId,
                ok: true,
                result: serialize(result),
            })
        );
    } catch (error) {
        console.log(
            prefix
            + JSON.stringify({
                id: requestId,
                ok: false,
                error: String(
                    error?.stack
                    || error?.message
                    || error
                ),
            })
        );
    }
})();
""" % (
            request_id,
            prefix_json,
            source_json,
        )

        self.page.runJavaScript(
            script
        )

        return request_id

    def execute_api_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: str = "",
    ) -> int | None:
        """
        Send a fetch from the loaded page context.

        The instrumentation wrapper sees the same fetch and emits the
        regular apiRequestDetected event, so API Lab traffic follows the
        normal SpiderView request -> graph pipeline.
        """

        method = (
            method.strip().upper()
            or "GET"
        )

        url = url.strip()

        if not url:
            return None

        self._api_lab_request_counter += 1

        request_id = (
            self._api_lab_request_counter
        )

        request_json = json.dumps(
            {
                "id": request_id,
                "method": method,
                "url": url,
                "headers": headers or {},
                "body": body,
            },
            ensure_ascii=False,
        )

        prefix_json = json.dumps(
            API_LAB_RESULT_PREFIX
        )

        script = r"""
(async () => {
    const request = %s;
    const prefix = %s;
    const startedAt = performance.now();

    try {
        const init = {
            method: request.method,
            headers: request.headers || {},
            credentials: "include",
            __spiderview_origin: "api_lab",
        };

        if (
            request.body
            && request.method !== "GET"
            && request.method !== "HEAD"
        ) {
            init.body = request.body;
        }

        const response = await fetch(
            request.url,
            init
        );

        const body = await response.text();

        const headers = {};

        response.headers.forEach(
            (value, name) => {
                headers[name] = value;
            }
        );

        const durationMs = (
            performance.now()
            - startedAt
        );

        console.log(
            prefix
            + JSON.stringify({
                id: request.id,
                ok: true,
                url: response.url,
                status: response.status,
                status_text: response.statusText,
                redirected: response.redirected,
                headers: headers,
                body: body.slice(0, 2000000),
                truncated: body.length > 2000000,
                duration_ms: Math.round(
                    durationMs * 100
                ) / 100,
            })
        );
    } catch (error) {
        const durationMs = (
            performance.now()
            - startedAt
        );

        console.log(
            prefix
            + JSON.stringify({
                id: request.id,
                ok: false,
                error: String(
                    error?.stack
                    || error?.message
                    || error
                ),
                duration_ms: Math.round(
                    durationMs * 100
                ) / 100,
            })
        );
    }
})();
""" % (
            request_json,
            prefix_json,
        )

        self.page.runJavaScript(
            script
        )

        return request_id

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