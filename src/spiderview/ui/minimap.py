from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView


class MiniMapView(QGraphicsView):
    """Small navigation overview that shares the SpiderCanvas scene."""

    def __init__(self, scene: QGraphicsScene, canvas, parent=None):
        super().__init__(scene, parent)
        self._canvas = canvas
        self.setFixedSize(220, 148)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setInteractive(False)
        self.setStyleSheet(
            "QGraphicsView { background: rgba(17, 24, 39, 235); "
            "border: 1px solid #42516A; border-radius: 8px; }"
        )
        self.setToolTip("Mapa geral — clique para navegar")
        self.refresh()

    def refresh(self) -> None:
        rect = self._canvas._visible_graph_rect()
        if rect is None or rect.isEmpty():
            return
        rect = rect.adjusted(-PagePadding.VALUE, -PagePadding.VALUE,
                             PagePadding.VALUE, PagePadding.VALUE)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        self.viewport().update()

    def drawForeground(self, painter: QPainter, rect) -> None:
        super().drawForeground(painter, rect)
        try:
            visible = self._canvas.mapToScene(
                self._canvas.viewport().rect()
            ).boundingRect()
        except RuntimeError:
            return
        pen = QPen(QColor("#55D6FF"), 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(visible)

    def mousePressEvent(self, event) -> None:
        point = self.mapToScene(event.position().toPoint())
        self._canvas.centerOn(point)
        self._canvas.viewport().update()
        self.refresh()
        event.accept()


class PagePadding:
    VALUE = 90.0
