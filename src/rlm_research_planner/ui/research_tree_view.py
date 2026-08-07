from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PySide6.QtCore import QPoint, QPointF, Qt, Signal, QTimer
from PySide6.QtGui import (
    QColor,
    QFont,
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
    QSlider,
    QSpinBox,
    QWidget,
)

from rlm_research_planner.services.tree_layout import (
    calculate_tree_positions,
    compact_explicit_row_slots,
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
    layout_column: int | None = None
    shortage_levels: int = 0


class _ResearchNodeItem(QGraphicsRectItem):
    def __init__(
        self,
        node: ResearchTreeNode,
        *,
        selected_callback,
        activated_callback,
        level_editing_enabled: bool = False,
    ) -> None:
        super().__init__(0.0, 0.0, NODE_WIDTH, NODE_HEIGHT)
        self.research_id = node.research_id
        self._selected_callback = selected_callback
        self._activated_callback = activated_callback
        self._level_editing_enabled = level_editing_enabled
        self._current_level = 0 if node.current_level is None else node.current_level
        self._max_level = node.max_level
        self.setFlag(QGraphicsRectItem.ItemIsSelectable, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(f"{node.name}\n{node.status}\n{node.recommendation}")

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

        title_font = QFont()
        title_font.setPointSizeF(26.0)
        title_font.setBold(True)
        self.title_item = self._text_item(
            node.name,
            title_font,
            QColor("#FFFFFF"),
            x=12.0,
            y=8.0,
            width=NODE_WIDTH - 24.0,
            height=43.0,
        )

        divider = QGraphicsRectItem(12.0, 57.0, NODE_WIDTH - 24.0, 1.0, self)
        divider.setPen(Qt.NoPen)
        divider.setBrush(QColor("#496170"))
        divider.setZValue(1.0)

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
        level_font.setPointSizeF(20.0)
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
        effect_font.setPointSizeF(20.0)
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
        maximum_point_size = font.pointSizeF()
        low = 1.0
        high = maximum_point_size
        best = low
        for _ in range(10):
            point_size = (low + high) / 2.0
            fitted_font = QFont(font)
            fitted_font.setPointSizeF(point_size)
            item.setFont(fitted_font)
            rendered_bounds = item.boundingRect()
            if (
                rendered_bounds.width() <= width + 0.5
                and rendered_bounds.height() <= height + 0.5
            ):
                best = point_size
                low = point_size
            else:
                high = point_size
        fitted_font = QFont(font)
        fitted_font.setPointSizeF(best)
        item.setFont(fitted_font)
        item.setPos(x, y + max(0.0, (height - item.boundingRect().height()) / 2.0))
        return item

    def itemChange(self, change, value):
        if change == QGraphicsRectItem.ItemSelectedHasChanged and bool(value):
            self._selected_callback(self.research_id)
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
        self._zoom_factor = 1.0
        self._pointer_origin: QPoint | None = None
        self._pointer_last: QPoint | None = None
        self._pointer_node: _ResearchNodeItem | None = None
        self._pointer_dragging = False
        self._pending_level_research_id = ""
        self._pending_level_editor_kind = ""
        self._level_edit_timer = QTimer(self)
        self._level_edit_timer.setSingleShot(True)
        self._level_edit_timer.timeout.connect(self._open_pending_level_editor)
        self._level_editor: QWidget | None = None
        self._level_editor_commit = None

    @property
    def zoom_factor(self) -> float:
        return self._zoom_factor

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            if steps:
                self._zoom_by_steps(steps)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event) -> None:
        self._cancel_pending_level_edit()
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
                self._schedule_level_edit(pressed_node.research_id, editor_kind)
            else:
                self._scene.clearSelection()
                pressed_node.setSelected(True)
        event.accept()

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            node = self._node_at(event.position().toPoint())
            if node is not None:
                self._cancel_pending_level_edit()
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
        self._level_editor = None
        self._level_editor_commit = None
        if editor is not None:
            editor.blockSignals(True)
            editor.hide()
            editor.setParent(None)
            editor.deleteLater()

    def _schedule_level_edit(self, research_id: str, editor_kind: str) -> None:
        self._pending_level_research_id = research_id
        self._pending_level_editor_kind = editor_kind
        app = QApplication.instance()
        interval = app.doubleClickInterval() if app is not None else 400
        self._level_edit_timer.start(max(1, interval))

    def _cancel_pending_level_edit(self) -> None:
        self._level_edit_timer.stop()
        self._pending_level_research_id = ""
        self._pending_level_editor_kind = ""

    def _open_pending_level_editor(self) -> None:
        research_id = self._pending_level_research_id
        editor_kind = self._pending_level_editor_kind
        self._pending_level_research_id = ""
        self._pending_level_editor_kind = ""
        if not research_id or editor_kind not in {"number", "slider"}:
            return
        for item in self._scene.items():
            if (
                isinstance(item, _ResearchNodeItem)
                and item.research_id == research_id
            ):
                self._show_level_editor(item, editor_kind)
                return

    def _show_level_editor(
        self, item: _ResearchNodeItem, editor_kind: str = "number"
    ) -> None:
        if item._max_level is None:
            return
        self._cancel_level_editor()
        if editor_kind == "slider":
            editor = QSlider(Qt.Horizontal, self.viewport())
            editor.setRange(0, item._max_level)
            editor.setValue(item._current_level)
            editor.setSingleStep(1)
            editor.setPageStep(1)
            editor.setStyleSheet(
                "QSlider{background:#101A20;border:2px solid #E0A72B;}"
                "QSlider::groove:horizontal{height:8px;background:#34434C;}"
                "QSlider::sub-page:horizontal{background:#E0A72B;}"
                "QSlider::handle:horizontal{width:18px;margin:-6px 0;"
                "background:#FFFFFF;border:1px solid #8B6B19;}"
            )
            top_left = self.mapFromScene(item.mapToScene(QPointF(12.0, 62.0)))
            bottom_right = self.mapFromScene(
                item.mapToScene(QPointF(NODE_WIDTH - 12.0, 88.0))
            )
            minimum_width = 150
            minimum_height = 28
        else:
            editor = QSpinBox(self.viewport())
            editor.setRange(0, item._max_level)
            editor.setValue(item._current_level)
            editor.setAlignment(Qt.AlignCenter)
            editor.setKeyboardTracking(False)
            editor.setStyleSheet(
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
        committed = False

        def commit() -> None:
            nonlocal committed
            if committed or self._level_editor is not editor:
                return
            committed = True
            level = editor.value()
            research_id = item.research_id
            self._level_editor = None
            self._level_editor_commit = None
            editor.hide()
            editor.setParent(None)
            editor.deleteLater()
            self.researchLevelChanged.emit(research_id, level)

        self._level_editor_commit = commit
        if isinstance(editor, QSpinBox):
            editor.editingFinished.connect(commit)
        else:
            editor.sliderReleased.connect(commit)
            editor.valueChanged.connect(
                lambda value: self._preview_slider_level(item, value)
            )
        editor.show()
        editor.raise_()
        editor.setFocus(Qt.MouseFocusReason)
        if isinstance(editor, QSpinBox):
            editor.selectAll()

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

    def set_research(
        self,
        nodes: Iterable[ResearchTreeNode],
        prerequisite_edges: Iterable[tuple[str, str]],
        selected_research_id: str = "",
        empty_message: str = "No research entries",
        connection_groups: Iterable[
            tuple[Iterable[str], Iterable[str]]
        ] = (),
    ) -> None:
        self._cancel_pending_level_edit()
        self._cancel_level_editor()
        self._reset_pointer_state()
        node_list = list(nodes)
        edge_list = list(prerequisite_edges)
        connection_group_list = [
            (tuple(prerequisites), tuple(research))
            for prerequisites, research in connection_groups
        ]
        self._scene.clear()
        if not node_list:
            message = QGraphicsTextItem(empty_message)
            message.setDefaultTextColor(QColor("#C9D4DA"))
            message_font = QFont()
            message_font.setPointSizeF(12.0)
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
                max(int(node.layout_column or 0) for node in node_list) + 1
            )
            target_column_count = max(len(row) for row in rows.values())
            for row_index, row_nodes in rows.items():
                row_nodes.sort(key=lambda node: int(node.layout_column or 0))
                slots = compact_explicit_row_slots(
                    (int(node.layout_column or 0) for node in row_nodes),
                    source_column_count=source_column_count,
                    target_column_count=target_column_count,
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
            middle_y = (max(point[1] for point in start_points) + min(
                point[1] for point in end_points
            )) / 2.0
            path = QPainterPath()
            for start_x, start_y in start_points:
                path.moveTo(start_x, start_y)
                path.lineTo(start_x, middle_y)
            bus_points = [point[0] for point in (*start_points, *end_points)]
            path.moveTo(min(bus_points), middle_y)
            path.lineTo(max(bus_points), middle_y)
            for end_x, end_y in end_points:
                path.moveTo(end_x, middle_y)
                path.lineTo(end_x, end_y)
            edge = QGraphicsPathItem(path)
            edge.setPen(QPen(QColor("#D2A51B"), 2.5))
            edge.setZValue(-1.0)
            self._scene.addItem(edge)

        by_id = {node.research_id: node for node in node_list}
        for research_id, (x, y) in coordinates.items():
            item = _ResearchNodeItem(
                by_id[research_id],
                selected_callback=self.researchSelected.emit,
                activated_callback=self.researchActivated.emit,
                level_editing_enabled=self._level_editing_enabled,
            )
            item.setPos(x, y)
            self._scene.addItem(item)
            if research_id == selected_research_id:
                item.setSelected(True)

        self._scene.setSceneRect(
            self._scene.itemsBoundingRect().adjusted(
                -SCENE_MARGIN, -SCENE_MARGIN, SCENE_MARGIN, SCENE_MARGIN
            )
        )
