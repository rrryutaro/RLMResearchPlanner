from __future__ import annotations

import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtGui import QColor, QFontMetrics, QImage, QPainter, QPalette
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QGraphicsPathItem,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QPoint, QPointF, QRect, Qt
from PySide6.QtTest import QTest

from rlm_research_planner.domain.models import (
    PaidItem,
    PaidOffer,
    SpeedupInventoryItem,
)
from rlm_research_planner.paths import AppPaths
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.repositories.master_repository import JsonMasterRepository
from rlm_research_planner.repositories.player_repository import PlayerRepository
from rlm_research_planner.repositories.research_dataset_repository import (
    JsonResearchDatasetRepository,
)
from rlm_research_planner.services.localization import Translator
from rlm_research_planner.services.ocr import OcrCandidate, OcrLine, OcrResult
from rlm_research_planner.services.paid_pack import SpeedupEntry
from rlm_research_planner.services.speedup_inventory import (
    PaidOfferRecommendation,
    SpeedupCoverage,
)
from rlm_research_planner.services.window_capture import CapturableWindow
from rlm_research_planner.settings import AppSettings, SettingsRepository
from rlm_research_planner.ui import main_window as main_window_module
from rlm_research_planner.ui.main_window import MainWindow
from rlm_research_planner.ui.research_tree_view import NODE_HEIGHT, NODE_WIDTH
from rlm_research_planner.ui.step_spin_box import (
    VisibleDoubleSpinBox,
    VisibleSpinBox,
)
from rlm_research_planner.ui.table_cell_widgets import (
    TABLE_CELL_ROW_HEIGHT,
    set_table_cell_widget,
    update_table_cell_widget_visual_styles,
)
from rlm_research_planner.ui.update_controller import UpdateController
from rlm_research_planner.ui.visual_styles import window_style_sheet
from rlm_research_planner.version import version_string


def _rendered_corner_color(widget) -> QColor:
    image = QImage(widget.size(), QImage.Format.Format_RGB32)
    image.fill(Qt.GlobalColor.transparent)
    widget.render(image)
    return image.pixelColor(5, 5)


def _relative_luminance(color: QColor) -> float:
    def component(value: int) -> float:
        normalized = value / 255.0
        if normalized <= 0.04045:
            return normalized / 12.92
        return ((normalized + 0.055) / 1.055) ** 2.4

    return (
        0.2126 * component(color.red())
        + 0.7152 * component(color.green())
        + 0.0722 * component(color.blue())
    )


def _contrast_ratio(first: QColor, second: QColor) -> float:
    brighter, darker = sorted(
        (_relative_luminance(first), _relative_luminance(second)),
        reverse=True,
    )
    return (brighter + 0.05) / (darker + 0.05)


def test_official_japanese_research_category_names_are_present() -> None:
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    names = {
        category.category_id: category.localized_title("ja-JP")
        for category in catalog
    }


    assert names == {
        "economy": "経済",
        "defense": "城壁防御",
        "military": "軍事",
        "monster_hunt": "魔獣討伐",
        "upgrade_defenses": "上級防城",
        "upgrade_military": "上級軍事",
        "army_leadership": "軍隊戦術",
        "military_command": "軍事指令",
        "familiars": "召喚獣",
        "familiar_battles": "召喚獣の出陣",
        "sigils": "シギル",
        "wonder_battles": "ワンダー",
        "gear": "部隊武装",
        "advanced_wonder_battles": "上級ワンダー軍事",
        "mana_awakening": "マナ覚醒",
        "guild_duel": "ギルドデュエル",
    }


def test_guild_duel_provisional_time_and_unverified_special_cost_are_visible_in_plan() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        window._set_plan_target("guild_duel_gathering_incentive")
        app.processEvents()

        special_column = window._plan_resource_columns["special"]
        assert window.plan_table.rowCount() == 2
        assert window.plan_table.item(0, 2).text() == "02:09:05"
        assert window.plan_table.item(0, special_column).text() == window.t(
            "common.unknown"
        )
        assert window.plan_table.item(1, special_column).text() == window.t(
            "common.unknown"
        )
        assert not window.plan_table.isColumnHidden(special_column)
        assert window.t("plan.speedup_unknown_time") not in (
            window.plan_speedup_panel.status_label.text()
        )
        assert not window.plan_speedup_panel.toggle_button.isChecked()
        assert window.plan_speedup_panel.content.isHidden()
        window.close()
    finally:
        player_repository.close()


def test_expanded_speedup_panel_keeps_titles_clear_and_compact() -> None:
    app = QApplication.instance() or QApplication([])

    def translate(key: str, **values: object) -> str:
        suffix = " ".join(str(value) for value in values.values())
        return f"{key} {suffix}".strip()

    panel = main_window_module._SpeedupSimulationPanel(
        translate,
    )
    coverage = SpeedupCoverage(
        target_kind="research",
        required_seconds=20_000_000,
        available_seconds=6_000_000,
        applied_seconds=6_000_000,
        remaining_seconds=14_000_000,
        surplus_seconds=0,
        remaining_task_seconds=(14_000_000,),
        used_items=tuple(
            SpeedupInventoryItem("research", duration, quantity)
            for duration, quantity in (
                (24 * 3600, 60),
                (15 * 3600, 1),
                (8 * 3600, 40),
                (3 * 3600, 428),
                (3600, 961),
                (30 * 60, 607),
                (15 * 60, 357),
            )
        ),
    )
    recommendations = tuple(
        PaidOfferRecommendation(
            offer_id=str(index),
            title=f"Research value pack {index}",
            purchases=1,
            seconds_per_purchase=index * 100_000,
            total_seconds=index * 100_000,
            diamond_cost_each=index * 999,
            total_diamond_cost=index * 999,
            gems_per_purchase=0,
            available_gems=0,
            applied_speedup_seconds=index * 100_000,
            gems_used=0,
            gem_applied_seconds=0,
            remaining_seconds=14_000_000 - index * 100_000,
            excess_seconds=0,
            applied_general_speedup_seconds=(index * 100_000 if index == 1 else 0),
            applied_target_speedup_seconds=(index * 100_000 if index != 1 else 0),
        )
        for index in range(1, 6)
    )
    panel.resize(1200, 360)
    panel.show_result(coverage, recommendations)
    panel.toggle_button.setChecked(True)
    panel.show()
    app.processEvents()

    assert not panel.hint_label.isVisible()
    assert panel.toggle_button.toolTip()
    assert panel.owned_title_label.geometry().right() < (
        panel.available_label.geometry().left()
    )
    assert panel.remaining_title_label.geometry().right() < (
        panel.remaining_label.geometry().left()
    )
    assert not hasattr(panel, "gem_checkbox")
    assert panel.direct_gems_label.isVisible()
    assert panel.used_items_strip.isVisible()
    assert panel.used_items_strip.parent() is panel.owned_group
    assert len(panel.used_item_badges) == 7
    assert all("paid.kind.research" not in badge.text() for badge in panel.used_item_badges)
    assert all(
        badge.text().startswith("plan.speedup_used_item_compact")
        for badge in panel.used_item_badges
    )
    assert panel.used_items_strip.height() < 60
    assert not hasattr(panel, "used_items_toggle")
    assert not panel.offers_group.isVisible()
    assert panel.offers_toggle.parent() is panel.remaining_group
    panel.offers_toggle.click()
    app.processEvents()
    assert panel.offers_group.isVisible()
    assert "5" in panel.offers_toggle.text()
    assert "plan.speedup_offer_sort_order" in panel.offers_toggle.toolTip()
    first_offer = panel.offers_layout.itemAtPosition(0, 0).widget()
    assert first_offer is not None
    assert first_offer.height() < 42
    panel.close()


