from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QFontMetricsF, QImage, QPainter, QTextOption, QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsPathItem,
    QSlider,
    QSpinBox,
    QToolButton,
    QWidget,
)

from rlm_research_planner.ui.research_tree_view import (
    HORIZONTAL_GAP,
    NODE_WIDTH,
    ResearchTreeNode,
    ResearchTreeView,
)
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)


def _catalog_path() -> Path:
    return Path(__file__).parents[1] / "data" / "research" / "catalog.json"


def test_research_node_renders_label_meter_and_effects_inside_scene() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.set_research(
        [
            ResearchTreeNode(
                research_id="test",
                name="研究名ラベル",
                current_level=4,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=1,
                current_effect="+4%",
                next_effect="+5%",
                layout_row=0,
                layout_column=0,
            )
        ],
        [],
    )
    node = next(
        item for item in view.scene().items() if hasattr(item, "research_id")
    )
    assert node.title_item.toPlainText() == "研究名ラベル"
    assert node.level_item.toPlainText() == "4 / 10"
    assert node.current_effect_item.toPlainText() == "+4%"
    assert node.next_effect_item.toPlainText() == "+5%"
    assert node.title_item.font().pointSizeF() > 20.0
    assert node.current_effect_item.font().pointSizeF() > 14.0
    for text_item in (
        node.title_item,
        node.level_item,
        node.current_effect_item,
        node.next_effect_item,
    ):
        option = text_item.document().defaultTextOption()
        assert option.alignment() == Qt.AlignCenter
        assert option.wrapMode() == QTextOption.NoWrap
    assert node.meter_fill.rect().width() > 0
    assert view.sceneRect().contains(view.scene().itemsBoundingRect())


def test_long_tree_text_fits_its_single_line_regions() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.set_research(
        [
            ResearchTreeNode(
                research_id="long",
                name="ワンダー騎兵遠距離攻撃力強化III",
                current_level=9,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=0,
                current_effect="ワンダー騎兵遠距離攻撃力+123.45%",
                next_effect="ワンダー騎兵遠距離攻撃力+150.00%",
                layout_row=0,
                layout_column=0,
            )
        ],
        [],
    )
    node = next(item for item in view.scene().items() if hasattr(item, "research_id"))
    for item, width, height in (
        (node.title_item, NODE_WIDTH - 24.0, 43.0),
        (node.level_item, NODE_WIDTH - 24.0, 24.0),
        (node.current_effect_item, NODE_WIDTH - 24.0, 48.0),
        (node.next_effect_item, NODE_WIDTH - 24.0, 48.0),
    ):
        metrics = QFontMetricsF(item.font())
        assert metrics.horizontalAdvance(item.toPlainText()) <= width
        assert metrics.height() <= height
    view.close()


