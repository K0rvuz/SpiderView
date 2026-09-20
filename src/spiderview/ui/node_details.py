from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..graph import (
    NodeMetrics,
    NodeVisualWeight,
    ViewNode,
)
from ..models import PageNode, Transition


class NodeDetailsPanel(QWidget):
    """
    Painel lateral de inspeção.

    Não altera o grafo. Apenas apresenta:
    - PageNode / API;
    - GroupCard virtual;
    - Transition / ViewEdge;
    - métricas estruturais calculadas pela camada graph/.
    """

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self.setMinimumWidth(
            330
        )

        self._root = QVBoxLayout(
            self
        )

        self._root.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self._root.setSpacing(
            0
        )

        # --------------------------------------------------------------
        # Header
        # --------------------------------------------------------------

        header = QWidget()

        header_layout = QVBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            14,
            12,
            14,
            12,
        )

        header_layout.setSpacing(
            3
        )

        self._title = QLabel(
            "Details"
        )

        title_font = QFont()
        title_font.setPointSize(
            11
        )
        title_font.setWeight(
            QFont.Weight.DemiBold
        )

        self._title.setFont(
            title_font
        )

        self._title.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        self._subtitle = QLabel(
            "Selecione um card ou conexão"
        )

        self._subtitle.setWordWrap(
            True
        )

        self._subtitle.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        header_layout.addWidget(
            self._title
        )

        header_layout.addWidget(
            self._subtitle
        )

        self._root.addWidget(
            header
        )

        separator = QFrame()
        separator.setFrameShape(
            QFrame.Shape.HLine
        )

        self._root.addWidget(
            separator
        )

        # --------------------------------------------------------------
        # Scroll area
        # --------------------------------------------------------------

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(
            True
        )

        self._content = QWidget()

        self._content_layout = (
            QVBoxLayout(
                self._content
            )
        )

        self._content_layout.setContentsMargins(
            10,
            10,
            10,
            16,
        )

        self._content_layout.setSpacing(
            10
        )

        self._content_layout.addStretch(
            1
        )

        self._scroll.setWidget(
            self._content
        )

        self._root.addWidget(
            self._scroll,
            stretch=1,
        )

        self._apply_theme()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def clear(
        self,
    ) -> None:
        self._title.setText(
            "Details"
        )

        self._subtitle.setText(
            "Selecione um card ou conexão"
        )

        self._clear_sections()

    def show_node(
        self,
        node: PageNode,
        *,
        metrics: NodeMetrics | None = None,
        weight: NodeVisualWeight | None = None,
    ) -> None:
        self._clear_sections()

        self._title.setText(
            node.title
        )

        self._subtitle.setText(
            f"{node.kind.value} · {node.method.upper()}"
        )

        self._add_section(
            "Resource",
            [
                (
                    "Type",
                    node.kind.value,
                ),
                (
                    "Method",
                    node.method.upper(),
                ),
                (
                    "Status",
                    (
                        str(node.status)
                        if node.status
                        is not None
                        else "—"
                    ),
                ),
                (
                    "URL",
                    node.url or "—",
                ),
                (
                    "ID",
                    node.id,
                ),
            ],
        )

        metadata = (
            node.metadata
            or {}
        )

        # API/browser observations.
        interesting = []

        request_count = (
            metadata.get(
                "request_count"
            )
        )

        if request_count is not None:
            interesting.append(
                (
                    "Requests",
                    request_count,
                )
            )

        transports = (
            metadata.get(
                "transports"
            )
        )

        if transports:
            interesting.append(
                (
                    "Transports",
                    ", ".join(
                        str(value)
                        for value
                        in transports
                    ),
                )
            )

        mapping = (
            (
                "Content-Type",
                "last_content_type",
            ),
            (
                "Duration",
                "last_duration_ms",
            ),
            (
                "Last status",
                "last_status",
            ),
            (
                "Last error",
                "last_error",
            ),
            (
                "Source URL",
                "last_source_url",
            ),
            (
                "Request URL",
                "last_request_url",
            ),
        )

        for label, key in mapping:
            value = metadata.get(
                key
            )

            if value in (
                None,
                "",
                [],
                {},
            ):
                continue

            if (
                key
                == "last_duration_ms"
            ):
                try:
                    value = (
                        f"{float(value):.2f} ms"
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    pass

            interesting.append(
                (
                    label,
                    value,
                )
            )

        if interesting:
            self._add_section(
                "HTTP / Runtime",
                interesting,
            )

        if metrics is not None:
            graph_rows = [
                (
                    "In-degree",
                    metrics.in_degree,
                ),
                (
                    "Out-degree",
                    metrics.out_degree,
                ),
                (
                    "Unique in",
                    metrics.unique_in_degree,
                ),
                (
                    "Unique out",
                    metrics.unique_out_degree,
                ),
                (
                    "Degree centrality",
                    f"{metrics.degree_centrality:.4f}",
                ),
                (
                    "Betweenness",
                    f"{metrics.betweenness_centrality:.4f}",
                ),
                (
                    "Discovery depth",
                    metrics.discovery_depth,
                ),
                (
                    "SCC size",
                    metrics.scc_size,
                ),
                (
                    "Component",
                    metrics.weak_component_index,
                ),
            ]

            if weight is not None:
                graph_rows.extend(
                    [
                        (
                            "Visual weight",
                            f"{weight.total:.2f}",
                        ),
                        (
                            "Connectivity weight",
                            f"{weight.connectivity:.2f}",
                        ),
                        (
                            "Traffic weight",
                            f"{weight.traffic:.2f}",
                        ),
                        (
                            "Centrality weight",
                            f"{weight.centrality:.2f}",
                        ),
                    ]
                )

            self._add_section(
                "Graph analysis",
                graph_rows,
            )

        if metadata:
            self._add_json_section(
                "Metadata",
                metadata,
            )

        self._finish_sections()

    def show_group(
        self,
        view_node: ViewNode,
    ) -> None:
        self._clear_sections()

        self._title.setText(
            view_node.title
        )

        group_kind = (
            view_node.group_kind
            or "group"
        )

        self._subtitle.setText(
            f"virtual group · {group_kind}"
        )

        metadata = (
            view_node.metadata
            or {}
        )

        self._add_section(
            "Group",
            [
                (
                    "Kind",
                    group_kind,
                ),
                (
                    "Members",
                    len(
                        view_node.raw_node_ids
                    ),
                ),
                (
                    "Expanded",
                    (
                        "yes"
                        if metadata.get(
                            "expanded",
                            False,
                        )
                        else "no"
                    ),
                ),
                (
                    "ID",
                    view_node.id,
                ),
            ],
        )

        summary = []

        for label, key in (
            (
                "Requests observed",
                "request_count",
            ),
            (
                "Host",
                "host",
            ),
            (
                "Path prefix",
                "path_prefix",
            ),
        ):
            value = metadata.get(
                key
            )

            if value in (
                None,
                "",
            ):
                continue

            summary.append(
                (
                    label,
                    value,
                )
            )

        for label, key in (
            (
                "Methods",
                "methods",
            ),
            (
                "Statuses",
                "statuses",
            ),
            (
                "Transports",
                "transports",
            ),
        ):
            values = metadata.get(
                key
            )

            if not values:
                continue

            summary.append(
                (
                    label,
                    self._format_mapping(
                        values
                    ),
                )
            )

        if summary:
            self._add_section(
                "Summary",
                summary,
            )

        self._add_section(
            "Raw members",
            [
                (
                    str(index + 1),
                    node_id,
                )
                for index, node_id
                in enumerate(
                    view_node.raw_node_ids
                )
            ],
        )

        if metadata:
            self._add_json_section(
                "Metadata",
                metadata,
            )

        self._finish_sections()

    def show_edge(
        self,
        transition: Transition,
        *,
        source_title: str = "",
        target_title: str = "",
    ) -> None:
        self._clear_sections()

        self._title.setText(
            transition.label
            or transition.type.value
        )

        self._subtitle.setText(
            f"transition · {transition.type.value}"
        )

        self._add_section(
            "Transition",
            [
                (
                    "Type",
                    transition.type.value,
                ),
                (
                    "Label",
                    transition.label or "—",
                ),
                (
                    "Source",
                    source_title
                    or transition.source_id,
                ),
                (
                    "Target",
                    target_title
                    or transition.target_id,
                ),
                (
                    "Source ID",
                    transition.source_id,
                ),
                (
                    "Target ID",
                    transition.target_id,
                ),
                (
                    "ID",
                    transition.id,
                ),
            ],
        )

        if transition.metadata:
            self._add_json_section(
                "Metadata",
                transition.metadata,
            )

        self._finish_sections()

    # ------------------------------------------------------------------
    # Sections
    # ------------------------------------------------------------------

    def _clear_sections(
        self,
    ) -> None:
        while (
            self._content_layout.count()
            > 0
        ):
            item = (
                self._content_layout
                .takeAt(0)
            )

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def _finish_sections(
        self,
    ) -> None:
        self._content_layout.addStretch(
            1
        )

    def _add_section(
        self,
        title: str,
        rows: list[
            tuple[str, Any]
        ],
    ) -> None:
        box = QGroupBox(
            title
        )

        form = QFormLayout(
            box
        )

        form.setContentsMargins(
            10,
            12,
            10,
            10,
        )

        form.setHorizontalSpacing(
            12
        )

        form.setVerticalSpacing(
            7
        )

        for label_text, value in rows:
            label = QLabel(
                str(label_text)
            )

            value_label = QLabel(
                str(value)
            )

            value_label.setWordWrap(
                True
            )

            value_label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )

            form.addRow(
                label,
                value_label,
            )

        self._content_layout.addWidget(
            box
        )

    def _add_json_section(
        self,
        title: str,
        data: dict,
    ) -> None:
        box = QGroupBox(
            title
        )

        layout = QVBoxLayout(
            box
        )

        layout.setContentsMargins(
            8,
            10,
            8,
            8,
        )

        editor = QPlainTextEdit()

        editor.setReadOnly(
            True
        )

        editor.setMaximumBlockCount(
            2000
        )

        editor.setPlainText(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        editor.setMinimumHeight(
            150
        )

        layout.addWidget(
            editor
        )

        self._content_layout.addWidget(
            box
        )

    @staticmethod
    def _format_mapping(
        value,
    ) -> str:
        if not isinstance(
            value,
            dict,
        ):
            return str(
                value
            )

        return " · ".join(
            f"{key} {amount}"
            for key, amount
            in sorted(
                value.items()
            )
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _apply_theme(
        self,
    ) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #181C22;
                color: #D8DEE9;
            }

            QLabel {
                background: transparent;
            }

            QGroupBox {
                background: #1E232A;
                border: 1px solid #303741;
                border-radius: 7px;
                margin-top: 9px;
                padding-top: 8px;
                font-weight: 600;
            }

            QGroupBox::title {
                subcontrol-origin: margin;
                left: 9px;
                padding: 0 4px;
                color: #E5E7EB;
            }

            QScrollArea {
                border: none;
                background: #181C22;
            }

            QPlainTextEdit {
                background: #11151A;
                color: #BCC5D0;
                border: 1px solid #303741;
                border-radius: 5px;
                padding: 6px;
                font-family: Consolas, monospace;
                font-size: 10px;
            }
            """
        )