def test_tree_instant_finish_filter_uses_next_level_speed_and_vip_time() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        assert window.tree_instant_finish_check.text() == "即時終了のみ"
        assert not window.tree_instant_finish_check.isChecked()
        assert window.tree_technolabe_check.text() == "叡智の輪推奨のみ"
        assert not window.tree_technolabe_check.isChecked()
        window.academy_spin.setValue(25)
        window.tree_instant_finish_check.setChecked(True)
        app.processEvents()

        rendered_ids = {
            item.research_id
            for item in window.tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert rendered_ids == {
            "economy_construction_speed",
            "economy_food_harvest_1",
        }
        assert "economy_vault_management" not in rendered_ids

        window.search_edit.setText("建設速度")
        app.processEvents()
        rendered_ids = {
            item.research_id
            for item in window.tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert rendered_ids == {"economy_construction_speed"}

        window.search_edit.clear()
        window.research_speed_boost_spin.setValue(100.0)
        app.processEvents()
        rendered_ids = {
            item.research_id
            for item in window.tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert "economy_vault_management" in rendered_ids

        window._set_tree_level("economy_construction_speed", 10)
        app.processEvents()
        rendered_ids = {
            item.research_id
            for item in window.tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert "economy_construction_speed" not in rendered_ids
        assert "economy_food_harvest_1" in rendered_ids
        window.close()
    finally:
        player_repository.close()


def test_tree_instant_finish_filter_rejects_long_locked_prerequisite() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.vip_level_spin.setValue(11)
        window.academy_spin.setValue(25)
        window.research_speed_spin.setValue(228.0)
        app.processEvents()

        assert not window._research_is_instant_finish(
            "monster_hunt_monster_hunt_iv", 1
        )
        assert not window._research_is_instant_finish(
            "monster_hunt_mp_advantage", 10
        )

        window._set_tree_level("monster_hunt_monster_hunt_iv", 1)
        assert window._research_is_instant_finish(
            "monster_hunt_mp_advantage", 10
        )
        window.close()
    finally:
        player_repository.close()


def test_every_catalog_category_renders_complete_level_zero_cards() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        assert window.tree_dataset_list.currentItem().data(Qt.UserRole) == (
            "observation:catalog-economy"
        )
        assert "QListWidget::item:selected" in window.tree_dataset_list.styleSheet()
        displayed_categories = {
            window.tree_dataset_list.item(index).text()
            for index in range(window.tree_dataset_list.count())
        }
        assert "ワンダー" in displayed_categories
        assert "ギルドデュエル" in displayed_categories
        for category in catalog:
            index = window._dataset_list_row(
                f"observation:{category.observation_id}"
            )
            assert index >= 0
            window.tree_dataset_list.setCurrentRow(index)
            app.processEvents()
            rendered_nodes = [
                item
                for item in window.tree_view.scene().items()
                if hasattr(item, "research_id")
            ]
            assert len(rendered_nodes) == len(category.nodes)
            assert window.tree_view.sceneRect().width() > 1
            assert window.tree_view.sceneRect().contains(
                window.tree_view.scene().itemsBoundingRect()
            )
            for node in rendered_nodes:
                assert node.level_item.toPlainText().startswith("0 / ")
                assert "Lv." not in node.level_item.toPlainText()
                assert "進行中" not in node.level_item.toPlainText()
                assert node.title_item.toPlainText().strip()
                assert node.title_item.toPlainText() != "XXX"
                assert ": " not in node.current_effect_item.toPlainText()
                assert ": " not in node.next_effect_item.toPlainText()
                assert not any(
                    marker in (
                        node.current_effect_item.toPlainText()
                        + node.next_effect_item.toPlainText()
                    )
                    for marker in (
                        "Battle Slot",
                        "Effect",
                        "Manasteel Refinement",
                        "Reduction",
                        "Result",
                        "Unlock",
                        "Upgrade",
                    )
                )
                assert node.next_effect_item.toPlainText().strip() != "-"
                assert node.rect().contains(node.childrenBoundingRect())
            if category.category_id == "economy":
                construction = next(
                    node
                    for node in rendered_nodes
                    if node.research_id == "economy_construction_speed"
                )
                food = next(
                    node
                    for node in rendered_nodes
                    if node.research_id == "economy_food_harvest_1"
                )
                assert "建設速度+0" == construction.current_effect_item.toPlainText()
                assert construction.next_effect_item.toPlainText() == "建設速度+1%"
                assert food.current_effect_item.toPlainText() == "食糧生産量+0"
                assert food.next_effect_item.toPlainText() == "食糧生産量+1%"
                assert "現在効果:" not in construction.current_effect_item.toPlainText()
                assert "次の効果:" not in construction.next_effect_item.toPlainText()
            if category.category_id == "defense":
                upper_trap_group = category.connection_groups[1]
                assert upper_trap_group.prerequisite_ids == (
                    "defense_spikes",
                    "defense_archer_tower",
                    "defense_spike_boulders",
                )
                assert upper_trap_group.research_ids == (
                    "defense_trap_power_i",
                )
                trap_defense = category.node_by_id()[
                    "defense_trap_defense_i"
                ].level_data(1)
                assert trap_defense is not None
                assert {
                    (requirement.research_id, requirement.level)
                    for requirement in trap_defense.requirements
                } == {("defense_trap_power_i", 1)}
                rendered_connections = [
                    item
                    for item in window.tree_view.scene().items()
                    if isinstance(item, QGraphicsPathItem)
                ]
                assert len(rendered_connections) == len(category.connection_groups) == 9
                trap_cards = {
                    item.research_id: item
                    for item in rendered_nodes
                    if item.research_id
                    in {
                        "defense_trap_defense_i",
                        "defense_trap_power_i",
                        "defense_trap_durability_i",
                    }
                }
                trap_centers = {
                    research_id: item.sceneBoundingRect().center()
                    for research_id, item in trap_cards.items()
                }
                upper_cards = {
                    item.research_id: item
                    for item in rendered_nodes
                    if item.research_id
                    in {
                        "defense_spikes",
                        "defense_archer_tower",
                        "defense_spike_boulders",
                    }
                }
                upper_bottom_points = {
                    (
                        round(item.pos().x() + NODE_WIDTH / 2.0),
                        round(item.pos().y() + NODE_HEIGHT),
                    )
                    for item in upper_cards.values()
                }
                upper_bus_paths = []
                for connection in rendered_connections:
                    points = {
                        (
                            round(connection.path().elementAt(index).x),
                            round(connection.path().elementAt(index).y),
                        )
                        for index in range(connection.path().elementCount())
                    }
                    if points >= upper_bottom_points:
                        upper_bus_paths.append(points)
                assert len(upper_bus_paths) == 1
                upper_bus_points = upper_bus_paths[0]
                assert (
                    round(
                        trap_cards["defense_trap_power_i"].pos().x()
                        + NODE_WIDTH / 2.0
                    ),
                    round(trap_cards["defense_trap_power_i"].pos().y()),
                ) in upper_bus_points
                for research_id in (
                    "defense_trap_defense_i",
                    "defense_trap_durability_i",
                ):
                    assert (
                        round(trap_cards[research_id].pos().x() + NODE_WIDTH / 2.0),
                        round(trap_cards[research_id].pos().y()),
                    ) not in upper_bus_points
                center_y = round(trap_centers["defense_trap_power_i"].y())
                assert any(
                    {
                        (
                            round(path.path().elementAt(index).x),
                            round(path.path().elementAt(index).y),
                        )
                        for index in range(path.path().elementCount())
                    }
                    >= {
                        (
                            round(trap_centers[research_id].x()),
                            center_y,
                        )
                        for research_id in trap_centers
                    }
                    for path in rendered_connections
                )
            if category.category_id == "monster_hunt":
                rendered_connections = [
                    item
                    for item in window.tree_view.scene().items()
                    if isinstance(item, QGraphicsPathItem)
                ]
                cards = {
                    item.research_id: item
                    for item in rendered_nodes
                    if item.research_id
                    in {
                        "monster_hunt_energy_recovery_i",
                        "monster_hunt_energy_limit_i",
                        "monster_hunt_energy_saver_i",
                        "monster_hunt_monster_hunt_ii",
                        "monster_hunt_aggressive_hunter_i",
                        "monster_hunt_animal_handling",
                        "monster_hunt_monster_hunter_i",
                    }
                }

                def top_point(research_id: str) -> tuple[int, int]:
                    card = cards[research_id]
                    return (
                        round(card.pos().x() + NODE_WIDTH / 2.0),
                        round(card.pos().y()),
                    )

                def bottom_point(research_id: str) -> tuple[int, int]:
                    card = cards[research_id]
                    return (
                        round(card.pos().x() + NODE_WIDTH / 2.0),
                        round(card.pos().y() + NODE_HEIGHT),
                    )

                path_points = [
                    {
                        (
                            round(path.path().elementAt(index).x),
                            round(path.path().elementAt(index).y),
                        )
                        for index in range(path.path().elementCount())
                    }
                    for path in rendered_connections
                ]
                upper_ids = (
                    "monster_hunt_energy_recovery_i",
                    "monster_hunt_energy_limit_i",
                    "monster_hunt_energy_saver_i",
                )
                lower_ids = (
                    "monster_hunt_aggressive_hunter_i",
                    "monster_hunt_animal_handling",
                    "monster_hunt_monster_hunter_i",
                )
                upper_bus = next(
                    points
                    for points in path_points
                    if points >= {bottom_point(item) for item in upper_ids}
                )
                assert top_point("monster_hunt_monster_hunt_ii") in upper_bus
                assert not any(top_point(item) in upper_bus for item in lower_ids)
                lower_bus = next(
                    points
                    for points in path_points
                    if bottom_point("monster_hunt_monster_hunt_ii") in points
                )
                assert lower_bus >= {top_point(item) for item in lower_ids}
            if category.category_id == "military":
                rendered_connections = [
                    item
                    for item in window.tree_view.scene().items()
                    if isinstance(item, QGraphicsPathItem)
                ]
                assert len(rendered_connections) == len(category.connection_groups) == 25
                dense_row_ids = {
                    node.id for node in category.nodes if node.row == 2
                }
                dense_row_x = sorted(
                    item.x()
                    for item in rendered_nodes
                    if item.research_id in dense_row_ids
                )
                assert len(dense_row_x) == 4
                assert {
                    round(right - left)
                    for left, right in zip(dense_row_x, dense_row_x[1:])
                } == {296}
                army_cards = {
                    item.research_id: item
                    for item in rendered_nodes
                    if item.research_id
                    in {
                        "military_army_defense_i",
                        "military_army_offense_i",
                        "military_army_health_i",
                    }
                }
                army_centers = {
                    research_id: item.sceneBoundingRect().center()
                    for research_id, item in army_cards.items()
                }
                assert (
                    army_centers["military_army_defense_i"].x()
                    < army_centers["military_army_offense_i"].x()
                    < army_centers["military_army_health_i"].x()
                )
                center_y = round(
                    army_centers["military_army_offense_i"].y()
                )
                side_connection = next(
                    path
                    for path in rendered_connections
                    if {
                        (
                            round(path.path().elementAt(index).x),
                            round(path.path().elementAt(index).y),
                        )
                        for index in range(path.path().elementCount())
                    }
                    >= {
                        (
                            round(army_centers["military_army_defense_i"].x()),
                            center_y,
                        ),
                        (
                            round(army_centers["military_army_offense_i"].x()),
                            center_y,
                        ),
                        (
                            round(army_centers["military_army_health_i"].x()),
                            center_y,
                        ),
                    }
                )
                assert side_connection is not None
                assert window.tree_view.sceneRect().width() < 1300
        assert window.tree_capture_button.isEnabled()
        window.close()
    finally:
        player_repository.close()


def test_plan_tab_shows_only_unmet_dependency_tree_and_totals() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window._tree_level_draft.update(
            {
                "defense_trap_durability_i": 7,
                "defense_trap_power_i": 6,
            }
        )
        window._open_tree_detail("defense_trap_durability_i")
        window.plan_level_spin.setValue(8)
        window._calculate_plan()
        app.processEvents()

        rendered_ids = {
            item.research_id
            for item in window.plan_tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert rendered_ids == {
            "defense_trap_power_i",
            "defense_trap_durability_i",
        }
        assert window.tabs.currentIndex() == 1
        assert window._plan_target_research_id == "defense_trap_durability_i"
        assert "/" in window.plan_target_name_label.text()
        assert not hasattr(window, "plan_target_combo")
        assert not hasattr(window, "plan_warnings")
        toolbar_layout = window.plan_toolbar.layout()
        assert toolbar_layout.indexOf(window.plan_mode_combo) >= 0
        assert toolbar_layout.indexOf(window.plan_resource_mode_combo) >= 0
        assert toolbar_layout.indexOf(window.plan_directive_panel) >= 0
        assert toolbar_layout.indexOf(window.plan_shortest_controls) >= 0
        assert window.plan_table.rowCount() == 3
        headers = [
            window.plan_table.horizontalHeaderItem(column).text()
            for column in range(window.plan_table.columnCount())
        ]
        assert headers == [
            "研究",
            "Lv.",
            "元時間",
            "開始時",
            "ヘルプ後",
            "叡智の輪",
            "食糧",
            "石材",
            "木材",
            "鉱石",
            "ゴールド",
            "特殊資源",
            "ゴールドハンマー",
            "戦典",
            "鋼鉄の手枷",
            "霊魂石",
            "古代の書物",
            "マナ鉱石",
            "月晶",
            "必要施設",
            "パワー",
            "操作",
        ]
        assert window.plan_table.item(2, 0).text() == "合計"
        assert window.plan_table.item(2, 1).text() == "2レベル"
        food_column = headers.index("食糧")
        food_steps = sum(
            int(window.plan_table.item(row, food_column).text().replace(",", ""))
            for row in range(2)
            if window.plan_table.item(row, food_column).text() != "-"
        )
        assert window.plan_table.item(2, food_column).text() == f"{food_steps:,}"
        for label in (
            "特殊資源",
            "ゴールドハンマー",
            "戦典",
            "鋼鉄の手枷",
            "霊魂石",
            "古代の書物",
            "マナ鉱石",
            "月晶",
        ):
            assert window.plan_table.isColumnHidden(headers.index(label))
        assert not window.plan_table.isColumnHidden(food_column)
        window.player_state.settings.technolabe_count = 10
        assert "所持" not in window._technolabe_text(2, 95.0)
        assert "所持 10 / 必要 2" in window._technolabe_text(
            2, 95.0, include_owned=True
        )
        assert window.plan_table.isColumnHidden(4)
        assert window.guild_help_spin.maximum() == 6
        window.castle_spin.setValue(25)
        assert window.guild_help_spin.maximum() == 30
        window.guild_help_spin.setValue(30)
        window._calculate_plan()
        app.processEvents()
        assert window.plan_table.horizontalHeaderItem(4).text() == "ヘルプ後"
        assert "最大30回" in window.plan_table.horizontalHeaderItem(4).toolTip()
        assert not window.plan_table.isColumnHidden(4)
        for row in range(3):
            for column in (2, 3, 4):
                assert re.fullmatch(
                    r"(?:\d+d )?\d{2}:\d{2}:\d{2}",
                    window.plan_table.item(row, column).text(),
                )
        assert all(
            "不足 1レベル" == item.next_effect_item.toPlainText()
            for item in window.plan_tree_view.scene().items()
            if hasattr(item, "research_id")
        )
        assert window.plan_table.cellWidget(0, window.plan_table.columnCount() - 1)
        assert window.plan_register_button.isEnabled()
        window.plan_register_button.click()
        app.processEvents()
        assert [
            (task.research_id, task.target_level)
            for task in player_repository.load().plan_tasks
        ] == [("defense_trap_durability_i", 8)]
        tasks_index = window.plan_mode_combo.findData("tasks")
        window.plan_mode_combo.setCurrentIndex(tasks_index)
        app.processEvents()
        assert not window.plan_directive_panel.isHidden()
        assert window.plan_table.rowCount() == 1
        assert window.plan_table.item(0, 0).data(Qt.UserRole) == (
            "defense_trap_durability_i"
        )
        window.plan_mode_combo.setCurrentIndex(
            window.plan_mode_combo.findData("target")
        )
        assert window.plan_directive_panel.isHidden()
        window.plan_resource_mode_combo.setCurrentIndex(
            window.plan_resource_mode_combo.findData("short")
        )
        assert player_repository.load().settings.resource_display_mode == "short"
        assert window.plan_complete_button.isEnabled()
        window.plan_complete_button.click()
        app.processEvents()
        assert window._tree_level_draft["defense_trap_power_i"] == 7
        assert window._tree_level_draft["defense_trap_durability_i"] == 8
        assert player_repository.load().research_levels[
            "defense_trap_power_i"
        ] == 7
        assert player_repository.load().research_levels[
            "defense_trap_durability_i"
        ] == 8
        assert not window.plan_complete_button.isEnabled()
        window.plan_mode_combo.setCurrentIndex(tasks_index)
        app.processEvents()
        assert "完了済み" in window.plan_table.item(0, 1).text()
        window.close()
    finally:
        player_repository.close()


def test_plan_tab_lists_currently_available_research_shortest_first() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.plan_mode_combo.setCurrentIndex(
            window.plan_mode_combo.findData("shortest")
        )
        app.processEvents()

        expected = window.catalog_planner.shortest_available_steps(
            window.player_state
        )
        assert expected
        page_size = int(window.plan_shortest_page_size_combo.currentData())
        assert window.plan_table.rowCount() == min(page_size, len(expected))
        assert window.plan_tree_view.isHidden()
        assert window.plan_target_name_label.isHidden()
        assert not window.plan_shortest_controls.isHidden()
        assert window.plan_directive_panel.isHidden()
        assert [
            window.plan_table.item(row, 0).data(Qt.UserRole)
            for row in range(window.plan_table.rowCount())
        ] == [step.research_id for step in expected[:page_size]]
        displayed_times = [
            window.plan_table.item(row, 3).data(Qt.UserRole)
            for row in range(window.plan_table.rowCount())
        ]
        assert displayed_times == sorted(displayed_times)
        assert all(
            " / " in window.plan_table.item(row, 0).text()
            for row in range(window.plan_table.rowCount())
        )

        window.plan_shortest_page_size_combo.setCurrentIndex(
            window.plan_shortest_page_size_combo.findData(10)
        )
        app.processEvents()
        assert window.plan_table.rowCount() == min(10, len(expected))
        assert "全" in window.plan_shortest_page_label.text()
        if len(expected) > 10:
            assert window.plan_shortest_next_button.isEnabled()
            window.plan_shortest_next_button.click()
            app.processEvents()
            assert [
                window.plan_table.item(row, 0).data(Qt.UserRole)
                for row in range(window.plan_table.rowCount())
            ] == [step.research_id for step in expected[10:20]]
            assert window.plan_shortest_previous_button.isEnabled()

        link_item = window.plan_table.item(0, 0)
        research_id = str(link_item.data(Qt.UserRole))
        observation = window._node_observation[research_id]
        assert link_item.font().underline()
        assert link_item.toolTip() == window.t("plan.open_in_tree")
        window.search_edit.setText("no matching research")
        window.tree_instant_finish_check.setChecked(True)
        window.tabs.setCurrentIndex(1)
        window._plan_table_item_clicked(link_item)
        app.processEvents()
        assert window.tabs.currentIndex() == 0
        assert window.search_edit.text() == ""
        assert not window.tree_instant_finish_check.isChecked()
        assert window.tree_dataset_list.currentItem().data(Qt.UserRole) == (
            f"observation:{observation.observation_id}"
        )
        assert any(
            getattr(item, "research_id", "") == research_id and item.isSelected()
            for item in window.tree_view.scene().items()
        )
        selected_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == research_id
        )
        assert selected_card.isSelected()

        window._set_plan_target(expected[0].research_id)
        assert window.plan_mode_combo.currentData() == "target"
        assert not window.plan_tree_view.isHidden()
        assert not window.plan_target_name_label.isHidden()
        window.close()
    finally:
        player_repository.close()


def test_innate_talent_level_one_defaults_to_an_unfinished_level_two_plan() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        research_id = "upgrade_military_innate_talent"
        window._tree_level_draft[research_id] = 1
        window._set_plan_target(research_id)

        # Reproduce a target left at Lv.1 before the current level became Lv.1.
        window.plan_level_spin.blockSignals(True)
        window.plan_level_spin.setValue(1)
        window.plan_level_spin.blockSignals(False)
        window._calculate_plan()
        app.processEvents()

        rendered_ids = {
            item.research_id
            for item in window.plan_tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert window.plan_level_spin.value() == 2
        assert research_id in rendered_ids
        assert window.plan_table.rowCount() > 1
        window.close()
    finally:
        player_repository.close()


def test_food_harvesting_uses_the_game_effect_name_and_cumulative_value() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window._tree_level_draft["economy_food_harvest_1"] = 9
        window._refresh_tree()
        food = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_food_harvest_1"
        )
        assert food.current_effect_item.toPlainText() == "食糧生産量+58%"
        assert food.next_effect_item.toPlainText() == "食糧生産量+80%"
        assert "累計効果" not in food.current_effect_item.toPlainText()

        window._tree_level_draft["economy_food_harvest_1"] = 10
        window._refresh_tree()
        food = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_food_harvest_1"
        )
        assert food.current_effect_item.toPlainText() == "食糧生産量+80%"
        assert food.next_effect_item.toPlainText() == ""
        window.close()
    finally:
        player_repository.close()


def test_research_card_regions_are_found_from_level_meters() -> None:
    image = QImage(1000, 400, QImage.Format_RGB32)
    image.fill(QColor(58, 100, 123))
    painter = QPainter(image)
    for left in (20, 280):
        painter.fillRect(left, 110, 199, 40, QColor(29, 39, 53))
        painter.fillRect(left, 150, 199, 16, QColor(20, 17, 11))
        painter.fillRect(left, 150, 139, 16, QColor(214, 106, 0))
    painter.end()
    regions = MainWindow._research_card_ocr_regions(image)
    assert len(regions) == 2
    assert [region.center().x() for region in regions] == [120, 380]


def test_research_meter_detection_preserves_native_supported_resolutions() -> None:
    for width, height in (
        (1024, 576),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ):
        scale = min(width / 1280, height / 720)
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(QColor(58, 100, 123))
        painter = QPainter(image)
        left = round(width * 0.20)
        panel_top = round(height * 0.28)
        meter_width = round(199 * scale)
        panel_height = round(40 * scale)
        meter_height = max(4, round(16 * scale))
        inset = max(1, round(2 * scale))
        painter.fillRect(
            left,
            panel_top,
            meter_width,
            panel_height,
            QColor(29, 39, 53),
        )
        painter.fillRect(
            left,
            panel_top + panel_height,
            meter_width,
            meter_height,
            QColor(20, 17, 11),
        )
        painter.fillRect(
            left + inset,
            panel_top + panel_height + inset,
            round((meter_width - inset * 2) * 0.7),
            max(2, meter_height - inset * 2),
            QColor(214, 106, 0),
        )
        painter.end()

        meter_regions = MainWindow._research_card_meter_regions(image)

        assert len(meter_regions) == 1, (width, height)
        _region, fill_ratio = meter_regions[0]
        assert 0.65 <= fill_ratio <= 0.75, (width, height, fill_ratio)


def test_paid_ocr_regions_follow_game_content_without_resizing_the_frame() -> None:
    for width, height in (
        (1024, 576),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ):
        image = QImage(width, height, QImage.Format_RGB32)
        image.fill(QColor(58, 100, 123))
        title_height = round(height * 31 / 720)
        painter = QPainter(image)
        painter.fillRect(0, 0, width, title_height, QColor(242, 242, 242))
        painter.end()

        content = MainWindow._ocr_content_rect(image)
        row = MainWindow._relative_ocr_region(
            content, 0.17, 0.419, 0.67, 0.102
        )
        scale = MainWindow._ocr_detail_scale(row, target_height=220)

        assert content.top() == title_height, (width, height)
        assert content.width() == width
        assert row.top() == content.top() + round(content.height() * 0.419)
        assert row.right() <= content.right()
        assert scale >= 1.0
        assert 210 <= round(row.height() * scale) <= 225


def test_fullscreen_game_image_uses_the_entire_native_frame() -> None:
    image = QImage(1920, 1080, QImage.Format_RGB32)
    image.fill(QColor(40, 105, 128))

    assert MainWindow._ocr_content_rect(image) == image.rect()


def test_meter_detection_ignores_bright_level_text_over_the_dark_track() -> None:
    image = QImage(600, 300, QImage.Format_RGB32)
    image.fill(QColor(58, 100, 123))
    painter = QPainter(image)
    painter.fillRect(100, 100, 199, 40, QColor(29, 39, 53))
    painter.fillRect(100, 140, 199, 16, QColor(20, 17, 11))
    painter.fillRect(102, 142, 117, 12, QColor(214, 106, 0))
    painter.fillRect(230, 145, 35, 6, QColor(245, 245, 245))
    painter.end()

    meter_regions = MainWindow._research_card_meter_regions(image)

    assert len(meter_regions) == 1
    region, fill_ratio = meter_regions[0]
    assert 205 <= region.width() <= 215
    assert 0.55 <= fill_ratio <= 0.65


def test_research_card_regions_include_gold_max_meters_but_not_tree_lines() -> None:
    image = QImage(1000, 400, QImage.Format_RGB32)
    image.fill(QColor(58, 100, 123))
    painter = QPainter(image)
    for left in (20, 280):
        painter.fillRect(left, 110, 199, 40, QColor(29, 39, 53))
        painter.fillRect(left, 150, 199, 16, QColor(20, 17, 11))
        painter.fillRect(left + 2, 152, 195, 12, QColor(246, 187, 26))
    painter.fillRect(520, 300, 199, 7, QColor(246, 187, 26))
    painter.end()
    meter_regions = MainWindow._research_card_meter_regions(image)
    assert len(meter_regions) == 2
    assert [region.center().x() for region, _fill_ratio in meter_regions] == [120, 380]
    assert all(fill_ratio >= 0.94 for _region, fill_ratio in meter_regions)


def test_defense_full_meters_are_resolved_from_cropped_card_labels() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.tree_dataset_list.setCurrentRow(
            window._dataset_list_row("observation:catalog-defense")
        )
        image = QImage(1000, 600, QImage.Format_RGB32)
        image.fill(QColor(58, 100, 123))
        painter = QPainter(image)
        for left, panel_top in ((400, 80), (20, 350), (280, 350), (540, 350)):
            painter.fillRect(left, panel_top, 199, 40, QColor(29, 39, 53))
            painter.fillRect(left, panel_top + 40, 199, 16, QColor(20, 17, 11))
            painter.fillRect(
                left + 2, panel_top + 42, 195, 12, QColor(246, 187, 26)
            )
        painter.end()
        window._ocr_image = image
        regions = window._research_card_ocr_regions(image)
        assert len(regions) == 4
        labels = ("罠配置I", "スパイク", "アーチャータワー", "スパイクボルダー")
        window._ocr_card_groups = [
            (
                region,
                (
                    OcrLine(
                        label,
                        region.x() + 10,
                        region.y() + 10,
                        region.width() - 20,
                        24,
                    ),
                ),
            )
            for region, label in zip(regions, labels)
        ]
        window._ocr_card_groups.append((QRect(800, 600, 180, 50), ()))

        window._append_layout_ocr_candidates()

        assert {(item.research_id, item.level) for item in window._ocr_candidates} == {
            ("defense_trap_crafting_i", 1),
            ("defense_spikes", 1),
            ("defense_archer_tower", 1),
            ("defense_spike_boulders", 1),
        }
        window.close()
    finally:
        player_repository.close()


def test_defense_partial_meter_recovers_trap_hp_without_level_text() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.tree_dataset_list.setCurrentRow(
            window._dataset_list_row("observation:catalog-defense")
        )
        image = QImage(1000, 650, QImage.Format_RGB32)
        image.fill(QColor(58, 100, 123))
        painter = QPainter(image)
        card_specs = (
            (50, 100, 7),
            (350, 100, 7),
            (650, 100, 6),
            (350, 400, 7),
        )
        for left, panel_top, level in card_specs:
            painter.fillRect(left, panel_top, 199, 40, QColor(29, 39, 53))
            painter.fillRect(left, panel_top + 40, 199, 16, QColor(20, 17, 11))
            painter.fillRect(
                left + 2,
                panel_top + 42,
                round(195 * level / 10),
                12,
                QColor(214, 106, 0),
            )
        painter.end()
        window._ocr_image = image
        regions = window._research_card_ocr_regions(image)
        assert len(regions) == 4
        labels = ("罠防御力I", "罠攻撃力I", "罠HPI", "城壁強度I")
        window._ocr_card_groups = [
            (
                region,
                (
                    OcrLine(
                        label,
                        region.x() + 10,
                        region.y() + 10,
                        region.width() - 20,
                        24,
                    ),
                ),
            )
            for region, label in zip(regions, labels)
        ]

        window._append_layout_ocr_candidates()

        assert {(item.research_id, item.level) for item in window._ocr_candidates} == {
            ("defense_trap_defense_i", 7),
            ("defense_trap_power_i", 7),
            ("defense_trap_durability_i", 6),
            ("defense_wall_strength_i", 7),
        }
        window.close()
    finally:
        player_repository.close()


def test_tree_capture_button_applies_ocr_level_to_the_active_tree() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        capture_options: list[bool] = []

        def recognized_current_screen(*, force_window_capture: bool = False) -> None:
            capture_options.append(force_window_capture)
            window._set_ocr_progress(1, maximum=1)
            window._ocr_candidates = [
                OcrCandidate(
                    research_id="economy_vault_management",
                    level=10,
                    evidence="captured tree card 10/10",
                )
            ]

        window._run_ocr = recognized_current_screen
        window.tree_capture_button.click()
        app.processEvents()

        assert player_repository.load().research_levels == {}
        assert window._tree_level_draft["economy_vault_management"] == 10
        assert window.tree_save_levels_button.isEnabled()
        assert capture_options == [True]
        vault_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_vault_management"
        )
        assert vault_card.level_item.toPlainText() == "10 / 10"
        assert not hasattr(window, "tree_capture_status_label")
        assert window.tree_capture_progress.value() == (
            window.tree_capture_progress.maximum()
        )

        window.tree_save_levels_button.click()
        app.processEvents()
        assert player_repository.load().research_levels == {
            "economy_vault_management": 10
        }
        assert not window.tree_save_levels_button.isEnabled()
        window.close()
    finally:
        player_repository.close()


def test_player_save_commits_staged_tree_levels_for_the_next_start(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda *_args, **_kwargs: main_window_module.QMessageBox.Ok,
    )
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window._set_tree_level("economy_vault_management", 7)
        assert player_repository.load().research_levels == {}

        window._save_player()
        app.processEvents()
        window.close()

        restarted = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        assert restarted.player_state.research_levels == {
            "economy_vault_management": 7
        }
        assert restarted._tree_level_draft == {
            "economy_vault_management": 7
        }
        restarted.close()
    finally:
        player_repository.close()


def test_visible_window_confirms_unsaved_player_settings_before_exit() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.show()
        app.processEvents()
        window.vip_level_spin.setValue(11)

        assert window._has_unsaved_player_changes()
        window._ask_unsaved_close_action = lambda: "cancel"
        assert not window.close()
        assert window.isVisible()
        assert player_repository.load().settings.vip_level != 11

        window._ask_unsaved_close_action = lambda: "save"
        assert window.close()
        app.processEvents()
        assert not window.isVisible()
        assert player_repository.load().settings.vip_level == 11

        restarted = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        restarted.show()
        app.processEvents()
        restarted.vip_level_spin.setValue(12)
        restarted._ask_unsaved_close_action = lambda: "discard"
        assert restarted.close()
        app.processEvents()
        assert player_repository.load().settings.vip_level == 11
    finally:
        player_repository.close()


def test_tree_level_editor_uses_staged_inline_card_input() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        assert not hasattr(window, "observation_panel")
        assert not hasattr(window, "observation_level_slider")
        assert not hasattr(window, "observation_level_spin")
        assert not hasattr(window, "observation_progress_combo")
        assert not hasattr(window, "observation_save_button")
        assert window.tabs.widget(3).isAncestorOf(window.tree_clear_levels_button)
        assert window.tabs.widget(3).isAncestorOf(window.tree_save_levels_button)
        assert not window.tabs.widget(0).isAncestorOf(
            window.tree_clear_levels_button
        )
        vault_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_vault_management"
        )
        window.tree_view._show_level_editor(vault_card)
        editor = window.tree_view._level_editor
        assert editor is not None
        assert editor.maximum() == 10
        assert editor.suffix() == ""
        editor.setValue(7)
        QTest.mouseClick(
            window.tree_view.viewport(),
            Qt.LeftButton,
            Qt.NoModifier,
            QPoint(5, 5),
        )
        app.processEvents()
        assert window._tree_level_draft["economy_vault_management"] == 7
        assert player_repository.load().research_levels == {}
        assert window.tree_save_levels_button.isEnabled()
        assert all(
            isinstance(editor, QSpinBox)
            for editor in window._progress_editors.values()
        )
        assert (
            window._progress_editors["economy_vault_management"].value() == 7
        )
        assert (
            window._progress_editors["economy_vault_management"].suffix()
            == ""
        )
        maximum_item = window._progress_maximum_items["economy_vault_management"]
        assert maximum_item.text() == "10"
        assert not maximum_item.flags() & Qt.ItemIsEditable
        assert window.progress_table.columnCount() == 3
        window.resize(window.minimumSize())
        window.show()
        app.processEvents()
        assert window.progress_table.columnWidth(1) >= 120
        assert (
            window.progress_table.columnWidth(2)
            >= window.progress_table.fontMetrics().horizontalAdvance(
                window.t("player.maximum_level")
            )
            + 16
        )

        window.tree_clear_levels_button.click()
        app.processEvents()
        assert window._tree_level_draft == {}
        assert player_repository.load().research_levels == {}
        assert all(
            editor.value() == 0
            for editor in window._progress_editors.values()
        )

        vault_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_vault_management"
        )
        window.tree_view._show_level_editor(vault_card)
        editor = window.tree_view._level_editor
        assert editor is not None
        editor.setValue(6)
        editor.editingFinished.emit()
        app.processEvents()
        assert window._tree_level_draft["economy_vault_management"] == 6
        window.tree_save_levels_button.click()
        app.processEvents()
        assert player_repository.load().research_levels == {
            "economy_vault_management": 6
        }
        assert not window.tree_save_levels_button.isEnabled()
        window.tabs.setCurrentIndex(0)
        vault_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_vault_management"
        )
        level_position = window.tree_view.mapFromScene(
            vault_card.mapToScene(QPointF(122.0, 96.0))
        )
        QTest.mouseClick(
            window.tree_view.viewport(),
            Qt.LeftButton,
            Qt.NoModifier,
            level_position,
        )
        QTest.mouseDClick(
            window.tree_view.viewport(),
            Qt.LeftButton,
            Qt.NoModifier,
            level_position,
        )
        app.processEvents()
        assert window.tabs.currentIndex() == 0
        assert window._plan_target_research_id == ""
        window._ask_unsaved_close_action = lambda: "discard"
        window.close()
    finally:
        player_repository.close()


