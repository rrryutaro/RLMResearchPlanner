from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from difflib import SequenceMatcher
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect, QSize, Qt
from PySide6.QtGui import (
    QBrush,
    QCloseEvent,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPixmap,
    qBlue,
    qGray,
    qGreen,
    qRed,
    qRgb,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from rlm_research_planner.domain.models import (
    MasterData,
    PlayerState,
    ResearchPlanTask,
    RESOURCE_KEYS,
)
from rlm_research_planner.domain.observations import (
    ObservedResearchNode,
    ResearchTreeObservation,
)
from rlm_research_planner.paths import AppPaths
from rlm_research_planner.repositories.player_repository import PlayerRepository
from rlm_research_planner.services.calculation import (
    apply_free_speedup_time,
    apply_guild_helps,
    apply_research_speed,
    free_speedup_seconds_for_vip,
    format_duration,
)
from rlm_research_planner.services.catalog_planning import (
    CatalogPlanResult,
    CatalogPlanStep,
    CatalogResearchPlanner,
)
from rlm_research_planner.services.castle_planning import (
    CASTLE_RESOURCE_KEYS,
    CastleCatalog,
    CastlePlanStep,
)
from rlm_research_planner.services.localization import Translator
from rlm_research_planner.services.ocr import (
    OcrCandidate,
    OcrCardLevel,
    OcrFieldCandidate,
    OcrLine,
    PreferredOcrEngine,
    TesseractOcrEngine,
    WindowsOcrEngine,
    load_ocr_profiles,
    map_ocr_card_levels_by_layout,
    match_ocr_card_label,
    normalize_ocr_label,
    pair_ocr_label_values,
    pair_ocr_research_card_levels,
    parse_ocr_percentage,
    parse_ocr_card_level,
    parse_research_candidates,
    parse_research_level_fields,
)
from rlm_research_planner.services.paid_pack import (
    SPEEDUP_KINDS,
    SpeedupEntry,
    detect_pack_price,
    parse_gem_bundle,
    parse_speedup_ocr,
    summarize_speedups,
)
from rlm_research_planner.services.resource_format import format_resource_amount
from rlm_research_planner.services.window_capture import (
    CapturableWindow,
    capture_visible_window,
    list_capturable_windows,
    preferred_window_index,
    reveal_window_for_capture,
    should_refresh_window_before_ocr,
)
from rlm_research_planner.settings import (
    AppSettings,
    SettingsRepository,
    normalize_visual_style,
)
from rlm_research_planner.ui.research_tree_view import (
    ResearchTreeNode,
    ResearchTreeView,
)
from rlm_research_planner.ui.update_controller import UpdateController
from rlm_research_planner.ui.visual_styles import (
    dataset_style_sheet,
    table_link_color,
    window_style_sheet,
)
from rlm_research_planner.version import version_string


RESOURCE_LABELS = {
    "food": "Food",
    "stone": "Stone",
    "timber": "Timber",
    "ore": "Ore",
    "gold": "Gold",
    "special": "Special",
    "ancient_tomes": "Ancient Tomes",
    "mana_ore": "Mana Ore",
    "lunite": "Lunite",
}
PLAN_RESOURCE_KEYS = tuple(RESOURCE_LABELS)


class _OcrImagePreview(QLabel):
    def __init__(self, empty_text: str, parent: QWidget | None = None) -> None:
        super().__init__(empty_text, parent)
        self._source_image = QImage()

    def set_image(self, image: QImage) -> None:
        self._source_image = image.copy()
        self._update_preview()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_preview()

    def _update_preview(self) -> None:
        if self._source_image.isNull() or self.width() <= 1 or self.height() <= 1:
            return
        self.setPixmap(
            QPixmap.fromImage(self._source_image).scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )


class _AutoFitListWidget(QListWidget):
    """Use the largest single-line font that fits every fixed dataset item."""

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.fit_items()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.fit_items()

    def fit_items(self) -> None:
        count = self.count()
        if count <= 0 or self.viewport().width() <= 1:
            return
        available_height = max(1, self.viewport().height() - 2)
        row_height = max(28, min(52, available_height // count))
        available_width = max(40, self.viewport().width() - 18)
        item_texts = [self.item(index).text() for index in range(count)]
        base_font = QFont(self.font())
        low = 1.0
        high = 22.0
        best = low
        for _ in range(10):
            point_size = (low + high) / 2.0
            candidate = QFont(base_font)
            candidate.setPointSizeF(point_size)
            metrics = QFontMetrics(candidate)
            if (
                max(metrics.horizontalAdvance(text) for text in item_texts)
                <= available_width
                and metrics.height() <= row_height - 6
            ):
                best = point_size
                low = point_size
            else:
                high = point_size
        fitted_font = QFont(base_font)
        fitted_font.setPointSizeF(best)
        for index in range(count):
            item = self.item(index)
            item.setFont(fitted_font)
            item.setTextAlignment(Qt.AlignCenter)
            item.setSizeHint(QSize(0, row_height))


class MainWindow(QMainWindow):
    def __init__(
        self,
        *,
        paths: AppPaths,
        master: MasterData,
        observations: tuple[ResearchTreeObservation, ...],
        player_repository: PlayerRepository,
        player_state: PlayerState,
        settings_repository: SettingsRepository,
        app_settings: AppSettings,
        translator: Translator,
    ) -> None:
        super().__init__()
        self.paths = paths
        self.master = master
        self.observations = observations
        self.player_repository = player_repository
        self.player_state = player_state
        self._tree_level_draft = dict(player_state.research_levels)
        self.settings_repository = settings_repository
        self.app_settings = app_settings
        self.translator = translator
        self.catalog_planner = CatalogResearchPlanner(observations)
        self.castle_catalog = CastleCatalog.load(paths.castle_catalog)
        self._building_level_draft = dict(player_state.building_levels)
        self._research = master.research_by_id()
        self._observation_by_id = {
            observation.observation_id: observation for observation in observations
        }
        self._observed_nodes: dict[str, ObservedResearchNode] = {}
        self._node_observation: dict[str, ResearchTreeObservation] = {}
        for observation in observations:
            for node in observation.nodes:
                self._observed_nodes[node.id] = node
                self._node_observation[node.id] = observation
        self._selected_research_id = master.research[0].id if master.research else ""
        self._selected_tree_node_id = self._selected_research_id
        self._plan_target_research_id = ""
        self._plan_mode = "target"
        self._current_catalog_plan: CatalogPlanResult | None = None
        self._preserve_completed_plan_target = False
        self._capturable_windows: list[CapturableWindow] = []
        self._ocr_profiles = load_ocr_profiles(paths.ocr_profiles)
        self._ocr_engine = PreferredOcrEngine(
            WindowsOcrEngine(paths.windows_ocr_script),
            TesseractOcrEngine(),
        )
        self._ocr_image = QImage()
        self._ocr_image_source = ""
        self._ocr_candidates: list[OcrCandidate] = []
        self._ocr_fields: list[OcrFieldCandidate] = []
        self._ocr_raw_text = ""
        self._ocr_line_groups: list[tuple[OcrLine, ...]] = []
        self._ocr_paid_line_groups: list[tuple[OcrLine, ...]] = []
        self._ocr_paid_gem_line_groups: list[tuple[OcrLine, ...]] = []
        self._ocr_card_groups: list[tuple[QRect, tuple[OcrLine, ...]]] = []
        self._tree_levels_dirty = False
        self._player_settings_dirty = False
        self.update_controller = UpdateController(
            self, self.settings_repository, self.app_settings
        )
        self.setMinimumSize(980, 640)
        self._build_ui()
        self._apply_visual_style()
        self._restore_geometry()
        self.update_controller.schedule_startup_check()

    def t(self, key: str, **values: object) -> str:
        return self.translator.text(key, **values)

    def _resource_label(self, key: str) -> str:
        translated = self.t(f"resource.{key}")
        return translated if translated != f"resource.{key}" else RESOURCE_LABELS.get(key, key)

    def _tree_effect_lines(
        self, research_id: str, current_level: int, max_level: int
    ) -> tuple[str, str]:
        localized = self.master.localized_research(
            research_id, self.translator.locale
        )
        effect_label = (
            self.translator.effect_label(localized.effect_label)
            or localized.effect_label
            or self.t("common.unknown")
        )
        if current_level <= 0:
            current_value = self._format_effect_line(effect_label, "0")
        else:
            current_data = self.master.level(research_id, current_level)
            current_value = self._format_effect_line(
                effect_label, f"{current_data.cumulative_effect:g}"
            )
        if current_level >= max_level:
            next_value = ""
        else:
            next_data = self.master.level(research_id, current_level + 1)
            next_value = self._format_effect_line(
                effect_label, f"{next_data.cumulative_effect:g}"
            )
        return current_value, next_value

    def _observed_tree_effect_lines(
        self, node: ObservedResearchNode, current_level: int
    ) -> tuple[str, str]:
        source_label = node.effect_label.strip()
        label = self.translator.effect_label(source_label)
        if not label:
            generic_labels = {
                "",
                "ATK+",
                "Boost",
                "Cost Reduction",
                "DEF+",
                "Def. Boost",
                "Effect",
                "HP+",
                "Reduction",
                "Result",
                "Speed+",
                "Unlock",
                "Unlocks",
                "Upgrade Result",
                "Upgrade Results",
            }
            if self.translator.locale.startswith("ja") or source_label in generic_labels:
                label = self._effect_label_from_research_name(
                    node.localized_name(self.translator.locale)
                )
            else:
                label = source_label
        if current_level > 0:
            current_value = self._localized_observed_effect_value(
                node.effect_at(current_level)
            )
        elif self._is_unlock_effect(node.effect_at(1)):
            current_value = self.t("effect.not_unlocked")
        else:
            current_value = "0"
        current_value = self._format_effect_line(label, current_value)
        if node.max_level is not None and current_level >= node.max_level:
            next_value = ""
        else:
            next_level = current_level + 1
            next_effect = self._localized_observed_effect_value(
                node.effect_at(next_level)
            )
            next_value = self._format_effect_line(
                label, next_effect or self.t("common.unknown")
            )
        return current_value, next_value

    @staticmethod
    def _effect_label_from_research_name(name: str) -> str:
        label = re.sub(r"\s*(?:I|II|III|IV|V)$", "", name.strip()).strip()
        if label.endswith("補助"):
            label = f"{label.removesuffix('補助')}コスト低下"
        return label

    @staticmethod
    def _is_unlock_effect(value: str) -> bool:
        normalized = value.strip()
        return normalized == "Unlocked" or normalized.startswith(
            ("Unlock ", "Unlocks ")
        )

    def _format_effect_line(self, label: str, value: str) -> str:
        normalized_label = label.strip()
        normalized_value = value.strip()
        decimal_comma = re.fullmatch(r"(\d+),(\d{1,2})%", normalized_value)
        if decimal_comma:
            normalized_value = f"{decimal_comma.group(1)}.{decimal_comma.group(2)}%"
        if re.fullmatch(r"\d[\d,.]*(?:%|分)?", normalized_value):
            normalized_value = f"+{normalized_value}"
        if not normalized_label:
            return normalized_value
        separator = "" if self.translator.locale.startswith("ja") else " "
        return f"{normalized_label}{separator}{normalized_value}"

    def _localized_observed_effect_value(self, value: str) -> str:
        if not self.translator.locale.startswith("ja"):
            return value
        normalized = value.strip()
        if normalized == "Unlocked" or normalized.startswith(("Unlock ", "Unlocks ")):
            return "解放"
        minutes = re.fullmatch(r"(\d+)\s+(?:min|minutes)", normalized)
        if minutes:
            return f"{minutes.group(1)}分"
        hunt_level = re.fullmatch(r"Hunt Level (\d+) monsters", normalized)
        if hunt_level:
            return f"Lv.{hunt_level.group(1)}魔獣を討伐可能"
        battle_slots = {
            "3rd Familiar Battle Slot": "召喚獣編成枠3",
            "4th Battle Slot": "召喚獣編成枠4",
            "Battle Slot V": "召喚獣編成枠5",
        }
        if normalized in battle_slots:
            return battle_slots[normalized]
        if normalized == "Manasteel Refinement Bonus +1":
            return "マナスチール精製ボーナス+1"
        return normalized

    def _build_ui(self) -> None:
        self.setWindowTitle(self.t("app.title"))
        root = QWidget(self)
        root.setObjectName("RlmRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tree_tab(), self.t("tab.tree"))
        self.tabs.addTab(self._build_plan_tab(), self.t("tab.plan"))
        self.tabs.addTab(self._build_castle_tab(), self.t("tab.castle"))
        self.tabs.addTab(self._build_player_tab(), self.t("tab.player"))
        self.tabs.addTab(self._build_ocr_tab(), self.t("tab.ocr"))
        self.tabs.addTab(self._build_paid_tab(), self.t("tab.paid"))
        self.tabs.addTab(self._build_help_tab(), self.t("tab.help"))
        layout.addWidget(self.tabs, 1)
        self.setCentralWidget(root)

    def _build_tree_tab(self) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Horizontal)

        dataset_panel = QWidget()
        dataset_panel.setMinimumWidth(220)
        dataset_panel.setMaximumWidth(360)
        dataset_layout = QVBoxLayout(dataset_panel)
        dataset_layout.setContentsMargins(0, 0, 8, 0)
        dataset_heading = QLabel(self.t("tree.dataset"))
        dataset_heading.setStyleSheet("font-weight:700;")
        dataset_layout.addWidget(dataset_heading)
        self.tree_dataset_list = _AutoFitListWidget()
        self.tree_dataset_list.setStyleSheet(
            dataset_style_sheet(self.app_settings.visual_style)
        )
        self._tree_dataset_search_active = False
        self._tree_dataset_search_restore = ""
        for observation in self.observations:
            item = QListWidgetItem(
                observation.localized_title(self.translator.locale)
            )
            item.setData(
                Qt.UserRole, f"observation:{observation.observation_id}"
            )
            item.setToolTip(
                f"{observation.verification_status}\n{observation.notes}"
            )
            self.tree_dataset_list.addItem(item)
        self.tree_dataset_list.fit_items()
        dataset_layout.addWidget(self.tree_dataset_list, 1)
        splitter.addWidget(dataset_panel)

        tree_panel = QWidget()
        layout = QVBoxLayout(tree_panel)
        layout.setContentsMargins(8, 0, 0, 0)
        filters = QHBoxLayout()
        filters.addWidget(QLabel(self.t("tree.search")))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText(self.t("tree.search_placeholder"))
        self.search_edit.textChanged.connect(self._tree_search_changed)
        filters.addWidget(self.search_edit, 1)
        self.tree_instant_finish_check = QCheckBox(
            self.t("tree.instant_finish_only")
        )
        self.tree_instant_finish_check.setToolTip(
            self.t("tree.instant_finish_hint")
        )
        self.tree_instant_finish_check.toggled.connect(
            self._tree_instant_finish_changed
        )
        filters.addWidget(self.tree_instant_finish_check)
        self.tree_capture_button = QPushButton(self.t("tree.capture_levels"))
        self.tree_capture_button.clicked.connect(self._capture_tree_levels)
        filters.addWidget(self.tree_capture_button)
        self.tree_capture_progress = QProgressBar()
        self.tree_capture_progress.setRange(0, 100)
        self.tree_capture_progress.setValue(0)
        self.tree_capture_progress.setMinimumWidth(110)
        self.tree_capture_progress.setMaximumWidth(170)
        filters.addWidget(self.tree_capture_progress)
        self.tree_fit_button = QPushButton(self.t("tree.fit_all"))
        self.tree_reset_zoom_button = QPushButton(self.t("tree.reset_zoom"))
        filters.addWidget(self.tree_fit_button)
        filters.addWidget(self.tree_reset_zoom_button)
        layout.addLayout(filters)

        self.tree_view = ResearchTreeView(level_editing_enabled=True)
        self.tree_view.researchSelected.connect(self._tree_selection_changed)
        self.tree_view.researchActivated.connect(self._open_tree_detail)
        self.tree_view.researchLevelChanged.connect(self._set_tree_level)
        self.tree_fit_button.clicked.connect(self.tree_view.fit_all)
        self.tree_reset_zoom_button.clicked.connect(self.tree_view.reset_zoom)
        layout.addWidget(self.tree_view, 1)

        splitter.addWidget(tree_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([230, 1000])
        page_layout.addWidget(splitter, 1)

        self.tree_dataset_list.currentRowChanged.connect(
            self._tree_dataset_changed
        )
        preferred = self._dataset_list_row("observation:catalog-economy")
        if preferred >= 0:
            self.tree_dataset_list.setCurrentRow(preferred)
        elif self.observations:
            self.tree_dataset_list.setCurrentRow(0)
        self._tree_dataset_changed()
        self._refresh_tree()
        return page

    def _tree_search_changed(self, text: str) -> None:
        self._tree_filters_changed()

    def _tree_instant_finish_changed(self, _checked: bool) -> None:
        self._tree_filters_changed()

    def _tree_filters_changed(self) -> None:
        query = self.search_edit.text().strip().casefold()
        instant_only = self.tree_instant_finish_check.isChecked()
        current = self.tree_dataset_list.currentItem()
        current_value = (
            str(current.data(Qt.UserRole) or "") if current is not None else ""
        )
        filter_active = bool(query) or instant_only
        if filter_active and not self._tree_dataset_search_active:
            self._tree_dataset_search_restore = current_value
        preferred_value = (
            self._tree_dataset_search_restore
            if not filter_active and self._tree_dataset_search_active
            else current_value
        )
        self._tree_dataset_search_active = filter_active
        self._filter_tree_datasets(query, preferred_value)

    def _filter_tree_datasets(self, query: str, preferred_value: str) -> None:
        self.tree_dataset_list.blockSignals(True)
        self.tree_dataset_list.clear()
        instant_only = self.tree_instant_finish_check.isChecked()
        for observation in self.observations:
            title = observation.localized_title(self.translator.locale)
            if (query or instant_only) and not any(
                self._tree_node_matches_query(node, query)
                and (
                    not instant_only
                    or self._tree_node_is_instant_finish(node)
                )
                for node in observation.nodes
            ):
                continue
            item = QListWidgetItem(title)
            item.setData(
                Qt.UserRole, f"observation:{observation.observation_id}"
            )
            item.setToolTip(
                f"{observation.verification_status}\n{observation.notes}"
            )
            self.tree_dataset_list.addItem(item)
        preferred_row = self._dataset_list_row(preferred_value)
        if preferred_row >= 0:
            self.tree_dataset_list.setCurrentRow(preferred_row)
        elif self.tree_dataset_list.count() > 0:
            self.tree_dataset_list.setCurrentRow(0)
        self.tree_dataset_list.fit_items()
        self.tree_dataset_list.blockSignals(False)
        self._tree_dataset_changed()

    def _tree_node_matches_query(
        self, node: ObservedResearchNode, query: str
    ) -> bool:
        if not query:
            return True
        research = self._research.get(node.id)
        tags = research.tags if research is not None else ()
        search_text = " ".join(
            (node.localized_name(self.translator.locale), node.id, *tags)
        )
        return query in search_text.casefold()

    def _tree_node_is_instant_finish(
        self, node: ObservedResearchNode
    ) -> bool:
        return self._research_is_instant_finish(node.id, node.max_level)

    def _research_is_instant_finish(
        self, research_id: str, max_level: int | None
    ) -> bool:
        if max_level is None or max_level <= 0:
            return False
        current_level = max(0, self._tree_level_draft.get(research_id, 0))
        if current_level >= max_level:
            return False
        free_seconds = free_speedup_seconds_for_vip(
            self.player_state.settings.vip_level
        )
        memo: dict[tuple[str, int], bool] = {}
        visiting: set[tuple[str, int]] = set()

        def can_finish_through(target_id: str, target_level: int) -> bool:
            current = max(0, self._tree_level_draft.get(target_id, 0))
            if current >= target_level:
                return True
            key = (target_id, target_level)
            if key in memo:
                return memo[key]
            if key in visiting:
                return False
            visiting.add(key)
            result = True
            observed = self._observed_nodes.get(target_id)
            if observed is not None:
                if observed.max_level is None or target_level > observed.max_level:
                    result = False
                else:
                    for level_number in range(current + 1, target_level + 1):
                        level_data = observed.level_data(level_number)
                        if (
                            level_data is None
                            or level_data.base_time_seconds is None
                            or level_data.base_time_seconds <= 0
                            or (
                                level_data.academy_level is not None
                                and level_data.academy_level
                                > self.player_state.settings.academy_level
                            )
                        ):
                            result = False
                            break
                        if any(
                            not can_finish_through(
                                requirement.research_id, requirement.level
                            )
                            for requirement in level_data.requirements
                        ):
                            result = False
                            break
                        adjusted_seconds = apply_research_speed(
                            level_data.base_time_seconds,
                            self.player_state.settings.effective_research_speed_percent,
                        )
                        if adjusted_seconds > free_seconds:
                            result = False
                            break
            else:
                research = self._research.get(target_id)
                if research is None or target_level > research.max_level:
                    result = False
                else:
                    for level_number in range(current + 1, target_level + 1):
                        try:
                            level_data = self.master.level(target_id, level_number)
                        except KeyError:
                            result = False
                            break
                        if (
                            level_data.academy_level
                            > self.player_state.settings.academy_level
                            or apply_research_speed(
                                level_data.base_time_seconds,
                                self.player_state.settings.effective_research_speed_percent,
                            )
                            > free_seconds
                        ):
                            result = False
                            break
                        requirements = (
                            requirement
                            for requirement in self.master.prerequisites
                            if requirement.research_id == target_id
                            and requirement.target_level <= level_number
                            and requirement.prerequisite_research_id
                        )
                        if any(
                            not can_finish_through(
                                str(requirement.prerequisite_research_id),
                                requirement.prerequisite_level,
                            )
                            for requirement in requirements
                        ):
                            result = False
                            break
            visiting.remove(key)
            memo[key] = result
            return result

        return can_finish_through(research_id, current_level + 1)

    def _refresh_tree_filter_results(self) -> None:
        if not hasattr(self, "tree_instant_finish_check"):
            return
        current = self.tree_dataset_list.currentItem()
        current_value = (
            str(current.data(Qt.UserRole) or "") if current is not None else ""
        )
        self._filter_tree_datasets(
            self.search_edit.text().strip().casefold(), current_value
        )

    def _dataset_list_row(self, value: str) -> int:
        if not hasattr(self, "tree_dataset_list"):
            return -1
        for row in range(self.tree_dataset_list.count()):
            item = self.tree_dataset_list.item(row)
            if item is not None and str(item.data(Qt.UserRole) or "") == value:
                return row
        return -1

    def _active_observation(self) -> ResearchTreeObservation | None:
        if not hasattr(self, "tree_dataset_list"):
            return None
        selected = self.tree_dataset_list.currentItem()
        value = str(selected.data(Qt.UserRole) or "") if selected else ""
        if not value.startswith("observation:"):
            return None
        return self._observation_by_id.get(value.split(":", 1)[1])

    def _tree_dataset_changed(self, *_args: object) -> None:
        observation = self._active_observation()
        if observation and observation.nodes:
            visible_ids = {node.id for node in observation.nodes}
            if self._selected_tree_node_id not in visible_ids:
                self._selected_tree_node_id = observation.nodes[0].id
        elif observation:
            self._selected_tree_node_id = ""
        else:
            self._selected_tree_node_id = self._selected_research_id
        self._refresh_tree()

    def _observed_connection_unlocked(self, node: ObservedResearchNode) -> bool:
        if self._tree_level_draft.get(node.id, 0) > 0:
            return True
        level_one = node.level_data(1)
        if level_one is None:
            return False
        return all(
            self._tree_level_draft.get(requirement.research_id, 0)
            >= requirement.level
            for requirement in level_one.requirements
        )

    def _master_connection_unlocked(self, research_id: str) -> bool:
        if self._tree_level_draft.get(research_id, 0) > 0:
            return True
        requirements = (
            item
            for item in self.master.prerequisites
            if item.research_id == research_id
            and item.target_level <= 1
            and item.prerequisite_research_id
        )
        return all(
            self._tree_level_draft.get(str(item.prerequisite_research_id), 0)
            >= item.prerequisite_level
            for item in requirements
        )

    def _refresh_tree(self) -> None:
        if not hasattr(self, "tree_view"):
            return
        observation = self._active_observation()
        if observation is not None:
            query = self.search_edit.text().strip().casefold()
            instant_only = self.tree_instant_finish_check.isChecked()
            visible = []
            for node in sorted(
                observation.nodes, key=lambda item: (item.row, item.column)
            ):
                name = node.localized_name(self.translator.locale)
                if not self._tree_node_matches_query(node, query):
                    continue
                if instant_only and not self._tree_node_is_instant_finish(node):
                    continue
                current = self._tree_level_draft.get(node.id, 0)
                if current <= 0:
                    status = self.t("status.not_started")
                elif node.max_level is not None and current >= node.max_level:
                    status = self.t("status.complete")
                else:
                    status = self.t("status.in_progress")
                current_effect, next_effect = self._observed_tree_effect_lines(
                    node, current
                )
                visible.append(
                    ResearchTreeNode(
                        research_id=node.id,
                        name=name,
                        current_level=current,
                        max_level=node.max_level,
                        status=status,
                        recommendation=observation.verification_status,
                        display_order=node.row * 10_000 + node.column,
                        current_effect=current_effect,
                        next_effect=next_effect,
                        layout_row=node.row,
                        layout_column=node.column,
                    )
                )
            visible_ids = {node.research_id for node in visible}
            edges = {
                (edge.prerequisite_id, edge.research_id)
                for edge in observation.edges
                if edge.prerequisite_id in visible_ids
                and edge.research_id in visible_ids
            }
            node_by_id = observation.node_by_id()
            active_edges = {
                edge
                for edge in edges
                if self._observed_connection_unlocked(node_by_id[edge[1]])
            }
            self.tree_view.set_research(
                visible,
                edges,
                self._selected_tree_node_id,
                self.t("tree.empty_dataset"),
                connection_groups=(
                    (group.prerequisite_ids, group.research_ids)
                    for group in observation.connection_groups
                ),
                active_edges=active_edges,
            )
            return
        if self.observations and self.tree_dataset_list.count() == 0:
            self.tree_view.set_research(
                [],
                set(),
                "",
                self.t("tree.empty_dataset"),
            )
            return
        category = self.category_combo.currentData() if hasattr(self, "category_combo") else ""
        tag = self.tag_combo.currentData() if hasattr(self, "tag_combo") else ""
        query = self.search_edit.text().strip().casefold() if hasattr(self, "search_edit") else ""
        instant_only = (
            self.tree_instant_finish_check.isChecked()
            if hasattr(self, "tree_instant_finish_check")
            else False
        )
        visible: list[ResearchTreeNode] = []
        category_order = {
            item.id: item.display_order for item in self.master.categories
        }
        for research in sorted(
            self.master.research,
            key=lambda item: (item.category_id, item.display_order),
        ):
            localized = self.master.localized_research(research.id, self.translator.locale)
            haystack = " ".join((localized.name, research.id, *research.tags)).casefold()
            if category and research.category_id != category:
                continue
            if tag and tag not in research.tags:
                continue
            if query and query not in haystack:
                continue
            if instant_only and not self._research_is_instant_finish(
                research.id, research.max_level
            ):
                continue
            current = self._tree_level_draft.get(research.id, 0)
            if current <= 0:
                status = self.t("status.not_started")
            elif current >= research.max_level:
                status = self.t("status.complete")
            else:
                status = self.t("status.in_progress")
            current_effect, next_effect = self._tree_effect_lines(
                research.id, current, research.max_level
            )
            visible.append(
                ResearchTreeNode(
                    research_id=research.id,
                    name=localized.name,
                    current_level=current,
                    max_level=research.max_level,
                    status=status,
                    recommendation=self.t(
                        f"recommendation.{research.recommendation}"
                    ),
                    display_order=(
                        category_order.get(research.category_id, 0) * 100_000
                        + research.display_order
                    ),
                    current_effect=current_effect,
                    next_effect=next_effect,
                )
            )
        visible_ids = {node.research_id for node in visible}
        edges = {
            (item.prerequisite_research_id, item.research_id)
            for item in self.master.prerequisites
            if item.prerequisite_research_id in visible_ids
            and item.research_id in visible_ids
        }
        active_edges = {
            edge
            for edge in edges
            if self._master_connection_unlocked(edge[1])
        }
        self.tree_view.set_research(
            visible,
            edges,
            self._selected_tree_node_id,
            active_edges=active_edges,
        )

    def _tree_selection_changed(self, research_id: str) -> None:
        self._selected_tree_node_id = research_id
        if research_id in self._research:
            self._selected_research_id = research_id
            self._select_combo_data(
                getattr(self, "detail_research_combo", None), research_id
            )

    def _open_tree_detail(self, research_id: str) -> None:
        if research_id in self._observed_nodes:
            self._tree_selection_changed(research_id)
            self._set_plan_target(research_id)
            self.tabs.setCurrentIndex(1)
            return
        self._selected_research_id = research_id
        self.tabs.setCurrentIndex(1)
        self._select_combo_data(self.detail_research_combo, research_id)

    def _set_tree_level(self, research_id: str, level: int) -> None:
        if research_id not in self._observed_nodes:
            return
        node = self._observed_nodes[research_id]
        maximum = node.max_level if node.max_level is not None else 99
        self._selected_tree_node_id = research_id
        self._tree_level_draft[research_id] = max(0, min(int(level), maximum))
        self._tree_levels_dirty = True
        self._update_player_save_button()
        self._refresh_tree_after_level_change(preserve_view=True)
        self._sync_progress_editor(research_id)
        self._calculate_plan()

    def _refresh_tree_preserving_view(self) -> None:
        if not hasattr(self, "tree_view"):
            return
        viewport_center = self.tree_view.viewport().rect().center()
        scene_center = self.tree_view.mapToScene(viewport_center)
        self._refresh_tree()
        self.tree_view.centerOn(scene_center)

    def _refresh_tree_after_level_change(
        self, *, preserve_view: bool = False
    ) -> None:
        if (
            hasattr(self, "tree_instant_finish_check")
            and self.tree_instant_finish_check.isChecked()
        ):
            self._refresh_tree_filter_results()
        elif preserve_view:
            self._refresh_tree_preserving_view()
        else:
            self._refresh_tree()

    def _clear_tree_levels(self) -> None:
        changed_ids = set(self._tree_level_draft) | set(
            self.player_state.research_levels
        )
        self._tree_level_draft.clear()
        self._tree_levels_dirty = True
        self._update_player_save_button()
        for research_id in changed_ids:
            self._sync_progress_editor(research_id)
        self._refresh_tree_after_level_change(preserve_view=True)
        self._refresh_detail()
        self._calculate_plan()

    def _save_tree_levels(self) -> None:
        self._save_player()

    def _commit_tree_level_draft(self) -> set[str]:
        changed_ids = set(self.player_state.research_levels) | set(
            self._tree_level_draft
        )
        self.player_state.research_levels.clear()
        self.player_state.research_levels.update(self._tree_level_draft)
        self._tree_levels_dirty = False
        self._update_player_save_button()
        return changed_ids

    def _capture_tree_levels(self) -> None:
        observation = self._active_observation()
        if observation is None or not observation.nodes:
            self._show_info(self.t("tree.capture_no_tree"))
            return
        self._ocr_candidates = []
        self.tree_capture_button.setEnabled(False)
        QApplication.processEvents()
        try:
            self._run_ocr(force_window_capture=True)
        finally:
            self.tree_capture_button.setEnabled(True)
        active_ids = {node.id for node in observation.nodes}
        candidates_by_id = {
            candidate.research_id: candidate
            for candidate in self._ocr_candidates
            if candidate.research_id in active_ids and candidate.level > 0
        }
        if not candidates_by_id:
            self._show_info(self.t("tree.capture_no_levels"))
            return
        for candidate in candidates_by_id.values():
            self._tree_level_draft[candidate.research_id] = candidate.level
        self._tree_levels_dirty = True
        self._update_player_save_button()
        self._refresh_tree_after_level_change(preserve_view=True)
        for candidate in candidates_by_id.values():
            self._sync_progress_editor(candidate.research_id)
        self._calculate_plan()

    def _build_detail_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        selector = QHBoxLayout()
        selector.addWidget(QLabel(self.t("detail.research")))
        self.detail_research_combo = self._research_combo()
        self._select_combo_data(self.detail_research_combo, self._selected_research_id)
        self.detail_research_combo.currentIndexChanged.connect(self._refresh_detail)
        selector.addWidget(self.detail_research_combo, 1)
        layout.addLayout(selector)

        self.detail_description = QLabel()
        self.detail_description.setWordWrap(True)
        layout.addWidget(self.detail_description)
        form = QFormLayout()
        self.detail_values: dict[str, QLabel] = {}
        for key in (
            "current_level",
            "next_level",
            "effect",
            "base_time",
            "adjusted_time",
            "after_help",
            "resources",
            "power",
            "prerequisites",
            "source",
            "verification",
        ):
            value = QLabel()
            value.setWordWrap(True)
            self.detail_values[key] = value
            form.addRow(self.t(f"detail.{key}"), value)
        layout.addLayout(form)
        layout.addStretch(1)
        self._refresh_detail()
        return page

    def _refresh_detail(self) -> None:
        if not hasattr(self, "detail_research_combo"):
            return
        research_id = self.detail_research_combo.currentData()
        if not research_id:
            return
        self._selected_research_id = str(research_id)
        research = self._research[self._selected_research_id]
        localized = self.master.localized_research(research.id, self.translator.locale)
        current = self._tree_level_draft.get(research.id, 0)
        self.detail_description.setText(
            f"{localized.description}\n{localized.recommendation_reason}"
        )
        self.detail_values["current_level"].setText(f"{current} / {research.max_level}")
        if current >= research.max_level:
            for key in (
                "next_level",
                "effect",
                "base_time",
                "adjusted_time",
                "after_help",
                "resources",
                "power",
                "prerequisites",
                "source",
                "verification",
            ):
                self.detail_values[key].setText(self.t("detail.maximum"))
            return
        next_level = current + 1
        level = self.master.level(research.id, next_level)
        adjusted = apply_research_speed(
            level.base_time_seconds,
            self.player_state.settings.effective_research_speed_percent,
        )
        adjusted = apply_free_speedup_time(
            adjusted,
            free_speedup_seconds_for_vip(
                self.player_state.settings.vip_level
            ),
        )
        after_help = apply_guild_helps(adjusted, self.player_state.settings.max_guild_helps)
        resources = ", ".join(
            f"{self._resource_label(key)} {level.resources.get(key, 0):,}"
            for key in RESOURCE_KEYS
            if level.resources.get(key, 0)
        )
        prerequisites = []
        for item in self.master.prerequisites:
            if item.research_id != research.id or item.target_level > next_level:
                continue
            if item.prerequisite_research_id:
                name = self.master.localized_research(
                    item.prerequisite_research_id, self.translator.locale
                ).name
                prerequisites.append(f"{name} Lv.{item.prerequisite_level}")
            if item.building:
                prerequisites.append(f"{item.building} Lv.{item.building_level}")
        self.detail_values["next_level"].setText(str(next_level))
        self.detail_values["effect"].setText(
            f"{localized.effect_label} +{level.effect_value:g} "
            f"(total {level.cumulative_effect:g})"
        )
        self.detail_values["base_time"].setText(format_duration(level.base_time_seconds))
        self.detail_values["adjusted_time"].setText(
            f"{format_duration(adjusted)} ({self.t('common.estimated')})"
        )
        self.detail_values["after_help"].setText(
            f"{format_duration(after_help)} ({self.t('common.estimated')})"
        )
        self.detail_values["resources"].setText(resources or "-")
        self.detail_values["power"].setText(f"{level.power:,}")
        self.detail_values["prerequisites"].setText(", ".join(prerequisites) or "-")
        self.detail_values["source"].setText(
            f"{level.source} / {level.checked_on} / {level.game_version}"
        )
        self.detail_values["verification"].setText(level.verification_status)

    def _build_castle_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.t("castle.current_level")))
        self.castle_plan_current_spin = self._integer_spin(
            1, 25, self.player_state.settings.castle_level
        )
        controls.addWidget(self.castle_plan_current_spin)
        controls.addWidget(QLabel(self.t("castle.mana_stage")))
        self.castle_plan_current_mana_spin = self._integer_spin(
            0,
            self.castle_catalog.max_mana_stage,
            self.player_state.settings.castle_mana_stage,
        )
        controls.addWidget(self.castle_plan_current_mana_spin)
        controls.addSpacing(16)
        controls.addWidget(QLabel(self.t("castle.target_level")))
        self.castle_plan_target_spin = self._integer_spin(
            1,
            25,
            max(
                self.player_state.settings.castle_level,
                min(
                    25,
                    self.player_state.settings.castle_target_level
                    or self.player_state.settings.castle_level + 1,
                ),
            ),
        )
        self.player_state.settings.castle_target_level = (
            self.castle_plan_target_spin.value()
        )
        controls.addWidget(self.castle_plan_target_spin)
        controls.addWidget(QLabel(self.t("castle.target_mana_stage")))
        initial_target_mana = self.player_state.settings.castle_target_mana_stage
        if (
            self.player_state.settings.castle_level == 25
            and self.castle_plan_target_spin.value() == 25
            and initial_target_mana <= self.player_state.settings.castle_mana_stage
        ):
            initial_target_mana = min(
                self.castle_catalog.max_mana_stage,
                self.player_state.settings.castle_mana_stage + 1,
            )
        self.castle_plan_target_mana_spin = self._integer_spin(
            0,
            self.castle_catalog.max_mana_stage,
            initial_target_mana,
        )
        self.player_state.settings.castle_target_mana_stage = initial_target_mana
        controls.addWidget(self.castle_plan_target_mana_spin)
        controls.addStretch(1)
        self.castle_plan_speed_label = QLabel()
        controls.addWidget(self.castle_plan_speed_label)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        levels_panel = QWidget()
        levels_layout = QVBoxLayout(levels_panel)
        levels_layout.setContentsMargins(0, 0, 6, 0)
        levels_heading = QLabel(self.t("castle.facility_levels"))
        levels_heading.setStyleSheet("font-weight:700;font-size:15px;")
        levels_layout.addWidget(levels_heading)
        hint = QLabel(self.t("castle.facility_levels_hint"))
        hint.setWordWrap(True)
        levels_layout.addWidget(hint)

        facility_ids = [
            building_id
            for building_id in self.castle_catalog.buildings
            if building_id != "castle"
        ]
        self.castle_level_table = QTableWidget(len(facility_ids), 3)
        self.castle_level_table.setHorizontalHeaderLabels(
            [
                self.t("castle.facility"),
                self.t("castle.current"),
                self.t("castle.required"),
            ]
        )
        self.castle_level_table.verticalHeader().setVisible(False)
        level_header = self.castle_level_table.horizontalHeader()
        level_header.setSectionResizeMode(0, QHeaderView.Stretch)
        level_header.setSectionResizeMode(1, QHeaderView.Fixed)
        level_header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.castle_level_table.setColumnWidth(1, 92)
        self.castle_level_table.setColumnWidth(2, 72)
        self._building_level_spins: dict[str, QSpinBox] = {}
        self._building_required_items: dict[str, QTableWidgetItem] = {}
        minimums = self.castle_catalog.minimum_levels_for_castle(
            self.player_state.settings.castle_level
        )
        for row, building_id in enumerate(facility_ids):
            building = self.castle_catalog.buildings[building_id]
            name_item = QTableWidgetItem(
                building.localized_name(self.translator.locale)
            )
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.castle_level_table.setItem(row, 0, name_item)
            value = max(
                minimums.get(building_id, 0),
                self._building_level_draft.get(building_id, 0),
            )
            spin = self._integer_spin(
                minimums.get(building_id, 0), building.max_level, value
            )
            spin.valueChanged.connect(
                lambda changed, selected_id=building_id: self._building_level_changed(
                    selected_id, changed
                )
            )
            self._building_level_spins[building_id] = spin
            self.castle_level_table.setCellWidget(row, 1, spin)
            required_item = QTableWidgetItem(str(value))
            required_item.setTextAlignment(Qt.AlignCenter)
            required_item.setFlags(required_item.flags() & ~Qt.ItemIsEditable)
            self._building_required_items[building_id] = required_item
            self.castle_level_table.setItem(row, 2, required_item)
        levels_layout.addWidget(self.castle_level_table, 1)
        splitter.addWidget(levels_panel)

        plan_panel = QWidget()
        plan_layout = QVBoxLayout(plan_panel)
        plan_layout.setContentsMargins(6, 0, 0, 0)
        plan_heading = QLabel(self.t("castle.plan"))
        plan_heading.setStyleSheet("font-weight:700;font-size:15px;")
        plan_layout.addWidget(plan_heading)
        self.castle_plan_summary_label = QLabel()
        self.castle_plan_summary_label.setWordWrap(True)
        plan_layout.addWidget(self.castle_plan_summary_label)
        self.castle_plan_table = QTableWidget(
            0, 3 + len(CASTLE_RESOURCE_KEYS) + 1
        )
        self.castle_plan_table.setHorizontalHeaderLabels(
            [
                self.t("castle.facility"),
                self.t("castle.level_range"),
                self.t("castle.adjusted_time"),
                *(self._resource_label(key) for key in CASTLE_RESOURCE_KEYS),
                self.t("plan.action"),
            ]
        )
        self.castle_plan_table.verticalHeader().setVisible(False)
        plan_header = self.castle_plan_table.horizontalHeader()
        plan_header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, self.castle_plan_table.columnCount()):
            plan_header.setSectionResizeMode(column, QHeaderView.ResizeToContents)
        plan_layout.addWidget(self.castle_plan_table, 1)
        splitter.addWidget(plan_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([360, 760])
        layout.addWidget(splitter, 1)

        self.castle_plan_current_spin.valueChanged.connect(
            self._castle_current_level_changed
        )
        self.castle_plan_target_spin.valueChanged.connect(
            self._castle_target_level_changed
        )
        self.castle_plan_current_mana_spin.valueChanged.connect(
            self._castle_current_mana_stage_changed
        )
        self.castle_plan_target_mana_spin.valueChanged.connect(
            self._castle_target_mana_stage_changed
        )
        self._sync_castle_mana_controls()
        self._calculate_castle_plan()
        return page

    def _castle_current_level_changed(self, value: int) -> None:
        normalized = max(1, min(25, int(value)))
        self.player_state.settings.castle_level = normalized
        if hasattr(self, "castle_spin") and self.castle_spin.value() != normalized:
            self.castle_spin.blockSignals(True)
            self.castle_spin.setValue(normalized)
            self.castle_spin.blockSignals(False)
        if self.castle_plan_target_spin.value() <= normalized:
            self.castle_plan_target_spin.setValue(min(25, normalized + 1))
        self.player_state.settings.castle_target_level = (
            self.castle_plan_target_spin.value()
        )
        if (
            normalized == 25
            and self.castle_plan_target_spin.value() == 25
            and self.castle_plan_target_mana_spin.value()
            <= self.castle_plan_current_mana_spin.value()
            and self.castle_plan_current_mana_spin.value()
            < self.castle_catalog.max_mana_stage
        ):
            self.castle_plan_target_mana_spin.setValue(
                self.castle_plan_current_mana_spin.value() + 1
            )
        self._sync_castle_mana_controls()
        self._refresh_castle_level_inputs()
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._calculate_castle_plan()

    def _castle_target_level_changed(self, value: int) -> None:
        self.player_state.settings.castle_target_level = max(
            self.castle_plan_current_spin.value(),
            min(25, int(value)),
        )
        self._sync_castle_mana_controls()
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._calculate_castle_plan()

    def _sync_castle_mana_controls(self) -> None:
        if not hasattr(self, "castle_plan_current_mana_spin"):
            return
        current_enabled = self.castle_plan_current_spin.value() == 25
        target_enabled = self.castle_plan_target_spin.value() == 25
        current_stage = (
            self.castle_plan_current_mana_spin.value() if current_enabled else 0
        )
        if not current_enabled:
            self.castle_plan_current_mana_spin.blockSignals(True)
            self.castle_plan_current_mana_spin.setValue(0)
            self.castle_plan_current_mana_spin.blockSignals(False)
        minimum_target = current_stage if current_enabled and target_enabled else 0
        self.castle_plan_target_mana_spin.blockSignals(True)
        self.castle_plan_target_mana_spin.setMinimum(minimum_target)
        if not target_enabled:
            self.castle_plan_target_mana_spin.setValue(0)
        elif self.castle_plan_target_mana_spin.value() < minimum_target:
            self.castle_plan_target_mana_spin.setValue(minimum_target)
        self.castle_plan_target_mana_spin.blockSignals(False)
        self.castle_plan_current_mana_spin.setEnabled(current_enabled)
        self.castle_plan_target_mana_spin.setEnabled(target_enabled)
        self.player_state.settings.castle_mana_stage = current_stage
        self.player_state.settings.castle_target_mana_stage = (
            self.castle_plan_target_mana_spin.value() if target_enabled else 0
        )
        if hasattr(self, "castle_mana_stage_spin"):
            self.castle_mana_stage_spin.blockSignals(True)
            self.castle_mana_stage_spin.setEnabled(current_enabled)
            self.castle_mana_stage_spin.setValue(current_stage)
            self.castle_mana_stage_spin.blockSignals(False)

    def _castle_current_mana_stage_changed(self, value: int) -> None:
        normalized = (
            max(0, min(self.castle_catalog.max_mana_stage, int(value)))
            if self.castle_plan_current_spin.value() == 25
            else 0
        )
        self.player_state.settings.castle_mana_stage = normalized
        if (
            self.castle_plan_target_spin.value() == 25
            and self.castle_plan_target_mana_spin.value() <= normalized
            and normalized < self.castle_catalog.max_mana_stage
        ):
            self.castle_plan_target_mana_spin.setValue(normalized + 1)
        self._sync_castle_mana_controls()
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._calculate_castle_plan()

    def _castle_target_mana_stage_changed(self, value: int) -> None:
        minimum = (
            self.castle_plan_current_mana_spin.value()
            if self.castle_plan_current_spin.value() == 25
            else 0
        )
        self.player_state.settings.castle_target_mana_stage = (
            max(minimum, min(self.castle_catalog.max_mana_stage, int(value)))
            if self.castle_plan_target_spin.value() == 25
            else 0
        )
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._calculate_castle_plan()

    def _refresh_castle_level_inputs(self) -> None:
        if not hasattr(self, "_building_level_spins"):
            return
        minimums = self.castle_catalog.minimum_levels_for_castle(
            self.player_state.settings.castle_level
        )
        for building_id, spin in self._building_level_spins.items():
            minimum = minimums.get(building_id, 0)
            spin.blockSignals(True)
            spin.setMinimum(minimum)
            spin.setValue(
                max(minimum, self._building_level_draft.get(building_id, 0))
            )
            spin.blockSignals(False)
            self._building_level_draft[building_id] = spin.value()

    def _building_level_changed(self, building_id: str, value: int) -> None:
        self._building_level_draft[building_id] = max(0, int(value))
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._calculate_castle_plan()

    def _calculate_castle_plan(self, *_args: object) -> None:
        if not hasattr(self, "castle_plan_table"):
            return
        result = self.castle_catalog.create_plan(
            castle_level=self.castle_plan_current_spin.value(),
            target_castle_level=self.castle_plan_target_spin.value(),
            current_mana_stage=self.castle_plan_current_mana_spin.value(),
            target_mana_stage=self.castle_plan_target_mana_spin.value(),
            saved_levels=self._building_level_draft,
            construction_speed_percent=(
                self.player_state.settings.effective_construction_speed_percent
            ),
            vip_level=self.player_state.settings.vip_level,
            guild_helps=self.player_state.settings.max_guild_helps,
        )
        self._current_castle_plan = result
        self.castle_plan_speed_label.setText(
            self.t("player.effective_construction_speed")
            + ": "
            + f"{self.player_state.settings.effective_construction_speed_percent:g}%"
        )
        for building_id, item in self._building_required_items.items():
            item.setText(str(result.effective_levels.get(building_id, 0)))
        for summary in result.buildings:
            item = self._building_required_items.get(summary.building_id)
            if item is not None:
                item.setText(str(summary.target_level))

        if not result.steps:
            self.castle_plan_summary_label.setText(self.t("castle.no_work"))
        else:
            resource_summary = " / ".join(
                f"{self._resource_label(key)} "
                f"{format_resource_amount(result.total_costs[key], self.player_state.settings.resource_display_mode)}"
                for key in CASTLE_RESOURCE_KEYS
                if result.total_costs[key] > 0
            )
            self.castle_plan_summary_label.setText(
                f"{self.t('castle.total')}: "
                f"{format_duration(result.total_adjusted_seconds)}  |  "
                f"{resource_summary}"
            )

        self.castle_plan_table.setRowCount(
            len(result.steps) + (1 if result.steps else 0)
        )
        for row, step in enumerate(result.steps):
            building = self.castle_catalog.buildings[step.building_id]
            building_name = (
                self.t("castle.mana_upgrade")
                if step.mana_stage > 0
                else building.localized_name(self.translator.locale)
            )
            values = [
                building_name,
                self._castle_progress_text(step.level, step.mana_stage),
                format_duration(step.adjusted_seconds),
                *(
                    format_resource_amount(
                        step.costs[key],
                        self.player_state.settings.resource_display_mode,
                    )
                    for key in CASTLE_RESOURCE_KEYS
                ),
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if column >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                if column == 2:
                    item.setToolTip(
                        f"{self.t('castle.base_time')}: "
                        f"{format_duration(step.base_seconds)}"
                    )
                self.castle_plan_table.setItem(row, column, item)
            complete_button = QPushButton(self.t("plan.complete_step"))
            complete_button.clicked.connect(
                lambda _checked=False, saved=step: self._complete_castle_plan_step(
                    saved
                )
            )
            self.castle_plan_table.setCellWidget(
                row,
                self.castle_plan_table.columnCount() - 1,
                complete_button,
            )
        if result.steps:
            row = len(result.steps)
            total_values = [
                self.t("castle.total"),
                "",
                format_duration(result.total_adjusted_seconds),
                *(
                    format_resource_amount(
                        result.total_costs[key],
                        self.player_state.settings.resource_display_mode,
                    )
                    for key in CASTLE_RESOURCE_KEYS
                ),
            ]
            for column, value in enumerate(total_values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                if column >= 1:
                    item.setTextAlignment(Qt.AlignCenter)
                self.castle_plan_table.setItem(row, column, item)

    def _complete_castle_plan_step(self, step: CastlePlanStep) -> None:
        result = getattr(self, "_current_castle_plan", None)
        if result is None or step not in result.steps:
            return
        step_index = result.steps.index(step)
        for completed in result.steps[: step_index + 1]:
            if completed.building_id == "castle":
                self.player_state.settings.castle_level = max(
                    self.player_state.settings.castle_level,
                    completed.level,
                )
                if completed.mana_stage > 0:
                    self.player_state.settings.castle_mana_stage = max(
                        self.player_state.settings.castle_mana_stage,
                        completed.mana_stage,
                    )
            else:
                self._building_level_draft[completed.building_id] = max(
                    self._building_level_draft.get(completed.building_id, 0),
                    completed.level,
                )
        castle_level = self.player_state.settings.castle_level
        for spin in (self.castle_plan_current_spin, self.castle_spin):
            spin.blockSignals(True)
            spin.setValue(castle_level)
            spin.blockSignals(False)
        for spin in (
            self.castle_plan_current_mana_spin,
            self.castle_mana_stage_spin,
        ):
            spin.blockSignals(True)
            spin.setValue(self.player_state.settings.castle_mana_stage)
            spin.blockSignals(False)
        self._sync_castle_mana_controls()
        self._refresh_castle_level_inputs()
        self._player_settings_dirty = True
        self._save_player()

    @staticmethod
    def _castle_progress_text(level: int, mana_stage: int = 0) -> str:
        suffix = f"-{mana_stage}" if level >= 25 and mana_stage > 0 else ""
        return f"Lv.{level}{suffix}"

    def _build_player_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Horizontal)

        settings_panel = QWidget()
        settings_form = QFormLayout(settings_panel)
        self.player_settings_form = settings_form
        self.vip_level_spin = self._integer_spin(
            1, 15, self.player_state.settings.vip_level
        )
        vip_row = QWidget()
        vip_layout = QHBoxLayout(vip_row)
        vip_layout.setContentsMargins(0, 0, 0, 0)
        vip_layout.addWidget(self.vip_level_spin)
        self.vip_free_speedup_label = QLabel()
        vip_layout.addWidget(self.vip_free_speedup_label, 1)
        self.castle_spin = self._integer_spin(1, 25, self.player_state.settings.castle_level)
        self.castle_mana_stage_spin = self._integer_spin(
            0,
            self.castle_catalog.max_mana_stage,
            self.player_state.settings.castle_mana_stage,
        )
        self.castle_mana_stage_spin.setEnabled(
            self.player_state.settings.castle_level == 25
        )
        self.academy_spin = self._integer_spin(1, 25, self.player_state.settings.academy_level)
        self.construction_speed_spin = QDoubleSpinBox()
        self.construction_speed_spin.setRange(0.0, 10000.0)
        self.construction_speed_spin.setDecimals(2)
        self.construction_speed_spin.setValue(
            self.player_state.settings.construction_speed_percent
        )
        self.construction_speed_boost_spin = QDoubleSpinBox()
        self.construction_speed_boost_spin.setRange(0.0, 10000.0)
        self.construction_speed_boost_spin.setDecimals(2)
        self.construction_speed_boost_spin.setValue(
            self.player_state.settings.construction_speed_boost_percent
        )
        self.construction_speed_boost_spin.setToolTip(
            self.t("player.construction_speed_boost_hint")
        )
        self.research_speed_spin = QDoubleSpinBox()
        self.research_speed_spin.setRange(0.0, 10000.0)
        self.research_speed_spin.setDecimals(2)
        self.research_speed_spin.setValue(self.player_state.settings.research_speed_percent)
        self.research_speed_boost_spin = QDoubleSpinBox()
        self.research_speed_boost_spin.setRange(0.0, 10000.0)
        self.research_speed_boost_spin.setDecimals(2)
        self.research_speed_boost_spin.setValue(
            self.player_state.settings.research_speed_boost_percent
        )
        self.research_speed_boost_spin.setToolTip(
            self.t("player.research_speed_boost_hint")
        )
        self.guild_help_spin = self._integer_spin(0, 1000, self.player_state.settings.max_guild_helps)
        self.speedup_spin = self._integer_spin(0, 2_000_000_000, self.player_state.settings.speedup_seconds)
        common_group = QGroupBox(self.t("player.common_settings"))
        common_form = QFormLayout(common_group)
        self.player_settings_form = common_form
        common_form.addRow(self.t("player.vip_level"), vip_row)
        common_form.addRow(self.t("player.castle_level"), self.castle_spin)
        common_form.addRow(
            self.t("player.castle_mana_stage"), self.castle_mana_stage_spin
        )
        common_form.addRow(self.t("player.academy_level"), self.academy_spin)
        common_form.addRow(self.t("player.guild_helps"), self.guild_help_spin)
        common_form.addRow(self.t("player.speedups"), self.speedup_spin)
        settings_form.addRow(common_group)

        construction_group = QGroupBox(self.t("player.construction_time_settings"))
        construction_form = QFormLayout(construction_group)
        construction_form.addRow(
            self.t("player.construction_speed"), self.construction_speed_spin
        )
        construction_form.addRow(
            self.t("player.construction_speed_boost"),
            self.construction_speed_boost_spin,
        )
        settings_form.addRow(construction_group)

        research_group = QGroupBox(self.t("player.research_time_settings"))
        research_form = QFormLayout(research_group)
        research_form.addRow(self.t("player.research_speed"), self.research_speed_spin)
        research_form.addRow(
            self.t("player.research_speed_boost"),
            self.research_speed_boost_spin,
        )
        settings_form.addRow(research_group)

        resources_group = QGroupBox(self.t("player.resources"))
        resources_form = QFormLayout(resources_group)
        self.resource_spins: dict[str, QSpinBox] = {}
        for key in RESOURCE_KEYS:
            spin = self._integer_spin(
                0, 2_000_000_000, self.player_state.settings.resources.get(key, 0)
            )
            self.resource_spins[key] = spin
            resources_form.addRow(self._resource_label(key), spin)
        settings_form.addRow(resources_group)
        splitter.addWidget(settings_panel)

        progress_panel = QWidget()
        progress_layout = QVBoxLayout(progress_panel)
        progress_layout.addWidget(QLabel(self.t("player.progress")))
        progress_entries: list[tuple[str, str, int | None, bool]] = []
        for research in self.master.research:
            progress_entries.append(
                (
                    research.id,
                    self.master.localized_research(
                        research.id, self.translator.locale
                    ).name,
                    research.max_level,
                    False,
                )
            )
        seen_progress_ids = {item.id for item in self.master.research}
        for observation in self.observations:
            for node in observation.nodes:
                if node.id in seen_progress_ids:
                    continue
                seen_progress_ids.add(node.id)
                progress_entries.append(
                    (
                        node.id,
                        node.localized_name(self.translator.locale),
                        node.max_level,
                        True,
                    )
                )

        self._progress_editors: dict[str, QSpinBox] = {}
        self._progress_maximum_items: dict[str, QTableWidgetItem] = {}
        self.progress_table = QTableWidget(len(progress_entries), 3)
        self.progress_table.setHorizontalHeaderLabels(
            [
                self.t("tree.name"),
                self.t("player.current_level"),
                self.t("player.maximum_level"),
            ]
        )
        self.progress_table.verticalHeader().setVisible(False)
        progress_header = self.progress_table.horizontalHeader()
        progress_header.setSectionResizeMode(0, QHeaderView.Stretch)
        progress_header.setSectionResizeMode(1, QHeaderView.Fixed)
        progress_header.setSectionResizeMode(2, QHeaderView.Fixed)
        self.progress_table.setColumnWidth(1, 100)
        self.progress_table.setColumnWidth(2, 72)
        for row, (research_id, name, max_level, observed) in enumerate(progress_entries):
            display_name = (
                f"{name} [{self.t('tree.observed')}]" if observed else name
            )
            self.progress_table.setItem(row, 0, QTableWidgetItem(display_name))
            editor = self._integer_spin(
                0,
                max_level if max_level is not None else 99,
                self._tree_level_draft.get(research_id, 0),
            )
            editor.setAccelerated(True)
            editor.valueChanged.connect(
                lambda value, selected_id=research_id: self._progress_changed(
                    selected_id, value
                )
            )
            self._progress_editors[research_id] = editor
            self.progress_table.setCellWidget(row, 1, editor)
            maximum_item = QTableWidgetItem(
                str(max_level) if max_level is not None else "?"
            )
            maximum_item.setTextAlignment(Qt.AlignCenter)
            maximum_item.setFlags(maximum_item.flags() & ~Qt.ItemIsEditable)
            self._progress_maximum_items[research_id] = maximum_item
            self.progress_table.setItem(row, 2, maximum_item)
        progress_layout.addWidget(self.progress_table)
        progress_panel.setMinimumWidth(420)
        splitter.addWidget(progress_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 480])
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.player_save_status_label = QLabel()
        actions.addWidget(self.player_save_status_label, 1)
        self.tree_clear_levels_button = QPushButton(self.t("tree.clear_levels"))
        self.tree_clear_levels_button.clicked.connect(self._clear_tree_levels)
        self.tree_save_levels_button = QPushButton(self.t("player.save_all"))
        self.tree_save_levels_button.clicked.connect(self._save_player)
        self._update_player_save_button()
        export_button = QPushButton(self.t("common.export"))
        export_button.clicked.connect(self._export_backup)
        import_button = QPushButton(self.t("common.import"))
        import_button.clicked.connect(self._import_backup)
        actions.addStretch(1)
        actions.addWidget(self.tree_clear_levels_button)
        actions.addWidget(self.tree_save_levels_button)
        actions.addWidget(import_button)
        actions.addWidget(export_button)
        layout.addLayout(actions)

        self.vip_level_spin.valueChanged.connect(self._vip_level_changed)
        self._update_vip_free_speedup_label()
        self.castle_spin.valueChanged.connect(self._settings_changed)
        self.castle_mana_stage_spin.valueChanged.connect(self._settings_changed)
        self.construction_speed_spin.valueChanged.connect(self._settings_changed)
        self.construction_speed_boost_spin.valueChanged.connect(
            self._settings_changed
        )
        self.academy_spin.valueChanged.connect(self._settings_changed)
        self.research_speed_spin.valueChanged.connect(self._settings_changed)
        self.research_speed_boost_spin.valueChanged.connect(
            self._settings_changed
        )
        self.guild_help_spin.valueChanged.connect(self._settings_changed)
        self.speedup_spin.valueChanged.connect(self._settings_changed)
        for spin in self.resource_spins.values():
            spin.valueChanged.connect(self._settings_changed)
        return page

    def _integer_spin(self, minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setGroupSeparatorShown(True)
        return spin

    def _settings_changed(self, *_args) -> None:
        if not hasattr(self, "castle_spin"):
            return
        settings = self.player_state.settings
        previous_castle_level = settings.castle_level
        previous_mana_stage = settings.castle_mana_stage
        settings.vip_level = self.vip_level_spin.value()
        settings.castle_level = self.castle_spin.value()
        settings.castle_mana_stage = (
            self.castle_mana_stage_spin.value()
            if settings.castle_level == 25
            else 0
        )
        self.castle_mana_stage_spin.blockSignals(True)
        self.castle_mana_stage_spin.setEnabled(settings.castle_level == 25)
        self.castle_mana_stage_spin.setValue(settings.castle_mana_stage)
        self.castle_mana_stage_spin.blockSignals(False)
        settings.academy_level = self.academy_spin.value()
        settings.construction_speed_percent = self.construction_speed_spin.value()
        settings.construction_speed_boost_percent = (
            self.construction_speed_boost_spin.value()
        )
        settings.research_speed_percent = self.research_speed_spin.value()
        settings.research_speed_boost_percent = (
            self.research_speed_boost_spin.value()
        )
        settings.max_guild_helps = self.guild_help_spin.value()
        settings.speedup_seconds = self.speedup_spin.value()
        settings.resources = {key: spin.value() for key, spin in self.resource_spins.items()}
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._refresh_detail()
        self._calculate_plan()
        if hasattr(self, "castle_plan_current_spin"):
            if self.castle_plan_current_spin.value() != settings.castle_level:
                self.castle_plan_current_spin.blockSignals(True)
                self.castle_plan_current_spin.setValue(settings.castle_level)
                self.castle_plan_current_spin.blockSignals(False)
                if self.castle_plan_target_spin.value() <= settings.castle_level:
                    self.castle_plan_target_spin.setValue(
                        min(25, settings.castle_level + 1)
                    )
                self._refresh_castle_level_inputs()
            if (
                self.castle_plan_current_mana_spin.value()
                != settings.castle_mana_stage
            ):
                self.castle_plan_current_mana_spin.blockSignals(True)
                self.castle_plan_current_mana_spin.setValue(
                    settings.castle_mana_stage
                )
                self.castle_plan_current_mana_spin.blockSignals(False)
                self._sync_castle_mana_controls()
            castle_progress_changed = (
                previous_castle_level != settings.castle_level
                or previous_mana_stage != settings.castle_mana_stage
            )
            if (
                castle_progress_changed
                and settings.castle_level == 25
                and self.castle_plan_target_spin.value() == 25
                and self.castle_plan_target_mana_spin.value()
                <= settings.castle_mana_stage
                and settings.castle_mana_stage
                < self.castle_catalog.max_mana_stage
            ):
                self.castle_plan_target_mana_spin.setValue(
                    settings.castle_mana_stage + 1
                )
            self._calculate_castle_plan()
        if (
            hasattr(self, "tree_instant_finish_check")
            and self.tree_instant_finish_check.isChecked()
        ):
            self._refresh_tree_filter_results()

    def _vip_level_changed(self, *_args) -> None:
        self._update_vip_free_speedup_label()
        self._settings_changed()

    def _update_vip_free_speedup_label(self) -> None:
        if not hasattr(self, "vip_free_speedup_label"):
            return
        minutes = free_speedup_seconds_for_vip(
            self.vip_level_spin.value()
        ) // 60
        self.vip_free_speedup_label.setText(
            self.t("player.vip_free_speedup", minutes=minutes)
        )

    def _progress_changed(self, research_id: str, value: int) -> None:
        self._tree_level_draft[research_id] = value
        self._tree_levels_dirty = True
        self._update_player_save_button()
        self._refresh_tree_after_level_change()
        self._refresh_detail()
        self._calculate_plan()

    def _sync_progress_editor(self, research_id: str) -> None:
        if not hasattr(self, "_progress_editors"):
            return
        editor = self._progress_editors.get(research_id)
        if editor is None:
            return
        editor.blockSignals(True)
        editor.setValue(self._tree_level_draft.get(research_id, 0))
        editor.blockSignals(False)

    def _update_player_save_button(self) -> None:
        if hasattr(self, "tree_save_levels_button"):
            dirty = self._tree_levels_dirty or self._player_settings_dirty
            self.tree_save_levels_button.setEnabled(dirty)
            if dirty and hasattr(self, "player_save_status_label"):
                self.player_save_status_label.clear()

    def _save_player(self) -> None:
        self._settings_changed()
        changed_ids = self._commit_tree_level_draft()
        self.player_state.building_levels = dict(self._building_level_draft)
        self.player_repository.save(self.player_state)
        self._player_settings_dirty = False
        self._update_player_save_button()
        for research_id in changed_ids:
            self._sync_progress_editor(research_id)
        self._calculate_plan()
        if hasattr(self, "player_save_status_label"):
            self.player_save_status_label.setText(self.t("player.saved"))

    def _export_backup(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.t("common.export"),
            str(self.paths.tool_root / "RLMResearchPlanner-backup.json"),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.player_repository.export_json(self.player_state, Path(path))
            QMessageBox.information(
                self, self.t("info.title"), self.t("player.backup_exported")
            )
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))

    def _import_backup(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.t("common.import"),
            str(self.paths.tool_root),
            "JSON (*.json)",
        )
        if not path:
            return
        try:
            self.player_state = self.player_repository.import_json(Path(path))
            self._tree_level_draft = dict(self.player_state.research_levels)
            self._building_level_draft = dict(self.player_state.building_levels)
            self._tree_levels_dirty = False
            self._player_settings_dirty = False
            self._build_ui()
            QMessageBox.information(
                self, self.t("info.title"), self.t("player.backup_restored")
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._show_error(str(exc))

    def _build_plan_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QVBoxLayout()
        selection_controls = QHBoxLayout()
        action_controls = QHBoxLayout()
        selection_controls.addWidget(QLabel(self.t("plan.mode")))
        self.plan_mode_combo = QComboBox()
        self.plan_mode_combo.addItem(self.t("plan.mode.target"), "target")
        self.plan_mode_combo.addItem(self.t("plan.mode.shortest"), "shortest")
        self.plan_mode_combo.addItem(self.t("plan.mode.tasks"), "tasks")
        initial_mode = self._plan_mode
        mode_index = self.plan_mode_combo.findData(initial_mode)
        self.plan_mode_combo.setCurrentIndex(max(0, mode_index))
        self.plan_mode_combo.setToolTip(self.t("plan.mode.tooltip"))
        selection_controls.addWidget(self.plan_mode_combo)
        self.plan_target_caption = QLabel(self.t("plan.target"))
        selection_controls.addWidget(self.plan_target_caption)
        self.plan_target_name_label = QLabel(self.t("plan.no_target"))
        self.plan_target_name_label.setStyleSheet("font-weight:700;font-size:15px;")
        selection_controls.addWidget(self.plan_target_name_label, 1)
        self.plan_level_caption = QLabel(self.t("plan.target_level"))
        selection_controls.addWidget(self.plan_level_caption)
        self.plan_level_spin = QSpinBox()
        self.plan_level_spin.setMinimum(1)
        self.plan_level_spin.valueChanged.connect(self._calculate_plan)
        self.plan_level_spin.setEnabled(False)
        selection_controls.addWidget(self.plan_level_spin)
        self.plan_complete_button = QPushButton(self.t("plan.mark_complete"))
        self.plan_complete_button.setEnabled(False)
        self.plan_complete_button.clicked.connect(self._complete_current_plan)
        action_controls.addStretch(1)
        self.plan_register_button = QPushButton(self.t("plan.register_task"))
        self.plan_register_button.setEnabled(False)
        self.plan_register_button.clicked.connect(self._register_current_plan)
        action_controls.addWidget(QLabel(self.t("plan.resource_display")))
        self.plan_resource_mode_combo = QComboBox()
        self.plan_resource_mode_combo.addItem(self.t("plan.resource_exact"), "exact")
        self.plan_resource_mode_combo.addItem(self.t("plan.resource_short"), "short")
        self.plan_resource_mode_combo.setCurrentIndex(
            max(
                0,
                self.plan_resource_mode_combo.findData(
                    self.player_state.settings.resource_display_mode
                ),
            )
        )
        self.plan_resource_mode_combo.currentIndexChanged.connect(
            self._resource_display_mode_changed
        )
        action_controls.addWidget(self.plan_resource_mode_combo)
        action_controls.addWidget(self.plan_register_button)
        action_controls.addWidget(self.plan_complete_button)
        self.plan_fit_button = QPushButton(self.t("tree.fit_all"))
        self.plan_reset_zoom_button = QPushButton(self.t("tree.reset_zoom"))
        action_controls.addWidget(self.plan_fit_button)
        action_controls.addWidget(self.plan_reset_zoom_button)
        controls.addLayout(selection_controls)
        controls.addLayout(action_controls)
        layout.addLayout(controls)

        self.plan_splitter = QSplitter(Qt.Vertical)
        self.plan_tree_view = ResearchTreeView()
        self.plan_fit_button.clicked.connect(self.plan_tree_view.fit_all)
        self.plan_reset_zoom_button.clicked.connect(self.plan_tree_view.reset_zoom)
        self.plan_splitter.addWidget(self.plan_tree_view)

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 6, 0, 0)
        fixed_columns = [
            self.t("tree.name"),
            self.t("plan.level"),
            self.t("plan.base_time"),
            self.t("plan.time"),
            self.t("plan.after_help"),
            self.t("plan.technolabe"),
        ]
        resource_columns = [
            self._resource_label(key) for key in PLAN_RESOURCE_KEYS
        ]
        self._plan_resource_columns = {
            key: len(fixed_columns) + index
            for index, key in enumerate(PLAN_RESOURCE_KEYS)
        }
        self.plan_table = QTableWidget(
            0,
            len(fixed_columns) + len(resource_columns) + 3,
        )
        self.plan_table.setHorizontalHeaderLabels(
            fixed_columns
            + resource_columns
            + [
                self.t("plan.building_requirements"),
                self.t("plan.power"),
                self.t("plan.action"),
            ]
        )
        for column, message_key in {
            1: "plan.level_hint",
            3: "plan.time_hint",
            4: "plan.after_help_hint",
            5: "plan.technolabe_hint",
        }.items():
            self.plan_table.horizontalHeaderItem(column).setToolTip(
                self.t(message_key)
            )
        self.plan_table.verticalHeader().setVisible(False)
        self.plan_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.plan_table.itemClicked.connect(self._plan_table_item_clicked)
        self.plan_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, self.plan_table.columnCount()):
            self.plan_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        self._set_visible_plan_resources(())
        details_layout.addWidget(self.plan_table, 1)
        self.plan_splitter.addWidget(details)
        self.plan_splitter.setStretchFactor(0, 3)
        self.plan_splitter.setStretchFactor(1, 2)
        self.plan_splitter.setSizes([480, 300])
        layout.addWidget(self.plan_splitter, 1)

        if self._plan_target_research_id in self._observed_nodes:
            self._set_plan_target(self._plan_target_research_id)
        else:
            self.plan_tree_view.set_research(
                [],
                [],
                empty_message=self.t("plan.no_target"),
            )
        self.plan_mode_combo.currentIndexChanged.connect(self._plan_mode_changed)
        requested_index = self.plan_mode_combo.findData(initial_mode)
        self.plan_mode_combo.blockSignals(True)
        self.plan_mode_combo.setCurrentIndex(max(0, requested_index))
        self.plan_mode_combo.blockSignals(False)
        self._plan_mode_changed()
        return page

    def _set_plan_target(self, research_id: str) -> None:
        node = self._observed_nodes.get(research_id)
        if node is None or node.max_level is None:
            return
        self._plan_target_research_id = research_id
        if not hasattr(self, "plan_target_name_label"):
            return
        self._plan_mode = "target"
        if hasattr(self, "plan_mode_combo"):
            self.plan_mode_combo.blockSignals(True)
            self.plan_mode_combo.setCurrentIndex(
                self.plan_mode_combo.findData("target")
            )
            self.plan_mode_combo.blockSignals(False)
            self._update_plan_mode_visibility()
        observation = self._node_observation[research_id]
        self.plan_target_name_label.setText(
            f"{observation.localized_title(self.translator.locale)} / "
            f"{node.localized_name(self.translator.locale)}"
        )
        current = self._tree_level_draft.get(research_id, 0)
        self.plan_level_spin.blockSignals(True)
        self.plan_level_spin.setMaximum(node.max_level)
        self.plan_level_spin.setValue(min(node.max_level, max(1, current + 1)))
        self.plan_level_spin.setEnabled(True)
        self.plan_level_spin.blockSignals(False)
        self._calculate_plan()

    def _plan_mode_changed(self, *_args: object) -> None:
        if not hasattr(self, "plan_mode_combo"):
            return
        self._plan_mode = str(self.plan_mode_combo.currentData() or "target")
        self._update_plan_mode_visibility()
        self._calculate_plan()

    def _update_plan_mode_visibility(self) -> None:
        if not hasattr(self, "plan_tree_view"):
            return
        target_mode = self._plan_mode == "target"
        for widget in (
            self.plan_target_caption,
            self.plan_target_name_label,
            self.plan_level_caption,
            self.plan_level_spin,
            self.plan_complete_button,
            self.plan_register_button,
            self.plan_fit_button,
            self.plan_reset_zoom_button,
            self.plan_tree_view,
        ):
            widget.setVisible(target_mode)
        self.plan_splitter.setSizes([480, 300] if target_mode else [0, 780])

    def _calculate_plan(self, *_args: object) -> None:
        if not hasattr(self, "plan_level_spin"):
            return
        if self._plan_mode == "shortest":
            self._current_catalog_plan = None
            self.plan_complete_button.setEnabled(False)
            planning_state = PlayerState(
                settings=self.player_state.settings,
                research_levels=dict(self._tree_level_draft),
            )
            self._render_shortest_plan(
                self.catalog_planner.shortest_available_steps(planning_state)
            )
            return
        if self._plan_mode == "tasks":
            self._current_catalog_plan = None
            self.plan_complete_button.setEnabled(False)
            self.plan_register_button.setEnabled(False)
            self._render_registered_tasks()
            return
        research_id = self._plan_target_research_id
        if not research_id:
            self._current_catalog_plan = None
            self.plan_complete_button.setEnabled(False)
            self.plan_table.setRowCount(0)
            return
        target_level = self._normalized_plan_target_level(research_id)
        planning_state = PlayerState(
            settings=self.player_state.settings,
            research_levels=dict(self._tree_level_draft),
        )
        try:
            result = self.catalog_planner.create_plan(
                planning_state,
                research_id,
                target_level,
            )
        except (KeyError, ValueError) as exc:
            self._current_catalog_plan = None
            self.plan_complete_button.setEnabled(False)
            self._show_error(str(exc))
            return
        self._current_catalog_plan = result
        self._render_catalog_plan(result)

    def _normalized_plan_target_level(self, research_id: str) -> int:
        """Keep a stale target level from becoming completed after a level update."""
        node = self._observed_nodes.get(research_id)
        if node is None or node.max_level is None:
            return self.plan_level_spin.value()
        current = max(0, self._tree_level_draft.get(research_id, 0))
        target = self.plan_level_spin.value()
        if (
            not self._preserve_completed_plan_target
            and current < node.max_level
            and target <= current
        ):
            target = current + 1
            self.plan_level_spin.blockSignals(True)
            self.plan_level_spin.setValue(target)
            self.plan_level_spin.blockSignals(False)
        return target

    def _render_catalog_plan(self, result: CatalogPlanResult) -> None:
        self._set_visible_plan_resources(
            key
            for key in PLAN_RESOURCE_KEYS
            if result.total_costs.get(key, 0) > 0
        )
        self.plan_complete_button.setEnabled(bool(result.steps))
        registered = any(
            task.research_id == result.target_research_id
            and task.target_level == result.target_level
            for task in self.player_state.plan_tasks
        )
        self.plan_register_button.setText(
            self.t("plan.task_registered_button")
            if registered
            else self.t("plan.register_task")
        )
        self.plan_register_button.setEnabled(bool(result.steps) and not registered)
        plan_nodes: list[ResearchTreeNode] = []
        observation_order = {
            observation.observation_id: index
            for index, observation in enumerate(self.observations)
        }
        row_keys = sorted(
            {
                (
                    observation_order.get(
                        self._node_observation[research_id].observation_id, 999
                    ),
                    self._observed_nodes[research_id].row,
                )
                for research_id in result.required_levels
            }
        )
        compact_rows = {key: index for index, key in enumerate(row_keys)}
        for research_id, required_level in result.required_levels.items():
            node = self._observed_nodes[research_id]
            observation_index = observation_order.get(
                self._node_observation[research_id].observation_id, 999
            )
            current = self._tree_level_draft.get(research_id, 0)
            missing = max(0, required_level - current)
            plan_nodes.append(
                ResearchTreeNode(
                    research_id=research_id,
                    name=node.localized_name(self.translator.locale),
                    current_level=current,
                    max_level=node.max_level,
                    status=self.t("plan.unmet_status", count=missing),
                    recommendation=self.t(
                        "plan.required_level", level=required_level
                    ),
                    display_order=node.row * 10_000 + node.column,
                    current_effect=self.t(
                        "plan.required_level", level=required_level
                    ),
                    next_effect=self.t("plan.missing_levels", count=missing),
                    layout_row=compact_rows[(observation_index, node.row)],
                    layout_column=node.column,
                    shortage_levels=missing,
                )
            )
        self.plan_tree_view.set_research(
            plan_nodes,
            result.edges,
            result.target_research_id,
            self.t("plan.no_steps"),
        )
        total_levels = sum(
            max(0, required - self._tree_level_draft.get(research_id, 0))
            for research_id, required in result.required_levels.items()
        )
        total_row = len(result.steps)
        self.plan_table.clearContents()
        self.plan_table.setRowCount(total_row + (1 if result.steps else 0))
        for row, step in enumerate(result.steps):
            self._set_plan_step_row(
                row,
                step,
                self._catalog_research_name(step.research_id),
            )

        if result.steps:
            total_values = [
                self.t("plan.total"),
                self.t("plan.total_levels", count=total_levels),
                format_duration(result.total_base_seconds)
                + self._partial_note(result.unknown_time_steps),
                format_duration(result.total_adjusted_seconds)
                + self._partial_note(result.unknown_time_steps),
                format_duration(result.total_after_help_seconds)
                + self._partial_note(result.unknown_time_steps),
                self._technolabe_text(
                    result.total_technolabes,
                    result.technolabe_efficiency_percent,
                ),
            ]
            total_values.extend(
                self._material_amount(result.total_costs.get(key, 0))
                for key in PLAN_RESOURCE_KEYS
            )
            total_values.extend(
                [
                    self._format_building_requirements(
                        result.building_requirements
                    )
                    or "-",
                    f"{result.total_power:,}"
                    + self._partial_note(result.unknown_power_steps),
                ]
            )
            for column, value in enumerate(total_values):
                item = QTableWidgetItem(value)
                font = item.font()
                font.setBold(True)
                item.setFont(font)
                self.plan_table.setItem(total_row, column, item)

    def _register_current_plan(self) -> None:
        result = self._current_catalog_plan
        if self._plan_mode != "target" or result is None or not result.steps:
            return
        task_key = (result.target_research_id, result.target_level)
        if any(
            (task.research_id, task.target_level) == task_key
            for task in self.player_state.plan_tasks
        ):
            return
        self.player_state.plan_tasks.append(
            ResearchPlanTask(result.target_research_id, result.target_level)
        )
        self.player_repository.save(self.player_state)
        self._render_catalog_plan(result)

    def _resource_display_mode_changed(self, *_args: object) -> None:
        if not hasattr(self, "plan_resource_mode_combo"):
            return
        self.player_state.settings.resource_display_mode = str(
            self.plan_resource_mode_combo.currentData() or "exact"
        )
        self.player_repository.save(self.player_state)
        self._calculate_plan()

    def _complete_current_plan(self) -> None:
        result = self._current_catalog_plan
        if self._plan_mode != "target" or result is None or not result.steps:
            return
        changed_ids: set[str] = set()
        for research_id, required_level in result.required_levels.items():
            node = self._observed_nodes.get(research_id)
            if node is None or node.max_level is None:
                continue
            level = max(0, min(int(required_level), node.max_level))
            if level <= self._tree_level_draft.get(research_id, 0):
                continue
            self._tree_level_draft[research_id] = level
            changed_ids.add(research_id)
        if not changed_ids:
            self._calculate_plan()
            return
        self._tree_levels_dirty = True
        for research_id in changed_ids:
            self._sync_progress_editor(research_id)
        self._refresh_tree_after_level_change(preserve_view=True)
        self._refresh_detail()
        self._preserve_completed_plan_target = True
        try:
            self._save_player()
        finally:
            self._preserve_completed_plan_target = False

    def _render_shortest_plan(self, steps: list[CatalogPlanStep]) -> None:
        self._set_visible_plan_resources(
            key
            for key in PLAN_RESOURCE_KEYS
            if any(step.costs.get(key, 0) > 0 for step in steps)
        )
        self.plan_table.clearContents()
        self.plan_table.setRowCount(len(steps))
        for row, step in enumerate(steps):
            observation = self._node_observation[step.research_id]
            name = (
                f"{observation.localized_title(self.translator.locale)} / "
                f"{self._catalog_research_name(step.research_id)}"
            )
            self._set_plan_step_row(row, step, name, link_to_tree=True)

    def _render_registered_tasks(self) -> None:
        tasks = [
            task
            for task in self.player_state.plan_tasks
            if task.research_id in self._observed_nodes
        ]
        planning_state = PlayerState(
            settings=self.player_state.settings,
            research_levels=dict(self._tree_level_draft),
        )
        task_results = [
            (
                task,
                self.catalog_planner.create_plan(
                    planning_state, task.research_id, task.target_level
                ),
            )
            for task in tasks
        ]
        self._set_visible_plan_resources(
            key
            for key in PLAN_RESOURCE_KEYS
            if any(
                result.total_costs.get(key, 0) > 0
                for _task, result in task_results
            )
        )
        self.plan_table.clearContents()
        self.plan_table.setRowCount(len(task_results))
        for row, (task, result) in enumerate(task_results):
            values = [
                self._catalog_research_name(task.research_id),
                f"Lv.{task.target_level}",
                self._known_duration(result.total_base_seconds),
                self._known_duration(result.total_adjusted_seconds),
                self._known_duration(result.total_after_help_seconds),
                self._technolabe_text(
                    result.total_technolabes,
                    result.technolabe_efficiency_percent,
                ),
            ]
            values.extend(
                self._material_amount(result.total_costs.get(key, 0))
                for key in PLAN_RESOURCE_KEYS
            )
            values.extend(
                [
                    self._format_building_requirements(
                        result.building_requirements
                    )
                    or "-",
                    f"{result.total_power:,}",
                ]
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.UserRole, task.research_id)
                    item.setData(Qt.UserRole + 1, task.target_level)
                    font = item.font()
                    font.setUnderline(True)
                    item.setFont(font)
                    item.setForeground(
                        QBrush(
                            QColor(
                                table_link_color(self.app_settings.visual_style)
                            )
                        )
                    )
                    item.setToolTip(self.t("plan.open_task"))
                self.plan_table.setItem(row, column, item)
            actions = QWidget()
            action_layout = QHBoxLayout(actions)
            action_layout.setContentsMargins(2, 0, 2, 0)
            show_button = QPushButton(self.t("plan.show_task"))
            show_button.clicked.connect(
                lambda _checked=False, saved=task: self._show_registered_task(saved)
            )
            remove_button = QPushButton(self.t("plan.remove_task"))
            remove_button.clicked.connect(
                lambda _checked=False, saved=task: self._remove_registered_task(saved)
            )
            action_layout.addWidget(show_button)
            action_layout.addWidget(remove_button)
            self.plan_table.setCellWidget(
                row, self.plan_table.columnCount() - 1, actions
            )

    def _set_visible_plan_resources(self, resource_keys: Iterable[str]) -> None:
        visible = set(resource_keys)
        for key, column in self._plan_resource_columns.items():
            self.plan_table.setColumnHidden(column, key not in visible)

    def _show_registered_task(self, task: ResearchPlanTask) -> None:
        self._set_plan_target(task.research_id)
        self.plan_level_spin.blockSignals(True)
        self.plan_level_spin.setValue(task.target_level)
        self.plan_level_spin.blockSignals(False)
        self._calculate_plan()

    def _remove_registered_task(self, task: ResearchPlanTask) -> None:
        self.player_state.plan_tasks = [
            saved
            for saved in self.player_state.plan_tasks
            if saved != task
        ]
        self.player_repository.save(self.player_state)
        self._render_registered_tasks()

    def _set_plan_step_row(
        self,
        row: int,
        step: CatalogPlanStep,
        name: str,
        *,
        link_to_tree: bool = False,
    ) -> None:
        values = [
            name,
            str(step.level),
            self._known_duration(step.base_time_seconds),
            self._known_duration(step.adjusted_time_seconds),
            self._known_duration(step.after_help_seconds),
            self._technolabe_text(
                step.technolabe_count,
                step.technolabe_efficiency_percent,
            ),
        ]
        values.extend(
            self._material_amount(step.costs.get(key, 0))
            for key in PLAN_RESOURCE_KEYS
        )
        values.extend(
            [
                self._step_building_requirements(step.research_id, step.level),
                (
                    f"{step.power:,}"
                    if step.power is not None
                    else self.t("common.unknown")
                ),
            ]
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setData(Qt.UserRole, step.research_id)
                if link_to_tree:
                    font = item.font()
                    font.setUnderline(True)
                    item.setFont(font)
                    item.setForeground(
                        QBrush(
                            QColor(
                                table_link_color(self.app_settings.visual_style)
                            )
                        )
                    )
                    item.setToolTip(self.t("plan.open_in_tree"))
            elif column == 3:
                item.setData(Qt.UserRole, step.adjusted_time_seconds)
            self.plan_table.setItem(row, column, item)
        complete_button = QPushButton(self.t("plan.complete_step"))
        complete_button.clicked.connect(
            lambda _checked=False, saved=step: self._complete_plan_step(saved)
        )
        self.plan_table.setCellWidget(
            row, self.plan_table.columnCount() - 1, complete_button
        )

    def _complete_plan_step(self, step: CatalogPlanStep) -> None:
        node = self._observed_nodes.get(step.research_id)
        if node is None or node.max_level is None:
            return
        current = self._tree_level_draft.get(step.research_id, 0)
        level = max(current, min(step.level, node.max_level))
        if level == current:
            return
        self._tree_level_draft[step.research_id] = level
        self._tree_levels_dirty = True
        self._sync_progress_editor(step.research_id)
        self._refresh_tree_after_level_change(preserve_view=True)
        self._refresh_detail()
        self._save_player()

    def _plan_table_item_clicked(self, item: QTableWidgetItem) -> None:
        if item.column() != 0:
            return
        research_id = str(item.data(Qt.UserRole) or "")
        if self._plan_mode == "shortest":
            self._jump_to_tree_research(research_id)
        elif self._plan_mode == "tasks":
            self._show_registered_task(
                ResearchPlanTask(
                    research_id,
                    int(item.data(Qt.UserRole + 1) or 1),
                )
            )

    def _jump_to_tree_research(self, research_id: str) -> None:
        observation = self._node_observation.get(research_id)
        if observation is None:
            return
        dataset_value = f"observation:{observation.observation_id}"
        self._selected_tree_node_id = research_id
        self._selected_research_id = research_id
        self.search_edit.blockSignals(True)
        self.search_edit.clear()
        self.search_edit.blockSignals(False)
        self.tree_instant_finish_check.blockSignals(True)
        self.tree_instant_finish_check.setChecked(False)
        self.tree_instant_finish_check.blockSignals(False)
        self._tree_dataset_search_active = False
        self._tree_dataset_search_restore = dataset_value
        self._filter_tree_datasets("", dataset_value)
        self.tabs.setCurrentIndex(0)
        self.tree_view.focus_research(research_id)

    def _known_duration(self, seconds: int | None) -> str:
        return (
            format_duration(seconds)
            if seconds is not None
            else self.t("common.unknown")
        )

    def _technolabe_text(
        self,
        count: int | None,
        efficiency_percent: float | None,
    ) -> str:
        if count is None:
            return self.t("common.unknown")
        if count <= 0:
            return "-"
        if efficiency_percent is None:
            return self.t("plan.technolabe_count", count=count)
        return self.t(
            "plan.technolabe_efficiency",
            count=count,
            efficiency=efficiency_percent,
        )

    def _material_amount(self, amount: int) -> str:
        if not amount:
            return "-"
        return format_resource_amount(
            amount, self.player_state.settings.resource_display_mode
        )

    def _step_building_requirements(
        self,
        research_id: str,
        level: int,
    ) -> str:
        node = self._observed_nodes.get(research_id)
        level_data = node.level_data(level) if node is not None else None
        if level_data is None:
            return self.t("common.unknown")
        requirements = dict(level_data.building_requirements)
        if level_data.academy_level is not None:
            requirements["academy"] = level_data.academy_level
        return self._format_building_requirements(requirements) or "-"

    def _format_materials(self, values: dict[str, int]) -> str:
        order = {name: index for index, name in enumerate(RESOURCE_LABELS)}
        return ", ".join(
            f"{self._resource_label(key)} {amount:,}"
            for key, amount in sorted(
                values.items(), key=lambda item: (order.get(item[0], 999), item[0])
            )
            if amount
        )

    def _format_building_requirements(self, values: dict[str, int]) -> str:
        return ", ".join(
            self.t(f"building.{name}", level=level)
            for name, level in sorted(values.items())
        )

    def _partial_note(self, count: int) -> str:
        return self.t("plan.known_partial", count=count) if count else ""

    def _build_paid_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)

        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.t("paid.price")))
        self.paid_diamond_spin = QSpinBox()
        self.paid_diamond_spin.setRange(0, 99_999_999)
        self.paid_diamond_spin.setGroupSeparatorShown(True)
        self.paid_diamond_spin.setSpecialValueText("-")
        self.paid_diamond_spin.valueChanged.connect(self._update_paid_summary)
        controls.addWidget(self.paid_diamond_spin)
        self.paid_capture_button = QPushButton(self.t("paid.capture"))
        self.paid_capture_button.clicked.connect(self._capture_paid_pack)
        controls.addWidget(self.paid_capture_button)
        self.paid_capture_progress = QProgressBar()
        self.paid_capture_progress.setRange(0, 100)
        self.paid_capture_progress.setValue(0)
        self.paid_capture_progress.setMinimumWidth(150)
        controls.addWidget(self.paid_capture_progress)
        controls.addStretch(1)
        self.paid_add_row_button = QPushButton(self.t("paid.add_row"))
        self.paid_add_row_button.clicked.connect(
            lambda: self._add_paid_row(focus=True)
        )
        controls.addWidget(self.paid_add_row_button)
        delete_button = QPushButton(self.t("paid.delete_rows"))
        delete_button.clicked.connect(self._remove_selected_paid_rows)
        controls.addWidget(delete_button)
        clear_button = QPushButton(self.t("paid.clear"))
        clear_button.clicked.connect(self._clear_paid_rows)
        controls.addWidget(clear_button)
        layout.addLayout(controls)

        gem_group = QGroupBox(self.t("paid.gems"))
        gem_layout = QHBoxLayout(gem_group)
        gem_layout.addWidget(QLabel(self.t("paid.gems.included")))
        self.paid_included_gems_spin = QSpinBox()
        self.paid_included_gems_spin.setRange(0, 99_999_999)
        self.paid_included_gems_spin.setGroupSeparatorShown(True)
        self.paid_included_gems_spin.valueChanged.connect(
            self._update_paid_summary
        )
        gem_layout.addWidget(self.paid_included_gems_spin)
        gem_layout.addWidget(QLabel(self.t("paid.gems.bonus")))
        self.paid_bonus_gems_spin = QSpinBox()
        self.paid_bonus_gems_spin.setRange(0, 99_999_999)
        self.paid_bonus_gems_spin.setGroupSeparatorShown(True)
        self.paid_bonus_gems_spin.valueChanged.connect(self._update_paid_summary)
        gem_layout.addWidget(self.paid_bonus_gems_spin)
        gem_layout.addStretch(1)
        gem_layout.addWidget(QLabel(self.t("paid.gems.total")))
        self.paid_total_gems_label = QLabel("0")
        self.paid_total_gems_label.setStyleSheet("font-weight:700;")
        gem_layout.addWidget(self.paid_total_gems_label)
        gem_layout.addWidget(QLabel(self.t("paid.gems.per_diamond")))
        self.paid_gems_per_diamond_label = QLabel("-")
        self.paid_gems_per_diamond_label.setStyleSheet("font-weight:700;")
        gem_layout.addWidget(self.paid_gems_per_diamond_label)
        layout.addWidget(gem_group)

        self.paid_item_table = QTableWidget(0, 5)
        self.paid_item_table.setHorizontalHeaderLabels(
            [
                self.t("paid.kind"),
                self.t("paid.duration"),
                self.t("paid.unit"),
                self.t("paid.quantity"),
                self.t("paid.subtotal"),
            ]
        )
        self.paid_item_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.paid_item_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.paid_item_table.verticalHeader().setMinimumSectionSize(34)
        self.paid_item_table.verticalHeader().setDefaultSectionSize(38)
        self.paid_item_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        for column in range(1, 5):
            self.paid_item_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        layout.addWidget(self.paid_item_table, 1)

        summary_group = QGroupBox(self.t("paid.summary"))
        summary_layout = QVBoxLayout(summary_group)
        self.paid_summary_table = QTableWidget(4, 4)
        self.paid_summary_table.setHorizontalHeaderLabels(
            [
                self.t("paid.kind"),
                self.t("paid.total_time"),
                self.t("paid.price"),
                self.t("paid.time_per_diamond"),
            ]
        )
        self.paid_summary_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.paid_summary_table.setSelectionMode(QTableWidget.NoSelection)
        self.paid_summary_table.verticalHeader().setVisible(False)
        self.paid_summary_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        summary_layout.addWidget(self.paid_summary_table)
        layout.addWidget(summary_group)

        self._add_paid_row()
        self._update_paid_summary()
        return page

    def _paid_kind_combo(self, kind: str = "general") -> QComboBox:
        combo = QComboBox()
        for key in SPEEDUP_KINDS:
            combo.addItem(self.t(f"paid.kind.{key}"), key)
        index = combo.findData(kind)
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(self._update_paid_summary)
        return combo

    def _paid_unit_combo(self, unit: str = "hours") -> QComboBox:
        combo = QComboBox()
        for key in ("seconds", "minutes", "hours", "days"):
            combo.addItem(self.t(f"paid.unit.{key}"), key)
        index = combo.findData(unit)
        combo.setCurrentIndex(max(0, index))
        combo.currentIndexChanged.connect(self._update_paid_summary)
        return combo

    @staticmethod
    def _paid_duration_value(seconds: int) -> tuple[int, str]:
        if seconds <= 0:
            return 0, "hours"
        for divisor, unit in (
            (86400, "days"),
            (3600, "hours"),
            (60, "minutes"),
        ):
            if seconds > 0 and seconds % divisor == 0:
                return seconds // divisor, unit
        return max(0, seconds), "seconds"

    def _add_paid_row(
        self, entry: SpeedupEntry | None = None, *, focus: bool = False
    ) -> None:
        row = self.paid_item_table.rowCount()
        self.paid_item_table.insertRow(row)
        kind = entry.kind if entry is not None else "general"
        if (
            entry is not None
            and entry.duration_value is not None
            and entry.duration_unit
        ):
            duration, unit = entry.duration_value, entry.duration_unit
        else:
            duration, unit = self._paid_duration_value(
                entry.duration_seconds if entry is not None else 0
            )
        quantity = entry.quantity if entry is not None else 0

        kind_combo = self._paid_kind_combo(kind)
        self.paid_item_table.setCellWidget(row, 0, kind_combo)
        duration_spin = QSpinBox()
        duration_spin.setRange(0, 99_999_999)
        duration_spin.setGroupSeparatorShown(True)
        duration_spin.setValue(duration)
        duration_spin.valueChanged.connect(self._update_paid_summary)
        self.paid_item_table.setCellWidget(row, 1, duration_spin)
        self.paid_item_table.setCellWidget(row, 2, self._paid_unit_combo(unit))
        quantity_spin = QSpinBox()
        quantity_spin.setRange(0, 99_999_999)
        quantity_spin.setGroupSeparatorShown(True)
        quantity_spin.setValue(quantity)
        quantity_spin.valueChanged.connect(self._update_paid_summary)
        self.paid_item_table.setCellWidget(row, 3, quantity_spin)
        subtotal = QTableWidgetItem("-")
        subtotal.setTextAlignment(Qt.AlignCenter)
        subtotal.setFlags(subtotal.flags() & ~Qt.ItemIsEditable)
        self.paid_item_table.setItem(row, 4, subtotal)
        self._update_paid_summary()
        if focus:
            self.paid_item_table.scrollToBottom()
            self.paid_item_table.setCurrentCell(row, 1)
            duration_spin.setFocus(Qt.OtherFocusReason)
            duration_spin.selectAll()

    def _remove_selected_paid_rows(self) -> None:
        rows = sorted(
            {index.row() for index in self.paid_item_table.selectedIndexes()},
            reverse=True,
        )
        for row in rows:
            self.paid_item_table.removeRow(row)
        if self.paid_item_table.rowCount() == 0:
            self._add_paid_row()
        self._update_paid_summary()

    def _clear_paid_rows(self) -> None:
        self.paid_item_table.setRowCount(0)
        self.paid_diamond_spin.setValue(0)
        self.paid_included_gems_spin.setValue(0)
        self.paid_bonus_gems_spin.setValue(0)
        self._add_paid_row()
        self._set_ocr_progress(0, maximum=100)

    @staticmethod
    def _paid_unit_seconds(unit: str) -> int:
        return {
            "seconds": 1,
            "minutes": 60,
            "hours": 3600,
            "days": 86400,
        }.get(unit, 1)

    def _paid_entries_from_table(self) -> tuple[SpeedupEntry, ...]:
        entries: list[SpeedupEntry] = []
        for row in range(self.paid_item_table.rowCount()):
            kind_combo = self.paid_item_table.cellWidget(row, 0)
            duration_spin = self.paid_item_table.cellWidget(row, 1)
            unit_combo = self.paid_item_table.cellWidget(row, 2)
            quantity_spin = self.paid_item_table.cellWidget(row, 3)
            if not (
                isinstance(kind_combo, QComboBox)
                and isinstance(duration_spin, QSpinBox)
                and isinstance(unit_combo, QComboBox)
                and isinstance(quantity_spin, QSpinBox)
            ):
                continue
            duration_seconds = duration_spin.value() * self._paid_unit_seconds(
                str(unit_combo.currentData())
            )
            quantity = quantity_spin.value()
            if duration_seconds <= 0 or quantity <= 0:
                continue
            entries.append(
                SpeedupEntry(
                    kind=str(kind_combo.currentData()),
                    duration_seconds=duration_seconds,
                    quantity=quantity,
                )
            )
        return tuple(entries)

    def _update_paid_summary(self, *_args) -> None:
        if not hasattr(self, "paid_item_table"):
            return
        entries = self._paid_entries_from_table()
        entry_by_row: dict[int, SpeedupEntry] = {}
        entry_index = 0
        for row in range(self.paid_item_table.rowCount()):
            duration_spin = self.paid_item_table.cellWidget(row, 1)
            quantity_spin = self.paid_item_table.cellWidget(row, 3)
            if not isinstance(duration_spin, QSpinBox) or not isinstance(
                quantity_spin, QSpinBox
            ):
                continue
            if duration_spin.value() > 0 and quantity_spin.value() > 0:
                entry_by_row[row] = entries[entry_index]
                entry_index += 1
        for row in range(self.paid_item_table.rowCount()):
            item = self.paid_item_table.item(row, 4)
            if item is not None:
                entry = entry_by_row.get(row)
                item.setText(format_duration(entry.total_seconds) if entry else "-")

        cost = self.paid_diamond_spin.value()
        total_gems = (
            self.paid_included_gems_spin.value()
            + self.paid_bonus_gems_spin.value()
        )
        self.paid_total_gems_label.setText(f"{total_gems:,}")
        self.paid_gems_per_diamond_label.setText(
            f"{total_gems / cost:,.2f}" if cost > 0 else "-"
        )
        summaries = summarize_speedups(entries, cost)
        for row, summary in enumerate(summaries):
            values = (
                self.t(f"paid.kind.{summary.kind}"),
                format_duration(summary.total_seconds),
                f"{cost:,}" if cost > 0 else "-",
                (
                    format_duration(summary.seconds_per_diamond)
                    if summary.seconds_per_diamond is not None
                    else "-"
                ),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setTextAlignment(Qt.AlignCenter)
                self.paid_summary_table.setItem(row, column, item)

    def _capture_paid_pack(self) -> None:
        self.paid_capture_button.setEnabled(False)
        try:
            self._ocr_raw_text = ""
            self._ocr_line_groups = []
            self._ocr_paid_line_groups = []
            self._ocr_paid_gem_line_groups = []
            self._run_ocr(force_window_capture=True, paid_pack=True)
            paid_line_groups = self._ocr_paid_line_groups
            entries = parse_speedup_ocr("", paid_line_groups)
            price = detect_pack_price(
                paid_line_groups,
                image_width=self._ocr_image.width(),
                image_height=self._ocr_image.height(),
            )
            gems = parse_gem_bundle(
                self._ocr_paid_gem_line_groups,
                image_width=self._ocr_image.width(),
                image_height=self._ocr_image.height(),
            )
            self.paid_diamond_spin.setValue(price or 0)
            self.paid_included_gems_spin.setValue(gems.included_gems)
            self.paid_bonus_gems_spin.setValue(gems.bonus_gems)
            if not entries:
                self.paid_item_table.setRowCount(0)
                self._add_paid_row()
                self._show_info(self.t("paid.no_items"))
                return
            self.paid_item_table.setRowCount(0)
            for entry in entries:
                self._add_paid_row(entry)
            self._update_paid_summary()
        finally:
            self.paid_capture_button.setEnabled(True)

    def _build_help_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        settings = QHBoxLayout()
        settings.addWidget(QLabel(self.t("language.label")))
        self.language_combo = QComboBox()
        self.language_combo.addItem("日本語", "ja-JP")
        self.language_combo.addItem("English", "en-US")
        index = self.language_combo.findData(self.translator.locale)
        self.language_combo.setCurrentIndex(max(0, index))
        self.language_combo.currentIndexChanged.connect(self._change_language)
        settings.addWidget(self.language_combo)
        settings.addWidget(QLabel(self.t("appearance.label")))
        self.visual_style_combo = QComboBox()
        self.visual_style_combo.addItem(
            self.t("appearance.desktop"), "desktop"
        )
        self.visual_style_combo.addItem(
            self.t("appearance.mobile"), "mobile"
        )
        visual_style_index = self.visual_style_combo.findData(
            normalize_visual_style(self.app_settings.visual_style)
        )
        self.visual_style_combo.setCurrentIndex(max(0, visual_style_index))
        self.visual_style_combo.currentIndexChanged.connect(
            self._change_visual_style
        )
        settings.addWidget(self.visual_style_combo)
        settings.addWidget(QLabel(self.t("help.font_size")))
        self.help_font_spin = QSpinBox()
        self.help_font_spin.setRange(9, 24)
        self.help_font_spin.setSuffix(" pt")
        self.help_font_spin.setValue(self.app_settings.help_font_size)
        self.help_font_spin.valueChanged.connect(self._change_help_font_size)
        settings.addWidget(self.help_font_spin)
        settings.addStretch(1)
        self.help_version_label = QLabel(
            self.t("app.version", version=version_string())
        )
        settings.addWidget(self.help_version_label)
        settings.addSpacing(12)
        self.update_check_button = QPushButton(self.t("update.check"))
        settings.addWidget(self.update_check_button)
        self.update_startup_checkbox = QCheckBox(
            self.t("update.check_on_startup_short")
        )
        settings.addWidget(self.update_startup_checkbox)
        self.update_releases_button = QPushButton(self.t("update.open_releases"))
        self.update_releases_button.clicked.connect(
            lambda: self.update_controller.open_releases_page()
        )
        settings.addWidget(self.update_releases_button)
        self.update_status_label = QLabel()
        self.update_status_label.setMinimumWidth(0)
        settings.addWidget(self.update_status_label, 1)
        self.update_controller.bind_help_controls(
            self.update_check_button,
            self.update_status_label,
            self.update_startup_checkbox,
        )
        layout.addLayout(settings)

        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)
        self.help_browser.setStyleSheet(
            f"font-size:{self.app_settings.help_font_size}pt;"
        )
        sections = (
            ("help.required_setup.title", "help.required_setup.body_v003"),
            ("help.tree.title", "help.tree.body"),
            ("help.levels.title", "help.levels.body_v003"),
            ("help.plan.title", "help.plan.body"),
            ("help.castle.title", "help.castle.body"),
            ("help.player.title", "help.player.body_v003"),
            ("help.ocr.title", "help.ocr.body_v003"),
            ("help.paid.title", "help.paid.body"),
            ("help.appearance.title", "help.appearance.body"),
            ("help.data.title", "help.data.body"),
            ("help.license.title", "help.license.body"),
            ("help.update.title", "help.update.body"),
        )
        body = [f"<h1>{self.t('help.title')}</h1>"]
        body.append(f"<p>{self.t('help.introduction')}</p>")
        for title_key, body_key in sections:
            body.append(f"<h2>{self.t(title_key)}</h2>")
            body.append(f"<p>{self.t(body_key)}</p>")
        body.append("<hr>")
        body.append(f"<p>{self.t('app.disclaimer')}</p>")
        self.help_browser.setHtml("".join(body))
        layout.addWidget(self.help_browser)
        return page

    def _apply_visual_style(self) -> None:
        visual_style = normalize_visual_style(self.app_settings.visual_style)
        self.app_settings.visual_style = visual_style
        self.setStyleSheet(window_style_sheet(visual_style))
        if hasattr(self, "tree_dataset_list"):
            self.tree_dataset_list.setStyleSheet(
                dataset_style_sheet(visual_style)
            )
        for tree_view_name in ("tree_view", "plan_tree_view"):
            tree_view = getattr(self, tree_view_name, None)
            if tree_view is not None:
                tree_view.set_visual_style(visual_style)
        if hasattr(self, "plan_table"):
            link_brush = QBrush(QColor(table_link_color(visual_style)))
            for row in range(self.plan_table.rowCount()):
                item = self.plan_table.item(row, 0)
                if item is not None and item.font().underline():
                    item.setForeground(link_brush)

    def _change_visual_style(self) -> None:
        visual_style = normalize_visual_style(
            self.visual_style_combo.currentData()
        )
        if visual_style == self.app_settings.visual_style:
            return
        self.app_settings.visual_style = visual_style
        self._apply_visual_style()
        self.settings_repository.save(self.app_settings)

    def _change_help_font_size(self, value: int) -> None:
        self.app_settings.help_font_size = max(9, min(24, int(value)))
        if hasattr(self, "help_browser"):
            self.help_browser.setStyleSheet(
                f"font-size:{self.app_settings.help_font_size}pt;"
            )
        self.settings_repository.save(self.app_settings)

    def _build_ocr_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QGridLayout()
        controls.addWidget(QLabel(self.t("ocr.window")), 0, 0)
        self.window_combo = QComboBox()
        controls.addWidget(self.window_combo, 0, 1, 1, 5)
        refresh = QPushButton(self.t("common.refresh"))
        refresh.clicked.connect(self._refresh_windows)
        controls.addWidget(refresh, 0, 6)
        capture = QPushButton(self.t("ocr.capture"))
        capture.clicked.connect(lambda: self._capture_window())
        controls.addWidget(capture, 1, 0, 1, 2)
        open_image = QPushButton(self.t("ocr.open_image"))
        open_image.clicked.connect(self._open_ocr_image)
        controls.addWidget(open_image, 1, 2)
        controls.addWidget(QLabel(self.t("ocr.language")), 1, 3)
        self.ocr_language_combo = QComboBox()
        for locale, profile in sorted(self._ocr_profiles.items()):
            self.ocr_language_combo.addItem(f"{locale} [{profile.status}]", locale)
        preferred = self.ocr_language_combo.findData(self.translator.locale)
        self.ocr_language_combo.setCurrentIndex(max(0, preferred))
        controls.addWidget(self.ocr_language_combo, 1, 4)
        self.run_ocr_button = QPushButton(self.t("ocr.run"))
        self.run_ocr_button.clicked.connect(self._run_ocr)
        controls.addWidget(self.run_ocr_button, 1, 5)
        self.ocr_progress = QProgressBar()
        self._set_ocr_progress(0, maximum=100)
        self.ocr_progress.setMinimumWidth(150)
        controls.addWidget(self.ocr_progress, 1, 6)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.ocr_image_label = _OcrImagePreview(self.t("ocr.no_image"))
        self.ocr_image_label.setAlignment(Qt.AlignCenter)
        self.ocr_image_label.setMinimumSize(360, 280)
        self.ocr_image_label.setStyleSheet("background:#111820;border:1px solid #34434C;")
        left_layout.addWidget(self.ocr_image_label)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        result_tabs = QTabWidget()
        field_page = QWidget()
        field_layout = QVBoxLayout(field_page)
        self.ocr_field_table = QTableWidget(0, 3)
        self.ocr_field_table.setHorizontalHeaderLabels(
            [
                self.t("ocr.field_label"),
                self.t("ocr.field_value"),
                self.t("ocr.field_mapping"),
            ]
        )
        self.ocr_field_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ocr_field_table.setEditTriggers(
            QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed
        )
        self.ocr_field_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.Stretch
        )
        field_layout.addWidget(self.ocr_field_table, 1)
        field_actions = QHBoxLayout()
        apply_field_button = QPushButton(self.t("ocr.apply_selected_mapped"))
        apply_field_button.clicked.connect(self._apply_selected_ocr_field)
        apply_all_fields_button = QPushButton(self.t("ocr.apply_all_mapped"))
        apply_all_fields_button.clicked.connect(self._apply_all_ocr_fields)
        field_actions.addStretch(1)
        field_actions.addWidget(apply_field_button)
        field_actions.addWidget(apply_all_fields_button)
        field_layout.addLayout(field_actions)
        result_tabs.addTab(field_page, self.t("ocr.fields"))

        research_page = QWidget()
        research_layout = QVBoxLayout(research_page)
        self.ocr_candidate_table = QTableWidget(0, 3)
        self.ocr_candidate_table.setHorizontalHeaderLabels(
            [self.t("tree.name"), self.t("tree.level"), self.t("ocr.evidence")]
        )
        self.ocr_candidate_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.ocr_candidate_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.ocr_candidate_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        research_layout.addWidget(self.ocr_candidate_table, 1)
        candidate_actions = QHBoxLayout()
        apply_button = QPushButton(self.t("common.apply"))
        apply_button.clicked.connect(self._apply_ocr_candidate)
        apply_all_candidates = QPushButton(self.t("ocr.apply_all_candidates"))
        apply_all_candidates.clicked.connect(self._apply_all_ocr_candidates)
        candidate_actions.addStretch(1)
        candidate_actions.addWidget(apply_button)
        candidate_actions.addWidget(apply_all_candidates)
        research_layout.addLayout(candidate_actions)
        result_tabs.addTab(research_page, self.t("ocr.candidates"))
        right_layout.addWidget(result_tabs, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        self._refresh_windows()
        self.window_combo.currentIndexChanged.connect(self._ocr_window_selected)
        return page

    def _refresh_windows(self) -> None:
        self._capturable_windows = list_capturable_windows()
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        for window in self._capturable_windows:
            self.window_combo.addItem(window.title, window)
        preferred_index = preferred_window_index(
            self._capturable_windows, self.app_settings.ocr_window_title
        )
        if preferred_index >= 0:
            self.window_combo.setCurrentIndex(preferred_index)
        else:
            self.window_combo.insertItem(
                0,
                self.t(
                    "ocr.preferred_missing",
                    title=self.app_settings.ocr_window_title,
                ),
                None,
            )
            self.window_combo.setCurrentIndex(0)
        self.window_combo.blockSignals(False)

    def _ocr_window_selected(self) -> None:
        window = self.window_combo.currentData()
        if not isinstance(window, CapturableWindow):
            return
        self.app_settings.ocr_window_title = window.title
        self.settings_repository.save(self.app_settings)

    def _capture_window(self) -> bool:
        live_windows = list_capturable_windows()
        preferred_index = preferred_window_index(
            live_windows, self.app_settings.ocr_window_title
        )
        if preferred_index < 0:
            self._refresh_windows()
            self._show_info(
                self.t(
                    "ocr.preferred_missing",
                    title=self.app_settings.ocr_window_title,
                )
            )
            return False
        window = live_windows[preferred_index]
        capture_bounds = QRect(
            window.left,
            window.top,
            window.width,
            window.height,
        )
        hide_for_capture = self.isVisible() and (
            window.is_minimized
            or window.is_fullscreen
            or self.frameGeometry().intersects(capture_bounds)
        )
        was_maximized = self.isMaximized()
        if hide_for_capture:
            self.hide()
            QApplication.processEvents()
            reveal_window_for_capture(window)
            refreshed_windows = list_capturable_windows()
            refreshed_index = preferred_window_index(
                refreshed_windows, self.app_settings.ocr_window_title
            )
            if refreshed_index >= 0:
                window = refreshed_windows[refreshed_index]
        try:
            image = capture_visible_window(window)
        finally:
            if hide_for_capture:
                if was_maximized:
                    self.showMaximized()
                else:
                    self.show()
                self.raise_()
                self.activateWindow()
        if image.isNull():
            self._show_error(self.t("ocr.capture_failed"))
            return False
        self._set_ocr_image(image, source="window")
        return True

    def _open_ocr_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.t("ocr.open_image"),
            str(self.paths.tool_root),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not path:
            return
        image = QImage(path)
        if image.isNull():
            self._show_error(self.t("ocr.no_image"))
            return
        self._set_ocr_image(image, source="file")

    def _set_ocr_image(self, image: QImage, *, source: str) -> None:
        self._ocr_image = image
        self._ocr_image_source = source
        self._ocr_candidates = []
        self._ocr_fields = []
        self._ocr_line_groups = []
        self._ocr_paid_line_groups = []
        self._ocr_paid_gem_line_groups = []
        self._ocr_card_groups = []
        self._ocr_raw_text = ""
        self.ocr_field_table.setRowCount(0)
        self.ocr_candidate_table.setRowCount(0)
        self._set_ocr_progress(0, maximum=100)
        self.run_ocr_button.setText(
            self.t("ocr.run_image") if source == "file" else self.t("ocr.run")
        )
        self.ocr_image_label.set_image(image)

    def _set_ocr_progress(self, value: int, *, maximum: int | None = None) -> None:
        for name in (
            "ocr_progress",
            "tree_capture_progress",
            "paid_capture_progress",
        ):
            progress = getattr(self, name, None)
            if not isinstance(progress, QProgressBar):
                continue
            if maximum is not None:
                progress.setRange(0, max(1, maximum))
            progress.setValue(max(progress.minimum(), min(value, progress.maximum())))

    @staticmethod
    def _image_png_bytes(image: QImage) -> bytes:
        output = QByteArray()
        buffer = QBuffer(output)
        buffer.open(QIODevice.WriteOnly)
        if not image.save(buffer, "PNG"):
            raise RuntimeError("Image could not be encoded")
        buffer.close()
        return bytes(output)

    @staticmethod
    def _high_contrast_ocr_image(image: QImage, threshold: int = 180) -> QImage:
        converted = image.convertToFormat(QImage.Format_RGB32)
        for y in range(converted.height()):
            for x in range(converted.width()):
                value = 255 if qGray(converted.pixel(x, y)) >= threshold else 0
                converted.setPixel(x, y, qRgb(value, value, value))
        return converted

    @staticmethod
    def _ocr_content_rect(image: QImage) -> QRect:
        """Return game content bounds, excluding an imported Windows title bar."""

        bounds = image.rect()
        if image.isNull() or image.width() < 100 or image.height() < 100:
            return bounds
        converted = image.convertToFormat(QImage.Format_RGB32)
        sample_step = max(1, converted.width() // 96)
        sample_xs = tuple(range(0, converted.width(), sample_step))

        def light_neutral_ratio(y: int) -> float:
            matches = 0
            for x in sample_xs:
                pixel = converted.pixel(x, y)
                red = qRed(pixel)
                green = qGreen(pixel)
                blue = qBlue(pixel)
                if min(red, green, blue) >= 175 and max(red, green, blue) - min(
                    red, green, blue
                ) <= 32:
                    matches += 1
            return matches / max(1, len(sample_xs))

        if light_neutral_ratio(0) < 0.62:
            return bounds
        last_title_row = 0
        misses = 0
        for y in range(1, max(2, round(converted.height() * 0.09))):
            if light_neutral_ratio(y) >= 0.50:
                last_title_row = y
                misses = 0
            else:
                misses += 1
                if misses >= 3:
                    break
        content_top = last_title_row + 1
        if not (
            converted.height() * 0.015
            <= content_top
            <= converted.height() * 0.08
        ):
            return bounds
        return QRect(
            bounds.left(),
            content_top,
            bounds.width(),
            bounds.height() - content_top,
        )

    @staticmethod
    def _relative_ocr_region(
        content: QRect,
        left: float,
        top: float,
        width: float,
        height: float,
    ) -> QRect:
        """Build a clipped OCR region from ratios of the detected game content."""

        region = QRect(
            content.x() + round(content.width() * left),
            content.y() + round(content.height() * top),
            round(content.width() * width),
            round(content.height() * height),
        )
        return region.intersected(content)

    @staticmethod
    def _ocr_detail_scale(
        region: QRect,
        *,
        target_height: int,
        maximum: float = 4.0,
    ) -> float:
        """Enlarge only small OCR crops; never reduce native image detail."""

        if region.height() <= 0:
            return 1.0
        return max(1.0, min(maximum, target_height / region.height()))

    @staticmethod
    def _research_card_meter_regions(image: QImage) -> list[tuple[QRect, float]]:
        """Find card panels and return their visually filled meter ratio."""
        converted = image.convertToFormat(QImage.Format_RGB32)
        width = converted.width()
        height = converted.height()
        if width < 200 or height < 120:
            return []

        def is_meter_fill(x: int, y: int) -> bool:
            pixel = converted.pixel(x, y)
            red = qRed(pixel)
            green = qGreen(pixel)
            blue = qBlue(pixel)
            return (
                red >= 155
                and 35 <= green <= 225
                and blue <= 105
                and red >= green + 20
            )

        minimum_run = max(3, round(width * 0.006))
        horizontal_join = max(1, round(width * 0.0025))
        components: list[dict[str, int]] = []
        for y in range(height):
            x = 0
            row_runs: list[tuple[int, int]] = []
            while x < width:
                if not is_meter_fill(x, y):
                    x += 1
                    continue
                start = x
                while x < width and is_meter_fill(x, y):
                    x += 1
                if x - start >= minimum_run:
                    row_runs.append((start, x - 1))
            for start, end in row_runs:
                match = next(
                    (
                        component
                        for component in components
                        if component["bottom"] == y - 1
                        and start <= component["right"] + horizontal_join
                        and end >= component["left"] - horizontal_join
                    ),
                    None,
                )
                if match is None:
                    components.append(
                        {
                            "left": start,
                            "right": end,
                            "top": y,
                            "bottom": y,
                        }
                    )
                else:
                    match["left"] = min(match["left"], start)
                    match["right"] = max(match["right"], end)
                    match["bottom"] = y

        regions: list[tuple[QRect, float]] = []
        for component in components:
            orange_width = component["right"] - component["left"] + 1
            orange_height = component["bottom"] - component["top"] + 1
            minimum_meter_height = max(2, round(height * 0.004))
            if (
                orange_width < minimum_run
                or not minimum_meter_height <= orange_height <= height * 0.06
            ):
                continue
            inset = max(1, orange_height // 5)
            meter_sample_ys = tuple(
                dict.fromkeys(
                    (
                        component["top"] + inset,
                        (component["top"] + component["bottom"]) // 2,
                        component["bottom"] - inset,
                    )
                )
            )

            def is_meter_pixel(x: int) -> bool:
                return any(
                    is_meter_fill(x, sample_y)
                    or (
                        qRed(converted.pixel(x, sample_y)) < 170
                        and qGreen(converted.pixel(x, sample_y)) < 130
                        and qBlue(converted.pixel(x, sample_y)) < 80
                    )
                    for sample_y in meter_sample_ys
                )

            meter_left = component["left"]
            while meter_left > 0 and is_meter_pixel(meter_left - 1):
                meter_left -= 1
            meter_right = component["right"]
            while meter_right + 1 < width and is_meter_pixel(meter_right + 1):
                meter_right += 1
            meter_width = meter_right - meter_left + 1
            if not width * 0.14 <= meter_width <= width * 0.35:
                continue

            unit = meter_width / 199.0
            if meter_width - orange_width < max(3, round(2.0 * unit)):
                # Tree connector lines are gold too, but do not have a dark meter frame.
                continue
            context_top = max(0, component["top"] - round(25.0 * unit))
            context_bottom = max(0, component["top"] - round(10.0 * unit))
            context_pixels = [
                converted.pixel(x, y)
                for y in range(context_top, context_bottom)
                for x in range(meter_left, meter_right + 1)
            ]
            dark_context_pixels = sum(
                1
                for pixel in context_pixels
                if qRed(pixel) < 170
                and qGreen(pixel) < 130
                and qBlue(pixel) < 80
            )
            if (
                not context_pixels
                or dark_context_pixels / len(context_pixels) < 0.65
            ):
                # The card name panel is dark; plain gold tree connectors are not.
                continue
            expected_height = round(84.0 * unit)
            region = QRect(
                round(meter_left - 4.0 * unit),
                round(component["top"] - 57.0 * unit),
                round(meter_width + 10.0 * unit),
                expected_height,
            ).intersected(converted.rect())
            if (
                region.width() < meter_width * 0.40
                or region.height() < expected_height * 0.85
            ):
                continue
            if any(
                abs(existing_region.center().x() - region.center().x())
                < meter_width * 0.3
                and abs(existing_region.center().y() - region.center().y())
                < meter_width * 0.2
                for existing_region, _fill_ratio in regions
            ):
                continue
            regions.append((region, orange_width / meter_width))
        non_overlapping: list[tuple[QRect, float]] = []
        for region, fill_ratio in sorted(
            regions,
            key=lambda candidate: candidate[0].width() * candidate[0].height(),
            reverse=True,
        ):
            if any(
                region.intersects(existing_region)
                for existing_region, _existing_ratio in non_overlapping
            ):
                continue
            non_overlapping.append((region, fill_ratio))
        return sorted(
            non_overlapping,
            key=lambda candidate: (candidate[0].y(), candidate[0].x()),
        )

    @staticmethod
    def _research_card_ocr_regions(image: QImage) -> list[QRect]:
        """Find research-card panels from orange progress or gold MAX meters."""
        return [
            region
            for region, _fill_ratio in MainWindow._research_card_meter_regions(image)
        ]

    def _selected_ocr_profile(self):
        locale = self.ocr_language_combo.currentData()
        return self._ocr_profiles[str(locale)]

    def _run_ocr(
        self, *, force_window_capture: bool = False, paid_pack: bool = False
    ) -> None:
        self._set_ocr_progress(0, maximum=100)
        if not self._ocr_engine.available:
            self._show_info(self.t("ocr.engine_missing"))
            return
        if force_window_capture or should_refresh_window_before_ocr(
            self._ocr_image_source
        ):
            if not self._capture_window():
                return
        if self._ocr_image.isNull():
            self._show_info(self.t("ocr.no_image"))
            return
        self.run_ocr_button.setEnabled(False)
        QApplication.processEvents()
        try:
            profile = self._selected_ocr_profile()
            image_inputs = [(self._ocr_image, 1.0, 0.0, 0.0, None)]
            paid_input_indexes: set[int] = set()
            gem_input_indexes: set[int] = set()
            detected_card_regions = self._research_card_ocr_regions(self._ocr_image)
            image_inputs.append(
                (
                    self._high_contrast_ocr_image(self._ocr_image),
                    1.0,
                    0.0,
                    0.0,
                    None,
                )
            )
            if paid_pack:
                content = self._ocr_content_rect(self._ocr_image)
                gem_region = self._relative_ocr_region(
                    content,
                    0.164,
                    0.209,
                    0.508,
                    0.232,
                )
                gem_image = self._ocr_image.copy(gem_region)
                gem_scale = self._ocr_detail_scale(
                    gem_region, target_height=610
                )
                gem_variants = [(gem_image, Qt.SmoothTransformation)]
                gem_variants.extend(
                    (
                        self._high_contrast_ocr_image(
                            gem_image, threshold=threshold
                        ),
                        Qt.FastTransformation,
                    )
                    for threshold in (130, 150, 180)
                )
                for gem_variant, transformation in gem_variants:
                    image_inputs.append(
                        (
                            gem_variant.scaled(
                                round(gem_image.width() * gem_scale),
                                round(gem_image.height() * gem_scale),
                                Qt.IgnoreAspectRatio,
                                transformation,
                            ),
                            gem_scale,
                            float(gem_region.x()),
                            float(gem_region.y()),
                            None,
                        )
                    )
                    input_index = len(image_inputs) - 1
                    paid_input_indexes.add(input_index)
                    gem_input_indexes.add(input_index)
                panel_region = self._relative_ocr_region(
                    content,
                    0.16,
                    0.206,
                    0.68,
                    0.70,
                )
                panel_image = self._ocr_image.copy(panel_region)
                panel_scale = self._ocr_detail_scale(
                    panel_region,
                    target_height=1400,
                    maximum=3.0,
                )
                image_inputs.append(
                    (
                        panel_image.scaled(
                            round(panel_image.width() * panel_scale),
                            round(panel_image.height() * panel_scale),
                            Qt.IgnoreAspectRatio,
                            Qt.SmoothTransformation,
                        ),
                        panel_scale,
                        float(panel_region.x()),
                        float(panel_region.y()),
                        None,
                    )
                )
                paid_input_indexes.add(len(image_inputs) - 1)
                for row_index in range(5):
                    paid_region = self._relative_ocr_region(
                        content,
                        0.17,
                        0.419 + row_index * 0.090,
                        0.67,
                        0.102,
                    )
                    paid_image = self._ocr_image.copy(paid_region)
                    paid_scale = self._ocr_detail_scale(
                        paid_region, target_height=220
                    )
                    image_inputs.append(
                        (
                            paid_image.scaled(
                                round(paid_image.width() * paid_scale),
                                round(paid_image.height() * paid_scale),
                                Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation,
                            ),
                            paid_scale,
                            float(paid_region.x()),
                            float(paid_region.y()),
                            None,
                        )
                    )
                    paid_input_indexes.add(len(image_inputs) - 1)
                    for threshold in (130, 150):
                        high_contrast_row = self._high_contrast_ocr_image(
                            paid_image, threshold=threshold
                        )
                        image_inputs.append(
                            (
                                high_contrast_row.scaled(
                                    round(paid_image.width() * paid_scale),
                                    round(paid_image.height() * paid_scale),
                                    Qt.IgnoreAspectRatio,
                                    Qt.FastTransformation,
                                ),
                                paid_scale,
                                float(paid_region.x()),
                                float(paid_region.y()),
                                None,
                            )
                        )
                        paid_input_indexes.add(len(image_inputs) - 1)
                price_region = self._relative_ocr_region(
                    content,
                    0.35,
                    0.853,
                    0.32,
                    0.147,
                )
                price_image = self._ocr_image.copy(price_region)
                price_scale = self._ocr_detail_scale(
                    price_region, target_height=400
                )
                for price_variant, transformation in (
                    (price_image, Qt.SmoothTransformation),
                    (
                        self._high_contrast_ocr_image(
                            price_image, threshold=150
                        ),
                        Qt.FastTransformation,
                    ),
                ):
                    image_inputs.append(
                        (
                            price_variant.scaled(
                                round(price_image.width() * price_scale),
                                round(price_image.height() * price_scale),
                                Qt.IgnoreAspectRatio,
                                transformation,
                            ),
                            price_scale,
                            float(price_region.x()),
                            float(price_region.y()),
                            None,
                        )
                    )
                    paid_input_indexes.add(len(image_inputs) - 1)
            for region in detected_card_regions:
                card = self._ocr_image.copy(region)
                card_scale = self._ocr_detail_scale(
                    region, target_height=340
                )
                for card_image, transformation in (
                    (card, Qt.SmoothTransformation),
                    (
                        self._high_contrast_ocr_image(card, threshold=140),
                        Qt.FastTransformation,
                    ),
                ):
                    image_inputs.append(
                        (
                            card_image.scaled(
                                round(card.width() * card_scale),
                                round(card.height() * card_scale),
                                Qt.IgnoreAspectRatio,
                                transformation,
                            ),
                            card_scale,
                            float(region.x()),
                            float(region.y()),
                            region,
                        )
                    )
            self._set_ocr_progress(0, maximum=len(image_inputs) + 1)
            results = []
            for index, (
                image,
                image_scale,
                offset_x,
                offset_y,
                region,
            ) in enumerate(image_inputs, start=1):
                results.append(
                    (
                        self._ocr_engine.recognize_png(
                            self._image_png_bytes(image), profile
                        ),
                        image_scale,
                        offset_x,
                        offset_y,
                        region,
                        index - 1 in paid_input_indexes,
                        index - 1 in gem_input_indexes,
                    )
                )
                self._set_ocr_progress(index)
                QApplication.processEvents()
            recognized_lines: list[str] = []
            seen_lines: set[str] = set()
            self._ocr_line_groups = []
            self._ocr_paid_line_groups = []
            self._ocr_paid_gem_line_groups = []
            self._ocr_card_groups = []
            for (
                result,
                image_scale,
                offset_x,
                offset_y,
                region,
                is_paid_input,
                is_gem_input,
            ) in results:
                for line in result.text.splitlines():
                    normalized = " ".join(line.split())
                    if normalized and normalized.casefold() not in seen_lines:
                        recognized_lines.append(normalized)
                        seen_lines.add(normalized.casefold())
                if result.lines:
                    transformed_lines = tuple(
                        OcrLine(
                            text=line.text,
                            x=line.x / image_scale + offset_x,
                            y=line.y / image_scale + offset_y,
                            width=line.width / image_scale,
                            height=line.height / image_scale,
                        )
                        for line in result.lines
                    )
                    self._ocr_line_groups.append(transformed_lines)
                    if is_paid_input:
                        self._ocr_paid_line_groups.append(transformed_lines)
                    if is_gem_input:
                        self._ocr_paid_gem_line_groups.append(transformed_lines)
                    if region is not None:
                        existing_index = next(
                            (
                                index
                                for index, (existing_region, _lines) in enumerate(
                                    self._ocr_card_groups
                                )
                                if existing_region == region
                            ),
                            -1,
                        )
                        if existing_index < 0:
                            self._ocr_card_groups.append((region, transformed_lines))
                        else:
                            existing_region, existing_lines = self._ocr_card_groups[
                                existing_index
                            ]
                            self._ocr_card_groups[existing_index] = (
                                existing_region,
                                existing_lines + transformed_lines,
                            )
            for region in detected_card_regions:
                if not any(
                    existing_region == region
                    for existing_region, _lines in self._ocr_card_groups
                ):
                    self._ocr_card_groups.append((region, ()))
            self._ocr_raw_text = "\n".join(recognized_lines)
            self._parse_ocr_fields(profile)
            self._parse_ocr_text()
            self._append_layout_ocr_candidates()
            self._set_ocr_progress(self.ocr_progress.maximum())
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            self._set_ocr_progress(0, maximum=100)
            self._show_error(str(exc))
        finally:
            self.run_ocr_button.setEnabled(True)

    def _parse_ocr_fields(self, profile) -> None:
        fields_by_label: dict[str, OcrFieldCandidate] = {}
        for lines in self._ocr_line_groups:
            candidates = pair_ocr_label_values(lines, profile)
            candidates.extend(pair_ocr_research_card_levels(lines, profile))
            for candidate in candidates:
                fields_by_label.setdefault(candidate.label.casefold(), candidate)
        self._ocr_fields = sorted(fields_by_label.values(), key=lambda item: item.y)
        self._ocr_field_mapping_combos: dict[int, QComboBox] = {}
        self.ocr_field_table.setRowCount(len(self._ocr_fields))
        for row, candidate in enumerate(self._ocr_fields):
            mapping = self._ocr_field_mapping(candidate.label)
            label_item = QTableWidgetItem(candidate.label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            label_item.setToolTip(candidate.evidence)
            value_item = QTableWidgetItem(candidate.value)
            value_item.setToolTip(self.t("ocr.edit_value_hint"))
            mapping_combo = QComboBox()
            mapping_combo.addItem(self.t("ocr.mapping_none"), "")
            mapping_combo.addItem(
                self.t("player.research_speed"), "research_speed"
            )
            mapping_combo.setCurrentIndex(
                max(0, mapping_combo.findData(mapping))
            )
            mapping_combo.setToolTip(self.t("ocr.mapping_hint"))
            self.ocr_field_table.setItem(row, 0, label_item)
            self.ocr_field_table.setItem(row, 1, value_item)
            self.ocr_field_table.setCellWidget(row, 2, mapping_combo)
            self._ocr_field_mapping_combos[row] = mapping_combo
        if self._ocr_fields:
            self.ocr_field_table.selectRow(0)

    def _ocr_field_mapping(self, label: str) -> str:
        profile = self._selected_ocr_profile()

        def compact(value: str) -> str:
            normalized = normalize_ocr_label(value, profile).casefold()
            return re.sub(
                r"[^\w\u3040-\u30ff\u3400-\u9fff]+", "", normalized
            )

        source = compact(label)
        if len(source) < 3:
            return ""
        aliases = {
            compact("研究速度"),
            compact("Research Speed"),
            compact(self.t("player.research_speed")),
        }
        aliases.discard("")
        if source in aliases or any(
            len(alias) >= 4 and (source in alias or alias in source)
            for alias in aliases
        ):
            return "research_speed"
        best = max(
            (SequenceMatcher(None, source, alias).ratio() for alias in aliases),
            default=0.0,
        )
        return "research_speed" if best >= 0.68 else ""

    def _selected_ocr_field_rows(self) -> list[int]:
        return [index.row() for index in self.ocr_field_table.selectionModel().selectedRows()]

    def _apply_selected_ocr_field(self) -> None:
        rows = self._selected_ocr_field_rows()
        if not rows:
            return
        self._confirm_and_store_ocr_fields(rows)

    def _apply_all_ocr_fields(self) -> None:
        if self.ocr_field_table.rowCount() <= 0:
            return
        self._confirm_and_store_ocr_fields(
            list(range(self.ocr_field_table.rowCount()))
        )

    def _confirm_and_store_ocr_fields(self, rows: list[int]) -> None:
        mapped_rows: list[tuple[str, str, str]] = []
        for row in rows:
            label_item = self.ocr_field_table.item(row, 0)
            value_item = self.ocr_field_table.item(row, 1)
            mapping_combo = getattr(
                self, "_ocr_field_mapping_combos", {}
            ).get(row)
            if (
                label_item is None
                or value_item is None
                or mapping_combo is None
            ):
                continue
            mapping = str(mapping_combo.currentData() or "")
            label = label_item.text().strip()
            value = value_item.text().strip()
            if mapping and label and value:
                mapped_rows.append((mapping, label, value))
        if not mapped_rows:
            self._show_info(self.t("ocr.no_mapped_fields"))
            return
        answer = QMessageBox.question(
            self,
            self.t("info.title"),
            self.t("ocr.confirm_fields", count=len(mapped_rows)),
        )
        if answer != QMessageBox.Yes:
            return
        research_speed: float | None = None
        applied = 0
        for mapping, label, value in mapped_rows:
            self.player_state.observed_stats[label] = value
            if mapping == "research_speed":
                research_speed = parse_ocr_percentage(value)
                if research_speed is not None:
                    applied += 1
        if applied <= 0:
            self._show_info(self.t("ocr.no_applicable_values"))
            return
        if research_speed is not None:
            self.player_state.settings.research_speed_percent = research_speed
            if hasattr(self, "research_speed_spin"):
                self.research_speed_spin.blockSignals(True)
                self.research_speed_spin.setValue(research_speed)
                self.research_speed_spin.blockSignals(False)
        self._player_settings_dirty = True
        self._update_player_save_button()
        self._refresh_detail()
        self._calculate_plan()
        self._show_info(self.t("ocr.mapped_fields_applied", count=applied))

    def _parse_ocr_text(self) -> None:
        profile = self._selected_ocr_profile()
        self._ocr_candidates = parse_research_candidates(
            self._ocr_raw_text, self.master, profile
        )
        existing_ids = {candidate.research_id for candidate in self._ocr_candidates}
        entries = [
            (
                research.id,
                self.master.localized_research(
                    research.id, self.translator.locale
                ).name,
                research.max_level,
            )
            for research in self.master.research
        ]
        active_observation = self._active_observation()
        observed_nodes = (
            active_observation.nodes
            if active_observation is not None
            else self._observed_nodes.values()
        )
        entries.extend(
            (
                node.id,
                node.localized_name(self.translator.locale),
                node.max_level,
            )
            for node in observed_nodes
            if node.id not in self._research and node.max_level is not None
        )
        self._ocr_candidates.extend(
            candidate
            for candidate in parse_research_level_fields(
                self._ocr_fields, entries, profile
            )
            if candidate.research_id not in existing_ids
        )
        self._display_ocr_candidates()
        if self._ocr_candidates or self._ocr_fields:
            self.ocr_candidate_table.selectRow(0)

    def _append_layout_ocr_candidates(self) -> None:
        observation = self._active_observation()
        if observation is None or not observation.nodes:
            return
        meter_fill_ratios = {
            (region.x(), region.y(), region.width(), region.height()): fill_ratio
            for region, fill_ratio in self._research_card_meter_regions(self._ocr_image)
        }
        card_levels: list[OcrCardLevel] = []
        direct_candidates: list[OcrCandidate] = []
        directly_resolved_regions: set[tuple[int, int, int, int]] = set()
        profile = self._selected_ocr_profile()
        label_entries = [
            (
                node.id,
                node.localized_name(self.translator.locale),
                int(node.max_level or 0),
            )
            for node in observation.nodes
            if node.max_level is not None
        ]
        for region, lines in self._ocr_card_groups:
            card = parse_ocr_card_level(
                lines,
                x=float(region.center().x()),
                y=float(region.center().y()),
                width=float(region.width()),
                height=float(region.height()),
            )
            region_key = (region.x(), region.y(), region.width(), region.height())
            fill_ratio = meter_fill_ratios.get(region_key)
            is_complete = fill_ratio is not None and fill_ratio >= 0.91
            label_match = match_ocr_card_label(lines, label_entries, profile)
            if label_match is not None and (card is not None or fill_ratio is not None):
                research_id, maximum, label_evidence = label_match
                maximum_matches = (
                    card is not None
                    and (
                        card.displayed_max == maximum
                        or (maximum >= 10 and card.displayed_max == maximum % 10)
                    )
                )
                if is_complete:
                    direct_level = maximum
                    direct_evidence = "full meter"
                elif card is not None and maximum_matches:
                    direct_level = int(card.current_level)
                    direct_evidence = card.evidence
                elif fill_ratio is not None:
                    direct_level = max(
                        1, min(maximum, round(fill_ratio * maximum))
                    )
                    direct_evidence = f"meter fill {fill_ratio:.3f}"
                else:
                    direct_level = int(card.current_level) if card is not None else 0
                    direct_evidence = card.evidence if card is not None else ""
                if 0 <= direct_level <= maximum:
                    direct_candidates.append(
                        OcrCandidate(
                            research_id=research_id,
                            level=direct_level,
                            evidence=(
                                f"{label_evidence}; card label + "
                                f"{direct_evidence}"
                            ),
                        )
                    )
                    directly_resolved_regions.add(region_key)
            if card is None and fill_ratio is None:
                continue
            card_levels.append(
                OcrCardLevel(
                    x=float(region.center().x()),
                    y=float(region.center().y()),
                    width=float(region.width()),
                    height=float(region.height()),
                    current_level=card.current_level if card is not None else 0,
                    displayed_max=card.displayed_max if card is not None else 0,
                    evidence=(
                        f"{card.evidence}; visually full level meter"
                        if card is not None and is_complete
                        else card.evidence
                        if card is not None
                        else "visually full level meter"
                    ),
                    is_complete=is_complete,
                    fill_ratio=fill_ratio,
                )
            )
        entries = [
            (node.id, node.row, node.column, node.max_level)
            for node in observation.nodes
            if node.max_level is not None
        ]
        # A matching label in the active research category is required before
        # layout can fill in neighboring cards.  Shape and position alone are
        # not category evidence because multiple game trees reuse both.
        mapped = (
            map_ocr_card_levels_by_layout(
                card_levels,
                entries,
                self._ocr_image.width(),
            )
            if direct_candidates
            else []
        )
        informative_regions = {
            (region.x(), region.y(), region.width(), region.height())
            for region, lines in self._ocr_card_groups
            if lines
        }
        if (
            direct_candidates
            and informative_regions
            and informative_regions.issubset(directly_resolved_regions)
        ):
            resolved = direct_candidates
        else:
            resolved_by_id = {
                candidate.research_id: candidate for candidate in mapped
            }
            resolved_by_id.update(
                {
                    candidate.research_id: candidate
                    for candidate in direct_candidates
                }
            )
            resolved = list(resolved_by_id.values())
        if resolved:
            active_ids = {node.id for node in observation.nodes}
            self._ocr_candidates = [
                candidate
                for candidate in self._ocr_candidates
                if candidate.research_id not in active_ids
            ] + resolved
        self._display_ocr_candidates()

    def _display_ocr_candidates(self) -> None:
        self.ocr_candidate_table.setRowCount(len(self._ocr_candidates))
        for row, candidate in enumerate(self._ocr_candidates):
            name = self._catalog_research_name(candidate.research_id)
            for column, value in enumerate((name, str(candidate.level), candidate.evidence)):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, row)
                self.ocr_candidate_table.setItem(row, column, item)
        if self._ocr_candidates:
            self.ocr_candidate_table.selectRow(0)

    def _apply_ocr_candidate(self) -> None:
        rows = self.ocr_candidate_table.selectionModel().selectedRows()
        if not rows:
            return
        candidate = self._ocr_candidates[rows[0].row()]
        if candidate.level <= 0:
            self._show_info(self.t("ocr.no_candidates"))
            return
        name = self._catalog_research_name(candidate.research_id)
        answer = QMessageBox.question(
            self,
            self.t("info.title"),
            self.t("ocr.confirm_apply", name=name, level=candidate.level),
        )
        if answer != QMessageBox.Yes:
            return
        self._tree_level_draft[candidate.research_id] = candidate.level
        self._tree_levels_dirty = True
        self._update_player_save_button()
        self._refresh_tree_after_level_change()
        self._refresh_detail()
        self._calculate_plan()
        self._sync_progress_editor(candidate.research_id)
        if candidate.research_id in self._observed_nodes:
            self._selected_tree_node_id = candidate.research_id
        self._show_info(self.t("ocr.applied_pending"))

    def _apply_all_ocr_candidates(self) -> None:
        candidates = [
            candidate for candidate in self._ocr_candidates if candidate.level > 0
        ]
        if not candidates:
            self._show_info(self.t("ocr.no_candidates"))
            return
        answer = QMessageBox.question(
            self,
            self.t("info.title"),
            self.t("ocr.confirm_apply_all", count=len(candidates)),
        )
        if answer != QMessageBox.Yes:
            return
        for candidate in candidates:
            self._tree_level_draft[candidate.research_id] = candidate.level
        self._tree_levels_dirty = True
        self._update_player_save_button()
        self._refresh_tree_after_level_change()
        self._refresh_detail()
        self._calculate_plan()
        for candidate in candidates:
            self._sync_progress_editor(candidate.research_id)
        self._show_info(
            self.t("ocr.applied_all_pending", count=len(candidates))
        )

    def _research_combo(self) -> QComboBox:
        combo = QComboBox()
        for research in self.master.research:
            localized = self.master.localized_research(research.id, self.translator.locale)
            combo.addItem(localized.name, research.id)
        return combo

    def _catalog_research_name(self, research_id: str) -> str:
        if research_id in self._research:
            return self.master.localized_research(
                research_id, self.translator.locale
            ).name
        node = self._observed_nodes.get(research_id)
        if node is not None:
            return node.localized_name(self.translator.locale)
        return research_id

    @staticmethod
    def _select_combo_data(combo: QComboBox | None, value: str) -> None:
        if combo is None:
            return
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def _change_language(self) -> None:
        locale = str(self.language_combo.currentData())
        if locale == self.translator.locale:
            return
        self.app_settings.locale = locale
        self.translator.set_locale(locale)
        current_tab = self.tabs.currentIndex()
        self._build_ui()
        self._apply_visual_style()
        self.tabs.setCurrentIndex(min(current_tab, self.tabs.count() - 1))

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, self.t("error.title"), message)

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, self.t("info.title"), message)

    def _has_unsaved_player_changes(self) -> bool:
        return self._tree_levels_dirty or self._player_settings_dirty

    def _ask_unsaved_close_action(self) -> str:
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle(self.t("player.unsaved_close.title"))
        dialog.setText(self.t("player.unsaved_close.body"))
        save_button = dialog.addButton(
            self.t("player.unsaved_close.save"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        discard_button = dialog.addButton(
            self.t("player.unsaved_close.discard"),
            QMessageBox.ButtonRole.DestructiveRole,
        )
        cancel_button = dialog.addButton(
            self.t("common.cancel"),
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(save_button)
        dialog.setEscapeButton(cancel_button)
        dialog.exec()
        clicked_button = dialog.clickedButton()
        if clicked_button is save_button:
            return "save"
        if clicked_button is discard_button:
            return "discard"
        return "cancel"

    def _restore_geometry(self) -> None:
        geometry = self.app_settings.window
        rectangle = QRect(geometry.x, geometry.y, geometry.width, geometry.height)
        if any(screen.availableGeometry().intersects(rectangle) for screen in QApplication.screens()):
            self.setGeometry(rectangle)
            return
        self.resize(1280, 820)
        screen = QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            self.move(
                available.center().x() - self.width() // 2,
                available.center().y() - self.height() // 2,
            )

    def closeEvent(self, event: QCloseEvent) -> None:
        if not event.isAccepted():
            return
        if self.isVisible() and self._has_unsaved_player_changes():
            action = self._ask_unsaved_close_action()
            if action == "cancel":
                event.ignore()
                return
            if action == "save":
                self._save_player()
        self.update_controller.shutdown()
        geometry = self.normalGeometry()
        if geometry.width() >= self.minimumWidth() and geometry.height() >= self.minimumHeight():
            self.app_settings.window.x = geometry.x()
            self.app_settings.window.y = geometry.y()
            self.app_settings.window.width = geometry.width()
            self.app_settings.window.height = geometry.height()
        self.settings_repository.save(self.app_settings)
        super().closeEvent(event)