def test_mobile_visual_style_uses_pwa_tree_palette() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.resize(420, 320)
    view.set_visual_style("mobile")
    view.set_research(
        [
            ResearchTreeNode(
                research_id="test",
                name="研究名",
                current_level=4,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=1,
            )
        ],
        [],
    )
    node = next(
        item for item in view.scene().items() if hasattr(item, "research_id")
    )
    assert view.visual_style == "mobile"
    assert view.backgroundBrush().color().name().upper() == "#07141C"
    assert node.brush().color().name().upper() == "#4B3910"
    assert node.pen().color().name().upper() == "#F2B632"
    view.show()
    app.processEvents()
    image = QImage(view.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    view.render(painter)
    painter.end()
    grid_pixels = sum(
        image.pixelColor(x, y).name().upper() == "#102631"
        for y in range(image.height())
        for x in range(image.width())
    )
    assert grid_pixels > 100

    view.set_visual_style("desktop")
    assert view.visual_style == "desktop"
    assert view.backgroundBrush().color().name().upper() == "#111820"
    assert node.brush().color().name().upper() == "#493716"
    app.processEvents()
    desktop_image = QImage(view.size(), QImage.Format.Format_RGB32)
    desktop_image.fill(Qt.GlobalColor.black)
    desktop_painter = QPainter(desktop_image)
    view.render(desktop_painter)
    desktop_painter.end()
    desktop_grid_pixels = sum(
        desktop_image.pixelColor(x, y).name().upper() == "#26323B"
        for y in range(desktop_image.height())
        for x in range(desktop_image.width())
    )
    assert desktop_grid_pixels > 100


def test_selected_research_card_has_a_high_contrast_outline() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.resize(420, 320)
    view.set_research(
        [
            ResearchTreeNode(
                research_id="selected",
                name="選択した研究",
                current_level=0,
                max_level=10,
                status="未着手",
                recommendation="test",
                display_order=1,
            )
        ],
        [],
        selected_research_id="selected",
    )
    view.show()
    app.processEvents()
    image = QImage(view.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.black)
    painter = QPainter(image)
    view.render(painter)
    painter.end()
    selected_outline_pixels = sum(
        image.pixelColor(x, y).name().upper() == "#C58BFF"
        for y in range(image.height())
        for x in range(image.width())
    )
    assert selected_outline_pixels > 100
    view.close()


def test_tree_connections_distinguish_unmet_and_unlocked_prerequisites() -> None:
    _app = QApplication.instance() or QApplication([])
    nodes = [
        ResearchTreeNode(
            research_id=research_id,
            name=research_id,
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=index,
            layout_column=0,
        )
        for index, research_id in enumerate(("parent", "child"))
    ]
    view = ResearchTreeView()
    view.set_research(nodes, [("parent", "child")], active_edges=[])
    edge = next(
        item for item in view.scene().items() if isinstance(item, QGraphicsPathItem)
    )
    assert edge.data(2) is False
    assert edge.pen().color().name().upper() == "#46545D"

    view.set_visual_style("mobile")
    assert edge.pen().color().name().upper() == "#35505A"

    view.set_research(
        nodes,
        [("parent", "child")],
        active_edges=[("parent", "child")],
    )
    edge = next(
        item for item in view.scene().items() if isinstance(item, QGraphicsPathItem)
    )
    assert edge.data(2) is True
    assert edge.pen().color().name().upper() == "#F2B632"


def test_cross_category_prerequisite_is_labeled_and_uses_a_dashed_edge() -> None:
    _app = QApplication.instance() or QApplication([])
    nodes = [
        ResearchTreeNode(
            research_id="economy_requirement",
            name="保管庫管理",
            current_level=7,
            max_level=10,
            status="不足",
            recommendation="必要 Lv.10",
            display_order=0,
            layout_row=0,
            layout_column=0,
            category_id="economy",
            category_name="経済",
        ),
        ResearchTreeNode(
            research_id="military_requirement",
            name="軍隊攻撃力Ⅰ",
            current_level=9,
            max_level=10,
            status="不足",
            recommendation="必要 Lv.10",
            display_order=1,
            layout_row=1,
            layout_column=0,
            category_id="military",
            category_name="軍事",
        ),
    ]
    view = ResearchTreeView()
    view.set_research(
        nodes,
        [("economy_requirement", "military_requirement")],
        cross_category_legend="点線：別分野からつながる前提研究",
    )

    cards = {
        item.research_id: item
        for item in view.scene().items()
        if getattr(item, "research_id", "")
    }
    assert cards["economy_requirement"].category_item.toPlainText() == "経済"
    assert cards["military_requirement"].category_item.toPlainText() == "軍事"
    edge = next(
        item for item in view.scene().items() if isinstance(item, QGraphicsPathItem)
    )
    assert edge.data(5) is True
    assert edge.pen().style() == Qt.DashLine
    assert edge.pen().color().name().upper() == "#55BFD4"
    legend = next(
        item
        for item in view.scene().items()
        if item.data(10) == "cross-category-legend"
    )
    assert legend.toPlainText() == "点線：別分野からつながる前提研究"
    view.close()


def test_tree_zoom_is_bounded() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.wheelEvent(
        QWheelEvent(
            QPointF(10.0, 10.0),
            QPointF(10.0, 10.0),
            QPoint(),
            QPoint(0, 120),
            Qt.NoButton,
            Qt.ControlModifier,
            Qt.NoScrollPhase,
            False,
        )
    )
    assert view.zoom_factor > 1.0
    view._zoom_by_steps(100)
    assert view.zoom_factor == 2.5
    view._zoom_by_steps(-100)
    assert view.zoom_factor == 0.35
    view.reset_zoom()
    assert view.zoom_factor == 1.0


def test_shared_connection_group_draws_one_bus_instead_of_crossing_edges() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    prerequisite_ids = ("army_def", "army_atk", "army_hp")
    research_ids = ("fighter", "destroyer", "cannoneer", "drake")
    nodes = [
        ResearchTreeNode(
            research_id=research_id,
            name=research_id,
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=0 if research_id in prerequisite_ids else 1,
            layout_column=index if research_id in prerequisite_ids else index - 3,
        )
        for index, research_id in enumerate((*prerequisite_ids, *research_ids))
    ]
    view.set_research(
        nodes,
        [
            (prerequisite_id, research_id)
            for prerequisite_id in prerequisite_ids
            for research_id in research_ids
        ],
        connection_groups=[(prerequisite_ids, research_ids)],
    )
    paths = [
        item for item in view.scene().items() if isinstance(item, QGraphicsPathItem)
    ]
    assert len(paths) == 1
    assert paths[0].path().elementCount() == 16


def test_same_row_connection_is_horizontal_without_dangling_stems() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    nodes = [
        ResearchTreeNode(
            research_id=research_id,
            name=research_id,
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=0,
            layout_column=index,
        )
        for index, research_id in enumerate(("left", "center", "right"))
    ]
    view.set_research(
        nodes,
        [("center", "left"), ("center", "right")],
        connection_groups=[(("center",), ("left", "right"))],
    )

    paths = [
        item for item in view.scene().items() if isinstance(item, QGraphicsPathItem)
    ]
    assert len(paths) == 1
    path = paths[0].path()
    points = [
        (path.elementAt(index).x, path.elementAt(index).y)
        for index in range(path.elementCount())
    ]
    assert len(points) == 3
    assert len({y for _x, y in points}) == 1


def test_single_same_row_connection_stays_between_card_edges() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    nodes = [
        ResearchTreeNode(
            research_id=research_id,
            name=research_id,
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=0,
            layout_column=index,
        )
        for index, research_id in enumerate(("parent", "child"))
    ]
    view.set_research(nodes, [("parent", "child")])

    path = next(
        item.path()
        for item in view.scene().items()
        if isinstance(item, QGraphicsPathItem)
    )
    start = path.elementAt(0)
    end = path.elementAt(path.elementCount() - 1)
    cards = {
        item.research_id: item
        for item in view.scene().items()
        if getattr(item, "research_id", "")
    }
    assert start.x == pytest.approx(cards["parent"].x() + NODE_WIDTH)
    assert end.x == pytest.approx(cards["child"].x())
    assert start.y == pytest.approx(end.y)
    view.close()


def test_long_vertical_connection_uses_an_empty_column_between_cards() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    layout = (
        ("source", 0, 1),
        ("block_left", 1, 0),
        ("block_right", 1, 2),
        ("target", 2, 1),
        ("lower_left", 3, 0),
        ("lower_center", 3, 1),
        ("lower_right", 3, 2),
    )
    nodes = [
        ResearchTreeNode(
            research_id=research_id,
            name=research_id,
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=row,
            layout_column=column,
        )
        for index, (research_id, row, column) in enumerate(layout)
    ]
    view.set_research(
        nodes,
        [("source", "target")],
        connection_groups=[(("source",), ("target",))],
    )

    path_item = next(
        item
        for item in view.scene().items()
        if isinstance(item, QGraphicsPathItem)
    )
    cards = {
        item.research_id: item
        for item in view.scene().items()
        if hasattr(item, "research_id")
    }
    source_x = cards["source"].sceneBoundingRect().center().x()
    assert cards["target"].sceneBoundingRect().center().x() == source_x
    assert {
        path_item.path().elementAt(index).x
        for index in range(path_item.path().elementCount())
    } == {source_x}
    assert not (
        cards["block_left"].sceneBoundingRect().left()
        <= source_x
        <= cards["block_left"].sceneBoundingRect().right()
    )
    assert not (
        cards["block_right"].sceneBoundingRect().left()
        <= source_x
        <= cards["block_right"].sceneBoundingRect().right()
    )


def test_long_branched_connection_routes_its_bus_below_intermediate_cards() -> None:
    _app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    layout = (
        ("source_left", 0, 0),
        ("source_right", 0, 2),
        ("block_center", 1, 1),
        ("target", 2, 1),
    )
    nodes = [
        ResearchTreeNode(
            research_id=research_id,
            name=research_id,
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=row,
            layout_column=column,
        )
        for index, (research_id, row, column) in enumerate(layout)
    ]
    view.set_research(
        nodes,
        [("source_left", "target"), ("source_right", "target")],
        connection_groups=[(("source_left", "source_right"), ("target",))],
    )

    path_item = next(
        item
        for item in view.scene().items()
        if isinstance(item, QGraphicsPathItem)
    )
    cards = {
        item.research_id: item
        for item in view.scene().items()
        if hasattr(item, "research_id")
    }
    path = path_item.path()
    points = [
        QPointF(path.elementAt(index).x, path.elementAt(index).y)
        for index in range(path.elementCount())
    ]
    horizontal_y = next(
        left.y()
        for left, right in zip(points, points[1:])
        if left.y() == right.y() and left.x() != right.x()
    )
    blocker = cards["block_center"].sceneBoundingRect()
    target = cards["target"].sceneBoundingRect()
    assert blocker.bottom() < horizontal_y < target.top()


def test_all_catalog_trees_draw_every_card_and_route_around_other_cards() -> None:
    _app = QApplication.instance() or QApplication([])
    categories = JsonResearchCatalogRepository(_catalog_path()).load_all()

    for category in categories:
        view = ResearchTreeView()
        nodes = [
            ResearchTreeNode(
                research_id=node.id,
                name=node.names.get("en-US", node.id),
                current_level=0,
                max_level=node.max_level,
                status="not started",
                recommendation="test",
                display_order=index,
                layout_row=node.row,
                layout_column=node.column,
            )
            for index, node in enumerate(category.nodes)
        ]
        groups = [
            (group.prerequisite_ids, group.research_ids)
            for group in category.connection_groups
        ]
        view.set_research(
            nodes,
            [
                (edge.prerequisite_id, edge.research_id)
                for edge in category.edges
            ],
            connection_groups=groups,
        )
        cards = {
            item.research_id: item
            for item in view.scene().items()
            if hasattr(item, "research_id")
        }
        paths = [
            item
            for item in view.scene().items()
            if isinstance(item, QGraphicsPathItem)
        ]
        assert len(cards) == len(category.nodes), category.category_id
        assert len(paths) == len(category.connection_groups), category.category_id
        catalog_nodes = category.node_by_id()
        for row in {node.row for node in category.nodes}:
            ordered_ids = [
                node.id
                for node in sorted(
                    (item for item in category.nodes if item.row == row),
                    key=lambda item: item.column,
                )
            ]
            centers = [
                cards[research_id].sceneBoundingRect().center().x()
                for research_id in ordered_ids
            ]
            assert centers == sorted(centers), category.category_id
            for left_id, right_id in zip(ordered_ids, ordered_ids[1:]):
                left_bounds = cards[left_id].sceneBoundingRect()
                right_bounds = cards[right_id].sceneBoundingRect()
                assert left_bounds.right() < right_bounds.left(), (
                    category.category_id,
                    catalog_nodes[left_id].column,
                    catalog_nodes[right_id].column,
                )

        for path_item in paths:
            endpoint_ids = set(path_item.data(0)) | set(path_item.data(1))
            path = path_item.path()
            for index in range(1, path.elementCount()):
                current = path.elementAt(index)
                if current.isMoveTo():
                    continue
                previous = path.elementAt(index - 1)
                left = min(previous.x, current.x)
                right = max(previous.x, current.x)
                top = min(previous.y, current.y)
                bottom = max(previous.y, current.y)
                for research_id, card in cards.items():
                    if research_id in endpoint_ids:
                        continue
                    bounds = card.sceneBoundingRect().adjusted(1.0, 1.0, -1.0, -1.0)
                    if previous.x == current.x:
                        crosses = (
                            bounds.left() < previous.x < bounds.right()
                            and top < bounds.bottom()
                            and bottom > bounds.top()
                        )
                    else:
                        crosses = (
                            bounds.top() < previous.y < bounds.bottom()
                            and left < bounds.right()
                            and right > bounds.left()
                        )
                    assert not crosses, (
                        category.category_id,
                        tuple(path_item.data(0)),
                        tuple(path_item.data(1)),
                        research_id,
                    )


def test_card_click_selects_but_card_drag_pans_without_selecting() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.resize(360, 260)
    nodes = [
        ResearchTreeNode(
            research_id=f"research_{index}",
            name=f"Research {index}",
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=index,
            layout_row=index,
            layout_column=0,
        )
        for index in range(5)
    ]
    view.set_research(nodes, [])
    selected: list[str] = []
    view.researchSelected.connect(selected.append)
    view.show()
    app.processEvents()

    card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "research_4"
    )
    view.centerOn(card)
    app.processEvents()
    start = view.mapFromScene(card.sceneBoundingRect().center())
    before_scroll = view.verticalScrollBar().value()
    QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(view.viewport(), start + QPoint(0, 48), delay=10)
    QTest.mouseRelease(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, start + QPoint(0, 48)
    )
    app.processEvents()
    assert view.verticalScrollBar().value() != before_scroll
    assert selected == []

    click_position = view.mapFromScene(card.sceneBoundingRect().center())
    QTest.mouseClick(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, click_position
    )
    app.processEvents()
    assert selected == ["research_4"]
    view.close()


