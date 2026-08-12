from __future__ import annotations

import json
from ctypes import wintypes
from pathlib import Path

import pytest

from rlm_research_planner.services.localization import Translator
from rlm_research_planner.services.ocr import (
    OcrCardLevel,
    OcrLine,
    load_ocr_profiles,
    map_ocr_card_levels_by_layout,
    match_ocr_card_label,
    pair_ocr_label_values,
    pair_ocr_research_card_levels,
    parse_ocr_card_level,
    parse_ocr_percentage,
    parse_research_candidates,
    parse_research_level_fields,
)
from rlm_research_planner.repositories.observation_repository import (
    JsonObservationRepository,
)
from rlm_research_planner.repositories.catalog_repository import (
    JsonResearchCatalogRepository,
)
from rlm_research_planner.services.validation import MasterDataValidator
from rlm_research_planner.services.window_capture import (
    CapturableWindow,
    preferred_window_index,
    rectangles_match,
    should_refresh_window_before_ocr,
)
from rlm_research_planner.settings import (
    DEFAULT_OCR_WINDOW_TITLE,
    AppSettings,
    SettingsRepository,
)


def test_sample_master_is_structurally_valid(master) -> None:
    assert MasterDataValidator().validate(master) == []


def test_visual_style_defaults_validates_and_persists(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    repository = SettingsRepository(path)
    assert repository.load().visual_style == "desktop"

    settings = AppSettings(visual_style="mobile", talent_auto_follow=False)
    repository.save(settings)
    assert repository.load().visual_style == "mobile"
    assert repository.load().talent_auto_follow is False

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["visual_style"] = "unsupported"
    path.write_text(json.dumps(raw), encoding="utf-8")
    assert repository.load().visual_style == "desktop"
    assert repository.load().talent_auto_follow is False


def test_localization_falls_back_to_english() -> None:
    resources = Path(__file__).resolve().parents[1] / "resources" / "i18n"
    translator = Translator(resources, "fr-FR")
    assert translator.text("tab.plan") == "Research Plan"


def test_japanese_effect_labels_are_localized_independently_from_research_names() -> None:
    resources = Path(__file__).resolve().parents[1] / "resources" / "i18n"
    translator = Translator(resources, "ja-JP")
    assert translator.effect_label("Food Production+%") == "食糧生産量"
    assert translator.effect_label("Gathering Speed") == "資源採取速度"
    assert translator.effect_label("Unknown effect") == ""


def test_japanese_ocr_text_maps_to_catalog_research() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_research_card_levels(
        [
            OcrLine("建設速度", 100, 100, 100, 20),
            OcrLine("2/10", 125, 140, 50, 20),
        ],
        profiles["ja-JP"],
    )
    candidates = parse_research_level_fields(
        fields,
        [("economy_construction_speed", "建設速度", 10)],
        profiles["ja-JP"],
    )
    assert [(item.research_id, item.level) for item in candidates] == [
        ("economy_construction_speed", 2)
    ]


def test_japanese_ocr_ignores_spaces_inserted_between_characters() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_research_card_levels(
        [
            OcrLine("建 設 速 度", 100, 100, 100, 20),
            OcrLine("2 / 10", 125, 140, 50, 20),
        ],
        profiles["ja-JP"],
    )
    candidates = parse_research_level_fields(
        fields,
        [("economy_construction_speed", "建設速度", 10)],
        profiles["ja-JP"],
    )
    assert [(item.research_id, item.level) for item in candidates] == [
        ("economy_construction_speed", 2)
    ]


def test_japanese_ocr_distinguishes_a_recognized_zero_from_a_missing_level() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    recognized = parse_research_level_fields(
        pair_ocr_research_card_levels(
            [
                OcrLine("建設速度", 100, 100, 100, 20),
                OcrLine("0 / 10", 125, 140, 50, 20),
            ],
            profiles["ja-JP"],
        ),
        [("economy_construction_speed", "建設速度", 10)],
        profiles["ja-JP"],
    )

    assert [(item.level, item.level_recognized) for item in recognized] == [
        (0, True)
    ]


def test_label_only_ocr_is_not_treated_as_a_recognized_zero(
    planning_master,
) -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    candidates = parse_research_candidates(
        "econ construction speed",
        planning_master,
        profiles["ja-JP"],
    )
    construction = next(
        item
        for item in candidates
        if item.research_id == "econ_construction_speed"
    )

    assert construction.level == 0
    assert construction.level_recognized is False


def test_card_level_is_parsed_from_a_cropped_tree_card() -> None:
    card = parse_ocr_card_level(
        [
            OcrLine("資源採取 I", 10, 20, 100, 24),
            OcrLine("9 / 10", 35, 72, 55, 20),
        ],
        x=620,
        y=350,
        width=220,
        height=180,
    )
    assert card is not None
    assert (card.current_level, card.displayed_max) == (9, 10)


def test_max_card_levels_tolerate_common_ocr_digit_shapes() -> None:
    ten_of_ten = parse_ocr_card_level(
        [OcrLine("10/IO", 35, 72, 55, 20)],
        x=620,
        y=350,
        width=220,
        height=180,
    )
    one_of_one = parse_ocr_card_level(
        [OcrLine("I/I", 35, 72, 55, 20)],
        x=620,
        y=350,
        width=220,
        height=180,
    )
    assert ten_of_ten is not None
    assert one_of_one is not None
    assert (ten_of_ten.current_level, ten_of_ten.displayed_max) == (10, 10)
    assert (one_of_one.current_level, one_of_one.displayed_max) == (1, 1)


def test_complete_card_can_be_identified_from_its_label_without_level_text() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    matched = match_ocr_card_label(
        [OcrLine("罠 配 置 I", 10, 10, 120, 24)],
        [
            ("defense_trap_crafting_i", "罠配置I", 1),
            ("defense_wall_strength_i", "城壁強度I", 10),
        ],
        profiles["ja-JP"],
    )
    assert matched == ("defense_trap_crafting_i", 1, "罠 配 置 I")


def test_duplicate_hp_label_reads_do_not_create_false_ambiguity() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    matched = match_ocr_card_label(
        [
            OcrLine("罠 HP ー", 10, 10, 120, 24),
            OcrLine("罠 HP 一", 10, 10, 120, 24),
            OcrLine("6 / 10", 30, 50, 60, 20),
        ],
        [
            ("defense_trap_defense_i", "罠防御力I", 10),
            ("defense_trap_power_i", "罠攻撃力I", 10),
            ("defense_trap_durability_i", "罠HPI", 10),
        ],
        profiles["ja-JP"],
    )
    assert matched == ("defense_trap_durability_i", 10, "罠 HP ー")


def test_visible_tree_card_levels_map_by_exact_row_order() -> None:
    catalog = JsonResearchCatalogRepository(
        Path(__file__).resolve().parents[1] / "data" / "research" / "catalog.json"
    ).load_all()
    economy = next(item for item in catalog if item.category_id == "economy")
    entries = [
        (node.id, node.row, node.column, node.max_level)
        for node in economy.nodes
        if node.max_level is not None
    ]
    cards = [
        OcrCardLevel(x, 100, 200, 180, 7, 10, "7/10")
        for x in (120, 380, 640, 900)
    ] + [
        OcrCardLevel(120, 400, 200, 180, 7, 10, "7/10"),
        OcrCardLevel(640, 400, 200, 180, 9, 10, "9/10"),
    ]
    candidates = map_ocr_card_levels_by_layout(cards, entries, 1000)
    assert {(item.research_id, item.level) for item in candidates} == {
        ("economy_vault_management", 7),
        ("economy_stone_harvest_1", 7),
        ("economy_timber_harvest_1", 7),
        ("economy_ore_harvest_1", 7),
        ("economy_weight_training_i", 7),
        ("economy_resource_harvesting_i", 9),
    }


def test_visually_complete_meter_maps_to_the_catalog_maximum() -> None:
    candidates = map_ocr_card_levels_by_layout(
        [OcrCardLevel(500, 100, 200, 180, 0, 0, "full meter", True)],
        [("military_training_speed_i", 0, 2, 1)],
        1000,
    )
    assert [(item.research_id, item.level) for item in candidates] == [
        ("military_training_speed_i", 1)
    ]


def test_partial_meter_fill_recovers_level_when_level_text_is_unreadable() -> None:
    candidates = map_ocr_card_levels_by_layout(
        [
            OcrCardLevel(
                500,
                100,
                200,
                180,
                0,
                0,
                "unreadable level text",
                fill_ratio=0.59,
            )
        ],
        [("defense_trap_durability_i", 0, 2, 10)],
        1000,
    )
    assert [(item.research_id, item.level) for item in candidates] == [
        ("defense_trap_durability_i", 6)
    ]


def test_military_top_slice_prefers_consecutive_rows_and_keeps_one_of_one() -> None:
    catalog = JsonResearchCatalogRepository(
        Path(__file__).resolve().parents[1] / "data" / "research" / "catalog.json"
    ).load_all()
    military = next(item for item in catalog if item.category_id == "military")
    entries = [
        (node.id, node.row, node.column, int(node.max_level or 0))
        for node in military.nodes
    ]
    cards = [
        OcrCardLevel(766, 212, 308, 124, 0, 0, "full meter", True),
        OcrCardLevel(579, 613, 323, 130, 8, 10, "8/10"),
        OcrCardLevel(968, 613, 323, 130, 8, 10, "8/10"),
    ]
    candidates = map_ocr_card_levels_by_layout(cards, entries, 1508)
    assert {(item.research_id, item.level) for item in candidates} == {
        ("military_training_speed_i", 1),
        ("military_intelligence_report", 8),
        ("military_quick_maneuvers_i", 8),
    }


def test_military_middle_slice_maps_four_full_t3_meters_before_army_stats() -> None:
    catalog = JsonResearchCatalogRepository(
        Path(__file__).resolve().parents[1] / "data" / "research" / "catalog.json"
    ).load_all()
    military = next(item for item in catalog if item.category_id == "military")
    entries = [
        (node.id, node.row, node.column, int(node.max_level or 0))
        for node in military.nodes
    ]
    cards = [
        OcrCardLevel(x, 220, 325, 130, 0, 0, "full meter", True)
        for x in (216, 602, 990, 1350)
    ] + [
        OcrCardLevel(x, 625, 325, 130, 7, 10, "7/10")
        for x in (406, 794, 1182)
    ]
    candidates = map_ocr_card_levels_by_layout(cards, entries, 1485)
    assert {(item.research_id, item.level) for item in candidates} == {
        ("military_royal_guard", 1),
        ("military_fire_trebuchet", 1),
        ("military_stealth_sniper", 1),
        ("military_royal_cavalry", 1),
        ("military_army_defense_i", 7),
        ("military_army_offense_i", 7),
        ("military_army_health_i", 7),
    }


def test_spatial_ocr_pairs_label_with_value_on_the_same_row() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_label_values(
        [
            OcrLine("研 究 速 度", 541, 483, 85, 20),
            OcrLine("十 167.84 %", 689, 485, 103, 16),
            OcrLine("鍛 造 速 度", 541, 519, 85, 20),
            OcrLine("+ 125 %", 689, 521, 70, 16),
        ],
        profiles["ja-JP"],
    )
    assert [(item.label, item.value, item.numeric_value) for item in fields] == [
        ("研究速度", "+167.84%", 167.84),
        ("鍛造速度", "+125%", 125.0),
    ]


def test_spatial_ocr_applies_japanese_label_corrections() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_label_values(
        [
            OcrLine("良 新 生 産", 542, 627, 85, 20),
            OcrLine("十 826.75 %", 689, 629, 103, 17),
        ],
        profiles["ja-JP"],
    )
    assert [(item.label, item.value) for item in fields] == [
        ("食糧生産", "+826.75%")
    ]
    assert parse_ocr_percentage("十 167.84 %") == 167.84


def test_research_card_ocr_pairs_stacked_name_and_level() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_research_card_levels(
        [
            OcrLine("食糧収穫 I", 671, 232, 111, 24),
            OcrLine("9/10", 698, 272, 58, 21),
            OcrLine("保管庫管理", 149, 501, 110, 25),
            OcrLine("7/10", 177, 542, 58, 21),
        ],
        profiles["ja-JP"],
    )
    assert [(item.label, item.value) for item in fields] == [
        ("食糧収穫I", "9/10"),
        ("保管庫管理", "7/10"),
    ]


def test_observed_research_level_fields_become_progress_candidates() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_research_card_levels(
        [
            OcrLine("食糧収穫 I", 671, 232, 111, 24),
            OcrLine("9/10", 698, 272, 58, 21),
        ],
        profiles["ja-JP"],
    )
    candidates = parse_research_level_fields(
        fields,
        [("economy_food_harvest_1", "食糧収穫 I", 10)],
        profiles["ja-JP"],
    )
    assert [(item.research_id, item.level) for item in candidates] == [
        ("economy_food_harvest_1", 9)
    ]


def test_research_level_recovers_a_missing_leading_digit_in_known_maximum() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_research_card_levels(
        [
            OcrLine("建設速度", 162, 234, 84, 18),
            OcrLine("1、0_、0", 176, 277, 55, 16),
        ],
        profiles["ja-JP"],
    )
    candidates = parse_research_level_fields(
        fields,
        [("economy_construction_speed", "建設速度", 10)],
        profiles["ja-JP"],
    )
    assert [(item.research_id, item.level) for item in candidates] == [
        ("economy_construction_speed", 10)
    ]


def test_economy_card_ocr_maps_all_six_visible_levels() -> None:
    profiles = load_ocr_profiles(
        Path(__file__).resolve().parents[1] / "data" / "ocr" / "profiles"
    )
    fields = pair_ocr_research_card_levels(
        [
            OcrLine("保管庫管理", 45, 20, 110, 22),
            OcrLine("7 / 10", 80, 55, 45, 18),
            OcrLine("石材収穫ー", 305, 20, 110, 22),
            OcrLine("7 / 10", 340, 55, 45, 18),
            OcrLine("木材収穫ー", 565, 20, 110, 22),
            OcrLine("7 / 10", 600, 55, 45, 18),
            OcrLine("鉱石収穫ー", 825, 20, 110, 22),
            OcrLine("7 / 10", 860, 55, 45, 18),
            OcrLine("資源所持量ー", 45, 290, 120, 22),
            OcrLine("7 / 10", 80, 325, 45, 18),
            OcrLine("資源採取]", 565, 290, 110, 22),
            OcrLine("9 / 10", 600, 325, 45, 18),
        ],
        profiles["ja-JP"],
    )
    catalog = JsonResearchCatalogRepository(
        Path(__file__).resolve().parents[1] / "data" / "research" / "catalog.json"
    ).load_all()
    economy = next(item for item in catalog if item.category_id == "economy")
    entries = [
        (node.id, node.localized_name("ja-JP"), node.max_level)
        for node in economy.nodes
        if node.max_level is not None
    ]
    candidates = parse_research_level_fields(fields, entries, profiles["ja-JP"])
    assert {(item.research_id, item.level) for item in candidates} == {
        ("economy_vault_management", 7),
        ("economy_stone_harvest_1", 7),
        ("economy_timber_harvest_1", 7),
        ("economy_ore_harvest_1", 7),
        ("economy_weight_training_i", 7),
        ("economy_resource_harvesting_i", 9),
    }


def test_default_ocr_window_title() -> None:
    assert AppSettings().ocr_window_title == "Lords Mobile PC"
    assert DEFAULT_OCR_WINDOW_TITLE == "Lords Mobile PC"


def test_preferred_window_is_resolved_by_exact_title() -> None:
    windows = [
        CapturableWindow(10, "Other Window", 0, 0, 800, 600),
        CapturableWindow(20, "Lords Mobile PC", 0, 0, 1280, 720),
    ]
    assert preferred_window_index(windows, "lords mobile pc") == 1
    assert preferred_window_index(windows, "Loads Mobile PC") == -1


def test_fullscreen_matching_uses_physical_monitor_coordinates() -> None:
    monitor = wintypes.RECT(-1920, 0, 0, 1080)

    assert rectangles_match(wintypes.RECT(-1920, 0, 0, 1080), monitor)
    assert rectangles_match(
        wintypes.RECT(-1919, 1, -1, 1079), monitor, tolerance=2
    )
    assert not rectangles_match(
        wintypes.RECT(-1920, 0, 0, 1040), monitor, tolerance=2
    )


def test_window_ocr_refreshes_the_current_frame_but_opened_images_do_not() -> None:
    assert should_refresh_window_before_ocr("") is True
    assert should_refresh_window_before_ocr("window") is True
    assert should_refresh_window_before_ocr("file") is False


def test_economy_tree_observation_references_known_observation_nodes() -> None:
    path = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "research"
        / "observations"
        / "economy_tree_ja-JP_2026-08-06.json"
    )
    if not path.is_file():
        pytest.skip("Private observation records are not included in public releases.")
    raw = json.loads(path.read_text(encoding="utf-8"))
    node_ids = {item["id"] for item in raw["nodes"]}
    assert len(node_ids) == 6
    assert all(item["max_level"] == 10 for item in raw["nodes"])
    assert all(
        edge["prerequisite_id"] in node_ids and edge["research_id"] in node_ids
        for edge in raw["edges"]
    )


def test_observation_repository_loads_verified_partial_tree() -> None:
    directory = (
        Path(__file__).resolve().parents[1]
        / "data"
        / "research"
        / "observations"
    )
    if not directory.is_dir():
        pytest.skip("Private observation records are not included in public releases.")
    observations = JsonObservationRepository(directory).load_all()
    assert len(observations) == 1
    observation = observations[0]
    assert observation.localized_title("ja-JP") == "経済（実画面確認・一部）"
    assert len(observation.nodes) == 6
    assert len(observation.edges) == 4
    assert observation.captured_on == "2026-08-06"
