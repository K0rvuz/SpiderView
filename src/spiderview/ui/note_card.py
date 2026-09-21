from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen

from ..models import PageNode
from .page_card import PageCard


class NoteCard(PageCard):
    """Card visual de um PageNode(kind=NOTE)."""

    WIDTH = 310.0
    HEIGHT = 190.0
    BORDER_RADIUS = 12.0

    CONNECTOR_RADIUS = 7.0
    CONNECTOR_HIT_RADIUS = 15.0

    def __init__(self, node: PageNode, parent=None):
        super().__init__(node, parent)
        self.setZValue(11)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.boundingRect()
        metadata = self.node.metadata or {}
        accent = self._safe_color(metadata.get("color", "#D9A441"))

        shadow = QPainterPath()
        shadow.addRoundedRect(rect.translated(0, 4), self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(shadow, QColor(0, 0, 0, 50))

        card = QPainterPath()
        card.addRoundedRect(rect, self.BORDER_RADIUS, self.BORDER_RADIUS)
        painter.fillPath(card, QColor("#24231F"))

        border = QColor("#60A5FA") if self.isSelected() else accent
        painter.setPen(QPen(border, 2.5 if self.isSelected() else 1.6))
        painter.drawPath(card)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(accent)
        painter.drawRoundedRect(QRectF(0, 0, 7, self.HEIGHT), 4, 4)

        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(title_font)
        painter.setPen(QColor("#F6F2E8"))
        title_metrics = QFontMetrics(title_font)
        title = title_metrics.elidedText(
            self.node.title or "Nota",
            Qt.TextElideMode.ElideRight,
            int(self.WIDTH - 44),
        )
        painter.drawText(
            QRectF(22, 13, self.WIDTH - 38, 26),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        body_font = QFont()
        body_font.setPointSize(9)
        painter.setFont(body_font)
        painter.setPen(QColor("#D6D0C2"))
        metrics = QFontMetrics(body_font)
        body = str(metadata.get("note_text", "") or "").strip()
        if not body:
            body = "Duplo clique para editar esta nota."

        lines = self._wrap_lines(body, metrics, int(self.WIDTH - 46), max_lines=5)
        y = 52.0
        for line in lines:
            painter.drawText(
                QRectF(22, y, self.WIDTH - 42, 20),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                line,
            )
            y += 21.0

        tags = metadata.get("tags", []) or []
        if isinstance(tags, str):
            tags = [tags]
        tag_text = "  ".join(f"#{str(tag).strip()}" for tag in tags if str(tag).strip())
        if tag_text:
            tag_font = QFont()
            tag_font.setPointSize(8)
            painter.setFont(tag_font)
            painter.setPen(QColor("#AFA58F"))
            tag_metrics = QFontMetrics(tag_font)
            tag_text = tag_metrics.elidedText(
                tag_text,
                Qt.TextElideMode.ElideRight,
                int(self.WIDTH - 44),
            )
            painter.drawText(
                QRectF(22, self.HEIGHT - 31, self.WIDTH - 40, 18),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                tag_text,
            )

        # Connector manual: arraste este ponto até outro card para criar
        # uma relação persistente Note -> Card.
        connector = self.connector_local_pos()
        painter.setPen(
            QPen(
                QColor("#171A1F"),
                2.0,
            )
        )
        painter.setBrush(accent)
        painter.drawEllipse(
            connector,
            self.CONNECTOR_RADIUS,
            self.CONNECTOR_RADIUS,
        )

        inner = max(
            2.0,
            self.CONNECTOR_RADIUS - 4.0,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#F6F2E8"))
        painter.drawEllipse(
            connector,
            inner,
            inner,
        )

    def connector_local_pos(self) -> QPointF:
        return QPointF(
            self.WIDTH - 15.0,
            self.HEIGHT / 2.0,
        )

    def connector_scene_pos(self) -> QPointF:
        return self.mapToScene(
            self.connector_local_pos()
        )

    def connector_hit_test(
        self,
        scene_pos: QPointF,
    ) -> bool:
        local = self.mapFromScene(
            scene_pos
        )
        center = self.connector_local_pos()

        dx = local.x() - center.x()
        dy = local.y() - center.y()

        return (
            dx * dx + dy * dy
            <= self.CONNECTOR_HIT_RADIUS * self.CONNECTOR_HIT_RADIUS
        )

    @staticmethod
    def _safe_color(value) -> QColor:
        color = QColor(str(value or ""))
        if not color.isValid():
            color = QColor("#D9A441")
        return color

    @staticmethod
    def _wrap_lines(text: str, metrics: QFontMetrics, width: int, max_lines: int) -> list[str]:
        clean = " ".join(text.split())
        if not clean:
            return [""]

        words = clean.split(" ")
        lines: list[str] = []
        current = ""

        for word in words:
            candidate = word if not current else f"{current} {word}"
            if metrics.horizontalAdvance(candidate) <= width:
                current = candidate
                continue

            if current:
                lines.append(current)
            current = word
            if len(lines) >= max_lines:
                break

        if current and len(lines) < max_lines:
            lines.append(current)

        if len(lines) == max_lines and " ".join(lines) != clean:
            lines[-1] = metrics.elidedText(
                lines[-1] + " …",
                Qt.TextElideMode.ElideRight,
                width,
            )

        return lines[:max_lines]