@pytest.mark.parametrize("recognized_level", [0, 4, 10])
def test_tree_capture_replaces_an_existing_level_with_recognized_value(
    recognized_level: int,
) -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        state = player_repository.load()
        state.research_levels["economy_vault_management"] = 7
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=state,
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        def recognized_current_screen(*, force_window_capture: bool = False) -> None:
            assert force_window_capture
            window._ocr_candidates = [
                OcrCandidate(
                    research_id="economy_vault_management",
                    level=recognized_level,
                    evidence=f"captured tree card {recognized_level}/10",
                )
            ]

        window._run_ocr = recognized_current_screen
        window.tree_capture_button.click()
        app.processEvents()

        assert (
            window._tree_level_draft["economy_vault_management"]
            == recognized_level
        )
        vault_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == "economy_vault_management"
        )
        assert vault_card.level_item.toPlainText() == f"{recognized_level} / 10"
        window._ask_unsaved_close_action = lambda: "discard"
        window.close()
    finally:
        player_repository.close()


def test_deep_plan_paid_offer_simulation_finishes_without_freezing() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    player_repository = PlayerRepository(":memory:")
    player_state = player_repository.load()
    player_state.settings.speedup_inventory = [
        SpeedupInventoryItem("general", 60, 100),
        SpeedupInventoryItem("research", 86_400, 60),
        SpeedupInventoryItem("research", 28_800, 40),
        SpeedupInventoryItem("research", 300, 40),
    ]
    player_state.paid_offers = [
        PaidOffer(
            "research-pack",
            "Research pack",
            diamond_cost=1_999,
            items=(
                PaidItem("research", quantity=60, duration_seconds=86_400),
                PaidItem("research", quantity=40, duration_seconds=28_800),
                PaidItem("research", quantity=40, duration_seconds=300),
            ),
        )
    ]
    try:
        window = MainWindow(
            paths=paths,
            master=JsonMasterRepository(paths.research_data).load(),
            observations=JsonResearchDatasetRepository(
                paths.research_dataset
            ).load_all(),
            player_repository=player_repository,
            player_state=player_state,
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        window._open_tree_detail("gear_luminary_marksman")
        app.processEvents()

        assert window.tabs.currentIndex() == 1
        assert window._current_catalog_plan is not None
        assert len(window._current_catalog_plan.steps) > 200
        assert window.plan_tree_view.scene().items()
    finally:
        window.close()
        player_repository.close()


def test_tree_technolabe_filter_uses_next_level_efficiency_and_is_exclusive() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchDatasetRepository(paths.research_dataset).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        research_id = "advanced_wonder_battles_leadership_infantry_atk_ii"
        window._tree_level_draft[research_id] = 7
        node = window._observed_nodes[research_id]
        assert window._tree_node_is_technolabe_candidate(node)
        window.tree_instant_finish_check.setChecked(True)
        window.tree_technolabe_check.setChecked(True)
        app.processEvents()
        assert window.tree_technolabe_check.isChecked()
        assert not window.tree_instant_finish_check.isChecked()
    finally:
        window.close()
        player_repository.close()


def test_tree_level_change_updates_in_place_and_defers_hidden_plan() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        research_id = "economy_vault_management"
        original_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == research_id
        )
        plan_calculations: list[bool] = []
        original_calculate_plan = window._calculate_plan
        window._calculate_plan = lambda *_args: plan_calculations.append(True)

        window._set_tree_level(research_id, 7)
        app.processEvents()

        updated_card = next(
            item
            for item in window.tree_view.scene().items()
            if getattr(item, "research_id", "") == research_id
        )
        assert updated_card is original_card
        assert updated_card.level_item.toPlainText() == "7 / 10"
        assert plan_calculations == []
        assert window._plan_dirty

        window.tabs.setCurrentIndex(1)
        app.processEvents()
        assert plan_calculations == [True]
        assert not window._plan_dirty
        window._calculate_plan = original_calculate_plan
        window._ask_unsaved_close_action = lambda: "discard"
        window.close()
    finally:
        player_repository.close()


