from __future__ import annotations

import re
import subprocess
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QRect, QSize, Qt, QTimer
from PySide6.QtGui import (
    QCloseEvent,
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

from rlm_research_planner.domain.models import MasterData, PlayerState, RESOURCE_KEYS
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
    format_duration,
)
from rlm_research_planner.services.catalog_planning import (
    CatalogPlanResult,
    CatalogResearchPlanner,
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
from rlm_research_planner.services.window_capture import (
    CapturableWindow,
    capture_visible_window,
    list_capturable_windows,
    preferred_window_index,
    should_refresh_window_before_ocr,
)
from rlm_research_planner.settings import AppSettings, SettingsRepository
from rlm_research_planner.ui.research_tree_view import (
    ResearchTreeNode,
    ResearchTreeView,
)
from rlm_research_planner.ui.update_controller import UpdateController
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
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(700)
        self._autosave_timer.timeout.connect(self._save_player_silently)
        self.update_controller = UpdateController(
            self, self.settings_repository, self.app_settings
        )
        self.setMinimumSize(980, 640)
        self._build_ui()
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
        layout = QVBoxLayout(root)
        layout.setContentsMargins(8, 8, 8, 8)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tree_tab(), self.t("tab.tree"))
        self.tabs.addTab(self._build_plan_tab(), self.t("tab.plan"))
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
        self.search_edit.textChanged.connect(self._refresh_tree)
        filters.addWidget(self.search_edit, 1)
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

    def _refresh_tree(self) -> None:
        if not hasattr(self, "tree_view"):
            return
        observation = self._active_observation()
        if observation is not None:
            query = self.search_edit.text().strip().casefold()
            visible = []
            for node in sorted(
                observation.nodes, key=lambda item: (item.row, item.column)
            ):
                name = node.localized_name(self.translator.locale)
                if query and query not in f"{name} {node.id}".casefold():
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
            self.tree_view.set_research(
                visible,
                edges,
                self._selected_tree_node_id,
                self.t("tree.empty_dataset"),
                connection_groups=(
                    (group.prerequisite_ids, group.research_ids)
                    for group in observation.connection_groups
                ),
            )
            return
        category = self.category_combo.currentData() if hasattr(self, "category_combo") else ""
        tag = self.tag_combo.currentData() if hasattr(self, "tag_combo") else ""
        query = self.search_edit.text().strip().casefold() if hasattr(self, "search_edit") else ""
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
        self.tree_view.set_research(visible, edges, self._selected_tree_node_id)

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
        self.tree_save_levels_button.setEnabled(True)
        self._refresh_tree_preserving_view()
        self._sync_progress_editor(research_id)
        self._calculate_plan()

    def _refresh_tree_preserving_view(self) -> None:
        if not hasattr(self, "tree_view"):
            return
        viewport_center = self.tree_view.viewport().rect().center()
        scene_center = self.tree_view.mapToScene(viewport_center)
        self._refresh_tree()
        self.tree_view.centerOn(scene_center)

    def _clear_tree_levels(self) -> None:
        self._tree_level_draft.clear()
        self._tree_levels_dirty = True
        self.tree_save_levels_button.setEnabled(True)
        self._refresh_tree_preserving_view()
        self._calculate_plan()

    def _save_tree_levels(self) -> None:
        changed_ids = self._commit_tree_level_draft()
        self.player_repository.save(self.player_state)
        for research_id in changed_ids:
            self._sync_progress_editor(research_id)
        self._calculate_plan()

    def _commit_tree_level_draft(self) -> set[str]:
        changed_ids = set(self.player_state.research_levels) | set(
            self._tree_level_draft
        )
        self.player_state.research_levels.clear()
        self.player_state.research_levels.update(self._tree_level_draft)
        self._tree_levels_dirty = False
        self.tree_save_levels_button.setEnabled(False)
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
        self.tree_save_levels_button.setEnabled(True)
        self._refresh_tree_preserving_view()
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
        current = self.player_state.research_levels.get(research.id, 0)
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
            self.player_state.settings.research_speed_percent,
        )
        adjusted = apply_free_speedup_time(
            adjusted,
            self.player_state.settings.free_speedup_seconds,
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

    def _build_player_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        splitter = QSplitter(Qt.Horizontal)

        settings_panel = QWidget()
        settings_form = QFormLayout(settings_panel)
        self.castle_spin = self._integer_spin(1, 99, self.player_state.settings.castle_level)
        self.academy_spin = self._integer_spin(1, 99, self.player_state.settings.academy_level)
        self.research_speed_spin = QDoubleSpinBox()
        self.research_speed_spin.setRange(0.0, 10000.0)
        self.research_speed_spin.setDecimals(2)
        self.research_speed_spin.setValue(self.player_state.settings.research_speed_percent)
        self.free_speedup_minutes_spin = self._integer_spin(
            0,
            24 * 60,
            self.player_state.settings.free_speedup_seconds // 60,
        )
        self.guild_help_spin = self._integer_spin(0, 1000, self.player_state.settings.max_guild_helps)
        self.speedup_spin = self._integer_spin(0, 2_000_000_000, self.player_state.settings.speedup_seconds)
        settings_form.addRow(self.t("player.castle_level"), self.castle_spin)
        settings_form.addRow(self.t("player.academy_level"), self.academy_spin)
        settings_form.addRow(self.t("player.research_speed"), self.research_speed_spin)
        settings_form.addRow(
            self.t("player.free_speedup_minutes"),
            self.free_speedup_minutes_spin,
        )
        settings_form.addRow(self.t("player.guild_helps"), self.guild_help_spin)
        settings_form.addRow(self.t("player.speedups"), self.speedup_spin)

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

        self._progress_editors: dict[str, QSpinBox | QComboBox] = {}
        self.progress_table = QTableWidget(len(progress_entries), 2)
        self.progress_table.setHorizontalHeaderLabels(
            [self.t("tree.name"), self.t("tree.level")]
        )
        self.progress_table.verticalHeader().setVisible(False)
        self.progress_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for row, (research_id, name, max_level, observed) in enumerate(progress_entries):
            display_name = (
                f"{name} [{self.t('tree.observed')}]" if observed else name
            )
            self.progress_table.setItem(row, 0, QTableWidgetItem(display_name))
            if observed:
                editor = QComboBox()
                maximum_for_input = max_level if max_level is not None else 99
                for level in range(maximum_for_input + 1):
                    label = (
                        f"{level} / {max_level}"
                        if max_level is not None
                        else f"Lv.{level}"
                    )
                    editor.addItem(label, level)
                current = self.player_state.research_levels.get(research_id, 0)
                editor.setCurrentIndex(max(0, editor.findData(current)))
                editor.currentIndexChanged.connect(
                    lambda _index, selected_id=research_id, selected=editor: (
                        self._observed_progress_changed(selected_id, selected)
                    )
                )
            else:
                editor = self._integer_spin(
                    0,
                    max_level,
                    self.player_state.research_levels.get(research_id, 0),
                )
                editor.valueChanged.connect(
                    lambda value, selected_id=research_id: self._progress_changed(
                        selected_id, value
                    )
                )
            self._progress_editors[research_id] = editor
            self.progress_table.setCellWidget(row, 1, editor)
        progress_layout.addWidget(self.progress_table)
        splitter.addWidget(progress_panel)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.tree_clear_levels_button = QPushButton(self.t("tree.clear_levels"))
        self.tree_clear_levels_button.clicked.connect(self._clear_tree_levels)
        self.tree_save_levels_button = QPushButton(self.t("tree.save_levels"))
        self.tree_save_levels_button.clicked.connect(self._save_tree_levels)
        self.tree_save_levels_button.setEnabled(self._tree_levels_dirty)
        save_button = QPushButton(self.t("common.save"))
        save_button.clicked.connect(self._save_player)
        export_button = QPushButton(self.t("common.export"))
        export_button.clicked.connect(self._export_backup)
        import_button = QPushButton(self.t("common.import"))
        import_button.clicked.connect(self._import_backup)
        actions.addStretch(1)
        actions.addWidget(self.tree_clear_levels_button)
        actions.addWidget(self.tree_save_levels_button)
        actions.addWidget(import_button)
        actions.addWidget(export_button)
        actions.addWidget(save_button)
        layout.addLayout(actions)

        self.castle_spin.valueChanged.connect(self._settings_changed)
        self.academy_spin.valueChanged.connect(self._settings_changed)
        self.research_speed_spin.valueChanged.connect(self._settings_changed)
        self.free_speedup_minutes_spin.valueChanged.connect(self._settings_changed)
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
        settings.castle_level = self.castle_spin.value()
        settings.academy_level = self.academy_spin.value()
        settings.research_speed_percent = self.research_speed_spin.value()
        settings.free_speedup_seconds = self.free_speedup_minutes_spin.value() * 60
        settings.max_guild_helps = self.guild_help_spin.value()
        settings.speedup_seconds = self.speedup_spin.value()
        settings.resources = {key: spin.value() for key, spin in self.resource_spins.items()}
        self._schedule_autosave()
        self._refresh_detail()
        self._calculate_plan()

    def _progress_changed(self, research_id: str, value: int) -> None:
        self.player_state.research_levels[research_id] = value
        self._tree_level_draft[research_id] = value
        self._schedule_autosave()
        self._refresh_tree()
        self._refresh_detail()
        self._calculate_plan()

    def _observed_progress_changed(
        self, research_id: str, editor: QComboBox
    ) -> None:
        level = editor.currentData()
        if level is None:
            self.player_state.research_levels.pop(research_id, None)
            self._tree_level_draft.pop(research_id, None)
        else:
            self.player_state.research_levels[research_id] = int(level)
            self._tree_level_draft[research_id] = int(level)
        self._schedule_autosave()
        self._refresh_tree()
        self._calculate_plan()

    def _sync_progress_editor(self, research_id: str) -> None:
        if not hasattr(self, "_progress_editors"):
            return
        editor = self._progress_editors.get(research_id)
        if editor is None:
            return
        editor.blockSignals(True)
        if isinstance(editor, QComboBox):
            current = self._tree_level_draft.get(research_id)
            editor.setCurrentIndex(max(0, editor.findData(current)))
        elif isinstance(editor, QSpinBox):
            editor.setValue(self._tree_level_draft.get(research_id, 0))
        editor.blockSignals(False)

    def _schedule_autosave(self) -> None:
        self._autosave_timer.start()

    def _save_player_silently(self) -> None:
        self.player_repository.save(self.player_state)

    def _save_player(self) -> None:
        self._settings_changed()
        changed_ids = self._commit_tree_level_draft()
        self.player_repository.save(self.player_state)
        for research_id in changed_ids:
            self._sync_progress_editor(research_id)
        self._calculate_plan()
        QMessageBox.information(self, self.t("info.title"), self.t("player.saved"))

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
            self._tree_levels_dirty = False
            self._build_ui()
            QMessageBox.information(
                self, self.t("info.title"), self.t("player.backup_restored")
            )
        except (OSError, ValueError, KeyError, TypeError) as exc:
            self._show_error(str(exc))

    def _build_plan_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        controls = QHBoxLayout()
        controls.addWidget(QLabel(self.t("plan.target")))
        self.plan_target_name_label = QLabel(self.t("plan.no_target"))
        self.plan_target_name_label.setStyleSheet("font-weight:700;font-size:15px;")
        controls.addWidget(self.plan_target_name_label, 1)
        controls.addWidget(QLabel(self.t("plan.target_level")))
        self.plan_level_spin = QSpinBox()
        self.plan_level_spin.setMinimum(1)
        self.plan_level_spin.valueChanged.connect(self._calculate_plan)
        self.plan_level_spin.setEnabled(False)
        controls.addWidget(self.plan_level_spin)
        self.plan_fit_button = QPushButton(self.t("tree.fit_all"))
        self.plan_reset_zoom_button = QPushButton(self.t("tree.reset_zoom"))
        controls.addWidget(self.plan_fit_button)
        controls.addWidget(self.plan_reset_zoom_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Vertical)
        self.plan_tree_view = ResearchTreeView()
        self.plan_fit_button.clicked.connect(self.plan_tree_view.fit_all)
        self.plan_reset_zoom_button.clicked.connect(self.plan_tree_view.reset_zoom)
        splitter.addWidget(self.plan_tree_view)

        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.setContentsMargins(0, 6, 0, 0)
        fixed_columns = [
            self.t("tree.name"),
            self.t("tree.level"),
            self.t("plan.base_time"),
            self.t("plan.time"),
            self.t("plan.after_help"),
        ]
        resource_columns = [
            self._resource_label(key) for key in PLAN_RESOURCE_KEYS
        ]
        self.plan_table = QTableWidget(
            0,
            len(fixed_columns) + len(resource_columns) + 2,
        )
        self.plan_table.setHorizontalHeaderLabels(
            fixed_columns
            + resource_columns
            + [self.t("plan.building_requirements"), self.t("plan.power")]
        )
        self.plan_table.verticalHeader().setVisible(False)
        self.plan_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.plan_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, self.plan_table.columnCount()):
            self.plan_table.horizontalHeader().setSectionResizeMode(
                column, QHeaderView.ResizeToContents
            )
        details_layout.addWidget(self.plan_table, 1)
        splitter.addWidget(details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([480, 300])
        layout.addWidget(splitter, 1)

        if self._plan_target_research_id in self._observed_nodes:
            self._set_plan_target(self._plan_target_research_id)
        else:
            self.plan_tree_view.set_research(
                [],
                [],
                empty_message=self.t("plan.no_target"),
            )
        return page

    def _set_plan_target(self, research_id: str) -> None:
        node = self._observed_nodes.get(research_id)
        if node is None or node.max_level is None:
            return
        self._plan_target_research_id = research_id
        if not hasattr(self, "plan_target_name_label"):
            return
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

    def _calculate_plan(self, *_args: object) -> None:
        if not hasattr(self, "plan_level_spin"):
            return
        research_id = self._plan_target_research_id
        if not research_id:
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
            self._show_error(str(exc))
            return
        self._render_catalog_plan(result)

    def _normalized_plan_target_level(self, research_id: str) -> int:
        """Keep a stale target level from becoming completed after a level update."""
        node = self._observed_nodes.get(research_id)
        if node is None or node.max_level is None:
            return self.plan_level_spin.value()
        current = max(0, self._tree_level_draft.get(research_id, 0))
        target = self.plan_level_spin.value()
        if current < node.max_level and target <= current:
            target = current + 1
            self.plan_level_spin.blockSignals(True)
            self.plan_level_spin.setValue(target)
            self.plan_level_spin.blockSignals(False)
        return target

    def _render_catalog_plan(self, result: CatalogPlanResult) -> None:
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
        self.plan_table.setRowCount(total_row + (1 if result.steps else 0))
        for row, step in enumerate(result.steps):
            values = [
                self._catalog_research_name(step.research_id),
                str(step.level),
                self._known_duration(step.base_time_seconds),
                self._known_duration(step.adjusted_time_seconds),
                self._known_duration(step.after_help_seconds),
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
                self.plan_table.setItem(row, column, QTableWidgetItem(value))

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

    def _known_duration(self, seconds: int | None) -> str:
        return (
            format_duration(seconds)
            if seconds is not None
            else self.t("common.unknown")
        )

    @staticmethod
    def _material_amount(amount: int) -> str:
        return f"{amount:,}" if amount else "-"

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
        settings.addStretch(1)
        settings.addWidget(QLabel(self.t("app.version", version=version_string())))
        layout.addLayout(settings)

        update_group = QGroupBox(self.t("update.title"))
        update_layout = QVBoxLayout(update_group)
        update_actions = QHBoxLayout()
        self.update_check_button = QPushButton(self.t("update.check"))
        update_actions.addWidget(self.update_check_button)
        self.update_status_label = QLabel()
        update_actions.addWidget(self.update_status_label, 1)
        self.update_releases_button = QPushButton(self.t("update.open_releases"))
        self.update_releases_button.clicked.connect(
            lambda: self.update_controller.open_releases_page()
        )
        update_actions.addWidget(self.update_releases_button)
        update_layout.addLayout(update_actions)
        self.update_startup_checkbox = QCheckBox(self.t("update.check_on_startup"))
        update_layout.addWidget(self.update_startup_checkbox)
        self.update_controller.bind_help_controls(
            self.update_check_button,
            self.update_status_label,
            self.update_startup_checkbox,
        )
        layout.addWidget(update_group)

        self.help_browser = QTextBrowser()
        self.help_browser.setOpenExternalLinks(True)
        sections = (
            ("help.tree.title", "help.tree.body"),
            ("help.levels.title", "help.levels.body"),
            ("help.plan.title", "help.plan.body"),
            ("help.player.title", "help.player.body"),
            ("help.ocr.title", "help.ocr.body"),
            ("help.paid.title", "help.paid.body"),
            ("help.data.title", "help.data.body"),
            ("help.update.title", "help.update.body"),
        )
        body = [f"<h1>{self.t('help.title')}</h1>"]
        body.append(f"<p>{self.t('help.introduction')}</p>")
        for title_key, body_key in sections:
            body.append(f"<h2>{self.t(title_key)}</h2>")
            body.append(f"<p>{self.t(body_key)}</p>")
        license_files = (
            (self.paths.application_license, self.t("help.licenses.application")),
            (
                self.paths.licenses / "THIRD_PARTY_NOTICES.md",
                self.t("help.licenses.third_party"),
            ),
            (self.paths.licenses / "LGPL-3.0.txt", "GNU LGPL v3"),
            (self.paths.licenses / "GPL-3.0.txt", "GNU GPL v3"),
            (
                self.paths.licenses / "Python-3.12-LICENSE.txt",
                "Python 3.12 License",
            ),
            (
                self.paths.licenses / "PyInstaller-COPYING.txt",
                "PyInstaller License",
            ),
        )
        available_licenses = [
            f'<li><a href="{path.as_uri()}">{label}</a></li>'
            for path, label in license_files
            if path.is_file()
        ]
        if available_licenses:
            body.append(f"<h2>{self.t('help.licenses.title')}</h2>")
            body.append(f"<p>{self.t('help.licenses.body')}</p>")
            body.append(f"<ul>{''.join(available_licenses)}</ul>")
        body.append("<hr>")
        body.append(f"<p>{self.t('app.disclaimer')}</p>")
        self.help_browser.setHtml("".join(body))
        layout.addWidget(self.help_browser)
        return page

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
        apply_field_button = QPushButton(self.t("ocr.apply_field"))
        apply_field_button.clicked.connect(self._apply_selected_ocr_field)
        apply_all_fields_button = QPushButton(self.t("ocr.apply_all_fields"))
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
        image = capture_visible_window(window)
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

        minimum_run = max(28, width // 40)
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
                        and start <= component["right"] + 3
                        and end >= component["left"] - 3
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
            if orange_width < minimum_run or not 5 <= orange_height <= height * 0.06:
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
                region.width() < 80
                or region.height() < 35
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
            longest_side = max(self._ocr_image.width(), self._ocr_image.height())
            scale = min(2.0, 2400.0 / max(1, longest_side))
            if scale >= 1.25:
                image_inputs.append(
                    (
                        self._ocr_image.scaled(
                            round(self._ocr_image.width() * scale),
                            round(self._ocr_image.height() * scale),
                            Qt.KeepAspectRatio,
                            Qt.SmoothTransformation,
                        ),
                        scale,
                        0.0,
                        0.0,
                        None,
                    )
                )
                high_contrast = self._high_contrast_ocr_image(self._ocr_image)
                image_inputs.append(
                    (
                        high_contrast.scaled(
                            round(high_contrast.width() * scale),
                            round(high_contrast.height() * scale),
                            Qt.KeepAspectRatio,
                            Qt.FastTransformation,
                        ),
                        scale,
                        0.0,
                        0.0,
                        None,
                    )
                )
            if paid_pack:
                gem_region = QRect(
                    round(self._ocr_image.width() * 0.164),
                    round(self._ocr_image.height() * 0.243),
                    round(self._ocr_image.width() * 0.508),
                    round(self._ocr_image.height() * 0.222),
                )
                gem_image = self._ocr_image.copy(gem_region)
                gem_scale = 4.0
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
                panel_region = QRect(
                    round(self._ocr_image.width() * 0.16),
                    round(self._ocr_image.height() * 0.24),
                    round(self._ocr_image.width() * 0.68),
                    round(self._ocr_image.height() * 0.67),
                )
                panel_image = self._ocr_image.copy(panel_region)
                panel_scale = min(
                    3.0, 2400.0 / max(1, panel_image.width())
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
                row_x = round(self._ocr_image.width() * 0.17)
                row_width = round(self._ocr_image.width() * 0.67)
                row_height = round(self._ocr_image.height() * 0.097)
                row_start_y = round(self._ocr_image.height() * 0.444)
                row_step = round(self._ocr_image.height() * 0.086)
                for row_index in range(5):
                    paid_region = QRect(
                        row_x,
                        row_start_y + row_index * row_step,
                        row_width,
                        row_height,
                    )
                    paid_image = self._ocr_image.copy(paid_region)
                    paid_scale = 3.0
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
                price_region = QRect(
                    round(self._ocr_image.width() * 0.35),
                    round(self._ocr_image.height() * 0.86),
                    round(self._ocr_image.width() * 0.32),
                    round(self._ocr_image.height() * 0.14),
                )
                price_image = self._ocr_image.copy(price_region)
                price_scale = 4.0
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
                card_scale = min(4.0, 1200.0 / max(1, card.width()))
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
        self.ocr_field_table.setRowCount(len(self._ocr_fields))
        for row, candidate in enumerate(self._ocr_fields):
            mapping = self._ocr_field_mapping(candidate.label)
            label_item = QTableWidgetItem(candidate.label)
            label_item.setFlags(label_item.flags() & ~Qt.ItemIsEditable)
            label_item.setToolTip(candidate.evidence)
            value_item = QTableWidgetItem(candidate.value)
            value_item.setToolTip(self.t("ocr.edit_value_hint"))
            mapping_item = QTableWidgetItem(mapping)
            mapping_item.setFlags(mapping_item.flags() & ~Qt.ItemIsEditable)
            self.ocr_field_table.setItem(row, 0, label_item)
            self.ocr_field_table.setItem(row, 1, value_item)
            self.ocr_field_table.setItem(row, 2, mapping_item)
        if self._ocr_fields:
            self.ocr_field_table.selectRow(0)

    def _ocr_field_mapping(self, label: str) -> str:
        key = "".join(label.split()).casefold()
        if key in {"研究速度", "researchspeed"}:
            return self.t("player.research_speed")
        return self.t("ocr.observed_stat")

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
        answer = QMessageBox.question(
            self,
            self.t("info.title"),
            self.t("ocr.confirm_fields", count=len(rows)),
        )
        if answer != QMessageBox.Yes:
            return
        research_speed: float | None = None
        for row in rows:
            label_item = self.ocr_field_table.item(row, 0)
            value_item = self.ocr_field_table.item(row, 1)
            if label_item is None or value_item is None:
                continue
            label = label_item.text().strip()
            value = value_item.text().strip()
            if not label or not value:
                continue
            self.player_state.observed_stats[label] = value
            if "".join(label.split()).casefold() in {"研究速度", "researchspeed"}:
                research_speed = parse_ocr_percentage(value)
        if research_speed is not None:
            self.player_state.settings.research_speed_percent = research_speed
            if hasattr(self, "research_speed_spin"):
                self.research_speed_spin.blockSignals(True)
                self.research_speed_spin.setValue(research_speed)
                self.research_speed_spin.blockSignals(False)
        self.player_repository.save(self.player_state)
        self._refresh_detail()
        self._show_info(self.t("ocr.fields_applied", count=len(rows)))

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
        mapped = map_ocr_card_levels_by_layout(
            card_levels,
            entries,
            self._ocr_image.width(),
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
        self.player_state.research_levels[candidate.research_id] = candidate.level
        self._tree_level_draft[candidate.research_id] = candidate.level
        self.player_repository.save(self.player_state)
        self._refresh_tree()
        self._refresh_detail()
        self._sync_progress_editor(candidate.research_id)
        if candidate.research_id in self._observed_nodes:
            self._selected_tree_node_id = candidate.research_id
        self._show_info(self.t("ocr.applied"))

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
            self.player_state.research_levels[candidate.research_id] = candidate.level
            self._tree_level_draft[candidate.research_id] = candidate.level
        self.player_repository.save(self.player_state)
        self._refresh_tree()
        self._refresh_detail()
        for candidate in candidates:
            self._sync_progress_editor(candidate.research_id)
        self._show_info(self.t("ocr.applied_all", count=len(candidates)))

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
        self.tabs.setCurrentIndex(min(current_tab, self.tabs.count() - 1))

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, self.t("error.title"), message)

    def _show_info(self, message: str) -> None:
        QMessageBox.information(self, self.t("info.title"), message)

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
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
        self.update_controller.shutdown()
        self.player_repository.save(self.player_state)
        geometry = self.normalGeometry()
        if geometry.width() >= self.minimumWidth() and geometry.height() >= self.minimumHeight():
            self.app_settings.window.x = geometry.x()
            self.app_settings.window.y = geometry.y()
            self.app_settings.window.width = geometry.width()
            self.app_settings.window.height = geometry.height()
        self.settings_repository.save(self.app_settings)
        super().closeEvent(event)
