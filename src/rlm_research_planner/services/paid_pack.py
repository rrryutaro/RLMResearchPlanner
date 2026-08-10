from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from rlm_research_planner.services.ocr import OcrLine


SPEEDUP_KINDS = ("general", "research", "training")


@dataclass(frozen=True)
class SpeedupEntry:
    kind: str
    duration_seconds: int
    quantity: int
    label: str = ""
    duration_value: int | None = None
    duration_unit: str = ""

    @property
    def total_seconds(self) -> int:
        return max(0, self.duration_seconds) * max(0, self.quantity)


@dataclass(frozen=True)
class SpeedupSummary:
    kind: str
    total_seconds: int
    diamond_cost: int

    @property
    def seconds_per_diamond(self) -> int | None:
        if self.diamond_cost <= 0 or self.total_seconds <= 0:
            return None
        return round(self.total_seconds / self.diamond_cost)


@dataclass(frozen=True)
class GemBundle:
    included_gems: int = 0
    bonus_gems: int = 0

    @property
    def total_gems(self) -> int:
        return max(0, self.included_gems) + max(0, self.bonus_gems)


_DURATION_PATTERN = re.compile(
    r"(?P<amount>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>days?|day|d|hours?|hour|hrs?|hr|h|minutes?|minute|mins?|min|m|"
    r"seconds?|second|secs?|sec|s|日|時間|時|分|秒)",
    re.IGNORECASE,
)
_INTEGER_PATTERN = re.compile(r"\d[\d,]*")


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text).replace("×", "x")


def _speedup_kind(text: str) -> str | None:
    normalized = _normalized(text)
    compact = re.sub(r"[\s_\-]+", "", normalized).casefold()
    compact = compact.replace("スビード", "スピード").replace(
        "スピド", "スピード"
    )
    if "スピードアップ" not in compact and "speedup" not in compact:
        return None
    if "研究" in compact or "research" in compact:
        return "research"
    if "訓練" in compact or "training" in compact:
        return "training"
    if "建設" in compact or "construction" in compact or "building" in compact:
        return "construction"
    return "general"


def _canonical_duration_unit(unit: str) -> str:
    normalized_unit = unit.casefold()
    if normalized_unit in {"日", "d", "day", "days"}:
        return "days"
    if normalized_unit in {
        "時間",
        "時",
        "h",
        "hr",
        "hrs",
        "hour",
        "hours",
    }:
        return "hours"
    if normalized_unit in {
        "分",
        "m",
        "min",
        "mins",
        "minute",
        "minutes",
    }:
        return "minutes"
    return "seconds"


def _duration_seconds(amount: str, unit: str) -> int:
    value = float(amount.replace(",", "."))
    multiplier = {
        "days": 86400,
        "hours": 3600,
        "minutes": 60,
        "seconds": 1,
    }[_canonical_duration_unit(unit)]
    return max(0, round(value * multiplier))