def test_help_tab_collects_usage_guidance_outside_work_tabs() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        assert window.tabs.count() == 8
        assert window.tabs.tabText(2) == "建設"
        assert window.tabs.tabText(3) == "プレイヤー設定"
        assert window.tabs.tabText(4) == "課金"
        assert window.tabs.tabText(5) == "OCR入力"
        assert window.tabs.tabText(6) == "設定"
        assert window.tabs.tabText(7) == "ヘルプ"
        assert window.player_workspace_tabs.count() == 4
        assert [
            window.player_workspace_tabs.tabText(index)
            for index in range(window.player_workspace_tabs.count())
        ] == ["レベル", "才能", "資源", "加速"]
        assert window.player_workspace_tabs.widget(3).isAncestorOf(
            window.speedup_inventory_groups_host
        )
        assert len(window.speedup_inventory_group_toggles) == 7
        assert all(
            not toggle.isChecked()
            for toggle in window.speedup_inventory_group_toggles.values()
        )
        assert all(
            body.isHidden()
            for body in window.speedup_inventory_group_bodies.values()
        )
        assert ("general", 60) in window.speedup_inventory_inputs
        assert ("research", 30 * 24 * 60 * 60) in window.speedup_inventory_inputs
        assert [
            window.speedup_inventory_duration_sections[("general", unit)].title()
            for unit in ("minutes", "hours", "days")
        ] == ["分", "時間", "日"]
        assert window._speedup_duration_label(60 * 60) == "60分"
        assert window._speedup_duration_label(24 * 60 * 60) == "24時間"
        assert not hasattr(window, "speedup_inventory_summary_label")
        assert all(
            label.text() != window.t("player.speedup_inventory_hint")
            for label in window.player_workspace_tabs.widget(3).findChildren(QLabel)
        )
        window.speedup_inventory_group_toggles["general"].setChecked(True)
        assert not window.speedup_inventory_group_bodies["general"].isHidden()
        window.speedup_inventory_inputs[("general", 60)].setValue(2)
        assert window.player_state.settings.speedup_inventory == [
            SpeedupInventoryItem("general", 60, 2)
        ]
        assert "00:02:00" in window.speedup_inventory_group_toggles[
            "general"
        ].text()
        assert window.player_workspace_tabs.widget(2).isAncestorOf(
            next(iter(window.resource_spins.values()))
        )
        assert window.player_workspace_tabs.widget(2).isAncestorOf(
            window.technolabe_threshold_spin
        )
        assert window.technolabe_threshold_spin.value() == 95.0
        assert window.technolabe_count_spin.value() == 0
        assert window.player_workspace_tabs.widget(1).isAncestorOf(
            window.talent_tree_view
        )
        talent_nodes = {
            item.research_id
            for item in window.talent_tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert talent_nodes == set(window.talent_catalog.talents)
        assert window.talent_priority_combo.count() > 1
        assert window.talent_priority_combo.isHidden()
        assert not window.talent_preset_combo.isHidden()
        assert window.talent_priority_label.text()
        assert window.talent_auto_follow_check.isChecked()
        assert window.talent_details_panel.isHidden()
        window.talent_details_toggle.setChecked(True)
        assert not window.talent_details_panel.isHidden()
        assert window.talent_details_toggle.arrowType() == Qt.ArrowType.DownArrow
        window.talent_details_toggle.setChecked(False)
        assert window.talent_details_panel.isHidden()
        assert window.talent_details_toggle.arrowType() == Qt.ArrowType.RightArrow
        focused_talents: list[str] = []
        original_focus_talent = window.talent_tree_view.focus_research

        def record_talent_focus(talent_id: str) -> bool:
            focused_talents.append(talent_id)
            return original_focus_talent(talent_id)

        window.talent_tree_view.focus_research = record_talent_focus
        window.talent_priority_combo.setCurrentIndex(1)
        assert focused_talents == [window.player_state.talent_priority_id]
        window.talent_auto_follow_check.setChecked(False)
        window.talent_priority_combo.setCurrentIndex(2)
        assert len(focused_talents) == 1
        window._talent_dirty = False
        assert window.windowTitle() == window.t("app.title")
        assert version_string() not in window.windowTitle()
        assert window.tabs.widget(6).isAncestorOf(window.ui_font_size_spin)
        assert window.tabs.widget(6).isAncestorOf(window.table_font_size_spin)
        assert window.tabs.widget(6).isAncestorOf(window.tree_font_size_spin)
        assert window.tabs.widget(6).isAncestorOf(window.help_font_size_spin)
        assert set(window.font_reset_buttons) == {"ui", "table", "tree", "help"}
        assert all(
            window.tabs.widget(6).isAncestorOf(button)
            for button in window.font_reset_buttons.values()
        )
        assert window.tabs.cornerWidget(Qt.Corner.TopRightCorner) is None
        assert window.tabs.widget(6).isAncestorOf(window.language_combo)
        assert window.tabs.widget(6).isAncestorOf(
            window.language_pack_export_button
        )
        assert window.tabs.widget(6).isAncestorOf(
            window.language_pack_import_button
        )
        assert window.tabs.widget(6).isAncestorOf(
            window.language_pack_remove_button
        )
        assert window.tabs.widget(6).isAncestorOf(window.visual_style_combo)
        assert window.tabs.widget(6).isAncestorOf(window.update_check_button)
        assert window.tabs.widget(6).isAncestorOf(window.settings_version_label)
        assert window.tabs.widget(6).isAncestorOf(
            window.settings_dataset_version_label
        )
        assert all(
            not window.tabs.widget(7).isAncestorOf(widget)
            for widget in (
                window.language_combo,
                window.language_pack_export_button,
                window.language_pack_import_button,
                window.language_pack_remove_button,
                window.visual_style_combo,
                window.update_check_button,
                window.update_startup_checkbox,
                window.update_releases_button,
                window.update_status_label,
                window.settings_version_label,
                window.settings_dataset_version_label,
            )
        )
        assert "docs/ja-JP/data-files.md" in window.help_browser.toHtml()
        assert "docs/ja-JP/translation-files.md" in window.help_browser.toHtml()
        window.resize(1700, 720)
        window.show()
        window.tabs.setCurrentIndex(6)
        app.processEvents()
        assert window.language_combo.width() <= (
            window.language_combo.sizeHint().width() + 4
        )
        assert window.update_check_button.width() <= (
            window.update_check_button.sizeHint().width() + 4
        )
        window.resize(980, 640)
        app.processEvents()
        settings_page = window.tabs.widget(6)
        for widget in (
            window.language_combo,
            window.language_pack_export_button,
            window.language_pack_import_button,
            window.language_pack_remove_button,
            window.visual_style_combo,
            window.update_check_button,
            window.update_startup_checkbox,
            window.update_releases_button,
        ):
            assert settings_page.isAncestorOf(widget)
        assert not any(
            group.title() == window.t("update.title")
            for group in window.tabs.widget(7).findChildren(QGroupBox)
        )
        assert window.ui_font_size_spin.value() == 11
        assert window.table_font_size_spin.value() == 11
        assert window.tree_font_size_spin.value() == 20
        assert window.help_font_size_spin.value() == 12
        assert window.help_browser.font().pointSize() == 12
        original_tab_font_size = window.tabs.font().pointSizeF()
        window.ui_font_size_spin.setValue(16)
        assert window.app_settings.ui_font_size == 16
        assert window.tabs.font().pointSizeF() > original_tab_font_size
        assert window.plan_speedup_panel.font().pointSize() == 16
        assert window.castle_speedup_panel.font().pointSize() == 16
        assert window.plan_table.font().pointSize() == 11
        assert window.help_browser.font().pointSize() == 12
        window.table_font_size_spin.setValue(15)
        assert window.app_settings.table_font_size == 15
        assert window.plan_table.font().pointSize() == 15
        window.tree_font_size_spin.setValue(24)
        assert window.app_settings.tree_font_size == 24
        assert window.tree_view._font_size == 24
        assert window.plan_tree_view._font_size == 24
        window.help_font_size_spin.setValue(18)
        assert window.app_settings.help_font_size == 18
        assert window.help_browser.font().pointSize() == 18
        assert window.tabs.font().pointSizeF() > original_tab_font_size
        window.font_reset_buttons["ui"].click()
        assert window.app_settings.ui_font_size == 11
        assert window.app_settings.table_font_size == 15
        assert window.app_settings.tree_font_size == 24
        assert window.app_settings.help_font_size == 18
        window.font_reset_buttons["table"].click()
        window.font_reset_buttons["tree"].click()
        window.font_reset_buttons["help"].click()
        assert window.app_settings.table_font_size == 11
        assert window.app_settings.tree_font_size == 20
        assert window.app_settings.help_font_size == 12
        assert window.ui_font_size_spin.value() == 11
        assert window.table_font_size_spin.value() == 11
        assert window.tree_font_size_spin.value() == 20
        assert window.help_font_size_spin.value() == 12
        assert window.visual_style_combo.currentData() == "desktop"
        assert window.styleSheet() == ""
        desktop_window_color = (
            window.palette().color(QPalette.Window).name().upper()
        )
        desktop_text_color = (
            window.palette().color(QPalette.WindowText).name().upper()
        )
        desktop_check_text_color = (
            window.tree_instant_finish_check.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
        )
        desktop_label_text_color = (
            window.settings_version_label.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
        )
        window.visual_style_combo.setCurrentIndex(
            window.visual_style_combo.findData("mobile")
        )
        app.processEvents()
        assert window.app_settings.visual_style == "mobile"
        assert "#07151D" in window.styleSheet()
        assert window.tree_view.visual_style == "mobile"
        assert window.plan_tree_view.visual_style == "mobile"
        assert "#F2B632" in window.tree_dataset_list.styleSheet()
        assert (
            window.tree_instant_finish_check.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
            == "#F4F8F8"
        )
        assert (
            window.settings_version_label.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
            == "#F4F8F8"
        )
        accent_labels = {"PlanTargetSelection", "ConstructionSelection"}
        assert all(
            widget.objectName() in accent_labels
            or widget.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
            == "#F4F8F8"
            for widget_type in (QLabel, QCheckBox)
            for widget in window.findChildren(widget_type)
        )
        assert window.update_startup_checkbox.isChecked()
        assert not window.update_check_button.isEnabled()
        assert window.update_status_label.text() == ""
        assert window.update_status_label.isHidden()
        assert any(
            label.text() == version_string()
            and window.tabs.widget(6).isAncestorOf(label)
            for label in window.centralWidget().findChildren(QLabel)
        )
        assert window.settings_dataset_version_label.text() == "0.1.0"
        assert not any(
            label.text() == version_string()
            and window.tabs.widget(7).isAncestorOf(label)
            for label in window.centralWidget().findChildren(QLabel)
        )
        assert not any(
            label.text() == window.t("app.title")
            for label in window.centralWidget().findChildren(QLabel)
        )
        help_text = window.help_browser.toPlainText()
        help_html = window.help_browser.toHtml()
        assert "最初に必ず行う設定" in help_text
        assert "VIPレベルを入力" in help_text
        assert "研究装備を着け" in help_text
        assert "追加ブースト" in help_text
        assert "ゲームとツールで同じ研究分野" in help_text
        assert help_text.index("最初に必ず行う設定") < help_text.index(
            "研究ツリーの操作"
        )
        assert "研究ツリーの操作" in help_text
        assert "現在レベルの設定" in help_text
        assert "ツリーのメーター" in help_text
        assert "短時間順" in help_text
        assert "ゲームのメモリにはアクセスしません" in help_text
        assert "アカデミー、現在24、目標25" in help_text
        assert window.t("help.paid.title") in help_text
        assert "ライセンス・出典" in help_text
        assert "Data licensing and attribution" in help_text
        assert "v2.200.309" in help_text
        assert "/RLMResearchPlanner/blob/main/LICENSE" in help_html
        assert "/RLMResearchPlanner/blob/main/DATA_LICENSE.md" in help_html
        assert "/RLMResearchPlanner/blob/main/licenses/THIRD_PARTY_NOTICES.md" in help_html
        assert "開発版では更新確認" not in help_text
        assert window.t("app.disclaimer") in help_text
        assert "重要な注意・免責" in help_text
        assert "無償の非公式ツール" in help_text
        assert "ゲーム画面で確認" in help_text
        assert "正確性を保証しません" in help_text
        assert not hasattr(window, "observation_panel")
        assert not hasattr(window, "play_style_edit")
        assert not hasattr(window, "free_speedup_minutes_spin")
        vip_row, _vip_role = window.player_settings_form.getWidgetPosition(
            window.vip_level_spin.parentWidget()
        )
        castle_row, _castle_role = window.player_settings_form.getWidgetPosition(
            window.castle_spin
        )
        assert vip_row < castle_row
        assert window.vip_level_spin.value() == 1
        assert window.vip_free_speedup_label.text() == "無料時間: 10分"
        window.vip_level_spin.setValue(15)
        app.processEvents()
        assert window.player_state.settings.vip_level == 15
        assert window.vip_free_speedup_label.text() == "無料時間: 150分"
        window.research_speed_boost_spin.setValue(10.0)
        assert (
            window.player_state.settings.research_speed_boost_percent == 10.0
        )
        window.event_research_discount_spin.setValue(30.0)
        assert (
            window.player_state.settings.event_research_discount_percent == 30.0
        )
        window.tree_save_levels_button.click()
        assert player_repository.load().settings.vip_level == 15
        assert (
            player_repository.load().settings.research_speed_boost_percent
            == 10.0
        )
        assert (
            player_repository.load().settings.event_research_discount_percent
            == 30.0
        )
        window.tabs.setCurrentIndex(7)
        window.language_combo.setCurrentIndex(
            window.language_combo.findData("en-US")
        )
        app.processEvents()
        assert window.translator.locale == "en-US"
        assert window.tabs.currentIndex() == 7
        assert window.tabs.tabText(7) == "Help"
        assert window.windowTitle() == "RLM Research Planner"
        assert window.visual_style_combo.currentData() == "mobile"
        assert "#07151D" in window.styleSheet()
        window.visual_style_combo.setCurrentIndex(
            window.visual_style_combo.findData("desktop")
        )
        app.processEvents()
        assert window.app_settings.visual_style == "desktop"
        assert window.visual_style_combo.currentData() == "desktop"
        assert window.styleSheet() == ""
        assert window.tree_view.visual_style == "desktop"
        assert window.plan_tree_view.visual_style == "desktop"
        assert "#F2B632" not in window.tree_dataset_list.styleSheet()
        assert (
            window.palette().color(QPalette.Window).name().upper()
            == desktop_window_color
        )
        assert (
            window.palette().color(QPalette.WindowText).name().upper()
            == desktop_text_color
        )
        assert (
            window.tree_instant_finish_check.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
            == desktop_check_text_color
        )
        assert (
            window.settings_version_label.palette()
            .color(QPalette.WindowText)
            .name()
            .upper()
            == desktop_label_text_color
        )
        window.close()
    finally:
        player_repository.close()


def test_mobile_visual_style_keeps_dialog_text_readable() -> None:
    app = QApplication.instance() or QApplication([])
    parent = QMainWindow()
    mobile_style = window_style_sheet("mobile")
    parent.setStyleSheet(mobile_style)
    assert "QSpinBox::up-button" not in mobile_style

    dialog = QDialog(parent)
    dialog.resize(260, 120)
    dialog_layout = QVBoxLayout(dialog)
    dialog_label = QLabel("ダイアログの本文")
    dialog_layout.addWidget(dialog_label)

    message_box = QMessageBox(parent)
    message_box.setText("確認メッセージ")
    message_box.setStandardButtons(QMessageBox.StandardButton.Ok)

    progress_dialog = QProgressDialog("更新しています", "キャンセル", 0, 100, parent)
    progress_dialog.setAutoClose(False)
    progress_dialog.setValue(25)

    dialogs = (dialog, message_box, progress_dialog)
    try:
        for target in dialogs:
            target.show()
        app.processEvents()

        for target in dialogs:
            background = _rendered_corner_color(target)
            assert background.name().upper() == "#0D2530"

        labels = (
            dialog_label,
            message_box.findChild(QLabel, "qt_msgbox_label"),
            progress_dialog.findChild(QLabel),
        )
        assert all(label is not None for label in labels)
        for label, target in zip(labels, dialogs, strict=True):
            foreground = label.palette().color(QPalette.ColorRole.WindowText)
            background = _rendered_corner_color(target)
            assert foreground.name().upper() == "#F4F8F8"
            assert _contrast_ratio(foreground, background) >= 7.0

        parent.setStyleSheet(window_style_sheet("desktop"))
        desktop_dialog = QDialog(parent)
        desktop_dialog.resize(160, 80)
        desktop_dialog.show()
        app.processEvents()
        assert _rendered_corner_color(desktop_dialog).lightness() > 180
        desktop_dialog.close()
    finally:
        for target in dialogs:
            target.close()
        parent.close()


def test_main_window_prepares_complete_qt_surface_before_show() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(visual_style="mobile"),
            translator=Translator(paths.translations, "ja-JP"),
        )

        assert not window.isVisible()
        assert window.windowOpacity() == 1.0
        assert not window.testAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground
        )
        assert not window.testAttribute(
            Qt.WidgetAttribute.WA_NoSystemBackground
        )
        assert window.autoFillBackground()
        assert (
            window.palette().color(QPalette.ColorRole.Window).name().upper()
            == "#07151D"
        )
        assert "#07151D" in window.styleSheet()
        assert (
            window.centralWidget()
            .palette()
            .color(QPalette.ColorRole.Window)
            .name()
            .upper()
            == "#07151D"
        )
        assert window.centralWidget().autoFillBackground()
        assert window.tabs.parentWidget() is window.centralWidget()
        assert not window.testAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        assert not hasattr(window, "_set_native_window_cloaked")
        for index in range(window.tabs.count()):
            page = window.tabs.widget(index)
            assert not page.isWindow()
            assert page.window() is window
        assert all(
            widget.parentWidget() is not None
            for widget in window.findChildren(QWidget)
        )
        window.close()
    finally:
        player_repository.close()