def test_meter_click_opens_inline_level_editor_and_emits_change() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView(level_editing_enabled=True)
    view.resize(420, 320)
    view.set_research(
        [
            ResearchTreeNode(
                research_id="test",
                name="研究項目",
                current_level=4,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=0,
                layout_row=0,
                layout_column=0,
            )
        ],
        [],
    )
    changed: list[tuple[str, int]] = []
    view.researchLevelChanged.connect(
        lambda research_id, level: changed.append((research_id, level))
    )
    view.show()
    app.processEvents()

    card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "test"
    )
    scene_item_count = len(view.scene().items())
    meter_position = view.mapFromScene(card.mapToScene(QPointF(122.0, 74.0)))
    QTest.mouseClick(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, meter_position
    )
    app.processEvents()
    editor = view._level_editor
    assert editor is not None
    assert isinstance(editor, QWidget)
    slider = view._level_value_editor
    assert isinstance(slider, QSlider)
    assert slider.hasFocus()
    decrease = editor.findChild(QToolButton, "levelDecreaseButton")
    increase = editor.findChild(QToolButton, "levelIncreaseButton")
    assert decrease is not None
    assert increase is not None
    assert decrease.text() == "−"
    assert increase.text() == "+"
    assert len(view.scene().items()) == scene_item_count
    assert card in view.scene().items()
    assert card.isVisible()
    assert card.title_item.isVisible()
    assert card.level_item.isVisible()
    assert card.current_effect_item.isVisible()
    assert card.next_effect_item.isVisible()
    QTest.mouseClick(increase, Qt.LeftButton)
    app.processEvents()
    assert slider.value() == 5
    assert view._level_editor is editor
    assert changed == []
    QTest.mouseClick(increase, Qt.LeftButton)
    app.processEvents()
    assert slider.value() == 6
    assert view._level_editor is editor
    assert changed == []
    slider.setValue(7)
    QTest.mouseClick(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, QPoint(8, 300)
    )
    app.processEvents()

    assert changed == [("test", 7)]
    view.close()


