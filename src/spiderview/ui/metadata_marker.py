from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsObject

from ..graph.metadata import (
    STATUS_COLORS,
    STATUS_LABELS,
    node_investigation_status,
    node_tags,
)


class MetadataMarker(QGraphicsObject):
    WIDTH = 148.0
    HEIGHT = 24.0

    def __init__(self, card):
        super().__init__(card)
        self.card = card
        self.setZValue(40)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setAcceptHoverEvents(False)
        self.setPos(10.0, -11.0)
        self.refresh()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def refresh(self) -> None:
        status = node_investigation_status(self.card.node)
        tags = node_tags(self.card.node)
        self.setVisible(bool(status or tags))
        self.update()

    def paint(self, painter: QPainter, option, widget=None) -> None:
        status = node_investigation_status(self.card.node)
        tags = node_tags(self.card.node)

        if not status and not tags:
            return

        pieces: list[str] = []
        if status:
            pieces.append(STATUS_LABELS.get(status, status))
        if tags:
            pieces.append(f"#{len(tags)}")

        text = " · ".join(pieces)

        font = QFont()
        font.setPointSize(8)
        font.setWeight(QFont.Weight.DemiBold)

        metrics = QFontMetrics(font)
        text_width = min(
            self.WIDTH - 28,
            max(28, metrics.horizontalAdvance(text)),
        )

        rect = QRectF(0, 1, text_width + 26, 21)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)

        painter.fillPath(path, QColor(24, 29, 35, 235))
        painter.setPen(QPen(QColor("#3B4552"), 1))
        painter.drawPath(path)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(STATUS_COLORS.get(status, "#8A96A6")))
        painter.drawEllipse(QRectF(7, 7, 9, 9))

        painter.setFont(font)
        painter.setPen(QColor("#DCE3EB"))
        shown = metrics.elidedText(
            text,
            Qt.TextElideMode.ElideRight,
            int(text_width),
        )
        painter.drawText(
            QRectF(21, 2, text_width, 19),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            shown,
        )