def test_mobile_update_dialog_applies_its_theme_directly() -> None:
    app = QApplication.instance() or QApplication([])
    parent = QMainWindow()
    parent.t = lambda key, **_values: key
    controller = UpdateController(
        parent,
        settings_repository=object(),
        app_settings=AppSettings(visual_style="mobile"),
    )
    box = controller._message_box(
        QMessageBox.Icon.Information,
        "PC版 0.0.15 / PWA版 0.0.12",
    )
    try:
        box.resize(460, 280)
        box.show()
        app.processEvents()

        background = _rendered_corner_color(box)
        label = box.findChild(QLabel, "qt_msgbox_label")
        assert label is not None
        foreground = label.palette().color(QPalette.ColorRole.WindowText)

        assert box.property("visualStyle") == "mobile"
        assert box.palette().color(QPalette.ColorRole.Window).name().upper() == "#0D2530"
        assert background.name().upper() == "#0D2530"
        assert foreground.name().upper() == "#F4F8F8"
        assert _contrast_ratio(foreground, background) >= 7.0
    finally:
        box.close()
        parent.close()


def test_visible_spin_buttons_stay_inside_field_with_consistent_contrast() -> None:
    app = QApplication.instance() or QApplication([])
    for visual_style in ("desktop", "mobile"):
        parent = QMainWindow()
        parent.setStyleSheet(window_style_sheet(visual_style))
        spin = VisibleSpinBox(parent)
        spin.setRange(0, 10)
        spin.setValue(5)
        spin.set_visual_style(visual_style)
        spin.resize(spin.minimumWidth(), 34)
        parent.setCentralWidget(spin)
        parent.resize(spin.minimumWidth(), 34)
        parent.show()
        app.processEvents()

        buttons = {
            button.text(): button for button in spin.findChildren(QToolButton)
        }
        assert set(buttons) == {"−", "+"}
        assert all(
            "max-width" not in button.styleSheet()
            and "max-height" not in button.styleSheet()
            for button in buttons.values()
        )
        assert spin.minimumWidth() >= 104
        assert not buttons["−"].geometry().intersects(buttons["+"].geometry())
        for button in buttons.values():
            assert spin.rect().contains(button.geometry())
            assert button.height() <= spin.height() - 2
            assert button.width() == 24
            image = button.grab().toImage()
            colors = [
                image.pixelColor(x, y)
                for y in range(3, max(4, image.height() - 3))
                for x in range(3, max(4, image.width() - 3))
            ]
            assert any(color.lightness() < 80 for color in colors)
            assert any(color.lightness() > 120 for color in colors)
        if visual_style == "desktop":
            enabled_background = buttons["+"].grab().toImage().pixelColor(5, 5)
            assert enabled_background.lightness() > 150
        else:
            enabled_background = buttons["+"].grab().toImage().pixelColor(5, 5)
            assert enabled_background.lightness() < 120
        parent.close()