def test_level_number_click_uses_numeric_input_without_maximum_suffix() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView(level_editing_enabled=True)
    view.resize(420, 320)
    view.set_research(
        [
            ResearchTreeNode(
                research_id="test",
                name="研究項目",
                current_level=4,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=0,
                layout_row=0,
                layout_column=0,
            )
        ],
        [],
    )
    view.show()
    app.processEvents()
    card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "test"
    )
    level_position = view.mapFromScene(card.mapToScene(QPointF(122.0, 96.0)))
    QTest.mouseClick(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, level_position
    )
    app.processEvents()

    editor = view._level_editor
    assert isinstance(editor, QSpinBox)
    assert editor.suffix() == ""
    assert editor.maximum() == 10
    assert card.level_item.isVisible()
    view.close()


def test_level_area_double_click_stays_in_the_level_editor() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView(level_editing_enabled=True)
    view.resize(420, 320)
    view.set_research(
        [
            ResearchTreeNode(
                research_id="test",
                name="研究項目",
                current_level=4,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=0,
                layout_row=0,
                layout_column=0,
            )
        ],
        [],
    )
    activated: list[str] = []
    view.researchActivated.connect(activated.append)
    view.show()
    app.processEvents()
    card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "test"
    )
    level_position = view.mapFromScene(card.mapToScene(QPointF(122.0, 96.0)))
    QTest.mouseClick(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, level_position
    )
    app.processEvents()
    editor = view._level_editor
    assert editor is not None
    QTest.mouseDClick(
        editor, Qt.LeftButton, Qt.NoModifier, editor.rect().center()
    )
    app.processEvents()

    assert activated == []
    assert view._level_editor is editor
    assert card.level_item.isVisible()
    view.close()