def _parse_speedup_line(
    text: str, *, quantity_override: int | None = None
) -> SpeedupEntry | None:
    normalized = _normalized(text)
    normalized = re.sub(
        r"(?<=\d)[dDoO](?=\s*(?:分|秒|minutes?|mins?|min|seconds?|secs?|sec))",
        "0",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(
        r"ろ\s*0(?=\s*(?:分|m(?:in)?))",
        "30",
        normalized,
        flags=re.IGNORECASE,
    )
    normalized = re.sub(r"ろ(?=\s*(?:時間|時))", "3", normalized)
    if "%" in normalized:
        return None
    kind = _speedup_kind(normalized)
    if kind is None:
        return None
    duration_match = _DURATION_PATTERN.search(normalized)
    if duration_match is None:
        return None
    duration_seconds = _duration_seconds(
        duration_match.group("amount"), duration_match.group("unit")
    )
    parsed_duration = float(duration_match.group("amount").replace(",", "."))
    duration_value = int(parsed_duration) if parsed_duration.is_integer() else None
    duration_unit = _canonical_duration_unit(duration_match.group("unit"))
    quantity = quantity_override
    if quantity is None:
        remainder = normalized[duration_match.end() :]
        quantity_match = _INTEGER_PATTERN.search(remainder)
        if quantity_match is not None:
            quantity = int(quantity_match.group(0).replace(",", ""))
    if duration_seconds <= 0 or quantity is None or quantity <= 0:
        return None
    return SpeedupEntry(
        kind=kind,
        duration_seconds=duration_seconds,
        quantity=quantity,
        label=" ".join(normalized.split()),
        duration_value=duration_value,
        duration_unit=duration_unit,
    )


def parse_speedup_text(text: str) -> tuple[SpeedupEntry, ...]:
    entries: list[SpeedupEntry] = []
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines:
        entry = _parse_speedup_line(line)
        if entry is not None:
            entries.append(entry)
    return _deduplicate(entries)


def _numeric_line_value(text: str) -> int | None:
    compact = re.sub(r"\s+", "", _normalized(text))
    if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+", compact):
        return int(re.sub(r"[,.]", "", compact))
    if re.fullmatch(r"\d[\d,]*", compact) is None:
        return None
    return int(compact.replace(",", ""))


def _embedded_numeric_value(text: str) -> int | None:
    compact = re.sub(r"\s+", "", _normalized(text))
    matches = re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d+", compact)
    if not matches:
        return None
    candidate = matches[-1]
    return int(re.sub(r"[,.]", "", candidate))


def _quantity_to_right(label: OcrLine, lines: Iterable[OcrLine]) -> int | None:
    lines = tuple(lines)
    label_center_y = label.y + label.height / 2.0
    candidates: list[tuple[float, float, float, int]] = []
    partial_candidates: list[tuple[float, float, str]] = []
    for line in lines:
        value = _numeric_line_value(line.text)
        if line.x <= label.x + label.width * 0.7:
            continue
        center_y = line.y + line.height / 2.0
        tolerance = max(18.0, label.height, line.height) * 0.85
        center_distance = abs(center_y - label_center_y)
        if (
            center_distance > tolerance
            or line.height > max(64.0, label.height * 2.0)
        ):
            continue
        if value is not None and value > 0:
            height_penalty = abs(line.height - label.height)
            candidates.append(
                (center_distance, height_penalty, line.x, value)
            )
            continue
        compact = re.sub(r"\s+", "", _normalized(line.text))
        digits = "".join(re.findall(r"\d", compact))
        if digits and re.search(r"[^\d,.]", compact):
            partial_candidates.append((center_distance, line.x, digits))
    if not candidates:
        return None
    counts = Counter(candidate[3] for candidate in candidates)
    selected_value = max(
        counts,
        key=lambda value: (
            counts[value],
            len(str(value)),
            -min(
                candidate[0]
                for candidate in candidates
                if candidate[3] == value
            ),
            value,
        ),
    )
    selected = min(
        (candidate for candidate in candidates if candidate[3] == selected_value),
        key=lambda candidate: (candidate[0], candidate[1]),
    )
    if selected_value < 10:
        for _distance, partial_x, prefix in sorted(partial_candidates):
            glyph_distance = max(
                label.height,
                next(
                    (
                        line.height
                        for line in lines
                        if line.x == selected[2]
                        and _numeric_line_value(line.text) == selected_value
                    ),
                    label.height,
                ),
            )
            if (
                abs(partial_x - selected[2]) > glyph_distance * 2.75
                or prefix == str(selected_value)
            ):
                continue
            combined = int(f"{prefix}{selected_value}")
            if 10 <= combined <= 500:
                return combined
    return selected_value


def parse_speedup_ocr(
    text: str, line_groups: Iterable[Iterable[OcrLine]]
) -> tuple[SpeedupEntry, ...]:
    candidates: list[tuple[float, SpeedupEntry, int, float, float]] = []
    groups = tuple(tuple(group) for group in line_groups)
    all_lines = tuple(line for group in groups for line in group)
    for group in groups:
        for line in group:
            if _speedup_kind(line.text) is None:
                continue
            line_center_y = line.y + line.height / 2.0
            quantity = _quantity_to_right(line, all_lines)
            direct_entry = _parse_speedup_line(
                line.text,
                quantity_override=quantity,
            )
            if direct_entry is not None:
                candidates.append(
                    (line_center_y, direct_entry, 1, 0.0, float(line.height))
                )

            # Windows OCR often recognizes the small icon duration (30m, 3h)
            # in a different input variant from the item label.  Match every
            # duration fragment on the same visual row and put it first so a
            # damaged duration inside the long label cannot win.
            for duration_line in all_lines:
                if duration_line is line or _speedup_kind(duration_line.text) is not None:
                    continue
                duration_center_y = duration_line.y + duration_line.height / 2.0
                row_tolerance = max(line.height, duration_line.height) * 1.7
                if abs(duration_center_y - line_center_y) > row_tolerance:
                    continue
                if duration_line.x > line.x + max(
                    line.height * 2.85, line.width * 0.25
                ):
                    continue
                icon_entry = _parse_speedup_line(
                    f"{duration_line.text} {line.text}",
                    quantity_override=quantity,
                )
                if icon_entry is not None:
                    candidates.append(
                        (
                            line_center_y,
                            icon_entry,
                            2,
                            abs(duration_center_y - line_center_y),
                            float(max(line.height, duration_line.height)),
                        )
                    )
    entries = list(parse_speedup_text(text))
    row_clusters: list[
        list[tuple[float, SpeedupEntry, int, float, float]]
    ] = []
    for candidate in sorted(candidates, key=lambda item: item[0]):
        row = next(
            (
                cluster
                for cluster in row_clusters
                if cluster[0][1].kind == candidate[1].kind
                and abs(cluster[0][0] - candidate[0])
                <= max(cluster[0][4], candidate[4]) * 0.9
            ),
            None,
        )
        if row is None:
            row_clusters.append([candidate])
        else:
            row.append(candidate)
    common_durations = {
        60,
        300,
        600,
        900,
        1800,
        3600,
        10800,
        28800,
        54000,
        86400,
        259200,
        604800,
        2592000,
    }
    selected_rows = [
        max(
            cluster,
            key=lambda item: (
                item[2],
                -item[3],
                item[1].duration_seconds in common_durations,
                item[1].quantity <= 500,
                -item[1].quantity,
            ),
        )
        for cluster in row_clusters
    ]
    for y, entry, _confidence, _duration_distance, row_height in selected_rows:
        if entry.kind == "general" and any(
            other.kind in {"research", "training"}
            and abs(other_y - y) <= max(row_height, other_height) * 0.9
            for (
                other_y,
                other,
                _other_confidence,
                _other_distance,
                other_height,
            ) in selected_rows
        ):
            continue
        entries.append(entry)
    return _deduplicate(entries)


def _deduplicate(entries: Iterable[SpeedupEntry]) -> tuple[SpeedupEntry, ...]:
    unique: dict[tuple[str, int, int], SpeedupEntry] = {}
    for entry in entries:
        key = (entry.kind, entry.duration_seconds, entry.quantity)
        unique.setdefault(key, entry)
    return tuple(unique.values())


def detect_pack_price(
    line_groups: Iterable[Iterable[OcrLine]],
    *,
    image_width: int,
    image_height: int,
) -> int | None:
    if image_width <= 0 or image_height <= 0:
        return None
    candidates: set[int] = set()
    for group in line_groups:
        for line in group:
            value = _numeric_line_value(line.text)
            center_x = line.x + line.width / 2.0
            center_y = line.y + line.height / 2.0
            compact_digits = re.sub(r"[\s,.]+", "", _normalized(line.text))
            if (
                (value is None or value == 0)
                and center_y >= image_height * 0.90
                and re.fullmatch(r"0{2,4}", compact_digits)
            ):
                # The outlined lower price used by the game is consistently
                # read as zeroes by Windows OCR (for example 999 -> 0 0 0).
                value = int("9" * len(compact_digits))
            if (
                value is not None
                and value >= 10
                and image_width * 0.30 <= center_x <= image_width * 0.70
                and center_y >= image_height * 0.58
            ):
                candidates.add(value)
    return min(candidates) if candidates else None


def parse_gem_bundle(
    line_groups: Iterable[Iterable[OcrLine]],
    *,
    image_width: int,
    image_height: int,
) -> GemBundle:
    if image_width <= 0 or image_height <= 0:
        return GemBundle()
    included_votes: list[tuple[int, float]] = []
    bonus_votes: list[tuple[int, float]] = []
    for group in line_groups:
        included_candidates: list[tuple[float, int]] = []
        bonus_candidates: list[tuple[float, int]] = []
        for line in group:
            value = _numeric_line_value(line.text)
            if value is None:
                value = _embedded_numeric_value(line.text)
            if value is None or not 100 <= value <= 10_000_000:
                continue
            center_x = line.x + line.width / 2.0
            center_y = line.y + line.height / 2.0
            if not (
                image_width * 0.15 <= center_x <= image_width * 0.75
                and image_height * 0.20 <= center_y <= image_height * 0.48
            ):
                continue
            if center_x >= image_width * 0.40:
                distance = abs(center_x - image_width * 0.52)
                included_candidates.append((distance, value))
            else:
                distance = abs(center_x - image_width * 0.28)
                bonus_candidates.append((distance, value))
        if included_candidates:
            distance, value = min(included_candidates)
            included_votes.append((value, distance))
        if bonus_candidates:
            distance, value = min(bonus_candidates)
            bonus_votes.append((value, distance))

    def consensus(votes: list[tuple[int, float]]) -> int:
        if not votes:
            return 0
        counts = Counter(value for value, _distance in votes)
        distances = {
            value: sum(distance for candidate, distance in votes if candidate == value)
            for value in counts
        }
        return max(
            counts,
            key=lambda value: (counts[value], -distances[value]),
        )

    return GemBundle(
        included_gems=consensus(included_votes),
        bonus_gems=consensus(bonus_votes),
    )


def summarize_speedups(
    entries: Iterable[SpeedupEntry], diamond_cost: int
) -> tuple[SpeedupSummary, ...]:
    totals = {kind: 0 for kind in SPEEDUP_KINDS}
    for entry in entries:
        if entry.kind in totals:
            totals[entry.kind] += entry.total_seconds
    summaries = [
        SpeedupSummary(kind, totals[kind], max(0, diamond_cost))
        for kind in SPEEDUP_KINDS
    ]
    summaries.append(
        SpeedupSummary("all", sum(totals.values()), max(0, diamond_cost))
    )
    return tuple(summaries)
