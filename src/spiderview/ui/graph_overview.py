from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from ..models import NodeKind


class GraphOverviewWidget(QWidget):
    """Abstract graph overview and path metrics, independent from QGraphicsScene."""

    def __init__(self, canvas, parent=None):
        super().__init__(parent)
        self._canvas = canvas
        self.setMinimumSize(220, 220)
        self.setMouseTracking(True)
        self.setToolTip("Visão geral do grafo — clique para centralizar")
        self.setStyleSheet("background: #0B1423; color: #E2E8F0;")

    def _snapshot(self):
        items = {}
        for node_id, card in self._canvas.nodes.items():
            if card.isVisible():
                items[node_id] = card
        for node_id, card in self._canvas.view_groups.items():
            if card.isVisible():
                items[node_id] = card

        edges = []
        seen = set()
        for edge_map in (self._canvas.edges, self._canvas.view_edges):
            for edge_id, edge in edge_map.items():
                if edge_id in seen or not edge.isVisible():
                    continue
                source_id = edge.transition.source_id
                target_id = edge.transition.target_id
                if source_id in items and target_id in items:
                    edges.append((edge_id, source_id, target_id))
                    seen.add(edge_id)
        return items, edges

    def _layout_snapshot(self):
        items, edges = self._snapshot()
        centers = {
            node_id: card.sceneBoundingRect().center()
            for node_id, card in items.items()
        }
        if not centers:
            return items, edges, centers, QRectF()
        xs = [p.x() for p in centers.values()]
        ys = [p.y() for p in centers.values()]
        bounds = QRectF(
            min(xs), min(ys),
            max(1.0, max(xs) - min(xs)),
            max(1.0, max(ys) - min(ys)),
        )
        padding = max(50.0, min(bounds.width(), bounds.height()) * 0.08)
        return items, edges, centers, bounds.adjusted(-padding, -padding, padding, padding)

    def _metrics(self, items, edges):
        pages = sum(
            1 for card in items.values()
            if getattr(getattr(card, "node", None), "kind", None) == NodeKind.PAGE
        )
        apis = sum(
            1 for card in items.values()
            if getattr(getattr(card, "node", None), "kind", None) == NodeKind.API
        )
        path_pages = 0
        path_apis = 0
        path_edge_ids = set(self._canvas._path_highlight_edge_ids)
        path_node_ids = set(self._canvas._path_highlight_node_ids)

        for node_id in path_node_ids:
            card = items.get(node_id)
            if card is None:
                continue
            kind = getattr(getattr(card, "node", None), "kind", None)
            if kind == NodeKind.PAGE:
                path_pages += 1
            elif kind == NodeKind.API:
                path_apis += 1

        # Count direct API calls made by highlighted pages, even when API
        # nodes are not explicitly included in the selected page path.
        for edge_id, source_id, target_id in edges:
            source = items.get(source_id)
            target = items.get(target_id)
            source_kind = getattr(getattr(source, "node", None), "kind", None)
            target_kind = getattr(getattr(target, "node", None), "kind", None)
            if (
                source_id in path_node_ids
                and source_kind == NodeKind.PAGE
                and target_kind == NodeKind.API
            ):
                path_apis += 1 if target_id not in path_node_ids else 0
                path_edge_ids.add(edge_id)

        return {
            "pages": pages,
            "apis": apis,
            "connections": len(edges),
            "path_pages": path_pages,
            "path_apis": path_apis,
            "path_connections": len(path_edge_ids),
            "path_active": bool(path_node_ids or path_edge_ids),
        }

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#0B1423"))

        items, edges, centers, bounds = self._layout_snapshot()
        metrics = self._metrics(items, edges)

        painter.setPen(QPen(QColor("#1B2A40"), 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 10, 10)

        painter.setPen(QColor("#E2E8F0"))
        title_font = QFont()
        title_font.setPointSize(10)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.drawText(14, 24, "Visualização do grafo")

        sub_font = QFont()
        sub_font.setPointSize(8)
        painter.setFont(sub_font)
        painter.setPen(QColor("#94A3B8"))
        painter.drawText(14, 42, "Mapa abstrato · navegação por clique")

        graph_rect = QRectF(12, 52, max(1, self.width() - 24), max(70, self.height() - 142))
        mapped = {}
        if centers and not bounds.isEmpty():
            sx = graph_rect.width() / max(1.0, bounds.width())
            sy = graph_rect.height() / max(1.0, bounds.height())
            scale = min(sx, sy)
            drawn_width = bounds.width() * scale
            drawn_height = bounds.height() * scale
            offset_x = graph_rect.left() + (graph_rect.width() - drawn_width) / 2
            offset_y = graph_rect.top() + (graph_rect.height() - drawn_height) / 2
            for node_id, point in centers.items():
                mapped[node_id] = QPointF(
                    offset_x + (point.x() - bounds.left()) * scale,
                    offset_y + (point.y() - bounds.top()) * scale,
                )

            for edge_id, source_id, target_id in edges:
                source = mapped.get(source_id)
                target = mapped.get(target_id)
                if source is None or target is None:
                    continue
                highlighted = edge_id in self._canvas._path_highlight_edge_ids
                color = QColor("#FB4766" if highlighted else "#30435D")
                pen = QPen(color, 1.8 if highlighted else 0.8)
                painter.setPen(pen)
                painter.drawLine(source, target)

            for node_id, point in mapped.items():
                card = items[node_id]
                node = getattr(card, "node", None)
                kind = getattr(node, "kind", None)
                highlighted = node_id in self._canvas._path_highlight_node_ids
                if highlighted:
                    color, radius = QColor("#FB4766"), 4.2
                elif kind == NodeKind.API:
                    color, radius = QColor("#6377FF"), 3.1
                elif kind == NodeKind.PAGE:
                    color, radius = QColor("#52739A"), 3.5
                else:
                    color, radius = QColor("#64748B"), 3.0
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(color))
                painter.drawEllipse(point, radius, radius)

            # Rectangle of the current canvas viewport.
            visible_scene = self._canvas.mapToScene(
                self._canvas.viewport().rect()
            ).boundingRect()
            top_left = QPointF(
                offset_x + (visible_scene.left() - bounds.left()) * scale,
                offset_y + (visible_scene.top() - bounds.top()) * scale,
            )
            bottom_right = QPointF(
                offset_x + (visible_scene.right() - bounds.left()) * scale,
                offset_y + (visible_scene.bottom() - bounds.top()) * scale,
            )
            viewport_box = QRectF(top_left, bottom_right).normalized()
            painter.setPen(QPen(QColor("#55D6FF"), 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(viewport_box.intersected(graph_rect))

        divider_y = max(110, self.height() - 82)
        painter.setPen(QPen(QColor("#1E3048"), 1))
        painter.drawLine(12, divider_y, self.width() - 12, divider_y)

        metrics_font = QFont()
        metrics_font.setPointSize(8)
        painter.setFont(metrics_font)
        columns = [
            ("PÁGINAS", str(metrics["path_pages"] if metrics["path_active"] else metrics["pages"]), "#DCE8F7"),
            ("APIs", str(metrics["path_apis"] if metrics["path_active"] else metrics["apis"]), "#8FA5FF"),
            ("CONEXÕES", str(metrics["path_connections"] if metrics["path_active"] else metrics["connections"]), "#DCE8F7"),
        ]
        col_width = max(1, (self.width() - 28) // 3)
        for index, (label, value, color) in enumerate(columns):
            x = 14 + index * col_width
            painter.setPen(QColor("#8FA0B8"))
            painter.drawText(x, divider_y + 18, label)
            value_font = QFont()
            value_font.setPointSize(13)
            value_font.setWeight(QFont.Weight.DemiBold)
            painter.setFont(value_font)
            painter.setPen(QColor(color))
            painter.drawText(x, divider_y + 39, value)
            painter.setFont(metrics_font)

        painter.setPen(QColor("#8FA0B8"))
        if metrics["path_active"]:
            status = "Caminho investigado · vermelho"
        else:
            status = f"{metrics['pages']} páginas · {metrics['apis']} APIs no grafo"
        painter.drawText(14, self.height() - 14, status)

    def mousePressEvent(self, event) -> None:
        items, _edges, centers, bounds = self._layout_snapshot()
        if not centers or bounds.isEmpty():
            return
        graph_rect = QRectF(12, 52, max(1, self.width() - 24), max(70, self.height() - 142))
        sx = graph_rect.width() / max(1.0, bounds.width())
        sy = graph_rect.height() / max(1.0, bounds.height())
        scale = min(sx, sy)
        drawn_width = bounds.width() * scale
        drawn_height = bounds.height() * scale
        offset_x = graph_rect.left() + (graph_rect.width() - drawn_width) / 2
        offset_y = graph_rect.top() + (graph_rect.height() - drawn_height) / 2
        point = event.position()
        scene_point = QPointF(
            bounds.left() + (point.x() - offset_x) / scale,
            bounds.top() + (point.y() - offset_y) / scale,
        )
        self._canvas.centerOn(scene_point)
        self._canvas.viewport().update()
        self.update()
        event.accept()
