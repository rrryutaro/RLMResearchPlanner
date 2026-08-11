from rlm_research_planner.services.ocr import OcrLine
from rlm_research_planner.services.paid_pack import (
    detect_pack_price,
    parse_gem_bundle,
    parse_paid_item_ocr,
    parse_speedup_ocr,
    parse_speedup_text,
    summarize_speedups,
)


def test_general_speedup_pack_total_and_time_per_diamond() -> None:
    entries = parse_speedup_text(
        "\n".join(
            (
                "スピードアップ 3時間 80",
                "スピードアップ 60分 65",
                "スピードアップ 30分 65",
            )
        )
    )

    summary = summarize_speedups(entries, 999)[0]

    assert summary.total_seconds == 1_215_000
    assert summary.seconds_per_diamond == 1_216


def test_research_pack_ignores_percentage_boost() -> None:
    entries = parse_speedup_text(
        "\n".join(
            (
                "研究スピードアップ 8時間 50",
                "研究スピードアップ 3時間 50",
                "研究スピードアップ 60分 50",
                "研究スピードアップ 10% 2",
            )
        )
    )

    summary = summarize_speedups(entries, 999)[1]

    assert len(entries) == 3
    assert summary.total_seconds == 2_160_000


def test_construction_speedup_is_kept_as_its_own_kind_for_offer_value() -> None:
    entries = parse_speedup_text("建設スピードアップ 3時間 10")

    assert len(entries) == 1
    assert entries[0].kind == "construction"
    assert entries[0].total_seconds == 30 * 3600


def test_ocr_confusion_between_zero_and_d_is_corrected_before_minutes() -> None:
    entries = parse_speedup_text("スピードアップ 3D分 65")

    assert len(entries) == 1
    assert entries[0].total_seconds == 30 * 60 * 65
    assert entries[0].duration_value == 30
    assert entries[0].duration_unit == "minutes"


def test_icon_duration_can_complete_a_label_with_missing_duration() -> None:
    lines = (
        OcrLine("スピードアップ", 330, 460, 300, 28),
        OcrLine("30m", 265, 488, 40, 16),
        OcrLine("65", 995, 458, 42, 28),
    )

    entries = parse_speedup_ocr("", (lines,))

    assert len(entries) == 1
    assert entries[0].duration_seconds == 30 * 60
    assert entries[0].quantity == 65


def test_icon_duration_from_another_ocr_variant_overrides_damaged_label() -> None:
    label_variant = (
        OcrLine("Speed Up 5m", 330, 460, 300, 28),
        OcrLine("65", 995, 458, 42, 28),
    )
    icon_variant = (OcrLine("30m", 265, 488, 40, 16),)

    entries = parse_speedup_ocr("", (label_variant, icon_variant))

    assert len(entries) == 1
    assert entries[0].duration_seconds == 30 * 60
    assert entries[0].duration_value == 30
    assert entries[0].duration_unit == "minutes"
    assert entries[0].quantity == 65


def test_training_icon_duration_from_another_variant_fills_missing_label() -> None:
    label_variant = (
        OcrLine("Training Speed Up", 330, 460, 300, 28),
        OcrLine("60", 995, 458, 42, 28),
    )
    icon_variant = (OcrLine("3h", 265, 488, 40, 16),)

    entries = parse_speedup_ocr("", (label_variant, icon_variant))

    assert len(entries) == 1
    assert entries[0].duration_seconds == 3 * 3600
    assert entries[0].duration_value == 3
    assert entries[0].duration_unit == "hours"
    assert entries[0].quantity == 60


def test_nearest_icon_duration_wins_between_adjacent_pack_rows() -> None:
    labels = (
        OcrLine("Research Speed Up", 334, 405, 310, 24),
        OcrLine("50", 995, 404, 41, 28),
        OcrLine("Research Speed Up 60m", 334, 467, 300, 24),
        OcrLine("50", 995, 466, 41, 28),
    )
    icons = (
        OcrLine("3h", 274, 426, 21, 16),
        OcrLine("60m", 266, 488, 37, 15),
    )

    entries = parse_speedup_ocr("", (labels, icons))

    assert {
        (entry.duration_value, entry.duration_unit, entry.quantity)
        for entry in entries
    } == {(3, "hours", 50), (60, "minutes", 50)}


def test_split_quantity_glyphs_are_recombined_on_the_same_row() -> None:
    label_variant = (
        OcrLine("Speed Up 30m", 103, 279, 250, 28),
        OcrLine("5", 780, 276, 18, 32),
    )
    partial_variant = (OcrLine("6 �", 763, 276, 41, 32),)

    entries = parse_speedup_ocr("", (label_variant, partial_variant))

    assert len(entries) == 1
    assert entries[0].duration_seconds == 30 * 60
    assert entries[0].quantity == 65


def test_complete_multi_digit_quantity_beats_single_digit_variant() -> None:
    label = OcrLine("Speed Up 30m", 103, 279, 250, 28)
    entries = parse_speedup_ocr(
        "",
        (
            (label, OcrLine("5", 780, 276, 18, 32)),
            (OcrLine("65", 763, 276, 41, 32),),
        ),
    )

    assert len(entries) == 1
    assert entries[0].quantity == 65


