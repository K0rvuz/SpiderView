from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsObject,
)

from ..models import PageNode

if TYPE_CHECKING:
    from .edge_item import EdgeItem


class PageCard(QGraphicsObject):
    """
    Representação visual de um PageNode dentro do canvas.
    """

    doubleClicked = Signal(str)
    moved = Signal(str, QPointF)

    WIDTH = 320.0
    HEIGHT = 250.0

    HEADER_HEIGHT = 52.0
    FOOTER_HEIGHT = 46.0

    BORDER_RADIUS = 12.0

    def __init__(
        self,
        node: PageNode,
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(parent)

        self.node = node

        self._edges: list["EdgeItem"] = []

        self._preview = QPixmap()

        if node.preview_path:
            self.set_preview_path(node.preview_path)

        self.setPos(node.x, node.y)

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

        self.setAcceptHoverEvents(True)

        # Cards ficam na frente das arestas.
        self.setZValue(10)

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def boundingRect(self) -> QRectF:
        return QRectF(
            0,
            0,
            self.WIDTH,
            self.HEIGHT,
        )

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------

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

        # --------------------------------------------------------------
        # Shadow
        # --------------------------------------------------------------

        shadow_rect = rect.translated(0, 4)

        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(
            shadow_rect,
            self.BORDER_RADIUS,
            self.BORDER_RADIUS,
        )

        painter.fillPath(
            shadow_path,
            QColor(0, 0, 0, 35),
        )

        # --------------------------------------------------------------
        # Main card
        # --------------------------------------------------------------

        card_path = QPainterPath()
        card_path.addRoundedRect(
            rect,
            self.BORDER_RADIUS,
            self.BORDER_RADIUS,
        )

        painter.fillPath(
            card_path,
            QColor("#1F232A"),
        )

        if self.isSelected():
            border_color = QColor("#4C9AFF")
            border_width = 2.5
        else:
            border_color = QColor("#3A4048")
            border_width = 1.2

        painter.setPen(
            QPen(
                border_color,
                border_width,
            )
        )

        painter.drawPath(card_path)

        # --------------------------------------------------------------
        # Header
        # --------------------------------------------------------------

        header_rect = QRectF(
            0,
            0,
            self.WIDTH,
            self.HEADER_HEIGHT,
        )

        header_path = QPainterPath()

        header_path.addRoundedRect(
            header_rect,
            self.BORDER_RADIUS,
            self.BORDER_RADIUS,
        )

        painter.fillPath(
            header_path,
            QColor("#292E36"),
        )

        # Pequena correção para os cantos inferiores do header.
        painter.fillRect(
            QRectF(
                0,
                self.HEADER_HEIGHT - self.BORDER_RADIUS,
                self.WIDTH,
                self.BORDER_RADIUS,
            ),
            QColor("#292E36"),
        )

        # --------------------------------------------------------------
        # Title
        # --------------------------------------------------------------

        title_font = QFont()
        title_font.setPointSize(11)
        title_font.setWeight(QFont.Weight.DemiBold)

        painter.setFont(title_font)
        painter.setPen(QColor("#F3F4F6"))

        title_metrics = QFontMetrics(title_font)

        title = title_metrics.elidedText(
            self.node.title,
            Qt.TextElideMode.ElideRight,
            int(self.WIDTH - 90),
        )

        painter.drawText(
            QRectF(
                16,
                8,
                self.WIDTH - 100,
                22,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            title,
        )

        # --------------------------------------------------------------
        # Method badge
        # --------------------------------------------------------------

        method_rect = QRectF(
            self.WIDTH - 68,
            12,
            52,
            24,
        )

        painter.setPen(Qt.PenStyle.NoPen)

        painter.setBrush(
            QColor("#3B82F6")
        )

        painter.drawRoundedRect(
            method_rect,
            5,
            5,
        )

        badge_font = QFont()
        badge_font.setPointSize(8)
        badge_font.setWeight(QFont.Weight.Bold)

        painter.setFont(badge_font)
        painter.setPen(QColor("#FFFFFF"))

        painter.drawText(
            method_rect,
            Qt.AlignmentFlag.AlignCenter,
            self.node.method.upper(),
        )

        # --------------------------------------------------------------
        # URL
        # --------------------------------------------------------------

        url_font = QFont()
        url_font.setPointSize(8)

        painter.setFont(url_font)
        painter.setPen(QColor("#9CA3AF"))

        url_metrics = QFontMetrics(url_font)

        url = url_metrics.elidedText(
            self.node.url,
            Qt.TextElideMode.ElideMiddle,
            int(self.WIDTH - 32),
        )

        painter.drawText(
            QRectF(
                16,
                29,
                self.WIDTH - 32,
                18,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            url,
        )

        # --------------------------------------------------------------
        # Preview
        # --------------------------------------------------------------

        preview_rect = QRectF(
            12,
            self.HEADER_HEIGHT + 12,
            self.WIDTH - 24,
            self.HEIGHT
            - self.HEADER_HEIGHT
            - self.FOOTER_HEIGHT
            - 24,
        )

        preview_path = QPainterPath()
        preview_path.addRoundedRect(
            preview_rect,
            7,
            7,
        )

        painter.fillPath(
            preview_path,
            QColor("#15181D"),
        )

        if not self._preview.isNull():

            painter.save()

            painter.setClipPath(preview_path)

            scaled = self._preview.scaled(
                preview_rect.size().toSize(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )

            x = (
                preview_rect.x()
                + (preview_rect.width() - scaled.width()) / 2
            )

            y = (
                preview_rect.y()
                + (preview_rect.height() - scaled.height()) / 2
            )

            painter.drawPixmap(
                QPointF(x, y),
                scaled,
            )

            painter.restore()

        else:

            placeholder_font = QFont()
            placeholder_font.setPointSize(9)

            painter.setFont(placeholder_font)
            painter.setPen(QColor("#6B7280"))

            painter.drawText(
                preview_rect,
                Qt.AlignmentFlag.AlignCenter,
                "Preview ainda não disponível",
            )

        # --------------------------------------------------------------
        # Footer
        # --------------------------------------------------------------

        footer_y = self.HEIGHT - self.FOOTER_HEIGHT

        painter.setPen(
            QPen(
                QColor("#343A43"),
                1,
            )
        )

        painter.drawLine(
            QPointF(12, footer_y),
            QPointF(self.WIDTH - 12, footer_y),
        )

        footer_font = QFont()
        footer_font.setPointSize(8)

        painter.setFont(footer_font)
        painter.setPen(QColor("#9CA3AF"))

        status = (
            str(self.node.status)
            if self.node.status is not None
            else "—"
        )

        painter.drawText(
            QRectF(
                16,
                footer_y + 8,
                100,
                24,
            ),
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter,
            f"HTTP {status}",
        )

        painter.drawText(
            QRectF(
                self.WIDTH - 140,
                footer_y + 8,
                124,
                24,
            ),
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignVCenter,
            self.node.kind.value,
        )

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    def set_preview_path(
        self,
        preview_path: str | None,
    ) -> None:

        self.node.preview_path = preview_path

        self._preview = QPixmap()

        if preview_path:

            path = Path(preview_path)

            if path.exists():
                self._preview.load(str(path))

        self.update()

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def attach_edge(
        self,
        edge: "EdgeItem",
    ) -> None:

        if edge not in self._edges:
            self._edges.append(edge)

    def detach_edge(
        self,
        edge: "EdgeItem",
    ) -> None:

        if edge in self._edges:
            self._edges.remove(edge)

    @property
    def edges(self) -> tuple["EdgeItem", ...]:
        return tuple(self._edges)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def mouseDoubleClickEvent(
        self,
        event,
    ) -> None:

        self.doubleClicked.emit(
            self.node.id
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

            position = self.pos()

            self.node.x = position.x()
            self.node.y = position.y()

            for edge in self._edges:
                edge.update_path()

            self.moved.emit(
                self.node.id,
                position,
            )

        return result