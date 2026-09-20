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

from ..graph.view_graph import ViewGraph
from ..models import (
    PageNode,
    Transition,
)
from .edge_item import EdgeItem
from .group_card import GroupCard
from .page_card import PageCard


class SpiderCanvas(QGraphicsView):
    """
    Canvas principal do SpiderView.

    self.nodes/self.edges:
        grafo REAL.

    self.view_groups/self.view_edges:
        projeção virtual da Investigation View.
        Nunca deve ser persistida.
    """

    nodeDoubleClicked = Signal(str)
    groupDoubleClicked = Signal(str)

    # Zoom manual normal.
    MIN_ZOOM = 0.08
    MAX_ZOOM = 4.5

    # Fit Graph pode precisar ir abaixo do zoom manual para enquadrar
    # grafos muito grandes, mas o wheelEvent saberá sair dessa faixa.
    FIT_MIN_ZOOM = 0.012

    ZOOM_FACTOR = 1.15

    # Labels somem quando o grafo está muito afastado.
    EDGE_LABEL_MIN_ZOOM = 0.58

    def __init__(
        self,
        parent=None,
    ):
        super().__init__(
            parent
        )

        self._scene = (
            QGraphicsScene(
                self
            )
        )

        self.setScene(
            self._scene
        )

        # --------------------------------------------------------------
        # Raw graph registry
        # --------------------------------------------------------------

        self.nodes: dict[
            str,
            PageCard,
        ] = {}

        self.edges: dict[
            str,
            EdgeItem,
        ] = {}

        # --------------------------------------------------------------
        # Virtual view registry
        # --------------------------------------------------------------

        self.view_groups: dict[
            str,
            GroupCard,
        ] = {}

        self.view_edges: dict[
            str,
            EdgeItem,
        ] = {}

        self._active_view_graph: (
            ViewGraph
            | None
        ) = None

        # --------------------------------------------------------------
        # View configuration
        # --------------------------------------------------------------

        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )

        # Mantém a correção do ghosting/resíduos visuais.
        self.setViewportUpdateMode(
            QGraphicsView.ViewportUpdateMode.FullViewportUpdate
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

        # Cena inicial menor. Ela cresce automaticamente conforme
        # o grafo ocupa mais espaço.
        self._scene.setSceneRect(
            -3000,
            -3000,
            6000,
            6000,
        )

        self._panning = False
        self._last_pan_point = (
            QPoint()
        )

    # ------------------------------------------------------------------
    # Raw Nodes
    # ------------------------------------------------------------------

    def add_node(
        self,
        node: PageNode,
    ) -> PageCard:
        if node.id in self.nodes:
            return self.nodes[
                node.id
            ]

        card = PageCard(
            node
        )

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

        self.nodes[
            node.id
        ] = card

        if self._active_view_graph is not None:
            card.set_position_persistence_enabled(
                False
            )

            card.setVisible(
                False
            )

        self._ensure_scene_contains(
            card.sceneBoundingRect()
        )

        return card

    def remove_node(
        self,
        node_id: str,
    ) -> None:
        # Uma view virtual fica inválida assim que
        # o raw graph sofre mutação estrutural.
        if self._active_view_graph is not None:
            self.clear_virtual_view()

        card = self.nodes.get(
            node_id
        )

        if card is None:
            return

        for edge in list(
            card.edges
        ):
            self.remove_edge(
                edge.transition.id
            )

        self._scene.removeItem(
            card
        )

        del self.nodes[
            node_id
        ]

    def get_node(
        self,
        node_id: str,
    ) -> PageCard | None:
        return self.nodes.get(
            node_id
        )

    # ------------------------------------------------------------------
    # Raw Edges
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
                "Source node not found: "
                f"{transition.source_id}"
            )

        if target is None:
            raise KeyError(
                "Target node not found: "
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

        if self._active_view_graph is not None:
            edge.setVisible(
                False
            )

        self._update_edge_label_lod()

        return edge

    def remove_edge(
        self,
        edge_id: str,
    ) -> None:
        if self._active_view_graph is not None:
            self.clear_virtual_view()

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
    # Investigation View
    # ------------------------------------------------------------------

    @property
    def virtual_view_active(
        self,
    ) -> bool:
        return (
            self._active_view_graph
            is not None
        )

    def clear_virtual_view(
        self,
    ) -> None:
        """
        Remove somente a projeção da Investigation View.

        Também restaura cada PageCard para PageNode.x/y.
        Como posições de Investigation nunca são persistidas,
        Tree/Graph/Raw voltam exatamente ao layout real anterior.
        """

        # Virtual edges primeiro, porque estão presas aos cards.
        for edge in list(
            self.view_edges.values()
        ):
            edge.dispose()

            if (
                edge.scene()
                is self._scene
            ):
                self._scene.removeItem(
                    edge
                )

        self.view_edges.clear()

        for card in list(
            self.view_groups.values()
        ):
            if (
                card.scene()
                is self._scene
            ):
                self._scene.removeItem(
                    card
                )

        self.view_groups.clear()

        # Restaura raw graph e suas coordenadas persistidas.
        for card in (
            self.nodes.values()
        ):
            card.set_position_persistence_enabled(
                False
            )

            card.restore_persisted_position()

            card.setVisible(
                True
            )

            card.set_position_persistence_enabled(
                True
            )

        for edge in (
            self.edges.values()
        ):
            edge.setVisible(
                True
            )

            edge.update_path()

        self._active_view_graph = (
            None
        )

        self._update_edge_label_lod()
        self.viewport().update()

    def apply_view_graph(
        self,
        view_graph: ViewGraph,
        positions: dict[
            str,
            tuple[float, float],
        ],
    ) -> None:
        """
        Aplica uma projeção virtual sobre o raw graph.

        Nenhum PageNode ou Transition real é removido.
        """

        self.clear_virtual_view()

        self._active_view_graph = (
            view_graph
        )

        visible_real_ids = {
            view_node.raw_node_ids[0]
            for view_node
            in view_graph.nodes.values()
            if view_node.is_real
        }

        # Raw cards entram em modo de posição visual.
        #
        # Arrastar ou reorganizar enquanto Investigation estiver
        # ativa NÃO altera PageNode.x/y.
        for node_id, card in (
            self.nodes.items()
        ):
            card.set_position_persistence_enabled(
                False
            )

            visible = (
                node_id
                in visible_real_ids
            )

            card.setVisible(
                visible
            )

            if (
                visible
                and node_id
                in positions
            ):
                x, y = positions[
                    node_id
                ]

                card.set_visual_position(
                    x,
                    y,
                )

        # Raw edges ficam completamente ocultas.
        #
        # A Investigation View desenha suas próprias edges para
        # manter styling e rastreabilidade separados do grafo real.
        for edge in (
            self.edges.values()
        ):
            edge.setVisible(
                False
            )

        # Create group cards.
        for view_node in (
            view_graph.nodes.values()
        ):
            if not view_node.is_group:
                continue

            card = GroupCard(
                view_node
            )

            self._scene.addItem(
                card
            )

            card.doubleClicked.connect(
                self._on_group_double_clicked
            )

            if (
                view_node.id
                in positions
            ):
                x, y = positions[
                    view_node.id
                ]

                card.setPos(
                    x,
                    y,
                )

            self.view_groups[
                view_node.id
            ] = card

            self._ensure_scene_contains(
                card.sceneBoundingRect()
            )

        # View edges.
        #
        # Mesmo uma relation real-real recebe um EdgeItem virtual.
        # Isso impede a Investigation View de alterar styling/estado
        # do EdgeItem pertencente ao Raw Graph.
        for view_edge in (
            view_graph.edges.values()
        ):
            if view_edge.layout_only:
                continue

            source_item = (
                self._view_item(
                    view_edge.source_id
                )
            )

            target_item = (
                self._view_item(
                    view_edge.target_id
                )
            )

            if (
                source_item is None
                or target_item is None
            ):
                continue

            transition = Transition(
                id=view_edge.id,
                source_id=(
                    view_edge.source_id
                ),
                target_id=(
                    view_edge.target_id
                ),
                type=view_edge.type,
                label=view_edge.label,
                metadata=dict(
                    view_edge.metadata
                ),
            )

            edge = EdgeItem(
                transition=transition,
                source=source_item,
                target=target_item,
            )

            self._scene.addItem(
                edge
            )

            self.view_edges[
                view_edge.id
            ] = edge

        self.grow_scene_to_graph()

        self._update_edge_label_lod()
        self.viewport().update()

    def _view_item(
        self,
        view_id: str,
    ):
        if view_id in (
            self.nodes
        ):
            card = self.nodes[
                view_id
            ]

            if card.isVisible():
                return card

        return self.view_groups.get(
            view_id
        )

    # ------------------------------------------------------------------
    # Canvas
    # ------------------------------------------------------------------

    def clear_graph(self) -> None:
        self.clear_virtual_view()

        self._scene.clear()

        self.nodes.clear()
        self.edges.clear()

        self.view_groups.clear()
        self.view_edges.clear()

    def fit_graph(self) -> None:
        """
        Enquadra apenas os itens visíveis sem deixar o zoom preso.

        QGraphicsView.fitInView() pode gerar uma escala menor que o
        MIN_ZOOM. O wheelEvent antigo então recusava qualquer tentativa
        de zoom porque a nova escala ainda permanecia fora da faixa.

        Aqui calculamos a escala explicitamente e mantemos um limite
        separado para Fit Graph.
        """

        rect = self._visible_graph_rect()

        if rect is None:
            return

        rect = rect.adjusted(
            -120,
            -120,
            120,
            120,
        )

        self._ensure_scene_contains(
            rect
        )

        viewport_rect = (
            self.viewport().rect()
        )

        viewport_width = max(
            1.0,
            float(
                viewport_rect.width()
            ),
        )

        viewport_height = max(
            1.0,
            float(
                viewport_rect.height()
            ),
        )

        scene_width = max(
            1.0,
            rect.width(),
        )

        scene_height = max(
            1.0,
            rect.height(),
        )

        scale_x = (
            viewport_width
            / scene_width
        )

        scale_y = (
            viewport_height
            / scene_height
        )

        target_scale = min(
            scale_x,
            scale_y,
            self.MAX_ZOOM,
        )

        target_scale = max(
            self.FIT_MIN_ZOOM,
            target_scale,
        )

        self.resetTransform()

        self.scale(
            target_scale,
            target_scale,
        )

        self.centerOn(
            rect.center()
        )

        self._update_edge_label_lod()

    def _visible_graph_rect(
        self,
    ) -> QRectF | None:
        visible_items = [
            item
            for item
            in self._scene.items()
            if (
                item.isVisible()
                and item.parentItem()
                is None
            )
        ]

        if not visible_items:
            return None

        rect: QRectF | None = None

        for item in visible_items:
            item_rect = (
                item.sceneBoundingRect()
            )

            if rect is None:
                rect = QRectF(
                    item_rect
                )
            else:
                rect = rect.united(
                    item_rect
                )

        return rect

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

    def _on_group_double_clicked(
        self,
        group_id: str,
    ) -> None:
        self.groupDoubleClicked.emit(
            group_id
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
        """
        Expande a cena progressivamente conforme o grafo cresce.

        A cena nunca encolhe durante a sessão. Quando precisamos
        crescer, reservamos espaço adicional proporcional ao tamanho
        já ocupado para evitar expansão a cada pequeno movimento.
        """

        current = (
            self._scene
            .sceneRect()
        )

        graph_span = max(
            rect.width(),
            rect.height(),
            1.0,
        )

        current_span = max(
            current.width(),
            current.height(),
            1.0,
        )

        padding = max(
            1200.0,
            graph_span * 0.22,
            current_span * 0.08,
        )

        expanded = rect.adjusted(
            -padding,
            -padding,
            padding,
            padding,
        )

        if current.contains(
            expanded
        ):
            return

        grown = current.united(
            expanded
        )

        reserve = max(
            800.0,
            max(
                grown.width(),
                grown.height(),
            )
            * 0.10,
        )

        grown = grown.adjusted(
            -reserve,
            -reserve,
            reserve,
            reserve,
        )

        self._scene.setSceneRect(
            grown
        )

    def grow_scene_to_graph(
        self,
    ) -> None:
        rect = self._visible_graph_rect()

        if rect is None:
            return

        self._ensure_scene_contains(
            rect
        )

    # ------------------------------------------------------------------
    # Edge label LOD
    # ------------------------------------------------------------------

    def _update_edge_label_lod(
        self,
    ) -> None:
        zoom = (
            self.transform()
            .m11()
        )

        visible = (
            zoom
            >= self.EDGE_LABEL_MIN_ZOOM
        )

        for edge in (
            list(
                self.edges.values()
            )
            + list(
                self.view_edges.values()
            )
        ):
            edge.set_label_visible(
                visible
            )

    # ------------------------------------------------------------------
    # Zoom
    # ------------------------------------------------------------------

    def wheelEvent(
        self,
        event: QWheelEvent,
    ) -> None:
        delta_y = (
            event.angleDelta().y()
        )

        if delta_y == 0:
            return

        mouse_pos = (
            event.position().toPoint()
        )

        old_scene_pos = (
            self.mapToScene(
                mouse_pos
            )
        )

        current_scale = abs(
            self.transform().m11()
        )

        if current_scale <= 0:
            current_scale = 1.0

        if delta_y > 0:
            # Se Fit Graph nos colocou abaixo do MIN_ZOOM, um único
            # scroll para cima já volta à faixa manual normal.
            if (
                current_scale
                < self.MIN_ZOOM
            ):
                target_scale = (
                    self.MIN_ZOOM
                )
            else:
                target_scale = min(
                    self.MAX_ZOOM,
                    current_scale
                    * self.ZOOM_FACTOR,
                )

        else:
            # Zoom-out manual pode chegar até o limite de Fit Graph.
            target_scale = max(
                self.FIT_MIN_ZOOM,
                current_scale
                / self.ZOOM_FACTOR,
            )

        if math.isclose(
            target_scale,
            current_scale,
            rel_tol=1e-9,
            abs_tol=1e-12,
        ):
            return

        factor = (
            target_scale
            / current_scale
        )

        self.scale(
            factor,
            factor,
        )

        new_scene_pos = (
            self.mapToScene(
                mouse_pos
            )
        )

        delta = (
            new_scene_pos
            - old_scene_pos
        )

        self.translate(
            delta.x(),
            delta.y(),
        )

        self._update_edge_label_lod()

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
            self._panning = (
                True
            )

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

            self._last_pan_point = (
                current
            )

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
            self._panning = (
                False
            )

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

        zoom = (
            self.transform()
            .m11()
        )

        minor_grid = 25
        major_grid = 100

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
                rect.left()
                / spacing
            )
            * spacing
        )

        top = (
            math.floor(
                rect.top()
                / spacing
            )
            * spacing
        )

        lines: list[
            QLineF
        ] = []

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
