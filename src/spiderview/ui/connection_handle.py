from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsObject


class ConnectionHandle(QGraphicsObject):
    connectionStarted = Signal(str, QPointF)

    RADIUS = 7.0
    HIT_RADIUS = 15.0

    def __init__(self, card):
        super().__init__(card)
        self.card = card
        self._hovered = False

        rect = card.boundingRect()
        self.setPos(rect.width() - 15.0, rect.height() / 2.0)
        self.setZValue(45)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def boundingRect(self) -> QRectF:
        r = self.HIT_RADIUS
        return QRectF(-r, -r, r * 2, r * 2)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        painter.setPen(QPen(QColor("#15191E"), 2))
        painter.setBrush(QColor("#70A8E8" if self._hovered else "#56687D"))
        painter.drawEllipse(QPointF(0, 0), self.RADIUS, self.RADIUS)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F4F7FA"))
        painter.drawEllipse(QPointF(0, 0), 2.5, 2.5)

    def hoverEnterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        self.connectionStarted.emit(
            self.card.node.id,
            event.scenePos(),
        )
        event.accept()