def test_visible_spin_buttons_refresh_when_target_range_changes() -> None:
    _app = QApplication.instance() or QApplication([])
    spin = VisibleSpinBox()
    spin.setRange(1, 1)
    spin.setValue(1)
    assert not spin._increase_button.isEnabled()

    spin.setMaximum(10)

    assert spin._increase_button.isEnabled()
    spin.close()


def test_plan_target_plus_button_is_not_covered_at_large_ui_font() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    player_repository = PlayerRepository(":memory:")
    window = MainWindow(
        paths=paths,
        master=JsonMasterRepository(paths.research_data).load(),
        observations=JsonResearchCatalogRepository(
            paths.research_catalog
        ).load_all(),
        player_repository=player_repository,
        player_state=player_repository.load(),
        settings_repository=SettingsRepository(None),
        app_settings=AppSettings(visual_style="mobile", ui_font_size=16),
        translator=Translator(paths.translations, "ja-JP"),
    )
    try:
        window.resize(957, 488)
        window.tabs.setCurrentIndex(1)
        window._set_plan_target("army_leadership_more_gatherers")
        window.show()
        app.processEvents()

        assert isinstance(window.plan_toolbar.layout(), QHBoxLayout)
        increase = window.plan_level_spin._increase_button
        hit_widget = QApplication.widgetAt(
            increase.mapToGlobal(increase.rect().center())
        )
        assert hit_widget is increase
        assert increase.isEnabled()
        QTest.mouseClick(
            hit_widget,
            Qt.MouseButton.LeftButton,
            pos=hit_widget.rect().center(),
        )
        app.processEvents()
        assert window.plan_level_spin.value() == 2
    finally:
        window.close()
        player_repository.close()


def test_plan_toolbar_surface_follows_mobile_and_desktop_themes() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    player_repository = PlayerRepository(":memory:")
    window = MainWindow(
        paths=paths,
        master=JsonMasterRepository(paths.research_data).load(),
        observations=JsonResearchCatalogRepository(
            paths.research_catalog
        ).load_all(),
        player_repository=player_repository,
        player_state=player_repository.load(),
        settings_repository=SettingsRepository(None),
        app_settings=AppSettings(visual_style="desktop"),
        translator=Translator(paths.translations, "ja-JP"),
    )
    try:
        window.resize(1176, 500)
        window.tabs.setCurrentIndex(1)
        window.show()
        app.processEvents()

        viewport = window.plan_toolbar_scroll.viewport()
        assert viewport.objectName() == "PlanToolbarViewport"
        assert window.plan_toolbar.objectName() == "PlanToolbar"
        desktop_image = viewport.grab().toImage()
        desktop_background = desktop_image.pixelColor(
            max(0, desktop_image.width() - 2),
            max(0, desktop_image.height() - 2),
        )
        assert desktop_background.lightness() > 160

        window.app_settings.visual_style = "mobile"
        window._apply_visual_style()
        app.processEvents()
        mobile_image = viewport.grab().toImage()
        mobile_background = mobile_image.pixelColor(
            max(0, mobile_image.width() - 2),
            max(0, mobile_image.height() - 2),
        )
        assert mobile_background.lightness() < 80
        assert viewport.height() >= window.plan_toolbar.height()
        for child in window.plan_toolbar.findChildren(
            QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly
        ):
            if child.isHidden():
                continue
            child_rect = QRect(child.mapTo(viewport, QPoint(0, 0)), child.size())
            assert child_rect.top() >= 0
            assert child_rect.bottom() < viewport.height()
            assert child.height() >= child.sizeHint().height()

        window.app_settings.visual_style = "desktop"
        window._apply_visual_style()
        app.processEvents()
        restored_image = viewport.grab().toImage()
        restored_background = restored_image.pixelColor(
            max(0, restored_image.width() - 2),
            max(0, restored_image.height() - 2),
        )
        assert restored_background.lightness() > 160
    finally:
        window.close()
        player_repository.close()


def test_all_pc_tab_step_buttons_stay_inside_their_numeric_fields() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    player_repository = PlayerRepository(":memory:")
    window = MainWindow(
        paths=paths,
        master=JsonMasterRepository(paths.research_data).load(),
        observations=JsonResearchCatalogRepository(
            paths.research_catalog
        ).load_all(),
        player_repository=player_repository,
        player_state=player_repository.load(),
        settings_repository=SettingsRepository(None),
        app_settings=AppSettings(),
        translator=Translator(paths.translations, "ja-JP"),
    )
    try:
        window.resize(1440, 900)
        window.show()
        for visual_style in ("desktop", "mobile"):
            window.app_settings.visual_style = visual_style
            window._apply_visual_style()
            for tab_index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(tab_index)
                app.processEvents()
                page = window.tabs.currentWidget()
                spins = [
                    *page.findChildren(VisibleSpinBox),
                    *page.findChildren(VisibleDoubleSpinBox),
                ]
                for spin in spins:
                    if not spin.isVisibleTo(window):
                        continue
                    buttons = {
                        button.text(): button
                        for button in spin.findChildren(QToolButton)
                    }
                    assert set(buttons) == {"−", "+"}
                    assert spin.width() >= 104
                    assert not buttons["−"].geometry().intersects(
                        buttons["+"].geometry()
                    )
                    for button in buttons.values():
                        assert spin.rect().contains(button.geometry())
                        assert button.height() <= spin.height() - 2
                        assert button.width() == 24
    finally:
        window.close()
        player_repository.close()


def test_mobile_player_settings_scroll_instead_of_overlapping_numeric_fields() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    player_repository = PlayerRepository(":memory:")
    window = MainWindow(
        paths=paths,
        master=JsonMasterRepository(paths.research_data).load(),
        observations=JsonResearchCatalogRepository(
            paths.research_catalog
        ).load_all(),
        player_repository=player_repository,
        player_state=player_repository.load(),
        settings_repository=SettingsRepository(None),
        app_settings=AppSettings(visual_style="mobile"),
        translator=Translator(paths.translations, "ja-JP"),
    )
    try:
        window.resize(1440, 900)
        window.tabs.setCurrentIndex(3)
        window.show()
        app.processEvents()
        assert window.player_settings_scroll.verticalScrollBar().maximum() >= 0
        assert window.player_settings_scroll.widgetResizable()

        panel = window.player_settings_panel
        spins = [
            *panel.findChildren(VisibleSpinBox),
            *panel.findChildren(VisibleDoubleSpinBox),
        ]
        rectangles = []
        for spin in spins:
            top_left = spin.mapTo(panel, QPoint(0, 0))
            rectangles.append(QRect(top_left, spin.size()))
        for index, first in enumerate(rectangles):
            assert all(
                not first.intersects(second)
                for second in rectangles[index + 1 :]
            )
    finally:
        window.close()
        player_repository.close()


def test_all_table_numeric_editors_use_inset_cell_layout() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    player_repository = PlayerRepository(":memory:")
    window = MainWindow(
        paths=paths,
        master=JsonMasterRepository(paths.research_data).load(),
        observations=JsonResearchCatalogRepository(
            paths.research_catalog
        ).load_all(),
        player_repository=player_repository,
        player_state=player_repository.load(),
        settings_repository=SettingsRepository(None),
        app_settings=AppSettings(visual_style="mobile"),
        translator=Translator(paths.translations, "ja-JP"),
    )
    try:
        window.resize(1280, 820)
        window.show()
        for tab_index in (2, 3, 4):
            window.tabs.setCurrentIndex(tab_index)
            app.processEvents()

        table_spins = [
            *window.castle_level_table.findChildren(VisibleSpinBox),
            *window.progress_table.findChildren(VisibleSpinBox),
            *window.paid_item_table.findChildren(VisibleSpinBox),
        ]
        assert table_spins
        for spin in table_spins:
            assert spin.property("tableCellEditor") is True
            buttons = {
                button.text(): button
                for button in spin.findChildren(QToolButton)
            }
            assert set(buttons) == {"−", "+"}
            for button in buttons.values():
                assert button.geometry().top() >= 3
                assert button.geometry().bottom() <= spin.height() - 4

        for tab_index, table in (
            (2, window.castle_level_table),
            (3, window.progress_table),
            (4, window.paid_item_table),
        ):
            window.tabs.setCurrentIndex(tab_index)
            app.processEvents()
            button_rectangles = []
            for spin in table.findChildren(VisibleSpinBox):
                if not spin.isVisibleTo(table):
                    continue
                for button in spin.findChildren(QToolButton):
                    top_left = button.mapTo(table.viewport(), QPoint(0, 0))
                    button_rectangles.append(
                        (spin, button, QRect(top_left, button.size()))
                    )
            for index, (first_spin, first_button, first) in enumerate(
                button_rectangles
            ):
                assert all(
                    not first.intersects(second)
                    for _second_spin, _second_button, second in (
                        button_rectangles[index + 1 :]
                    )
                ), (
                    table.objectName(),
                    first_spin.geometry(),
                    first_button.text(),
                    first,
                    [
                        (spin.geometry(), button.text(), rectangle)
                        for spin, button, rectangle in button_rectangles[
                            index + 1 :
                        ]
                        if first.intersects(rectangle)
                    ],
                )

        form_spins = [
            window.vip_level_spin,
            window.construction_speed_spin,
        ]
        assert all(not spin.property("tableCellEditor") for spin in form_spins)
    finally:
        window.close()
        player_repository.close()