def test_title_double_click_still_opens_the_research_plan() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView(level_editing_enabled=True)
    view.resize(420, 320)
    view.set_research(
        [
            ResearchTreeNode(
                research_id="test",
                name="研究項目",
                current_level=4,
                max_level=10,
                status="進行中",
                recommendation="test",
                display_order=0,
                layout_row=0,
                layout_column=0,
            )
        ],
        [],
    )
    activated: list[str] = []
    view.researchActivated.connect(activated.append)
    view.show()
    app.processEvents()
    card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "test"
    )
    title_position = view.mapFromScene(card.mapToScene(QPointF(122.0, 30.0)))
    QTest.mouseDClick(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, title_position
    )
    app.processEvents()

    assert activated == ["test"]
    view.close()


def test_incremental_level_update_keeps_cards_and_updates_connection_state() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView(level_editing_enabled=True)
    nodes = [
        ResearchTreeNode(
            research_id="parent",
            name="Parent",
            current_level=1,
            max_level=10,
            status="in progress",
            recommendation="test",
            display_order=0,
            layout_row=0,
            layout_column=0,
        ),
        ResearchTreeNode(
            research_id="child",
            name="Child",
            current_level=0,
            max_level=10,
            status="not started",
            recommendation="test",
            display_order=1,
            layout_row=1,
            layout_column=0,
        ),
    ]
    view.set_research(nodes, [("parent", "child")], active_edges=[])
    child_card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "child"
    )
    scene_items = tuple(view.scene().items())
    assert not any(
        bool(item.data(2))
        for item in scene_items
        if isinstance(item, QGraphicsPathItem)
    )

    changed = ResearchTreeNode(
        research_id="child",
        name="Child",
        current_level=1,
        max_level=10,
        status="in progress",
        recommendation="test",
        display_order=1,
        current_effect="+1%",
        next_effect="+2%",
        layout_row=1,
        layout_column=0,
    )
    assert view.update_research_state(changed, [("parent", "child")])
    app.processEvents()

    assert child_card in view.scene().items()
    assert tuple(view.scene().items()) == scene_items
    assert child_card.level_item.toPlainText() == "1 / 10"
    assert child_card.current_effect_item.toPlainText() == "+1%"
    assert any(
        bool(item.data(2))
        for item in view.scene().items()
        if isinstance(item, QGraphicsPathItem)
    )
    view.close()