def test_training_pack_uses_quantity_from_right_hand_ocr_column() -> None:
    lines = (
        OcrLine("訓練スピードアップ 24時間", 300, 330, 500, 42),
        OcrLine("50", 995, 332, 48, 42),
        OcrLine("訓練スピードアップ 8時間", 300, 395, 500, 42),
        OcrLine("60", 995, 397, 48, 42),
        OcrLine("訓練スピードアップ 3時間", 300, 460, 500, 42),
        OcrLine("60", 995, 462, 48, 42),
        OcrLine("訓練スピードアップ 20%", 300, 265, 500, 42),
        OcrLine("2", 995, 267, 30, 42),
    )

    entries = parse_speedup_ocr("", (lines,))
    summary = summarize_speedups(entries, 999)[2]

    assert len(entries) == 3
    assert summary.total_seconds == 6_696_000
    three_hour = next(entry for entry in entries if entry.duration_seconds == 10_800)
    assert three_hour.duration_value == 3
    assert three_hour.duration_unit == "hours"


def test_paid_pack_ocr_includes_resources_chests_and_percentage_boosts() -> None:
    lines = (
        OcrLine("研究スピードアップ 3時間", 300, 330, 500, 42),
        OcrLine("50", 995, 332, 48, 42),
        OcrLine("研究スピードアップ 10%", 300, 395, 500, 42),
        OcrLine("2", 995, 397, 30, 42),
        OcrLine("食糧 500,000", 300, 460, 500, 42),
        OcrLine("130", 980, 462, 64, 42),
        OcrLine("キラービーの宝箱", 300, 525, 500, 42),
        OcrLine("50", 995, 527, 48, 42),
    )

    entries = parse_paid_item_ocr("", (lines, lines))

    assert len(entries) == 4
    assert (entries[0].kind, entries[0].duration_seconds, entries[0].quantity) == (
        "research",
        3 * 3600,
        50,
    )
    assert {
        (entry.kind, entry.name, entry.quantity)
        for entry in entries[1:]
    } == {
        ("boost_item", "研究スピードアップ 10%", 2),
        ("resource", "食糧 500,000", 130),
        ("chest", "キラービーの宝箱", 50),
    }


def test_paid_pack_ocr_accepts_a_whole_item_row_as_one_ocr_line() -> None:
    lines = (
        OcrLine("食糧 500,000 130", 300, 395, 740, 42),
        OcrLine("キラービーの宝箱 50", 300, 460, 740, 42),
        OcrLine("研究スピードアップ 10% 2", 300, 525, 740, 42),
    )

    entries = parse_paid_item_ocr("", (lines,))

    assert {
        (entry.kind, entry.name, entry.quantity) for entry in entries
    } == {
        ("resource", "食糧 500,000", 130),
        ("chest", "キラービーの宝箱", 50),
        ("boost_item", "研究スピードアップ 10%", 2),
    }


def test_discounted_pack_price_is_selected_from_bottom_center() -> None:
    lines = (
        OcrLine("3,600", 610, 210, 120, 44),
        OcrLine("4,400", 310, 280, 120, 44),
        OcrLine("1,999", 610, 650, 120, 44),
        OcrLine("999", 625, 700, 100, 44),
        OcrLine("2", 1180, 700, 25, 35),
    )

    assert (
        detect_pack_price((lines,), image_width=1280, image_height=720) == 999
    )


def test_outlined_price_zero_shapes_are_corrected_to_nines() -> None:
    lines = (OcrLine("0 0 0", 649, 695, 57, 17),)

    assert (
        detect_pack_price((lines,), image_width=1280, image_height=720) == 999
    )


def test_gem_bundle_uses_consensus_across_ocr_variants() -> None:
    groups = (
        (
            OcrLine("3,600", 610, 215, 120, 44),
            OcrLine("4,400", 310, 280, 120, 44),
        ),
        (
            OcrLine("5,600", 610, 215, 120, 44),
            OcrLine("4,400", 310, 280, 120, 44),
        ),
        (
            OcrLine("3 , 600", 610, 215, 120, 44),
            OcrLine("十 4 , 400", 310, 280, 120, 44),
        ),
    )

    bundle = parse_gem_bundle(groups, image_width=1280, image_height=720)

    assert bundle.included_gems == 3600
    assert bundle.bonus_gems == 4400
    assert bundle.total_gems == 8000


def test_speedup_rows_scale_with_every_supported_game_resolution() -> None:
    base_labels = (
        OcrLine("Speed Up", 330, 395, 300, 28),
        OcrLine("80", 995, 393, 42, 28),
        OcrLine("Speed Up", 330, 460, 300, 28),
        OcrLine("65", 995, 458, 42, 28),
    )
    base_icons = (
        OcrLine("3h", 265, 423, 40, 16),
        OcrLine("30m", 265, 488, 40, 16),
    )

    def scaled(line: OcrLine, width: int, height: int) -> OcrLine:
        return OcrLine(
            line.text,
            round(line.x * width / 1280),
            round(line.y * height / 720),
            max(1, round(line.width * width / 1280)),
            max(1, round(line.height * height / 720)),
        )

    for width, height in (
        (1024, 576),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ):
        entries = parse_speedup_ocr(
            "",
            (
                tuple(scaled(line, width, height) for line in base_labels),
                tuple(scaled(line, width, height) for line in base_icons),
            ),
        )

        assert {
            (entry.duration_seconds, entry.quantity) for entry in entries
        } == {(3 * 3600, 80), (30 * 60, 65)}