def test_every_table_cell_control_uses_one_non_overlapping_layout_rule() -> None:
    app = QApplication.instance() or QApplication([])
    host = QMainWindow()
    host.setProperty("visualStyle", "mobile")
    host.setStyleSheet(window_style_sheet("mobile"))
    table = QTableWidget(4, 1, host)
    host.setCentralWidget(table)
    table.resize(240, 220)

    spin = VisibleSpinBox()
    combo = QComboBox()
    combo.addItems(["時間", "分"])
    complete_button = QPushButton("完了")
    actions = QWidget()
    action_layout = QHBoxLayout(actions)
    action_layout.setContentsMargins(2, 0, 2, 0)
    action_layout.addWidget(QPushButton("表示"))
    action_layout.addWidget(QPushButton("削除"))

    controls = (spin, combo, complete_button, actions)
    for row, control in enumerate(controls):
        set_table_cell_widget(table, row, 0, control)

    host.resize(240, 220)
    host.show()
    app.processEvents()
    try:
        for row, control in enumerate(controls):
            assert table.cellWidget(row, 0) is control
            assert control.property("tableCellWidget") is True
            assert table.rowHeight(row) >= TABLE_CELL_ROW_HEIGHT

        assert spin.property("tableCellEditor") is True
        assert all(
            "#15333E" in button.styleSheet()
            for button in spin.findChildren(QToolButton)
        )
        assert combo.property("tableCellSelector") is True
        assert complete_button.property("tableCellAction") is True
        assert all(
            button.property("tableCellAction") is True
            for button in actions.findChildren(QPushButton)
        )

        host.setProperty("visualStyle", "desktop")
        host.setStyleSheet("")
        update_table_cell_widget_visual_styles(host, "desktop")
        app.processEvents()
        assert "#1976B9" in complete_button.styleSheet()
        assert "#FFFFFF" in complete_button.styleSheet()
        assert all(
            "#1976B9" in button.styleSheet()
            for button in actions.findChildren(QPushButton)
        )

        button_rectangles = []
        for row, control in enumerate(controls):
            buttons = ([control] if isinstance(control, QPushButton) else []) + list(
                control.findChildren(QPushButton)
            )
            row_top = table.rowViewportPosition(row)
            row_bottom = row_top + table.rowHeight(row) - 1
            for button in buttons:
                top_left = button.mapTo(table.viewport(), QPoint(0, 0))
                rectangle = QRect(top_left, button.size())
                assert rectangle.top() >= row_top
                assert rectangle.bottom() <= row_bottom
                button_rectangles.append(rectangle)
        for index, rectangle in enumerate(button_rectangles):
            assert all(
                not rectangle.intersects(other)
                for other in button_rectangles[index + 1 :]
            )
    finally:
        host.close()


def test_castle_tab_plans_facilities_and_saves_construction_settings() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        window.tabs.setCurrentIndex(2)
        assert isinstance(window.castle_plan_current_spin, VisibleSpinBox)
        assert window.castle_plan_current_spin.buttonSymbols() == (
            QAbstractSpinBox.ButtonSymbols.NoButtons
        )
        step_buttons = {
            button.text(): button
            for button in window.castle_plan_current_spin.findChildren(QToolButton)
        }
        assert set(step_buttons) == {"−", "+"}
        isolated_spin = VisibleSpinBox()
        isolated_spin.setRange(0, 10)
        isolated_spin.setValue(5)
        isolated_buttons = {
            button.text(): button
            for button in isolated_spin.findChildren(QToolButton)
        }
        isolated_buttons["+"].click()
        assert isolated_spin.value() == 6
        isolated_buttons["−"].click()
        assert isolated_spin.value() == 5
        assert window.castle_plan_current_spin.minimumWidth() >= 92
        window.castle_plan_current_spin.setValue(5)
        window.castle_plan_target_spin.setValue(6)
        app.processEvents()
        assert window.castle_plan_table.rowCount() == 8
        assert [
            window.castle_plan_table.item(row, 0).text() for row in range(7)
        ] == ["城壁", "保管庫", "保管庫", "保管庫", "保管庫", "保管庫", "城"]
        first_complete = window.castle_plan_table.cellWidget(
            0, window.castle_plan_table.columnCount() - 1
        )
        assert first_complete is not None
        first_complete.click()
        app.processEvents()
        assert player_repository.load().building_levels["castle_wall"] == 5
        assert player_repository.load().settings.castle_target_level == 6

        window.castle_plan_current_spin.setValue(24)
        window.castle_plan_target_spin.setValue(25)
        app.processEvents()
        total_row = window.castle_plan_table.rowCount() - 1
        normal_time = window.castle_plan_table.item(total_row, 2).text()
        window.construction_speed_spin.setValue(200.0)
        app.processEvents()
        faster_time = window.castle_plan_table.item(total_row, 2).text()
        assert faster_time != normal_time
        assert window.player_state.settings.construction_speed_percent == 200.0
        window.construction_speed_boost_spin.setValue(25.0)
        app.processEvents()
        boosted_time = window.castle_plan_table.item(total_row, 2).text()
        assert boosted_time != faster_time
        assert (
            window.player_state.settings.construction_speed_boost_percent
            == 25.0
        )
        assert "225" in window.castle_plan_speed_label.text()

        window._building_level_spins["academy"].setValue(20)
        window.tree_save_levels_button.click()
        saved = player_repository.load()
        assert saved.settings.construction_speed_percent == 200.0
        assert saved.settings.construction_speed_boost_percent == 25.0
        assert saved.building_levels["academy"] == 20

        academy_index = window.construction_target_combo.findData("academy")
        window.construction_target_combo.setCurrentIndex(academy_index)
        window.castle_plan_current_spin.setValue(24)
        window.castle_plan_target_spin.setValue(25)
        app.processEvents()
        assert window.castle_selection_summary_label.text() == (
            "アカデミー　Lv.24 → Lv.25"
        )
        assert "border:2px solid" in (
            window.castle_selection_summary_label.styleSheet()
        )
        window.resize(window.minimumSize())
        window.show()
        app.processEvents()
        castle_page = window.tabs.widget(2)
        summary_right = window.castle_selection_summary_label.mapTo(
            castle_page,
            window.castle_selection_summary_label.rect().topLeft(),
        ).x() + window.castle_selection_summary_label.width()
        assert summary_right <= castle_page.contentsRect().right() + 1
        assert window.castle_selection_summary_label.wordWrap() is True
        assert window.castle_selection_summary_label.height() >= (
            window.castle_selection_summary_label.fontMetrics().height()
        )
        window.tree_save_levels_button.click()
        window.close()
    finally:
        player_repository.close()


def test_castle_tab_plans_and_completes_post_25_mana_stages() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.castle_plan_current_spin.setValue(25)
        window.castle_plan_current_mana_spin.setValue(1)
        window.castle_plan_target_spin.setValue(25)
        window.castle_plan_target_mana_spin.setValue(3)
        app.processEvents()

        assert window.castle_plan_table.rowCount() == 3
        assert [
            window.castle_plan_table.item(row, 0).text() for row in range(2)
        ] == ["城（マナ強化）", "城（マナ強化）"]
        assert [
            window.castle_plan_table.item(row, 1).text() for row in range(2)
        ] == ["Lv.25-2", "Lv.25-3"]
        assert window.castle_plan_table.item(0, 11).text() == "23,029"
        assert window.castle_plan_table.item(0, 12).text() == "242"

        complete = window.castle_plan_table.cellWidget(
            1, window.castle_plan_table.columnCount() - 1
        )
        assert complete is not None
        complete.click()
        app.processEvents()
        restored = player_repository.load()
        assert restored.settings.castle_level == 25
        assert restored.settings.castle_mana_stage == 3
        assert restored.settings.castle_target_mana_stage == 3
        window.close()
    finally:
        player_repository.close()


def test_paid_tab_manual_entries_calculate_total_and_time_per_diamond() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.paid_item_table.setRowCount(0)
        window._add_paid_row(SpeedupEntry("general", 3 * 3600, 80))
        window._add_paid_row(SpeedupEntry("general", 60 * 60, 65))
        window._add_paid_row(SpeedupEntry("general", 30 * 60, 65))
        window.paid_diamond_spin.setValue(999)
        window.paid_included_gems_spin.setValue(3600)
        window.paid_bonus_gems_spin.setValue(4400)
        app.processEvents()

        assert window.tabs.tabText(4) == "課金"
        assert window.paid_summary_table.item(0, 1).text() == "14d 01:30:00"
        assert window.paid_summary_table.item(0, 2).text() == "999"
        assert window.paid_summary_table.item(0, 3).text() == "00:20:16"
        total_row = window.paid_summary_table.rowCount() - 1
        assert window.paid_summary_table.item(total_row, 1).text() == "14d 01:30:00"
        assert window.paid_total_gems_label.text() == "8,000"
        assert window.paid_gems_per_diamond_label.text() == "8.01"
        assert isinstance(window.paid_item_table.cellWidget(0, 0), QComboBox)
        assert isinstance(window.paid_item_table.cellWidget(0, 1), QSpinBox)
        assert isinstance(window.paid_item_table.cellWidget(0, 3), QSpinBox)
        window.close()
    finally:
        player_repository.close()


def test_paid_item_rows_keep_timeless_fields_hidden_and_can_be_reordered() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.paid_item_table.setRowCount(0)
        window._add_paid_row(
            PaidItem(kind="custom", name="任意素材", quantity=2)
        )
        custom_duration = window.paid_item_table.cellWidget(0, 1)
        custom_unit = window.paid_item_table.cellWidget(0, 2)
        assert custom_duration is not None and custom_duration.isHidden()
        assert custom_unit is not None and custom_unit.isHidden()

        window._add_paid_row(
            PaidItem(
                kind="general",
                name="汎用加速",
                quantity=3,
                duration_seconds=3600,
            )
        )
        app.processEvents()
        assert custom_duration.isHidden()
        assert custom_unit.isHidden()

        window.paid_item_table.selectRow(1)
        app.processEvents()
        assert window.paid_move_up_button.isEnabled()
        assert not window.paid_move_down_button.isEnabled()
        window.paid_move_up_button.click()
        app.processEvents()

        assert [
            window.paid_item_table.cellWidget(row, 5).text()
            for row in range(window.paid_item_table.rowCount())
        ] == ["汎用加速", "任意素材"]
        moved_custom_duration = window.paid_item_table.cellWidget(1, 1)
        moved_custom_unit = window.paid_item_table.cellWidget(1, 2)
        assert moved_custom_duration is not None and moved_custom_duration.isHidden()
        assert moved_custom_unit is not None and moved_custom_unit.isHidden()
        window.close()
    finally:
        player_repository.close()


def test_paid_tab_applies_ocr_items_and_discounted_price() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )

        def fake_ocr(
            *, force_window_capture: bool = False, paid_pack: bool = False
        ) -> None:
            assert force_window_capture
            assert paid_pack
            window._ocr_image = QImage(1280, 720, QImage.Format_RGB32)
            window._ocr_raw_text = ""
            window._ocr_line_groups = [
                (
                    OcrLine("研究スピードアップ 8時間", 300, 330, 500, 42),
                    OcrLine("50", 995, 332, 48, 42),
                    OcrLine("研究スピードアップ 3時間", 300, 395, 500, 42),
                    OcrLine("50", 995, 397, 48, 42),
                    OcrLine("研究スピードアップ 60分", 300, 460, 500, 42),
                    OcrLine("50", 995, 462, 48, 42),
                    OcrLine("3,600", 610, 215, 120, 44),
                    OcrLine("4,400", 310, 280, 120, 44),
                    OcrLine("1,999", 610, 650, 120, 44),
                    OcrLine("999", 625, 700, 100, 35),
                )
            ]
            window._ocr_paid_line_groups = list(window._ocr_line_groups)
            window._ocr_paid_gem_line_groups = list(window._ocr_line_groups)

        window._run_ocr = fake_ocr
        window._capture_paid_pack()
        app.processEvents()

        assert window.paid_item_table.rowCount() == 3
        assert window.paid_diamond_spin.value() == 999
        assert window.paid_included_gems_spin.value() == 3600
        assert window.paid_bonus_gems_spin.value() == 4400
        assert window.paid_total_gems_label.text() == "8,000"
        assert window.paid_gems_per_diamond_label.text() == "8.01"
        sixty_minutes = window.paid_item_table.cellWidget(2, 1)
        sixty_minutes_unit = window.paid_item_table.cellWidget(2, 2)
        assert isinstance(sixty_minutes, QSpinBox)
        assert isinstance(sixty_minutes_unit, QComboBox)
        assert sixty_minutes.value() == 60
        assert sixty_minutes_unit.currentData() == "minutes"
        assert window.paid_summary_table.item(1, 1).text() == "25d 00:00:00"
        assert window.paid_summary_table.item(1, 3).text() == "00:36:02"
        window.close()
    finally:
        player_repository.close()


