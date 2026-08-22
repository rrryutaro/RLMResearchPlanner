from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QEvent, QPoint, QPointF, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QTextOption,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QSlider,
    QToolButton,
    QWidget,
)

from rlm_research_planner.services.tree_layout import (
    calculate_tree_positions,
    compact_explicit_row_slots,
)
from rlm_research_planner.ui.step_spin_box import (
    VisibleSpinBox,
    configure_step_button,
)


NODE_WIDTH = 244.0
NODE_HEIGHT = 224.0
HORIZONTAL_GAP = 52.0
VERTICAL_GAP = 72.0
SCENE_MARGIN = 48.0


@dataclass(frozen=True)
class ResearchTreeNode:
    research_id: str
    name: str
    current_level: int | None
    max_level: int | None
    status: str
    recommendation: str
    display_order: int
    current_effect: str = "-"
    next_effect: str = "-"
    layout_row: int | None = None
    layout_column: float | None = None
    shortage_levels: int = 0
    category_id: str = ""
    category_name: str = ""


class _ResearchNodeItem(QGraphicsRectItem):
    def __init__(
        self,
        node: ResearchTreeNode,
        *,
        selected_callback,
        activated_callback,
        level_editing_enabled: bool = False,
        visual_style: str = "desktop",
        font_size: int = 20,
    ) -> None:
        super().__init__(0.0, 0.0, NODE_WIDTH, NODE_HEIGHT)
        self._node = node
        self._visual_style = "desktop"
        self._font_size = max(14, min(28, int(font_size)))
        self.research_id = node.research_id
        self._selected_callback = selected_callback
        self._activated_callback = activated_callback
        self._level_editing_enabled = level_editing_enabled
        self._current_level = 0 if node.current_level is None else node.current_level
        self._max_level = node.max_level
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(self._node_tooltip(node))

        if node.shortage_levels > 0:
            background = QColor("#48271D")
            border = QColor("#F07845")
        elif node.current_level is None:
            background = QColor("#1B3040")
            border = QColor("#4D91B8")
        elif node.max_level is not None and node.current_level >= node.max_level:
            background = QColor("#183E34")
            border = QColor("#45B88A")
        elif node.current_level > 0:
            background = QColor("#493716")
            border = QColor("#E0A72B")
        else:
            background = QColor("#222D35")
            border = QColor("#607481")
        self.setBrush(background)
        self.setPen(QPen(border, 2.0))

        category_font = QFont()
        category_font.setPointSizeF(self._scaled_point_size(10.0))
        category_font.setBold(True)
        self.category_item = self._text_item(
            node.category_name,
            category_font,
            QColor("#75D5E8"),
            x=12.0,
            y=4.0,
            width=NODE_WIDTH - 24.0,
            height=15.0,
        )
        self.category_item.setVisible(bool(node.category_name))

        title_font = QFont()
        title_font.setPointSizeF(self._scaled_point_size(26.0))
        title_font.setBold(True)
        title_y, title_height = self._title_geometry(node)
        self.title_item = self._text_item(
            node.name,
            title_font,
            QColor("#FFFFFF"),
            x=12.0,
            y=title_y,
            width=NODE_WIDTH - 24.0,
            height=title_height,
        )

        self.divider = QGraphicsRectItem(
            12.0, 57.0, NODE_WIDTH - 24.0, 1.0, self
        )
        self.divider.setPen(Qt.NoPen)
        self.divider.setBrush(QColor("#496170"))
        self.divider.setZValue(1.0)

        meter_x = 16.0
        meter_y = 68.0
        meter_width = NODE_WIDTH - 32.0
        meter_height = 12.0
        self.meter_track = QGraphicsRectItem(
            meter_x, meter_y, meter_width, meter_height, self
        )
        self.meter_track.setPen(QPen(QColor("#71828C"), 1.0))
        self.meter_track.setBrush(QColor("#0C1419"))
        self.meter_track.setZValue(1.0)
        progress = 0.0
        if (
            node.current_level is not None
            and node.max_level is not None
            and node.max_level > 0
        ):
            progress = max(0.0, min(1.0, node.current_level / node.max_level))
        self._progress = progress
        fill_color = QColor("#45B88A") if progress >= 1.0 else QColor("#E0A72B")
        self.meter_fill = QGraphicsRectItem(
            meter_x + 1.0,
            meter_y + 1.0,
            max(0.0, (meter_width - 2.0) * progress),
            meter_height - 2.0,
            self,
        )
        self.meter_fill.setPen(Qt.NoPen)
        self.meter_fill.setBrush(fill_color)
        self.meter_fill.setZValue(2.0)

        current_level = "0" if node.current_level is None else str(node.current_level)
        maximum = "-" if node.max_level is None else str(node.max_level)
        level_font = QFont()
        level_font.setPointSizeF(self._scaled_point_size(20.0))
        level_font.setBold(True)
        self.level_item = self._text_item(
            f"{current_level} / {maximum}",
            level_font,
            QColor("#E7EEF2"),
            x=12.0,
            y=84.0,
            width=NODE_WIDTH - 24.0,
            height=24.0,
        )

        effect_font = QFont()
        effect_font.setPointSizeF(self._scaled_point_size(20.0))
        self.current_effect_item = self._text_item(
            node.current_effect,
            effect_font,
            QColor("#D5E3EA"),
            x=12.0,
            y=112.0,
            width=NODE_WIDTH - 24.0,
            height=48.0,
        )
        self.next_effect_item = self._text_item(
            node.next_effect,
            effect_font,
            QColor("#9FD2EC"),
            x=12.0,
            y=164.0,
            width=NODE_WIDTH - 24.0,
            height=48.0,
        )
        self.set_visual_style(visual_style)

    def boundingRect(self):
        # The selected outline is wider than the normal card pen.  Reserve its
        # full paint area so Qt never clips the outer edge of a selected card.
        return super().boundingRect().adjusted(-3.0, -3.0, 3.0, 3.0)

    def set_visual_style(self, visual_style: str) -> None:
        self._visual_style = "mobile" if visual_style == "mobile" else "desktop"
        mobile = self._visual_style == "mobile"
        node = self._node
        if node.shortage_levels > 0:
            background = QColor("#4B2423" if mobile else "#48271D")
            border = QColor("#F1756B" if mobile else "#F07845")
        elif node.current_level is None:
            background = QColor("#0D202A" if mobile else "#1B3040")
            border = QColor("#496A75" if mobile else "#4D91B8")
        elif node.max_level is not None and node.current_level >= node.max_level:
            background = QColor("#16493E" if mobile else "#183E34")
            border = QColor("#45C7A3" if mobile else "#45B88A")
        elif node.current_level > 0:
            background = QColor("#4B3910" if mobile else "#493716")
            border = QColor("#F2B632" if mobile else "#E0A72B")
        else:
            background = QColor("#0D202A" if mobile else "#222D35")
            border = QColor("#496A75" if mobile else "#607481")
        self.setBrush(background)
        self.setPen(QPen(border, 2.0))
        self.title_item.setDefaultTextColor(
            QColor("#F4F8F8" if mobile else "#FFFFFF")
        )
        self.category_item.setDefaultTextColor(
            QColor("#7FE3F2" if mobile else "#75D5E8")
        )
        self.divider.setBrush(QColor("#2F5F6C" if mobile else "#496170"))
        self.meter_track.setPen(
            QPen(QColor("#5B7580" if mobile else "#71828C"), 1.0)
        )
        self.meter_track.setBrush(QColor("#061117" if mobile else "#0C1419"))
        self.meter_fill.setBrush(
            QColor(
                "#45C7A3"
                if mobile and self._progress >= 1.0
                else "#F2B632"
                if mobile
                else "#45B88A"
                if self._progress >= 1.0
                else "#E0A72B"
            )
        )
        self.level_item.setDefaultTextColor(
            QColor("#F4F8F8" if mobile else "#E7EEF2")
        )
        self.current_effect_item.setDefaultTextColor(
            QColor("#D7E4E7" if mobile else "#D5E3EA")
        )
        self.next_effect_item.setDefaultTextColor(
            QColor("#9EDFF2" if mobile else "#9FD2EC")
        )
        self.update()

    def update_node(self, node: ResearchTreeNode) -> None:
        if node.research_id != self.research_id:
            raise ValueError("Cannot replace a research card with a different ID")
        self._node = node
        self._current_level = 0 if node.current_level is None else node.current_level
        self._max_level = node.max_level
        self.setToolTip(self._node_tooltip(node))
        progress = 0.0
        if (
            node.current_level is not None
            and node.max_level is not None
            and node.max_level > 0
        ):
            progress = max(0.0, min(1.0, node.current_level / node.max_level))
        self._progress = progress
        self.meter_fill.setRect(
            17.0,
            69.0,
            max(0.0, (NODE_WIDTH - 34.0) * progress),
            10.0,
        )
        title_font = QFont()
        title_font.setPointSizeF(self._scaled_point_size(26.0))
        title_font.setBold(True)
        level_font = QFont()
        level_font.setPointSizeF(self._scaled_point_size(20.0))
        level_font.setBold(True)
        effect_font = QFont()
        effect_font.setPointSizeF(self._scaled_point_size(20.0))
        category_font = QFont()
        category_font.setPointSizeF(self._scaled_point_size(10.0))
        category_font.setBold(True)
        current_level = "0" if node.current_level is None else str(node.current_level)
        maximum = "-" if node.max_level is None else str(node.max_level)
        self.category_item.setVisible(bool(node.category_name))
        self._fit_text_item(
            self.category_item,
            node.category_name,
            category_font,
            x=12.0,
            y=4.0,
            width=NODE_WIDTH - 24.0,
            height=15.0,
        )
        title_y, title_height = self._title_geometry(node)
        self._fit_text_item(
            self.title_item,
            node.name,
            title_font,
            x=12.0,
            y=title_y,
            width=NODE_WIDTH - 24.0,
            height=title_height,
        )
        self._fit_text_item(
            self.level_item,
            f"{current_level} / {maximum}",
            level_font,
            x=12.0,
            y=84.0,
            width=NODE_WIDTH - 24.0,
            height=24.0,
        )
        self._fit_text_item(
            self.current_effect_item,
            node.current_effect,
            effect_font,
            x=12.0,
            y=112.0,
            width=NODE_WIDTH - 24.0,
            height=48.0,
        )
        self._fit_text_item(
            self.next_effect_item,
            node.next_effect,
            effect_font,
            x=12.0,
            y=164.0,
            width=NODE_WIDTH - 24.0,
            height=48.0,
        )
        self.set_visual_style(self._visual_style)

    def set_font_size(self, font_size: int) -> None:
        normalized = max(14, min(28, int(font_size)))
        if normalized == self._font_size:
            return
        self._font_size = normalized
        self.update_node(self._node)

    def _scaled_point_size(self, base_size: float) -> float:
        return base_size * self._font_size / 20.0

    @staticmethod
    def _title_geometry(node: ResearchTreeNode) -> tuple[float, float]:
        if node.category_name:
            return 19.0, 35.0
        return 8.0, 43.0

    @staticmethod
    def _node_tooltip(node: ResearchTreeNode) -> str:
        lines = [node.name]
        if node.category_name:
            lines.append(node.category_name)
        lines.extend((node.status, node.recommendation))
        return "\n".join(lines)

    def paint(self, painter, option, widget=None) -> None:
        painter.save()
        if self.isSelected():
            painter.setPen(QPen(QColor("#C58BFF"), 6.0))
        else:
            painter.setPen(self.pen())
        painter.setBrush(self.brush())
        painter.drawRoundedRect(self.rect(), 8.0, 8.0)
        painter.restore()

    def _text_item(
        self,
        text: str,
        font: QFont,
        color: QColor,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> QGraphicsTextItem:
        item = QGraphicsTextItem(self)
        text = " ".join(text.splitlines()).strip()
        item.setPlainText(text)
        item.setFont(font)
        item.setDefaultTextColor(color)
        item.setTextWidth(width)
        item.document().setDocumentMargin(0.0)
        text_option = item.document().defaultTextOption()
        text_option.setAlignment(Qt.AlignCenter)
        text_option.setWrapMode(QTextOption.NoWrap)
        item.document().setDefaultTextOption(text_option)
        item.setZValue(3.0)
        item.setAcceptedMouseButtons(Qt.NoButton)
        self._fit_text_item(
            item,
            text,
            font,
            x=x,
            y=y,
            width=width,
            height=height,
        )
        return item

    @staticmethod
    def _fit_text_item(
        item: QGraphicsTextItem,
        text: str,
        font: QFont,
        *,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> None:
        item.setPlainText(" ".join(text.splitlines()).strip())
        item.setTextWidth(width)
        maximum_point_size = font.pointSizeF()
        low = 1.0
        high = maximum_point_size
        best = low
        for _ in range(10):
            point_size = (low + high) / 2.0
            fitted_font = QFont(font)
            fitted_font.setPointSizeF(point_size)
            item.setFont(fitted_font)
            metrics = QFontMetricsF(fitted_font)
            if (
                metrics.horizontalAdvance(item.toPlainText()) <= width - 1.0
                and metrics.height() <= height - 1.0
            ):
                best = point_size
                low = point_size
            else:
                high = point_size
        fitted_font = QFont(font)
        fitted_font.setPointSizeF(best)
        item.setFont(fitted_font)
        item.setPos(x, y + max(0.0, (height - item.boundingRect().height()) / 2.0))

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemSelectedHasChanged and bool(value):
            self._selected_callback(self.research_id)
        if change == QGraphicsRectItem.ItemSelectedHasChanged:
            self.update()
        return super().itemChange(change, value)

    def level_control_kind_at(self, scene_position) -> str:
        if not self._level_editing_enabled or self._max_level is None:
            return ""
        local = self.mapFromScene(scene_position)
        if not 12.0 <= local.x() <= NODE_WIDTH - 12.0:
            return ""
        if 60.0 <= local.y() < 84.0:
            return "slider"
        if 84.0 <= local.y() <= 112.0:
            return "number"
        return ""

    def is_level_control_at(self, scene_position) -> bool:
        return bool(self.level_control_kind_at(scene_position))

    def mouseDoubleClickEvent(self, event) -> None:
        if self.is_level_control_at(event.scenePos()):
            event.accept()
            return
        self._activated_callback(self.research_id)
        event.accept()


class ResearchTreeView(QGraphicsView):
    researchSelected = Signal(str)
    researchActivated = Signal(str)
    researchLevelChanged = Signal(str, int)

    def __init__(self, parent=None, *, level_editing_enabled: bool = False) -> None:
        super().__init__(parent)
        self._level_editing_enabled = level_editing_enabled
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing, True)
        # QGraphicsView.ScrollHandDrag cannot start on a selectable card because
        # the card consumes the press.  Panning is handled below so the same
        # click-versus-drag rule applies both on cards and on empty space.
        self.setDragMode(QGraphicsView.NoDrag)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.setBackgroundBrush(QColor("#111820"))
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self._visual_style = "desktop"
        self._font_size = 20
        self._zoom_factor = 1.0
        self._pointer_origin: QPoint | None = None
        self._pointer_last: QPoint | None = None
        self._pointer_node: _ResearchNodeItem | None = None
        self._pointer_dragging = False
        self._level_editor: QWidget | None = None
        self._level_value_editor: QSlider | VisibleSpinBox | None = None
        self._level_editor_research_id = ""
        self._level_editor_commit = None
        self._node_items: dict[str, _ResearchNodeItem] = {}
        self._edge_pairs: set[tuple[str, str]] = set()
        self._cross_category_pairs: set[tuple[str, str]] = set()
        self._edge_pair_paths: dict[tuple[str, str], QPainterPath] = {}

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    @property
    def visual_style(self) -> str:
        return self._visual_style

    def set_visual_style(self, visual_style: str) -> None:
        self._visual_style = "mobile" if visual_style == "mobile" else "desktop"
        self.setBackgroundBrush(
            QColor("#07141C" if self._visual_style == "mobile" else "#111820")
        )
        for item in self._scene.items():
            if isinstance(item, _ResearchNodeItem):
                item.set_visual_style(self._visual_style)
            elif isinstance(item, QGraphicsPathItem):
                active = bool(item.data(2))
                if bool(item.data(4)) and not active:
                    item.setPen(Qt.NoPen)
                    continue
                item.setPen(
                    self._edge_pen(active, cross_category=bool(item.data(5)))
                )
            elif isinstance(item, QGraphicsTextItem) and item.parentItem() is None:
                if item.data(10) == "cross-category-legend":
                    item.setDefaultTextColor(
                        QColor(
                            "#7FE3F2"
                            if self._visual_style == "mobile"
                            else "#75D5E8"
                        )
                    )
                else:
                    item.setDefaultTextColor(
                        QColor(
                            "#A9C0C7"
                            if self._visual_style == "mobile"
                            else "#C9D4DA"
                        )
                    )
        self.viewport().update()

    def set_font_size(self, font_size: int) -> None:
        self._font_size = max(14, min(28, int(font_size)))
        for item in self._scene.items():
            if isinstance(item, _ResearchNodeItem):
                item.set_font_size(self._font_size)
            elif isinstance(item, QGraphicsTextItem) and item.parentItem() is None:
                font = QFont(item.font())
                base_size = 11.0 if item.data(10) == "cross-category-legend" else 12.0
                font.setPointSizeF(base_size * self._font_size / 20.0)
                item.setFont(font)
        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(
                -SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN, SCENE_MARGIN
            )
        )
        self.viewport().update()

    def _edge_pen(self, active: bool, *, cross_category: bool = False) -> QPen:
        if cross_category:
            color = "#7FE3F2" if self._visual_style == "mobile" else "#55BFD4"
            pen = QPen(QColor(color), 3.0)
            pen.setStyle(Qt.DashLine)
            return pen
        color = (
            "#F2B632"
            if active and self._visual_style == "mobile"
            else "#D2A51B"
            if active
            else "#35505A"
            if self._visual_style == "mobile"
            else "#46545D"
        )
        return QPen(QColor(color), 2.5)

    def drawBackground(self, painter, rect) -> None:
        mobile = self._visual_style == "mobile"
        painter.fillRect(rect, QColor("#07141C" if mobile else "#111820"))
        grid_size = 24.0
        grid_pen = QPen(QColor("#102631" if mobile else "#26323B"), 1.0)
        grid_pen.setCosmetic(True)
        painter.setPen(grid_pen)
        left = math.floor(rect.left() / grid_size) * grid_size
        top = math.floor(rect.top() / grid_size) * grid_size
        x = left
        while x <= rect.right():
            painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            x += grid_size
        y = top
        while y <= rect.bottom():
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            y += grid_size

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            if steps:
                self._zoom_by_steps(steps)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        self._finish_level_edit()
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        position = event.position().toPoint()
        self._pointer_origin = position
        self._pointer_last = position
        self._pointer_node = self._node_at(position)
        self._pointer_dragging = False
        self.setFocus(Qt.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._pointer_origin is None or not (event.buttons() & Qt.LeftButton):
            super().mouseMoveEvent(event)
            return
        position = event.position().toPoint()
        if not self._pointer_dragging:
            distance = (position - self._pointer_origin).manhattanLength()
            if distance >= QApplication.startDragDistance():
                self._pointer_dragging = True
                self.viewport().setCursor(Qt.ClosedHandCursor)
        if self._pointer_dragging and self._pointer_last is not None:
            delta = position - self._pointer_last
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
        self._pointer_last = position
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton or self._pointer_origin is None:
            super().mouseReleaseEvent(event)
            return
        position = event.position().toPoint()
        pressed_node = self._pointer_node
        was_dragging = self._pointer_dragging
        self._reset_pointer_state()
        if (
            not was_dragging
            and pressed_node is not None
            and self._node_at(position) is pressed_node
        ):
            scene_position = self.mapToScene(position)
            editor_kind = pressed_node.level_control_kind_at(scene_position)
            if editor_kind:
                self._scene.clearSelection()
                pressed_node.setSelected(True)
                self._show_level_editor(pressed_node, editor_kind)
            else:
                self._scene.clearSelection()
                pressed_node.setSelected(True)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            node = self._node_at(event.position().toPoint())
            if node is not None:
                if node.is_level_control_at(
                    self.mapToScene(event.position().toPoint())
                ):
                    self._reset_pointer_state()
                    event.accept()
                    return
                self._cancel_level_editor()
                self._reset_pointer_state()
                self.researchActivated.emit(node.research_id)
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def _node_at(self, viewport_position: QPoint) -> _ResearchNodeItem | None:
        item = self.itemAt(viewport_position)
        while item is not None and not isinstance(item, _ResearchNodeItem):
            item = item.parentItem()
        return item if isinstance(item, _ResearchNodeItem) else None

    def _finish_level_edit(self) -> None:
        if self._level_editor_commit is not None:
            self._level_editor_commit()

    def _cancel_level_editor(self) -> None:
        editor = self._level_editor
        research_id = self._level_editor_research_id
        self._level_editor = None
        self._level_value_editor = None
        self._level_editor_research_id = ""
        self._level_editor_commit = None
        if editor is not None:
            editor.blockSignals(True)
            editor.hide()
            editor.setParent(None)
            editor.deleteLater()
        item = self._node_items.get(research_id)
        if item is not None:
            item.update_node(item._node)

    def _show_level_editor(
        self, item: _ResearchNodeItem, editor_kind: str = "number"
    ) -> None:
        if item._max_level is None:
            return
        self._cancel_level_editor()
        if editor_kind == "slider":
            editor = QWidget(self.viewport())
            editor.setStyleSheet(
                "QWidget{background:#101A20;border:2px solid #E0A72B;}"
                "QToolButton{min-width:32px;max-width:32px;border:0;"
                "color:#FFFFFF;background:#263942;font-size:18px;font-weight:700;}"
                "QToolButton:hover{background:#3A525E;}"
            )
            editor_layout = QHBoxLayout(editor)
            editor_layout.setContentsMargins(2, 2, 2, 2)
            editor_layout.setSpacing(3)
            decrease_button = QToolButton(editor)
            configure_step_button(
                decrease_button,
                decrease=True,
                visual_style=self._visual_style,
            )
            decrease_button.setObjectName("levelDecreaseButton")
            decrease_button.setFixedWidth(32)
            decrease_button.setToolTip("Decrease level")
            value_editor = QSlider(Qt.Horizontal, editor)
            value_editor.setObjectName("levelSlider")
            value_editor.setRange(0, item._max_level)
            value_editor.setValue(item._current_level)
            value_editor.setSingleStep(1)
            value_editor.setPageStep(1)
            value_editor.setStyleSheet(
                "QSlider{background:#101A20;border:2px solid #E0A72B;}"
                "QSlider::groove:horizontal{height:8px;background:#34434C;}"
                "QSlider::sub-page:horizontal{background:#E0A72B;}"
                "QSlider::handle:horizontal{width:18px;margin:-6px 0;"
                "background:#FFFFFF;border:1px solid #8B6B19;}"
            )
            increase_button = QToolButton(editor)
            configure_step_button(
                increase_button,
                decrease=False,
                visual_style=self._visual_style,
            )
            increase_button.setObjectName("levelIncreaseButton")
            increase_button.setFixedWidth(32)
            increase_button.setToolTip("Increase level")
            editor_layout.addWidget(decrease_button)
            editor_layout.addWidget(value_editor, 1)
            editor_layout.addWidget(increase_button)

            def update_step_buttons(value: int) -> None:
                decrease_button.setEnabled(value > value_editor.minimum())
                increase_button.setEnabled(value < value_editor.maximum())

            decrease_button.clicked.connect(
                lambda: value_editor.setValue(value_editor.value() - 1)
            )
            increase_button.clicked.connect(
                lambda: value_editor.setValue(value_editor.value() + 1)
            )
            value_editor.valueChanged.connect(update_step_buttons)
            update_step_buttons(value_editor.value())
            top_left = self.mapFromScene(item.mapToScene(QPointF(12.0, 62.0)))
            bottom_right = self.mapFromScene(
                item.mapToScene(QPointF(NODE_WIDTH - 12.0, 88.0))
            )
            minimum_width = 210
            minimum_height = 34
        else:
            editor = VisibleSpinBox(self.viewport())
            editor.set_visual_style(self._visual_style)
            value_editor = editor
            value_editor.setRange(0, item._max_level)
            value_editor.setValue(item._current_level)
            value_editor.setAlignment(Qt.AlignCenter)
            value_editor.setKeyboardTracking(False)
            value_editor.setStyleSheet(
                "QSpinBox{background:#101A20;color:#FFFFFF;"
                "border:2px solid #E0A72B;font-size:18px;font-weight:700;}"
            )
            top_left = self.mapFromScene(item.mapToScene(QPointF(70.0, 82.0)))
            bottom_right = self.mapFromScene(
                item.mapToScene(QPointF(NODE_WIDTH - 70.0, 114.0))
            )
            minimum_width = 90
            minimum_height = 32
        width = max(minimum_width, bottom_right.x() - top_left.x())
        height = max(minimum_height, bottom_right.y() - top_left.y())
        x = max(0, min(top_left.x(), self.viewport().width() - width))
        y = max(0, min(top_left.y(), self.viewport().height() - height))
        editor.setGeometry(x, y, width, height)
        self._level_editor = editor
        self._level_value_editor = value_editor
        self._level_editor_research_id = item.research_id
        committed = False

        def commit() -> None:
            nonlocal committed
            if committed or self._level_editor is not editor:
                return
            committed = True
            level = value_editor.value()
            research_id = item.research_id
            self._level_editor = None
            self._level_value_editor = None
            self._level_editor_research_id = ""
            self._level_editor_commit = None
            editor.hide()
            editor.setParent(None)
            editor.deleteLater()
            self.researchLevelChanged.emit(research_id, level)

        self._level_editor_commit = commit
        if isinstance(value_editor, VisibleSpinBox):
            value_editor.editingFinished.connect(commit)
        else:
            value_editor.sliderReleased.connect(commit)
            value_editor.valueChanged.connect(
                lambda value: self._preview_slider_level(item, value)
            )
        editor.show()
        editor.raise_()
        editor.installEventFilter(self)
        for child in editor.findChildren(QWidget):
            child.installEventFilter(self)
        value_editor.setFocus(Qt.MouseFocusReason)
        if isinstance(value_editor, VisibleSpinBox):
            value_editor.selectAll()

    def eventFilter(self, watched, event) -> bool:
        # The editor is a real viewport child, so its click and double-click
        # gestures belong to its buttons, slider, or number field.  Do not
        # reinterpret them as activation of the card behind the editor.
        return super().eventFilter(watched, event)

    def hideEvent(self, event) -> None:
        self._finish_level_edit()
        super().hideEvent(event)

    @staticmethod
    def _preview_slider_level(item: _ResearchNodeItem, value: int) -> None:
        maximum = int(item._max_level or 0)
        item.level_item.setPlainText(f"{value} / {maximum}")
        progress = value / maximum if maximum > 0 else 0.0
        item.meter_fill.setRect(
            17.0,
            69.0,
            max(0.0, (NODE_WIDTH - 34.0) * progress),
            10.0,
        )

    def _reset_pointer_state(self) -> None:
        self._pointer_origin = None
        self._pointer_last = None
        self._pointer_node = None
        self._pointer_dragging = False
        self.viewport().unsetCursor()

    def _zoom_by_steps(self, steps: float) -> None:
        requested = self._zoom_factor * (1.15**steps)
        target = max(0.35, min(2.5, requested))
        factor = target / self._zoom_factor
        if abs(factor - 1.0) < 0.0001:
            return
        self.scale(factor, factor)
        self._zoom_factor = target

    def reset_zoom(self) -> None:
        self.resetTransform()
        self._zoom_factor = 1.0

    def fit_all(self) -> None:
        if self._scene.itemsBoundingRect().isEmpty():
            return
        self.fitInView(self._scene.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = self.transform().m11()

    def focus_research(self, research_id: str) -> bool:
        """Select and center a research card already rendered in the scene."""

        for item in self._scene.items():
            if (
                isinstance(item, _ResearchNodeItem)
                and item.research_id == research_id
            ):
                self._scene.clearSelection()
                item.setSelected(True)
                self.centerOn(item)
                return True
        return False

    def set_research(
        self,
        nodes: Iterable[ResearchTreeNode],
        prerequisite_edges: Iterable[tuple[str, str]],
        selected_research_id: str = "",
        empty_message: str = "No research entries",
        connection_groups: Iterable[
            tuple[Iterable[str], Iterable[str]]
        ] = (),
        active_edges: Iterable[tuple[str, str]] | None = None,
        preserve_explicit_columns: bool = False,
        cross_category_legend: str = "",
    ) -> None:
        self._cancel_level_editor()
        self._reset_pointer_state()
        node_list = list(nodes)
        edge_list = list(prerequisite_edges)
        by_id = {node.research_id: node for node in node_list}
        self._node_items = {}
        self._edge_pairs = set(edge_list)
        self._cross_category_pairs = {
            (prerequisite_id, research_id)
            for prerequisite_id, research_id in edge_list
            if prerequisite_id in by_id
            and research_id in by_id
            and by_id[prerequisite_id].category_id
            and by_id[research_id].category_id
            and by_id[prerequisite_id].category_id
            != by_id[research_id].category_id
        }
        self._edge_pair_paths = {}
        active_edge_set = set(edge_list if active_edges is None else active_edges)
        connection_group_list = [
            (tuple(prerequisites), tuple(research))
            for prerequisites, research in connection_groups
        ]
        self._scene.clear()
        if not node_list:
            message = QGraphicsTextItem(empty_message)
            message.setDefaultTextColor(
                QColor(
                    "#A9C0C7"
                    if self._visual_style == "mobile"
                    else "#C9D4DA"
                )
            )
            message_font = QFont()
            message_font.setPointSizeF(12.0 * self._font_size / 20.0)
            message.setFont(message_font)
            message.setTextWidth(560.0)
            message.setPos(SCENE_MARGIN, SCENE_MARGIN)
            self._scene.addItem(message)
            self._scene.setSceneRect(
                self._scene.itemsBoundingRect().adjusted(
                    -SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN, SCENE_MARGIN
                )
            )
            return

        coordinates: dict[str, tuple[float, float]] = {}
        explicit_layout = all(
            node.layout_row is not None and node.layout_column is not None
            for node in node_list
        )
        if explicit_layout:
            rows: dict[int, list[ResearchTreeNode]] = {}
            for node in node_list:
                rows.setdefault(int(node.layout_row or 0), []).append(node)
            source_column_count = (
                max(float(node.layout_column or 0) for node in node_list) + 1
            )
            target_column_count = max(len(row) for row in rows.values())
            for row_index, row_nodes in rows.items():
                row_nodes.sort(key=lambda node: float(node.layout_column or 0))
                slots = (
                    tuple(float(node.layout_column or 0) for node in row_nodes)
                    if preserve_explicit_columns
                    else compact_explicit_row_slots(
                        (float(node.layout_column or 0) for node in row_nodes),
                        source_column_count=source_column_count,
                        target_column_count=target_column_count,
                    )
                )
                for node, slot in zip(row_nodes, slots):
                    coordinates[node.research_id] = (
                        SCENE_MARGIN + slot * (NODE_WIDTH + HORIZONTAL_GAP),
                        SCENE_MARGIN
                        + row_index * (NODE_HEIGHT + VERTICAL_GAP),
                    )
        else:
            positions = calculate_tree_positions(
                (node.research_id for node in node_list),
                edge_list,
                {node.research_id: node.display_order for node in node_list},
            )
            rows: dict[int, list[str]] = {}
            for research_id, position in positions.items():
                rows.setdefault(position.depth, []).append(research_id)
            max_columns = max((len(row) for row in rows.values()), default=1)
            content_width = (
                max_columns * NODE_WIDTH + (max_columns - 1) * HORIZONTAL_GAP
            )
            for depth, row in rows.items():
                row.sort(key=lambda research_id: positions[research_id].column)
                row_width = len(row) * NODE_WIDTH + (len(row) - 1) * HORIZONTAL_GAP
                start_x = SCENE_MARGIN + (content_width - row_width) / 2.0
                y = SCENE_MARGIN + depth * (NODE_HEIGHT + VERTICAL_GAP)
                for column, research_id in enumerate(row):
                    coordinates[research_id] = (
                        start_x + column * (NODE_WIDTH + HORIZONTAL_GAP),
                        y,
                    )
        visible_connection_groups = []
        for prerequisites, research in connection_group_list:
            visible_prerequisites = tuple(
                research_id
                for research_id in prerequisites
                if research_id in coordinates
            )
            visible_research = tuple(
                research_id for research_id in research if research_id in coordinates
            )
            if visible_prerequisites and visible_research:
                visible_connection_groups.append(
                    (visible_prerequisites, visible_research)
                )
        if not visible_connection_groups:
            visible_connection_groups = [
                ((prerequisite_id,), (research_id,))
                for prerequisite_id, research_id in edge_list
                if prerequisite_id in coordinates and research_id in coordinates
            ]

        def add_edge_item(
            path: QPainterPath,
            *,
            active: bool,
            prerequisites: tuple[str, ...],
            research: tuple[str, ...],
            z_value: float = -1.0,
            pair_overlay: bool = False,
            visible: bool = True,
            cross_category: bool = False,
        ) -> None:
            edge = QGraphicsPathItem(path)
            edge.setPen(
                self._edge_pen(active, cross_category=cross_category)
                if visible
                else Qt.NoPen
            )
            edge.setZValue(z_value)
            edge.setData(0, prerequisites)
            edge.setData(1, research)
            edge.setData(2, active and visible)
            edge.setData(4, pair_overlay)
            edge.setData(5, cross_category)
            if cross_category and cross_category_legend:
                edge.setToolTip(cross_category_legend)
            self._scene.addItem(edge)

        edge_pair_set = set(edge_list)
        for prerequisites, research in visible_connection_groups:
            start_points = [
                (
                    coordinates[research_id][0] + NODE_WIDTH / 2.0,
                    coordinates[research_id][1] + NODE_HEIGHT,
                )
                for research_id in prerequisites
            ]
            end_points = [
                (
                    coordinates[research_id][0] + NODE_WIDTH / 2.0,
                    coordinates[research_id][1],
                )
                for research_id in research
            ]
            connection_rows = {
                coordinates[research_id][1]
                for research_id in (*prerequisites, *research)
            }
            group_pairs = {
                (prerequisite_id, research_id)
                for prerequisite_id in prerequisites
                for research_id in research
                if (prerequisite_id, research_id) in edge_pair_set
            }
            if not group_pairs:
                group_pairs = {
                    (prerequisite_id, research_id)
                    for prerequisite_id in prerequisites
                    for research_id in research
                }
            active_pairs = group_pairs & active_edge_set
            if len(connection_rows) == 1:
                center_y = coordinates[prerequisites[0]][1] + NODE_HEIGHT / 2.0
                if len(group_pairs) > 1:
                    horizontal_points = sorted(
                        {
                            coordinates[research_id][0] + NODE_WIDTH / 2.0
                            for research_id in (*prerequisites, *research)
                        }
                    )
                    group_path = QPainterPath()
                    group_path.moveTo(horizontal_points[0], center_y)
                    for point in horizontal_points[1:]:
                        group_path.lineTo(point, center_y)
                    add_edge_item(
                        group_path,
                        active=active_pairs == group_pairs,
                        prerequisites=prerequisites,
                        research=research,
                        cross_category=bool(
                            group_pairs & self._cross_category_pairs
                        ),
                    )
                    continue
                for prerequisite_id, research_id in sorted(group_pairs):
                    parent_x = coordinates[prerequisite_id][0]
                    child_x = coordinates[research_id][0]
                    start_x = (
                        parent_x + NODE_WIDTH if parent_x < child_x else parent_x
                    )
                    end_x = (
                        child_x if parent_x < child_x else child_x + NODE_WIDTH
                    )
                    pair_path = QPainterPath()
                    pair_path.moveTo(start_x, center_y)
                    pair_path.lineTo(end_x, center_y)
                    pair = (prerequisite_id, research_id)
                    self._edge_pair_paths[pair] = pair_path
                    add_edge_item(
                        pair_path,
                        active=pair in active_pairs,
                        prerequisites=(prerequisite_id,),
                        research=(research_id,),
                        cross_category=pair in self._cross_category_pairs,
                    )
                continue
            path = QPainterPath()
            # Route the bus through the final gap before the destination row.
            # For adjacent rows this is their midpoint.  For a long branch it
            # avoids drawing the horizontal bus through an intermediate card.
            middle_y = min(point[1] for point in end_points) - VERTICAL_GAP / 2.0
            for start_x, start_y in start_points:
                path.moveTo(start_x, start_y)
                path.lineTo(start_x, middle_y)
            bus_points = [point[0] for point in (*start_points, *end_points)]
            path.moveTo(min(bus_points), middle_y)
            path.lineTo(max(bus_points), middle_y)
            for end_x, end_y in end_points:
                path.moveTo(end_x, middle_y)
                path.lineTo(end_x, end_y)
            all_active = active_pairs == group_pairs
            add_edge_item(
                path,
                active=all_active,
                prerequisites=prerequisites,
                research=research,
                cross_category=bool(group_pairs & self._cross_category_pairs),
            )
            if len(group_pairs) > 1:
                for prerequisite_id, research_id in sorted(group_pairs):
                    start_x = coordinates[prerequisite_id][0] + NODE_WIDTH / 2.0
                    start_y = coordinates[prerequisite_id][1] + NODE_HEIGHT
                    end_x = coordinates[research_id][0] + NODE_WIDTH / 2.0
                    end_y = coordinates[research_id][1]
                    active_path = QPainterPath()
                    active_path.moveTo(start_x, start_y)
                    active_path.lineTo(start_x, middle_y)
                    active_path.lineTo(end_x, middle_y)
                    active_path.lineTo(end_x, end_y)
                    pair = (prerequisite_id, research_id)
                    self._edge_pair_paths[pair] = active_path
                    if pair in active_pairs and not all_active:
                        add_edge_item(
                            active_path,
                            active=True,
                            prerequisites=(prerequisite_id,),
                            research=(research_id,),
                            z_value=-0.9,
                            pair_overlay=True,
                            cross_category=pair in self._cross_category_pairs,
                        )

        if self._cross_category_pairs and cross_category_legend:
            legend = QGraphicsTextItem(cross_category_legend)
            legend.setData(10, "cross-category-legend")
            legend.setDefaultTextColor(
                QColor(
                    "#7FE3F2"
                    if self._visual_style == "mobile"
                    else "#75D5E8"
                )
            )
            legend_font = QFont()
            legend_font.setPointSizeF(11.0 * self._font_size / 20.0)
            legend_font.setBold(True)
            legend.setFont(legend_font)
            legend.setPos(SCENE_MARGIN, 12.0)
            legend.setZValue(2.0)
            self._scene.addItem(legend)

        for research_id, (x, y) in coordinates.items():
            item = _ResearchNodeItem(
                by_id[research_id],
                selected_callback=self.researchSelected.emit,
                activated_callback=self.researchActivated.emit,
                level_editing_enabled=self._level_editing_enabled,
                visual_style=self._visual_style,
                font_size=self._font_size,
            )
            item.setPos(x, y)
            self._scene.addItem(item)
            self._node_items[research_id] = item
            if research_id == selected_research_id:
                item.setSelected(True)

        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(
                -SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN, SCENE_MARGIN
            )
        )

    def update_research_state(
        self,
        node: ResearchTreeNode,
        active_edges: Iterable[tuple[str, str]],
    ) -> bool:
        item = self._node_items.get(node.research_id)
        if item is None:
            return False
        item.update_node(node)
        active_edge_set = set(active_edges)
        for edge in tuple(self._scene.items()):
            if isinstance(edge, QGraphicsPathItem) and bool(edge.data(4)):
                self._scene.removeItem(edge)
        overlays: list[tuple[tuple[str, str], QPainterPath]] = []
        for edge in tuple(self._scene.items()):
            if not isinstance(edge, QGraphicsPathItem):
                continue
            prerequisites = tuple(edge.data(0) or ())
            research = tuple(edge.data(1) or ())
            group_pairs = {
                (prerequisite_id, research_id)
                for prerequisite_id in prerequisites
                for research_id in research
                if (prerequisite_id, research_id) in self._edge_pairs
            }
            if not group_pairs:
                group_pairs = {
                    (prerequisite_id, research_id)
                    for prerequisite_id in prerequisites
                    for research_id in research
                }
            active_pairs = group_pairs & active_edge_set
            active = bool(group_pairs) and active_pairs == group_pairs
            edge.setPen(
                self._edge_pen(active, cross_category=bool(edge.data(5)))
            )
            edge.setData(2, active)
            if len(group_pairs) > 1 and not active:
                for pair in active_pairs:
                    pair_path = self._edge_pair_paths.get(pair)
                    if pair_path is not None:
                        overlays.append((pair, pair_path))
        for (prerequisite_id, research_id), path in overlays:
            overlay = QGraphicsPathItem(path)
            overlay.setZValue(-0.9)
            overlay.setData(0, (prerequisite_id,))
            overlay.setData(1, (research_id,))
            overlay.setData(2, True)
            overlay.setData(4, True)
            cross_category = (
                prerequisite_id,
                research_id,
            ) in self._cross_category_pairs
            overlay.setData(5, cross_category)
            overlay.setPen(
                self._edge_pen(True, cross_category=cross_category)
            )
            self._scene.addItem(overlay)
        self.viewport().update()
        return True