def test_explicit_columns_can_preserve_a_deliberate_center_lane() -> None:
    view = ResearchTreeView()
    nodes = [
        ResearchTreeNode(
            research_id="military",
            name="Military",
            current_level=0,
            max_level=1,
            status="not started",
            recommendation="test",
            display_order=0,
            layout_row=0,
            layout_column=1,
        ),
        ResearchTreeNode(
            research_id="economy",
            name="Economy",
            current_level=0,
            max_level=1,
            status="not started",
            recommendation="test",
            display_order=1,
            layout_row=0,
            layout_column=3,
        ),
    ]
    view.set_research(nodes, [], preserve_explicit_columns=True)

    cards = {
        item.research_id: item
        for item in view.scene().items()
        if getattr(item, "research_id", "")
    }
    assert cards["economy"].x() - cards["military"].x() == pytest.approx(
        2 * (NODE_WIDTH + HORIZONTAL_GAP)
    )
    view.close()


def test_drag_starting_on_meter_pans_without_opening_editor() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView(level_editing_enabled=True)
    view.resize(360, 260)
    view.set_research(
        [
            ResearchTreeNode(
                research_id=f"research_{index}",
                name=f"Research {index}",
                current_level=0,
                max_level=10,
                status="not started",
                recommendation="test",
                display_order=index,
                layout_row=index,
                layout_column=0,
            )
            for index in range(5)
        ],
        [],
    )
    view.show()
    app.processEvents()
    card = next(
        item
        for item in view.scene().items()
        if getattr(item, "research_id", "") == "research_4"
    )
    view.centerOn(card)
    app.processEvents()
    start = view.mapFromScene(card.mapToScene(QPointF(122.0, 74.0)))
    before_scroll = view.verticalScrollBar().value()
    QTest.mousePress(view.viewport(), Qt.LeftButton, Qt.NoModifier, start)
    QTest.mouseMove(view.viewport(), start + QPoint(0, 48), delay=10)
    QTest.mouseRelease(
        view.viewport(), Qt.LeftButton, Qt.NoModifier, start + QPoint(0, 48)
    )
    app.processEvents()

    assert view.verticalScrollBar().value() != before_scroll
    assert view._level_editor is None
    view.close()


def test_focus_research_selects_and_scrolls_a_distant_card_into_view() -> None:
    app = QApplication.instance() or QApplication([])
    view = ResearchTreeView()
    view.resize(360, 260)
    view.set_research(
        [
            ResearchTreeNode(
                research_id=f"talent_{index}",
                name=f"Talent {index}",
                current_level=0,
                max_level=10,
                status="not planned",
                recommendation="test",
                display_order=index,
                layout_row=index,
                layout_column=0,
            )
            for index in range(12)
        ],
        [],
        preserve_explicit_columns=True,
    )
    view.show()
    app.processEvents()

    before_scroll = view.verticalScrollBar().value()
    assert view.focus_research("talent_11")
    app.processEvents()

    selected = [
        item
        for item in view.scene().selectedItems()
        if getattr(item, "research_id", "") == "talent_11"
    ]
    assert selected
    assert view.verticalScrollBar().value() > before_scroll
    view.close()