def test_paid_tab_appends_scrolled_ocr_items_without_duplicates() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        captures = [
            (
                OcrLine("研究スピードアップ 3時間", 300, 330, 500, 42),
                OcrLine("50", 995, 332, 48, 42),
                OcrLine("食糧 500,000", 300, 395, 500, 42),
                OcrLine("130", 980, 397, 64, 42),
                OcrLine("3,600", 610, 215, 120, 44),
                OcrLine("4,400", 310, 280, 120, 44),
                OcrLine("999", 625, 700, 100, 35),
            ),
            (
                OcrLine("食糧 500,000", 300, 330, 500, 42),
                OcrLine("130", 980, 332, 64, 42),
                OcrLine("キラービーの宝箱", 300, 395, 500, 42),
                OcrLine("50", 995, 397, 48, 42),
            ),
        ]

        def fake_ocr(
            *, force_window_capture: bool = False, paid_pack: bool = False
        ) -> None:
            assert force_window_capture
            assert paid_pack
            lines = captures.pop(0)
            window._ocr_image = QImage(1280, 720, QImage.Format_RGB32)
            window._ocr_raw_text = ""
            window._ocr_line_groups = [lines]
            window._ocr_paid_line_groups = [lines]
            window._ocr_paid_gem_line_groups = [lines]

        window._run_ocr = fake_ocr
        window._capture_paid_pack()
        assert window.paid_item_table.rowCount() == 2
        assert window.paid_diamond_spin.value() == 999
        assert window.paid_included_gems_spin.value() == 3600
        assert window.paid_bonus_gems_spin.value() == 4400

        window._capture_paid_pack()
        app.processEvents()

        assert window.paid_item_table.rowCount() == 3
        assert window.paid_diamond_spin.value() == 999
        assert window.paid_included_gems_spin.value() == 3600
        assert window.paid_bonus_gems_spin.value() == 4400
        names = {
            window.paid_item_table.cellWidget(row, 5).text()
            for row in range(window.paid_item_table.rowCount())
        }
        assert names == {"", "食糧 500,000", "キラービーの宝箱"}
        window.close()
    finally:
        player_repository.close()


def test_paid_tab_saves_and_compares_a_named_offer() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window._show_info = lambda _message: None
        assert window.paid_workspace_tabs.currentIndex() == 0
        assert window.paid_workspace_tabs.count() == 4
        assert window.paid_workspace_tabs.tabText(3) == "共有"
        window.paid_item_table.setRowCount(0)
        window._add_paid_row(
            PaidItem(
                kind="monster_legendary",
                name="伝説素材",
                quantity=2,
                gem_value_each=1200,
                points_each=100,
            )
        )
        window.paid_title_edit.setText("魔獣素材パック")
        window.paid_memo_edit.setText("比較用")
        window.paid_diamond_spin.setValue(999)
        window._save_paid_offer()
        app.processEvents()

        loaded = player_repository.load()
        assert loaded.paid_offers[0].title == "魔獣素材パック"
        assert loaded.paid_offers[0].items[0].duration_seconds == 0
        assert window.paid_offer_table.rowCount() == 1
        assert window.paid_comparison_table.item(0, 6).text() != "-"
        window.close()
    finally:
        player_repository.close()


def test_paid_tab_add_button_creates_an_editable_manual_row() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.show()
        window.tabs.setCurrentIndex(4)
        app.processEvents()
        initial_rows = window.paid_item_table.rowCount()

        QTest.mouseClick(window.paid_add_row_button, Qt.LeftButton)
        app.processEvents()

        assert window.paid_item_table.rowCount() == initial_rows + 1
        row = window.paid_item_table.rowCount() - 1
        duration = window.paid_item_table.cellWidget(row, 1)
        quantity = window.paid_item_table.cellWidget(row, 3)
        assert isinstance(duration, QSpinBox)
        assert isinstance(quantity, QSpinBox)
        assert duration.hasFocus()
        duration.setValue(3)
        quantity.setValue(80)
        app.processEvents()
        assert duration.value() == 3
        assert quantity.value() == 80
        assert window.paid_item_table.item(row, 4).text() == "10d 00:00:00"
        window.close()
    finally:
        player_repository.close()


def test_dataset_list_uses_the_largest_centered_font_that_fits() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.resize(1400, 900)
        window.show()
        app.processEvents()
        window.tree_dataset_list.fit_items()
        available_width = window.tree_dataset_list.viewport().width() - 18
        total_height = 0
        for index in range(window.tree_dataset_list.count()):
            item = window.tree_dataset_list.item(index)
            metrics = QFontMetrics(item.font())
            assert metrics.horizontalAdvance(item.text()) <= available_width
            assert item.textAlignment() == Qt.AlignCenter
            assert item.font().pointSizeF() > 10.0
            total_height += item.sizeHint().height()
        assert total_height <= window.tree_dataset_list.viewport().height()
        window.close()
    finally:
        player_repository.close()


def test_layout_card_results_replace_fuzzy_candidates_in_the_active_tree() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.tree_dataset_list.setCurrentRow(
            window._dataset_list_row("observation:catalog-military")
        )
        window._ocr_image = QImage(1508, 964, QImage.Format_RGB32)
        window._ocr_image.fill(QColor("#315D6B"))
        window._ocr_candidates = [
            OcrCandidate("military_furious_offense_i", 8, "fuzzy false match")
        ]
        window._ocr_card_groups = [
                (
                    QRect(612, 150, 308, 124),
                    (
                        OcrLine("訓練速度I", 660, 190, 180, 24),
                        OcrLine("1/1", 700, 230, 80, 20),
                    ),
                ),
            (
                QRect(418, 548, 323, 130),
                (OcrLine("8/10", 530, 640, 90, 20),),
            ),
            (
                QRect(806, 548, 323, 130),
                (OcrLine("8/10", 920, 640, 90, 20),),
            ),
        ]

        window._append_layout_ocr_candidates()

        assert {(item.research_id, item.level) for item in window._ocr_candidates} == {
            ("military_training_speed_i", 1),
            ("military_intelligence_report", 8),
            ("military_quick_maneuvers_i", 8),
        }
        window.close()
    finally:
        player_repository.close()


def test_tree_search_filters_dataset_list_and_restores_selection() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        original_count = window.tree_dataset_list.count()
        assert window.tree_dataset_list.currentItem().data(Qt.UserRole) == (
            "observation:catalog-economy"
        )

        window.search_edit.setText("defense_trap_durability_i")
        app.processEvents()

        assert window.tree_dataset_list.count() == 1
        assert window.tree_dataset_list.currentItem().data(Qt.UserRole) == (
            "observation:catalog-defense"
        )
        rendered_ids = {
            item.research_id
            for item in window.tree_view.scene().items()
            if hasattr(item, "research_id")
        }
        assert rendered_ids == {"defense_trap_durability_i"}

        window.search_edit.setText("no-such-research-item")
        app.processEvents()

        assert window.tree_dataset_list.count() == 0
        assert not {
            item.research_id
            for item in window.tree_view.scene().items()
            if hasattr(item, "research_id")
        }

        window.search_edit.clear()
        app.processEvents()

        assert window.tree_dataset_list.count() == original_count
        assert window.tree_dataset_list.currentItem().data(Qt.UserRole) == (
            "observation:catalog-economy"
        )
    finally:
        player_repository.close()


def test_layout_does_not_apply_another_category_without_matching_labels() -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.tree_dataset_list.setCurrentRow(
            window._dataset_list_row("observation:catalog-defense")
        )
        window._ocr_image = QImage(1280, 720, QImage.Format_RGB32)
        window._ocr_image.fill(QColor("#315D6B"))
        window._ocr_candidates = []
        window._ocr_card_groups = [
            (
                QRect(120, 120, 250, 120),
                (
                    OcrLine("食糧収穫I", 150, 160, 160, 24),
                    OcrLine("9/10", 200, 210, 70, 20),
                ),
            ),
            (
                QRect(500, 120, 250, 120),
                (
                    OcrLine("保管庫管理", 530, 160, 160, 24),
                    OcrLine("7/10", 580, 210, 70, 20),
                ),
            ),
        ]

        window._append_layout_ocr_candidates()

        assert window._ocr_candidates == []
        window.close()
    finally:
        player_repository.close()


def test_window_capture_uses_current_visible_window_pixels(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    game_window = CapturableWindow(42, "Lords Mobile PC", -1200, 80, 1017, 653)
    captured = QImage(1017, 653, QImage.Format_RGB32)
    captured.fill(QColor("#1A6E82"))
    monkeypatch.setattr(
        main_window_module, "list_capturable_windows", lambda: [game_window]
    )
    monkeypatch.setattr(
        main_window_module, "capture_visible_window", lambda window: captured
    )
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        assert window._capture_window() is True
        assert window._ocr_image_source == "window"
        assert (window._ocr_image.width(), window._ocr_image.height()) == (1017, 653)
        assert window.ocr_image_label.pixmap() is not None
        window.close()
    finally:
        player_repository.close()


def test_ocr_tab_uses_a_progress_bar_without_raw_result_text() -> None:
    class FakeOcrEngine:
        available = True
        name = "Fake OCR"

        def recognize_png(self, _png_data, profile) -> OcrResult:
            return OcrResult("", self.name, profile.locale)

    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window._ocr_engine = FakeOcrEngine()
        image = QImage(320, 180, QImage.Format_RGB32)
        image.fill(QColor("#315D6B"))
        window._set_ocr_image(image, source="file")
        window.show()
        app.processEvents()

        assert not hasattr(window, "ocr_text")
        assert not hasattr(window, "ocr_status")
        assert window.ocr_progress.value() == 0
        assert window.tree_capture_progress.isVisible()
        window.tabs.setCurrentIndex(5)
        app.processEvents()
        assert window.ocr_progress.isVisible()
        window._run_ocr()
        app.processEvents()

        assert window.ocr_progress.maximum() > 0
        assert window.ocr_progress.value() == window.ocr_progress.maximum()
        assert window.tree_capture_progress.maximum() == (
            window.ocr_progress.maximum()
        )
        assert window.tree_capture_progress.value() == window.ocr_progress.value()
        assert window.paid_capture_progress.maximum() == (
            window.ocr_progress.maximum()
        )
        assert window.paid_capture_progress.value() == window.ocr_progress.value()
        assert window.run_ocr_button.isEnabled()
        window.close()
    finally:
        player_repository.close()


def test_minimized_fullscreen_game_is_restored_before_capture(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    minimized = CapturableWindow(
        42,
        "Lords Mobile PC",
        -32000,
        -32000,
        1920,
        1080,
        is_minimized=True,
    )
    restored = CapturableWindow(
        42,
        "Lords Mobile PC",
        0,
        0,
        1920,
        1080,
        is_fullscreen=True,
    )
    calls = 0
    revealed: list[CapturableWindow] = []
    captured_windows: list[CapturableWindow] = []

    def windows() -> list[CapturableWindow]:
        nonlocal calls
        calls += 1
        return [minimized if calls <= 2 else restored]

    def capture(window: CapturableWindow) -> QImage:
        captured_windows.append(window)
        image = QImage(window.width, window.height, QImage.Format_RGB32)
        image.fill(QColor("#1A6E82"))
        return image

    monkeypatch.setattr(main_window_module, "list_capturable_windows", windows)
    monkeypatch.setattr(
        main_window_module,
        "reveal_window_for_capture",
        lambda window: revealed.append(window),
    )
    monkeypatch.setattr(main_window_module, "capture_visible_window", capture)
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        window.show()
        app.processEvents()

        assert window._capture_window() is True
        assert revealed == [minimized]
        assert captured_windows == [restored]
        assert (window._ocr_image.width(), window._ocr_image.height()) == (
            1920,
            1080,
        )
        window.close()
    finally:
        player_repository.close()


def test_ocr_field_fuzzy_mapping_updates_research_speed_and_waits_for_save(
    monkeypatch,
) -> None:
    app = QApplication.instance() or QApplication([])
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(tool_root=root, bundled_root=root)
    master = JsonMasterRepository(paths.research_data).load()
    catalog = JsonResearchCatalogRepository(paths.research_catalog).load_all()
    player_repository = PlayerRepository(":memory:")
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *_args, **_kwargs: main_window_module.QMessageBox.Yes,
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "information",
        lambda *_args, **_kwargs: main_window_module.QMessageBox.Ok,
    )
    try:
        window = MainWindow(
            paths=paths,
            master=master,
            observations=catalog,
            player_repository=player_repository,
            player_state=player_repository.load(),
            settings_repository=SettingsRepository(None),
            app_settings=AppSettings(),
            translator=Translator(paths.translations, "ja-JP"),
        )
        profile = window._selected_ocr_profile()
        window._ocr_line_groups = [
            (
                OcrLine("研究連度", 100, 100, 130, 24),
                OcrLine("+224.84%", 300, 100, 100, 24),
            )
        ]

        window._parse_ocr_fields(profile)

        assert window.ocr_field_table.rowCount() == 1
        mapping = window._ocr_field_mapping_combos[0]
        assert mapping.currentData() == "research_speed"

        window._confirm_and_store_ocr_fields([0])

        assert window.research_speed_spin.value() == 224.84
        assert window.player_state.settings.research_speed_percent == 224.84
        assert player_repository.load().settings.research_speed_percent == 0.0
        assert window.tree_save_levels_button.isEnabled()

        window.tree_save_levels_button.click()
        app.processEvents()

        assert player_repository.load().settings.research_speed_percent == 224.84
        assert not window.tree_save_levels_button.isEnabled()
        window.close()
    finally:
        player_repository.close()
