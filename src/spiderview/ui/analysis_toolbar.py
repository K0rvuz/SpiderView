from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import (
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QAction,
)
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QLineEdit,
    QMenu,
    QSpinBox,
    QToolBar,
    QToolButton,
)

from ..graph.query import (
    DEFAULT_METHODS,
    DEFAULT_NODE_KINDS,
    DEFAULT_ORIGINS,
    DEFAULT_STATUS_FAMILIES,
    DEFAULT_TRANSPORTS,
    ViewQuery,
)
from ..models import NodeKind


class AnalysisToolbar(QToolBar):
    """
    Barra de consulta do canvas.

    Ordem:
        Focus
        Nodes
        HTTP
        Transport
        Origin
        Search
    """

    queryChanged = Signal(object)
    focusRequested = Signal()
    focusCleared = Signal()

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            "Analysis",
            parent,
        )

        self.setMovable(
            False
        )

        self._updating = False

        # --------------------------------------------------------------
        # Focus
        # --------------------------------------------------------------

        self._focus_button = (
            QToolButton()
        )

        self._focus_button.setText(
            "Focus"
        )

        self._focus_button.setCheckable(
            True
        )

        self._focus_button.toggled.connect(
            self._on_focus_toggled
        )

        self.addWidget(
            self._focus_button
        )

        self._focus_direction = (
            QComboBox()
        )

        self._focus_direction.addItem(
            "Both",
            "both",
        )

        self._focus_direction.addItem(
            "Outgoing",
            "outgoing",
        )

        self._focus_direction.addItem(
            "Incoming",
            "incoming",
        )

        self._focus_direction.currentIndexChanged.connect(
            self._emit_query
        )

        self.addWidget(
            self._focus_direction
        )

        self._focus_hops = (
            QSpinBox()
        )

        self._focus_hops.setRange(
            1,
            8,
        )

        self._focus_hops.setValue(
            2
        )

        self._focus_hops.setSuffix(
            " hops"
        )

        self._focus_hops.valueChanged.connect(
            self._emit_query
        )

        self.addWidget(
            self._focus_hops
        )

        self.addSeparator()

        # --------------------------------------------------------------
        # Node filters
        # --------------------------------------------------------------

        (
            self._node_button,
            self._node_actions,
        ) = self._build_check_menu(
            "Nodes",
            [
                (
                    "Page",
                    NodeKind.PAGE,
                    True,
                ),
                (
                    "API",
                    NodeKind.API,
                    True,
                ),
                (
                    "DOM State",
                    NodeKind.DOM_STATE,
                    True,
                ),
                (
                    "Group",
                    "group",
                    True,
                ),
                (
                    "Note",
                    NodeKind.NOTE,
                    True,
                ),
            ],
        )

        self.addWidget(
            self._node_button
        )

        # --------------------------------------------------------------
        # HTTP
        # --------------------------------------------------------------

        self._http_button = (
            QToolButton()
        )

        self._http_button.setText(
            "HTTP"
        )

        self._http_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        self._http_menu = QMenu(
            self._http_button
        )

        self._method_actions: dict[
            str,
            QAction,
        ] = {}

        for method in (
            "GET",
            "POST",
            "PUT",
            "PATCH",
            "DELETE",
        ):
            action = QAction(
                method,
                self._http_menu,
            )

            action.setCheckable(
                True
            )

            action.setChecked(
                True
            )

            action.toggled.connect(
                self._on_option_changed
            )

            self._http_menu.addAction(
                action
            )

            self._method_actions[
                method
            ] = action

        self._http_menu.addSeparator()

        self._status_actions: dict[
            str,
            QAction,
        ] = {}

        for family in (
            "2xx",
            "3xx",
            "4xx",
            "5xx",
        ):
            action = QAction(
                family,
                self._http_menu,
            )

            action.setCheckable(
                True
            )

            action.setChecked(
                True
            )

            action.toggled.connect(
                self._on_option_changed
            )

            self._http_menu.addAction(
                action
            )

            self._status_actions[
                family
            ] = action

        self._http_button.setMenu(
            self._http_menu
        )

        self.addWidget(
            self._http_button
        )

        # --------------------------------------------------------------
        # Transport
        # --------------------------------------------------------------

        (
            self._transport_button,
            self._transport_actions,
        ) = self._build_check_menu(
            "Transport",
            [
                (
                    "navigation",
                    "navigation",
                    True,
                ),
                (
                    "click",
                    "click",
                    True,
                ),
                (
                    "form",
                    "form",
                    True,
                ),
                (
                    "XHR",
                    "xhr",
                    True,
                ),
                (
                    "fetch",
                    "fetch",
                    True,
                ),
                (
                    "redirect",
                    "redirect",
                    True,
                ),
            ],
        )

        self.addWidget(
            self._transport_button
        )

        # --------------------------------------------------------------
        # Origin
        # --------------------------------------------------------------

        (
            self._origin_button,
            self._origin_actions,
        ) = self._build_check_menu(
            "Origin",
            [
                (
                    "first-party",
                    "first-party",
                    True,
                ),
                (
                    "third-party",
                    "third-party",
                    True,
                ),
            ],
        )

        self.addWidget(
            self._origin_button
        )

        self.addSeparator()

        # --------------------------------------------------------------
        # Search
        # --------------------------------------------------------------

        search_label = QLabel(
            "Search:"
        )

        self.addWidget(
            search_label
        )

        self._search = QLineEdit()

        self._search.setPlaceholderText(
            "URL, title, endpoint, domain…"
        )

        self._search.setClearButtonEnabled(
            True
        )

        self._search.setMinimumWidth(
            240
        )

        self.addWidget(
            self._search
        )

        self._search_timer = QTimer(
            self
        )

        self._search_timer.setSingleShot(
            True
        )

        self._search_timer.setInterval(
            220
        )

        self._search_timer.timeout.connect(
            self._emit_query
        )

        self._search.textChanged.connect(
            self._restart_search_timer
        )

        # --------------------------------------------------------------
        # Reset
        # --------------------------------------------------------------

        reset_button = (
            QToolButton()
        )

        reset_button.setText(
            "Reset"
        )

        reset_button.clicked.connect(
            self.reset_filters
        )

        self.addWidget(
            reset_button
        )

        self._refresh_button_labels()

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    def _build_check_menu(
        self,
        title: str,
        entries: list[
            tuple[
                str,
                object,
                bool,
            ]
        ],
    ) -> tuple[
        QToolButton,
        dict[
            object,
            QAction,
        ],
    ]:
        button = QToolButton()

        button.setText(
            title
        )

        button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        menu = QMenu(
            button
        )

        actions: dict[
            object,
            QAction,
        ] = {}

        for (
            label,
            value,
            checked,
        ) in entries:
            action = QAction(
                label,
                menu,
            )

            action.setCheckable(
                True
            )

            action.setChecked(
                checked
            )

            action.toggled.connect(
                self._on_option_changed
            )

            menu.addAction(
                action
            )

            actions[
                value
            ] = action

        button.setMenu(
            menu
        )

        return (
            button,
            actions,
        )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def query(
        self,
    ) -> ViewQuery:
        node_kinds = frozenset(
            value
            for value, action
            in self._node_actions.items()
            if (
                value != "group"
                and action.isChecked()
            )
        )

        show_groups = (
            self._node_actions[
                "group"
            ].isChecked()
        )

        methods = frozenset(
            method
            for method, action
            in self._method_actions.items()
            if action.isChecked()
        )

        statuses = frozenset(
            family
            for family, action
            in self._status_actions.items()
            if action.isChecked()
        )

        transports = frozenset(
            transport
            for transport, action
            in self._transport_actions.items()
            if action.isChecked()
        )

        origins = frozenset(
            origin
            for origin, action
            in self._origin_actions.items()
            if action.isChecked()
        )

        return ViewQuery(
            focus_enabled=(
                self._focus_button
                .isChecked()
            ),

            focus_hops=(
                self._focus_hops
                .value()
            ),

            focus_direction=(
                self._focus_direction
                .currentData()
            ),

            node_kinds=node_kinds,

            show_groups=(
                show_groups
            ),

            methods=methods,

            status_families=(
                statuses
            ),

            transports=(
                transports
            ),

            origins=origins,

            search_text=(
                self._search.text()
            ),
        )

    def set_focus_checked(
        self,
        checked: bool,
        *,
        emit: bool = False,
    ) -> None:
        previous = (
            self._focus_button
            .blockSignals(
                not emit
            )
        )

        self._focus_button.setChecked(
            checked
        )

        if not emit:
            self._focus_button.blockSignals(
                previous
            )

        self._refresh_button_labels()

    def reset_filters(
        self,
        *,
        emit: bool = True,
    ) -> None:
        self._updating = True

        try:
            self._focus_button.setChecked(
                False
            )

            self._focus_direction.setCurrentIndex(
                0
            )

            self._focus_hops.setValue(
                2
            )

            for action in (
                self._node_actions.values()
            ):
                action.setChecked(
                    True
                )

            for action in (
                self._method_actions.values()
            ):
                action.setChecked(
                    True
                )

            for action in (
                self._status_actions.values()
            ):
                action.setChecked(
                    True
                )

            for action in (
                self._transport_actions.values()
            ):
                action.setChecked(
                    True
                )

            for action in (
                self._origin_actions.values()
            ):
                action.setChecked(
                    True
                )

            self._search.clear()

        finally:
            self._updating = False

        self._refresh_button_labels()

        if emit:
            self.focusCleared.emit()

            self.queryChanged.emit(
                self.query()
            )

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _on_focus_toggled(
        self,
        checked: bool,
    ) -> None:
        self._refresh_button_labels()

        if self._updating:
            return

        if checked:
            self.focusRequested.emit()
        else:
            self.focusCleared.emit()

        self.queryChanged.emit(
            self.query()
        )

    def _on_option_changed(
        self,
        _checked: bool,
    ) -> None:
        self._refresh_button_labels()
        self._emit_query()

    def _restart_search_timer(
        self,
        _text: str,
    ) -> None:
        if self._updating:
            return

        self._search_timer.start()

    def _emit_query(
        self,
        *_args,
    ) -> None:
        if self._updating:
            return

        self._refresh_button_labels()

        self.queryChanged.emit(
            self.query()
        )

    # ------------------------------------------------------------------
    # Labels
    # ------------------------------------------------------------------

    def _refresh_button_labels(
        self,
    ) -> None:
        node_checked = sum(
            1
            for action
            in self._node_actions.values()
            if action.isChecked()
        )

        self._node_button.setText(
            f"Nodes {node_checked}/5"
        )

        method_checked = sum(
            1
            for action
            in self._method_actions.values()
            if action.isChecked()
        )

        status_checked = sum(
            1
            for action
            in self._status_actions.values()
            if action.isChecked()
        )

        self._http_button.setText(
            f"HTTP {method_checked + status_checked}/9"
        )

        transport_checked = sum(
            1
            for action
            in self._transport_actions.values()
            if action.isChecked()
        )

        self._transport_button.setText(
            f"Transport {transport_checked}/6"
        )

        origin_checked = sum(
            1
            for action
            in self._origin_actions.values()
            if action.isChecked()
        )

        self._origin_button.setText(
            f"Origin {origin_checked}/2"
        )

        if (
            self._focus_button
            .isChecked()
        ):
            self._focus_button.setText(
                "Focus ON"
            )
        else:
            self._focus_button.setText(
                "Focus"
            )
