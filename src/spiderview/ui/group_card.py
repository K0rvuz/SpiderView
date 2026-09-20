from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import (
    QPointF,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
)

from ..graph.view_graph import ViewNode

if TYPE_CHECKING:
    from .edge_item import EdgeItem


class GroupCard(QGraphicsObject):
    """
    Supernode virtual da Investigation View.

    Não corresponde a PageNode real e nunca é persistido.
    """

    doubleClicked = Signal(str)

    WIDTH = 300.0
    HEIGHT = 178.0

    BORDER_RADIUS = 12.0

    def __init__(
        self,
        view_node: ViewNode,
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(
            parent
        )

        self.view_node = (
            view_node
        )

        self._edges: list[
            "EdgeItem"
        ] = []

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setAcceptHoverEvents(
            True
        )

        self.setZValue(
            12
        )

    def boundingRect(
        self,
    ) -> QRectF:
        return QRectF(
            0,
            0,
            self.WIDTH,
            self.HEIGHT,
        )

    def paint(
        self,
        painter: QPainter,
        option,
        widget=None,
    ) -> None:
        painter.setRenderHint(
            QPainter.RenderHint.Antialiasing,
            True,
        )

        rect = self.boundingRect()

        shadow = QPainterPath()
        shadow.addRoundedRect(
            rect.translated(
                0,
                4,
            ),
            self.BORDER_RADIUS,
            self.BORDER_RADIUS,
        )

        painter.fillPath(
            shadow,
            QColor(
                0,
                0,
                0,
                45,
            ),
        )

        card = QPainterPath()
        card.addRoundedRect(
            rect,
            self.BORDER_RADIUS,
            self.BORDER_RADIUS,
        )

        painter.fillPath(
            card,
            QColor("#20262E"),
        )

        if self.isSelected():
            border = QColor(
                "#60A5FA"
            )
            border_width = 2.5
        else:
            border = QColor(
                "#46515E"
            )
            border_width = 1.4

        painter.setPen(
            QPen(
                border,
                border_width,
            )
        )

        painter.drawPath(
            card
        )

        # Header
        header_rect = QRectF(
            0,
            0,
            self.WIDTH,
            48,
        )

        header = QPainterPath()
        header.addRoundedRect(
            header_rect,
            self.BORDER_RADIUS,
            self.BORDER_RADIUS,
        )

        painter.fillPath(
            header,
            QColor("#2A323D"),
        )

        painter.fillRect(
            QRectF(
                0,
                48
                - self.BORDER_RADIUS,
                self.WIDTH,
                self.BORDER_RADIUS,
            ),
            QColor("#2A323D"),
        )

        title_font = QFont()
        title_font.setPointSize(
            10
        )
        title_font.setWeight(
            QFont.Weight.DemiBold
        )

        painter.setFont(
            title_font
        )
        painter.setPen(
            QColor("#F3F4F6")
        )

        painter.drawText(
            QRectF(
                14,
                9,
                self.WIDTH - 92,
                28,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            self.view_node.title,
        )

        count = int(
            self.view_node.metadata.get(
                "count",
                len(
                    self.view_node.raw_node_ids
                ),
            )
            or len(
                self.view_node.raw_node_ids
            )
        )

        badge_rect = QRectF(
            self.WIDTH - 68,
            11,
            52,
            24,
        )

        painter.setPen(
            Qt.PenStyle.NoPen
        )

        painter.setBrush(
            QColor("#3B82F6")
        )

        painter.drawRoundedRect(
            badge_rect,
            5,
            5,
        )

        badge_font = QFont()
        badge_font.setPointSize(
            8
        )
        badge_font.setWeight(
            QFont.Weight.Bold
        )

        painter.setFont(
            badge_font
        )
        painter.setPen(
            QColor("#FFFFFF")
        )

        painter.drawText(
            badge_rect,
            Qt.AlignmentFlag.AlignCenter,
            str(count),
        )

        # Body
        body_font = QFont()
        body_font.setPointSize(
            8
        )

        painter.setFont(
            body_font
        )
        painter.setPen(
            QColor("#B7C0CC")
        )

        if (
            self.view_node.group_kind
            == "api"
        ):
            lines = self._api_lines()
        elif (
            self.view_node.group_kind
            == "redirect"
        ):
            lines = [
                f"{count} intermediate redirects",
                "Double click to expand",
            ]
        else:
            lines = [
                f"{count} grouped nodes",
                "Double click to expand",
            ]

        y = 62.0

        for line in lines[
            :4
        ]:
            painter.drawText(
                QRectF(
                    16,
                    y,
                    self.WIDTH - 32,
                    20,
                ),
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignVCenter,
                line,
            )

            y += 23.0

        # Footer
        painter.setPen(
            QPen(
                QColor("#38424E"),
                1,
            )
        )

        painter.drawLine(
            QPointF(
                12,
                self.HEIGHT - 34,
            ),
            QPointF(
                self.WIDTH - 12,
                self.HEIGHT - 34,
            ),
        )

        painter.setPen(
            QColor("#93A0B0")
        )

        expanded = bool(
            self.view_node.metadata.get(
                "expanded",
                False,
            )
        )

        action_text = (
            "double click: collapse"
            if expanded
            else "double click: expand"
        )

        painter.drawText(
            QRectF(
                16,
                self.HEIGHT - 29,
                170,
                20,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            action_text,
        )

        painter.drawText(
            QRectF(
                self.WIDTH - 100,
                self.HEIGHT - 29,
                84,
                20,
            ),
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter,
            "group",
        )

    def _api_lines(
        self,
    ) -> list[str]:
        metadata = (
            self.view_node.metadata
        )

        methods = (
            metadata.get(
                "methods",
                {},
            )
            or {}
        )

        statuses = (
            metadata.get(
                "statuses",
                {},
            )
            or {}
        )

        transports = (
            metadata.get(
                "transports",
                {},
            )
            or {}
        )

        requests = int(
            metadata.get(
                "request_count",
                0,
            )
            or 0
        )

        method_text = "  ".join(
            f"{method} {count}"
            for method, count
            in sorted(
                methods.items()
            )
        )

        status_text = "  ".join(
            f"{status} {count}"
            for status, count
            in sorted(
                statuses.items()
            )
        )

        transport_text = "  ".join(
            f"{name} {count}"
            for name, count
            in sorted(
                transports.items()
            )
        )

        lines = []

        if requests:
            lines.append(
                f"Requests observed: {requests}"
            )

        if method_text:
            lines.append(
                method_text
            )

        if status_text:
            lines.append(
                status_text
            )

        if transport_text:
            lines.append(
                transport_text
            )

        if not lines:
            lines.append(
                "API request group"
            )

        return lines

    def attach_edge(
        self,
        edge: "EdgeItem",
    ) -> None:
        if edge not in self._edges:
            self._edges.append(
                edge
            )

    def detach_edge(
        self,
        edge: "EdgeItem",
    ) -> None:
        if edge in self._edges:
            self._edges.remove(
                edge
            )

    @property
    def edges(
        self,
    ) -> tuple[
        "EdgeItem",
        ...
    ]:
        return tuple(
            self._edges
        )

    def mouseDoubleClickEvent(
        self,
        event,
    ) -> None:
        self.doubleClicked.emit(
            self.view_node.id
        )

        event.accept()

    def itemChange(
        self,
        change,
        value,
    ):
        result = super().itemChange(
            change,
            value,
        )

        if (
            change
            == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
        ):
            for edge in (
                self._edges
            ):
                edge.update_path()

        return result
