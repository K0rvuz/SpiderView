from __future__ import annotations

import math
from typing import Protocol

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (
    QColor,
    QBrush,
    QFont,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsPolygonItem,
    QGraphicsSimpleTextItem,
)

from ..models import (
    Transition,
    TransitionType,
)


class EdgeEndpoint(Protocol):
    def sceneBoundingRect(self):
        ...

    def attach_edge(
        self,
        edge: "EdgeItem",
    ) -> None:
        ...

    def detach_edge(
        self,
        edge: "EdgeItem",
    ) -> None:
        ...


class EdgeItem(QGraphicsPathItem):
    """
    Ligação visual entre dois cards.

    Também suporta edges virtuais da Investigation View:
    - view_aggregated
    - view_membership
    - view_detail
    """

    def __init__(
        self,
        transition: Transition,
        source: EdgeEndpoint,
        target: EdgeEndpoint,
        parent: QGraphicsItem | None = None,
    ):
        super().__init__(
            parent
        )

        self.transition = (
            transition
        )

        self.source = source
        self.target = target

        self.setZValue(
            -10
        )

        self.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            True,
        )

        self._force_hide_label = False

        self._pen = self._build_pen()

        self.setPen(
            self._pen
        )

        # --------------------------------------------------------------
        # Arrow
        # --------------------------------------------------------------

        self._arrow = (
            QGraphicsPolygonItem(
                self
            )
        )

        self._arrow.setPen(
            QPen(
                Qt.PenStyle.NoPen
            )
        )

        arrow_color = (
            self._pen.color()
        )

        self._arrow.setBrush(
            QBrush(
                arrow_color
            )
        )

        # --------------------------------------------------------------
        # Label
        # --------------------------------------------------------------

        label = (
            transition.label
            or transition.type.value
        )

        self._label = (
            QGraphicsSimpleTextItem(
                label,
                self,
            )
        )

        self._label.setFlag(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable,
            False,
        )

        label_font = QFont()
        label_font.setPointSize(
            8
        )

        self._label.setFont(
            label_font
        )

        self._label.setBrush(
            QBrush(
                QColor("#B5BDC9")
            )
        )

        self._label.setZValue(
            1
        )

        self._label_visible = True

        self._apply_view_style()

        source.attach_edge(
            self
        )

        target.attach_edge(
            self
        )

        self.update_path()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _build_pen(
        self,
    ) -> QPen:
        metadata = (
            self.transition.metadata
            or {}
        )

        if metadata.get(
            "manual_note"
        ):
            pen = QPen(
                QColor("#D9A441"),
                2.2,
            )
            pen.setStyle(
                Qt.PenStyle.DashLine
            )
            return pen

        if metadata.get(
            "view_membership"
        ):
            pen = QPen(
                QColor("#536273"),
                1.5,
            )

            pen.setStyle(
                Qt.PenStyle.DashLine
            )

            return pen

        if metadata.get(
            "view_detail"
        ):
            return QPen(
                QColor("#5B6470"),
                1.0,
            )

        if metadata.get(
            "view_aggregated"
        ):
            return QPen(
                QColor("#718096"),
                2.6,
            )

        pen = QPen(
            QColor("#667085"),
            2.0,
        )

        if (
            self.transition.type
            == TransitionType.MANUAL
        ):
            pen.setStyle(
                Qt.PenStyle.DashLine
            )

        return pen

    def _apply_view_style(
        self,
    ) -> None:
        metadata = (
            self.transition.metadata
            or {}
        )

        if metadata.get(
            "view_membership"
        ):
            self.setOpacity(
                0.72
            )
            self._force_hide_label = True

        elif metadata.get(
            "view_detail"
        ):
            self.setOpacity(
                0.30
            )
            self._force_hide_label = True

        elif metadata.get(
            "view_aggregated"
        ):
            self.setOpacity(
                0.95
            )

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def set_label(
        self,
        label: str,
    ) -> None:
        self.transition.label = (
            label
        )

        self._label.setText(
            label
        )

        self.update_path()

    def set_label_visible(
        self,
        visible: bool,
    ) -> None:
        self._label_visible = bool(
            visible
        )

        self._label.setVisible(
            self._label_visible
            and not self._force_hide_label
            and self.isVisible()
        )

    def dispose(self) -> None:
        self.source.detach_edge(
            self
        )

        self.target.detach_edge(
            self
        )

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def update_path(self) -> None:
        (
            start,
            end,
            source_tangent,
            target_tangent,
        ) = self._calculate_anchor_points()

        dx = (
            end.x()
            - start.x()
        )

        dy = (
            end.y()
            - start.y()
        )

        distance = math.hypot(
            dx,
            dy,
        )

        control_distance = max(
            60.0,
            min(
                distance * 0.35,
                220.0,
            ),
        )

        control1 = QPointF(
            start.x()
            + source_tangent.x()
            * control_distance,

            start.y()
            + source_tangent.y()
            * control_distance,
        )

        control2 = QPointF(
            end.x()
            + target_tangent.x()
            * control_distance,

            end.y()
            + target_tangent.y()
            * control_distance,
        )

        path = QPainterPath(
            start
        )

        path.cubicTo(
            control1,
            control2,
            end,
        )

        self.setPath(
            path
        )

        self._update_arrow(
            control2,
            end,
        )

        self._update_label()

        self.update()
        self._arrow.update()
        self._label.update()

    def _calculate_anchor_points(
        self,
    ) -> tuple[
        QPointF,
        QPointF,
        QPointF,
        QPointF,
    ]:
        source_rect = (
            self.source
            .sceneBoundingRect()
        )

        target_rect = (
            self.target
            .sceneBoundingRect()
        )

        source_center = (
            source_rect.center()
        )

        target_center = (
            target_rect.center()
        )

        dx = (
            target_center.x()
            - source_center.x()
        )

        dy = (
            target_center.y()
            - source_center.y()
        )

        source_direction = (
            self._direction_for_vector(
                dx,
                dy,
            )
        )

        target_direction = (
            self._direction_for_vector(
                -dx,
                -dy,
            )
        )

        (
            start,
            source_tangent,
        ) = self._anchor_for_direction(
            source_rect,
            source_direction,
        )

        (
            end,
            target_tangent,
        ) = self._anchor_for_direction(
            target_rect,
            target_direction,
        )

        return (
            start,
            end,
            source_tangent,
            target_tangent,
        )

    @staticmethod
    def _direction_for_vector(
        dx: float,
        dy: float,
    ) -> str:
        if dx == 0 and dy == 0:
            return "E"

        angle = math.degrees(
            math.atan2(
                dy,
                dx,
            )
        )

        if angle < 0:
            angle += 360

        if (
            angle >= 337.5
            or angle < 22.5
        ):
            return "E"

        if angle < 67.5:
            return "SE"

        if angle < 112.5:
            return "S"

        if angle < 157.5:
            return "SW"

        if angle < 202.5:
            return "W"

        if angle < 247.5:
            return "NW"

        if angle < 292.5:
            return "N"

        return "NE"

    @staticmethod
    def _anchor_for_direction(
        rect,
        direction: str,
    ) -> tuple[
        QPointF,
        QPointF,
    ]:
        center = rect.center()

        diagonal = (
            1
            / math.sqrt(2)
        )

        anchors = {
            "N": (
                QPointF(
                    center.x(),
                    rect.top(),
                ),
                QPointF(
                    0,
                    -1,
                ),
            ),
            "NE": (
                QPointF(
                    rect.right(),
                    rect.top(),
                ),
                QPointF(
                    diagonal,
                    -diagonal,
                ),
            ),
            "E": (
                QPointF(
                    rect.right(),
                    center.y(),
                ),
                QPointF(
                    1,
                    0,
                ),
            ),
            "SE": (
                QPointF(
                    rect.right(),
                    rect.bottom(),
                ),
                QPointF(
                    diagonal,
                    diagonal,
                ),
            ),
            "S": (
                QPointF(
                    center.x(),
                    rect.bottom(),
                ),
                QPointF(
                    0,
                    1,
                ),
            ),
            "SW": (
                QPointF(
                    rect.left(),
                    rect.bottom(),
                ),
                QPointF(
                    -diagonal,
                    diagonal,
                ),
            ),
            "W": (
                QPointF(
                    rect.left(),
                    center.y(),
                ),
                QPointF(
                    -1,
                    0,
                ),
            ),
            "NW": (
                QPointF(
                    rect.left(),
                    rect.top(),
                ),
                QPointF(
                    -diagonal,
                    -diagonal,
                ),
            ),
        }

        return anchors[
            direction
        ]

    # ------------------------------------------------------------------
    # Arrow
    # ------------------------------------------------------------------

    def _update_arrow(
        self,
        control_point: QPointF,
        end: QPointF,
    ) -> None:
        dx = (
            end.x()
            - control_point.x()
        )

        dy = (
            end.y()
            - control_point.y()
        )

        angle = math.atan2(
            dy,
            dx,
        )

        arrow_size = 11.0
        angle_offset = math.radians(
            28
        )

        p1 = QPointF(
            end.x()
            - math.cos(
                angle
                - angle_offset
            )
            * arrow_size,

            end.y()
            - math.sin(
                angle
                - angle_offset
            )
            * arrow_size,
        )

        p2 = QPointF(
            end.x()
            - math.cos(
                angle
                + angle_offset
            )
            * arrow_size,

            end.y()
            - math.sin(
                angle
                + angle_offset
            )
            * arrow_size,
        )

        self._arrow.setPolygon(
            QPolygonF(
                [
                    end,
                    p1,
                    p2,
                ]
            )
        )

    # ------------------------------------------------------------------
    # Label
    # ------------------------------------------------------------------

    def _update_label(
        self,
    ) -> None:
        label_text = (
            self.transition.label
            or self.transition.type.value
        )

        if (
            self._label.text()
            != label_text
        ):
            self._label.setText(
                label_text
            )

        path = self.path()

        if path.isEmpty():
            return

        middle = (
            path.pointAtPercent(
                0.5
            )
        )

        rect = (
            self._label
            .boundingRect()
        )

        self._label.setPos(
            middle.x()
            - rect.width()
            / 2,

            middle.y()
            - rect.height()
            / 2,
        )

        self._label.setVisible(
            self._label_visible
            and not self._force_hide_label
            and self.isVisible()
        )
