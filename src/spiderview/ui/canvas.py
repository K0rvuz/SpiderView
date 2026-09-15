from __future__ import annotations

import math

from PySide6.QtCore import (
    QPoint,
    QPointF,
    QRectF,
    QLineF,
    Qt,
    Signal,
)

from PySide6.QtGui import (
    QColor,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsScene,
    QGraphicsView,
)

from ..models import (
    PageNode,
    Transition,
)
from .edge_item import EdgeItem
from .page_card import PageCard


class SpiderCanvas(QGraphicsView):
    """
    Canvas principal do SpiderView.

    Gerencia apenas a representação visual do grafo.
    """

    nodeDoubleClicked = Signal(str)

    MIN_ZOOM = 0.15
    MAX_ZOOM = 3.5

    ZOOM_FACTOR = 1.15

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(parent)

        self._scene = QGraphicsScene(self)

        self.setScene(
            self._scene
        )

        # --------------------------------------------------------------
        # Graph registry
        # --------------------------------------------------------------

        self.nodes: dict[str, PageCard] = {}
        self.edges: dict[str, EdgeItem] = {}

        # --------------------------------------------------------------
        # View configuration
        # --------------------------------------------------------------

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate
        )

        self.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.NoAnchor
        )

        self.setResizeAnchor(
            QGraphicsView.ViewportAnchor.NoAnchor
        )

        self.setDragMode(
            QGraphicsView.DragMode.NoDrag
        )

        self.setBackgroundBrush(
            QColor("#14171C")
        )

        # Espaço inicial grande.
        #
        # A cena será expandida automaticamente
        # conforme cards forem sendo movimentados.
        self._scene.setSceneRect(
            -5000,
            -5000,
            10000,
            10000,
        )

        # --------------------------------------------------------------
        # Pan
        # --------------------------------------------------------------

        self._panning = False

        self._last_pan_point = QPoint()

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def add_node(
        self,
        node: PageNode,
    ) -> PageCard:

        if node.id in self.nodes:
            return self.nodes[node.id]

        card = PageCard(node)

        self._scene.addItem(
            card
        )

        card.setPos(
            node.x,
            node.y,
        )

        card.doubleClicked.connect(
            self._on_node_double_clicked
        )

        card.moved.connect(
            self._on_node_moved
        )

        self.nodes[node.id] = card

        self._ensure_scene_contains(
            card.sceneBoundingRect()
        )

        return card

    def remove_node(
        self,
        node_id: str,
    ) -> None:

        card = self.nodes.get(
            node_id
        )

        if card is None:
            return

        # Copiamos pois remove_edge altera
        # a lista interna do card.
        for edge in list(card.edges):

            self.remove_edge(
                edge.transition.id
            )

        self._scene.removeItem(
            card
        )

        del self.nodes[node_id]

    def get_node(
        self,
        node_id: str,
    ) -> PageCard | None:

        return self.nodes.get(
            node_id
        )

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def add_edge(
        self,
        transition: Transition,
    ) -> EdgeItem:

        if transition.id in self.edges:
            return self.edges[
                transition.id
            ]

        source = self.nodes.get(
            transition.source_id
        )

        target = self.nodes.get(
            transition.target_id
        )

        if source is None:
            raise KeyError(
                f"Source node not found: "
                f"{transition.source_id}"
            )

        if target is None:
            raise KeyError(
                f"Target node not found: "
                f"{transition.target_id}"
            )

        edge = EdgeItem(
            transition=transition,
            source=source,
            target=target,
        )

        self._scene.addItem(
            edge
        )

        self.edges[
            transition.id
        ] = edge

        return edge

    def remove_edge(
        self,
        edge_id: str,
    ) -> None:

        edge = self.edges.get(
            edge_id
        )

        if edge is None:
            return

        edge.dispose()

        self._scene.removeItem(
            edge
        )

        del self.edges[
            edge_id
        ]

    # ------------------------------------------------------------------
    # Canvas
    # ------------------------------------------------------------------

    def clear_graph(self) -> None:

        self._scene.clear()

        self.nodes.clear()
        self.edges.clear()

    def fit_graph(self) -> None:

        if not self.nodes:
            return

        rect = self._scene.itemsBoundingRect()

        rect = rect.adjusted(
            -100,
            -100,
            100,
            100,
        )

        self.fitInView(
            rect,
            Qt.AspectRatioMode.KeepAspectRatio,
        )

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    def _on_node_double_clicked(
        self,
        node_id: str,
    ) -> None:

        self.nodeDoubleClicked.emit(
            node_id
        )

    def _on_node_moved(
        self,
        node_id: str,
        position: QPointF,
    ) -> None:

        card = self.nodes.get(
            node_id
        )

        if card is None:
            return

        self._ensure_scene_contains(
            card.sceneBoundingRect()
        )

    # ------------------------------------------------------------------
    # Infinite-ish scene
    # ------------------------------------------------------------------

    def _ensure_scene_contains(
        self,
        rect: QRectF,
    ) -> None:

        margin = 2000

        expanded = rect.adjusted(
            -margin,
            -margin,
            margin,
            margin,
        )

        current = (
            self._scene.sceneRect()
        )

        if not current.contains(
            expanded
        ):

            self._scene.setSceneRect(
                current.united(expanded)
            )

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def wheelEvent(
        self,
        event: QWheelEvent,
    ) -> None:

        if event.angleDelta().y() == 0:
            return

        old_scene_pos = self.mapToScene(
            event.position().toPoint()
        )

        current_scale = (
            self.transform().m11()
        )

        if event.angleDelta().y() > 0:

            factor = self.ZOOM_FACTOR

        else:

            factor = 1 / self.ZOOM_FACTOR

        new_scale = (
            current_scale * factor
        )

        if not (
            self.MIN_ZOOM
            <= new_scale
            <= self.MAX_ZOOM
        ):
            return

        self.scale(
            factor,
            factor,
        )

        new_scene_pos = self.mapToScene(
            event.position().toPoint()
        )

        delta = (
            new_scene_pos
            - old_scene_pos
        )

        self.translate(
            delta.x(),
            delta.y(),
        )

    # ------------------------------------------------------------------
    # Pan
    # ------------------------------------------------------------------

    def mousePressEvent(
        self,
        event,
    ) -> None:

        if (
            event.button()
            == Qt.MouseButton.MiddleButton
        ):

            self._panning = True

            self._last_pan_point = (
                event.position().toPoint()
            )

            self.setCursor(
                Qt.CursorShape.ClosedHandCursor
            )

            event.accept()

            return

        super().mousePressEvent(
            event
        )

    def mouseMoveEvent(
        self,
        event,
    ) -> None:

        if self._panning:

            current = (
                event.position().toPoint()
            )

            delta = (
                current
                - self._last_pan_point
            )

            self._last_pan_point = current

            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value()
                - delta.x()
            )

            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value()
                - delta.y()
            )

            event.accept()

            return

        super().mouseMoveEvent(
            event
        )

    def mouseReleaseEvent(
        self,
        event,
    ) -> None:

        if (
            event.button()
            == Qt.MouseButton.MiddleButton
        ):

            self._panning = False

            self.unsetCursor()

            event.accept()

            return

        super().mouseReleaseEvent(
            event
        )

    # ------------------------------------------------------------------
    # Grid
    # ------------------------------------------------------------------

    def drawBackground(
        self,
        painter: QPainter,
        rect: QRectF,
    ) -> None:

        super().drawBackground(
            painter,
            rect,
        )

        zoom = self.transform().m11()

        minor_grid = 25
        major_grid = 100

        # Quando estiver muito longe,
        # não desenhamos as linhas pequenas.
        if zoom >= 0.35:

            self._draw_grid(
                painter,
                rect,
                minor_grid,
                QColor("#1C2026"),
                1,
            )

        self._draw_grid(
            painter,
            rect,
            major_grid,
            QColor("#252B33"),
            1,
        )

    @staticmethod
    def _draw_grid(
        painter: QPainter,
        rect: QRectF,
        spacing: int,
        color: QColor,
        width: int,
    ) -> None:

        left = (
            math.floor(
                rect.left() / spacing
            )
            * spacing
        )

        top = (
            math.floor(
                rect.top() / spacing
            )
            * spacing
        )

        lines: list[QLineF] = []

        x = left

        while x <= rect.right():

            lines.append(
                QLineF(
                    x,
                    rect.top(),
                    x,
                    rect.bottom(),
                )
            )

            x += spacing

        y = top

        while y <= rect.bottom():

            lines.append(
                QLineF(
                    rect.left(),
                    y,
                    rect.right(),
                    y,
                )
            )

            y += spacing

        painter.setPen(
            QPen(
                color,
                width,
            )
        )

        painter.drawLines(
            lines
        )