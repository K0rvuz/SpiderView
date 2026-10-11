from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView


class MiniMapView(QGraphicsView):
    """Navigation overview that stays visible above the canvas viewport."""

    def __init__(self, scene: QGraphicsScene, canvas, parent=None):
        super().__init__(scene, parent)
        self._canvas = canvas
        self.setFixedSize(230, 154)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.RenderHint.Antialiasing)
        self.setInteractive(False)
        self.setBackgroundBrush(QColor("#111827"))
        self.setStyleSheet(
            "QGraphicsView { background-color: #111827; "
            "border: 1px solid #52627A; border-radius: 8px; }"
        )
        self.setToolTip("Mapa geral — clique para navegar")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def refresh(self, *_args) -> None:
        rect = self._canvas._visible_graph_rect()
        if rect is None or rect.isEmpty():
            self.viewport().update()
            return
        padding = max(90.0, min(rect.width(), rect.height()) * 0.06)
        rect = rect.adjusted(-padding, -padding, padding, padding)
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
        painter.save()
        pen = QPen(QColor("#55D6FF"), 2.0)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(visible)
        painter.restore()

    def mousePressEvent(self, event) -> None:
        point = self.mapToScene(event.position().toPoint())
        self._canvas.centerOn(point)
        self._canvas.viewport().update()
        self.refresh()
        event.accept()
