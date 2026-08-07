from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Iterable, Protocol

from rlm_research_planner.domain.models import MasterData


@dataclass(frozen=True)
class OcrProfile:
    locale: str
    status: str
    engine_languages: str
    level_patterns: tuple[str, ...]
    normalization_replacements: tuple[tuple[str, str], ...]
    notes: str


@dataclass(frozen=True)
class OcrResult:
    text: str
    engine: str
    locale: str
    warning: str = ""
    lines: tuple["OcrLine", ...] = ()


@dataclass(frozen=True)
class OcrLine:
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class OcrCandidate:
    research_id: str
    level: int
    evidence: str


@dataclass(frozen=True)
class OcrFieldCandidate:
    label: str
    value: str
    numeric_value: float | None
    unit: str
    evidence: str
    y: float


@dataclass(frozen=True)
class OcrCardLevel:
    x: float
    y: float
    width: float
    height: float
    current_level: int
    displayed_max: int
    evidence: str
    is_complete: bool = False
    fill_ratio: float | None = None


class OcrEngine(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def name(self) -> str: ...

    def recognize_png(self, png_data: bytes, profile: OcrProfile) -> OcrResult: ...


class TesseractOcrEngine:
    def __init__(self, executable: str | None = None) -> None:
        self.executable = executable or shutil.which("tesseract")

    @property
    def available(self) -> bool:
        return bool(self.executable)

    @property
    def name(self) -> str:
        return "Tesseract"

    def recognize_png(self, png_data: bytes, profile: OcrProfile) -> OcrResult:
        if not self.executable:
            raise RuntimeError("Tesseract executable was not found")
        process = subprocess.run(
            [
                self.executable,
                "stdin",
                "stdout",
                "-l",
                profile.engine_languages,
                "--psm",
                "6",
            ],
            input=png_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=30,
        )
        if process.returncode != 0:
            detail = process.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "Tesseract failed")
        return OcrResult(
            text=process.stdout.decode("utf-8", errors="replace").strip(),
            engine=self.name,
            locale=profile.locale,
            warning="" if profile.status == "verified" else profile.notes,
        )


class WindowsOcrEngine:
    def __init__(self, script_path: Path, executable: str | None = None) -> None:
        self.script_path = Path(script_path)
        self.executable = executable or shutil.which("powershell.exe")

    @property
    def available(self) -> bool:
        return os.name == "nt" and bool(self.executable) and self.script_path.is_file()

    @property
    def name(self) -> str:
        return "Windows OCR"

    def recognize_png(self, png_data: bytes, profile: OcrProfile) -> OcrResult:
        if not self.available or not self.executable:
            raise RuntimeError("Windows OCR is not available")
        request = json.dumps(
            {
                "locale": profile.locale,
                "png_base64": base64.b64encode(png_data).decode("ascii"),
            },
            ensure_ascii=True,
        ).encode("utf-8")
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.run(
            [
                self.executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script_path),
            ],
            input=request,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=45,
            creationflags=creation_flags,
        )
        if process.returncode != 0:
            detail = process.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(detail or "Windows OCR failed")
        try:
            raw = json.loads(process.stdout.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Windows OCR returned an invalid response") from exc
        lines = tuple(
            OcrLine(
                text=str(item.get("text", "")),
                x=float(item.get("x", 0.0)),
                y=float(item.get("y", 0.0)),
                width=float(item.get("width", 0.0)),
                height=float(item.get("height", 0.0)),
            )
            for item in raw.get("lines", [])
            if isinstance(item, dict)
        )
        return OcrResult(
            text=(
                "\n".join(line.text for line in lines).strip()
                or str(raw.get("text", "")).strip()
            ),
            engine=self.name,
            locale=profile.locale,
            warning="" if profile.status == "verified" else profile.notes,
            lines=lines,
        )


class PreferredOcrEngine:
    def __init__(self, *engines: OcrEngine) -> None:
        self.engines = tuple(engines)

    @property
    def available(self) -> bool:
        return any(engine.available for engine in self.engines)

    @property
    def name(self) -> str:
        names = [engine.name for engine in self.engines if engine.available]
        return " / ".join(names) if names else ""

    def recognize_png(self, png_data: bytes, profile: OcrProfile) -> OcrResult:
        errors: list[str] = []
        for engine in self.engines:
            if not engine.available:
                continue
            try:
                return engine.recognize_png(png_data, profile)
            except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
                errors.append(f"{engine.name}: {exc}")
        if errors:
            raise RuntimeError("\n".join(errors))
        raise RuntimeError("No OCR engine is available")


def load_ocr_profiles(directory: Path) -> dict[str, OcrProfile]:
    profiles: dict[str, OcrProfile] = {}
    for path in sorted(Path(directory).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        profile = OcrProfile(
            locale=str(raw["locale"]),
            status=str(raw["status"]),
            engine_languages=str(raw["engine_languages"]),
            level_patterns=tuple(str(value) for value in raw.get("level_patterns", [])),
            normalization_replacements=tuple(
                (str(source), str(replacement))
                for source, replacement in raw.get(
                    "normalization_replacements", {}
                ).items()
            ),
            notes=str(raw.get("notes", "")),
        )
        profiles[profile.locale] = profile
    return profiles


def normalize_ocr_label(text: str, profile: OcrProfile) -> str:
    value = re.sub(r"\s+", "", text.strip())
    for source, replacement in profile.normalization_replacements:
        value = value.replace(source, replacement)
    return value.strip("|:：・,，。")


def normalize_ocr_value(text: str) -> tuple[str, str] | None:
    value = re.sub(r"\s+", "", text).translate(
        str.maketrans(
            "０１２３４５６７８９＋％．，〇",
            "0123456789+%..0",
        )
    )
    if value.startswith("十"):
        value = "+" + value[1:]

    if "%" in value:
        value = value.replace("O", "0").replace("o", "0")
        value = re.sub(r"(?<=\d)ろ(?=[\d.])", "5", value)
        value = re.sub(r"(?<=[+.])ろ(?=\d)", "5", value)
        if re.fullmatch(r"[+-]?\d+(?:\.\d+)?%", value):
            return value, "%"

    duration = value.replace("O", "0").replace("o", "0")
    duration = re.sub(r"(?<=\d)ろ(?=\d|:)", "5", duration)
    if re.fullmatch(r"(?:\d+[dD])?\d{1,2}:\d{1,2}:\d{1,2}", duration):
        return duration.lower(), "duration"

    fraction = (
        value.replace("O", "0")
        .replace("o", "0")
        .replace("、", "")
        .replace("_", "/")
        .replace("＿", "/")
    )
    fraction = fraction.replace("\\", "/")
    if "/" not in fraction and re.fullmatch(r"[0-9OolI]+\|[0-9OolI]+", fraction):
        fraction = fraction.replace("|", "/", 1)
    fraction_parts = fraction.split("/")
    if len(fraction_parts) == 2:
        fraction_parts = [
            part.translate(
                str.maketrans(
                    {"O": "0", "o": "0", "I": "1", "l": "1", "|": "1"}
                )
            )
            for part in fraction_parts
        ]
        if all(re.fullmatch(r"\d+", part) for part in fraction_parts):
            return "/".join(fraction_parts), "level"
    return None


def parse_ocr_percentage(value: str) -> float | None:
    normalized = normalize_ocr_value(value)
    if normalized is None or normalized[1] != "%":
        return None
    try:
        return float(normalized[0].removesuffix("%"))
    except ValueError:
        return None


def pair_ocr_label_values(
    lines: tuple[OcrLine, ...] | list[OcrLine],
    profile: OcrProfile,
) -> list[OcrFieldCandidate]:
    values: list[tuple[OcrLine, str, str]] = []
    labels: list[tuple[OcrLine, str]] = []
    for line in lines:
        normalized_value = normalize_ocr_value(line.text)
        if normalized_value is not None:
            values.append((line, normalized_value[0], normalized_value[1]))
            continue
        label = normalize_ocr_label(line.text, profile)
        if len(label) >= 2 and re.search(r"[^\W\d_]", label, flags=re.UNICODE):
            labels.append((line, label))

    candidates: list[OcrFieldCandidate] = []
    for value_line, value, unit in values:
        value_center = value_line.y + value_line.height / 2.0
        matches: list[tuple[float, float, OcrLine, str]] = []
        for label_line, label in labels:
            if label_line.x >= value_line.x:
                continue
            label_center = label_line.y + label_line.height / 2.0
            vertical_distance = abs(label_center - value_center)
            tolerance = max(12.0, min(24.0, (label_line.height + value_line.height) * 0.7))
            if vertical_distance > tolerance:
                continue
            horizontal_gap = max(
                0.0,
                value_line.x - (label_line.x + label_line.width),
            )
            matches.append(
                (vertical_distance, horizontal_gap, label_line, label)
            )
        if not matches:
            continue
        _, _, label_line, label = min(matches, key=lambda item: (item[0], item[1]))
        numeric_value = parse_ocr_percentage(value)
        candidates.append(
            OcrFieldCandidate(
                label=label,
                value=value,
                numeric_value=numeric_value,
                unit=unit,
                evidence=f"{label_line.text.strip()} | {value_line.text.strip()}",
                y=(label_line.y + value_line.y) / 2.0,
            )
        )
    return sorted(candidates, key=lambda item: item.y)


def pair_ocr_research_card_levels(
    lines: tuple[OcrLine, ...] | list[OcrLine],
    profile: OcrProfile,
) -> list[OcrFieldCandidate]:
    values: list[tuple[OcrLine, str]] = []
    labels: list[tuple[OcrLine, str]] = []
    for line in lines:
        normalized_value = normalize_ocr_value(line.text)
        if normalized_value is not None and normalized_value[1] == "level":
            values.append((line, normalized_value[0]))
            continue
        label = normalize_ocr_label(line.text, profile)
        if len(label) >= 2 and re.search(r"[^\W\d_]", label, flags=re.UNICODE):
            labels.append((line, label))

    candidates: list[OcrFieldCandidate] = []
    for value_line, value in values:
        value_center_x = value_line.x + value_line.width / 2.0
        matches: list[tuple[float, float, OcrLine, str]] = []
        for label_line, label in labels:
            vertical_gap = value_line.y - (label_line.y + label_line.height)
            if vertical_gap < -4.0 or vertical_gap > 80.0:
                continue
            label_center_x = label_line.x + label_line.width / 2.0
            center_distance = abs(label_center_x - value_center_x)
            horizontal_tolerance = max(
                36.0, (label_line.width + value_line.width) * 0.45
            )
            if center_distance > horizontal_tolerance:
                continue
            matches.append((vertical_gap, center_distance, label_line, label))
        if not matches:
            continue
        _, _, label_line, label = min(matches, key=lambda item: (item[0], item[1]))
        candidates.append(
            OcrFieldCandidate(
                label=label,
                value=value,
                numeric_value=None,
                unit="level",
                evidence=f"{label_line.text.strip()} | {value_line.text.strip()}",
                y=(label_line.y + value_line.y) / 2.0,
            )
        )
    return sorted(candidates, key=lambda item: item.y)


def parse_research_level_fields(
    fields: Iterable[OcrFieldCandidate],
    research_entries: Iterable[tuple[str, str, int]],
    profile: OcrProfile,
) -> list[OcrCandidate]:
    entries = [
        (research_id, name, max_level, normalize_ocr_label(name, profile).casefold())
        for research_id, name, max_level in research_entries
        if name and max_level > 0
    ]
    candidates: list[OcrCandidate] = []
    seen_ids: set[str] = set()
    for field in fields:
        if field.unit != "level" or "/" not in field.value:
            continue
        try:
            current_text, displayed_max_text = field.value.split("/", 1)
            current_level = int(current_text)
            displayed_max = int(displayed_max_text)
        except ValueError:
            continue
        label = normalize_ocr_label(field.label, profile).casefold()
        matches = [
            entry
            for entry in entries
            if entry[3] == label
            or (len(entry[3]) >= 4 and entry[3] in label)
            or (len(label) >= 4 and label in entry[3])
        ]
        if not matches and label:
            scored = sorted(
                (
                    SequenceMatcher(None, label, entry[3]).ratio(),
                    entry,
                )
                for entry in entries
            )
            if scored:
                best_score, best_entry = scored[-1]
                second_score = scored[-2][0] if len(scored) > 1 else 0.0
                threshold = 0.72 if min(len(label), len(best_entry[3])) <= 4 else 0.62
                if best_score >= threshold and best_score - second_score >= 0.06:
                    matches = [best_entry]
        if not matches:
            continue
        research_id, name, max_level, _canonical_name = max(
            matches, key=lambda entry: len(entry[3])
        )
        if research_id in seen_ids:
            continue
        if displayed_max != max_level:
            missing_leading_digit = (
                max_level >= 10 and displayed_max == max_level % 10
            )
            if not missing_leading_digit:
                continue
            displayed_max = max_level
        if not 0 <= current_level <= max_level:
            continue
        seen_ids.add(research_id)
        candidates.append(
            OcrCandidate(
                research_id=research_id,
                level=current_level,
                evidence=f"{field.evidence} -> {name} {current_level}/{max_level}",
            )
        )
    return candidates


def parse_ocr_card_level(
    lines: Iterable[OcrLine],
    *,
    x: float,
    y: float,
    width: float,
    height: float,
) -> OcrCardLevel | None:
    for line in sorted(lines, key=lambda item: (item.y, item.x), reverse=True):
        normalized = normalize_ocr_value(line.text)
        if normalized is None or normalized[1] != "level":
            continue
        try:
            current_text, maximum_text = normalized[0].split("/", 1)
            current_level = int(current_text)
            displayed_max = int(maximum_text)
        except ValueError:
            continue
        if current_level < 0 or displayed_max < 0:
            continue
        return OcrCardLevel(
            x=x,
            y=y,
            width=width,
            height=height,
            current_level=current_level,
            displayed_max=displayed_max,
            evidence=line.text.strip(),
        )
    return None


def match_ocr_card_label(
    lines: Iterable[OcrLine],
    research_entries: Iterable[tuple[str, str, int]],
    profile: OcrProfile,
) -> tuple[str, int, str] | None:
    """Match a cropped card label without requiring its level text."""
    labels: list[tuple[str, str]] = []
    for line in lines:
        if normalize_ocr_value(line.text) is not None:
            continue
        normalized = normalize_ocr_label(line.text, profile).casefold()
        if len(normalized) >= 2 and re.search(
            r"[^\W\d_]", normalized, flags=re.UNICODE
        ):
            labels.append((normalized, line.text.strip()))
    entries = [
        (
            research_id,
            maximum,
            normalize_ocr_label(name, profile).casefold(),
        )
        for research_id, name, maximum in research_entries
        if name and maximum > 0
    ]
    scored: list[tuple[float, str, int, str]] = []
    for label, evidence in labels:
        for research_id, maximum, canonical in entries:
            if label == canonical:
                score = 1.0
            elif min(len(label), len(canonical)) >= 3 and (
                label in canonical or canonical in label
            ):
                score = 0.93
            else:
                score = SequenceMatcher(None, label, canonical).ratio()
            scored.append((score, research_id, maximum, evidence))
    if not scored:
        return None
    best_by_research: dict[str, tuple[float, str, int, str]] = {}
    for result in scored:
        prior = best_by_research.get(result[1])
        if prior is None or result[0] > prior[0]:
            best_by_research[result[1]] = result
    distinct_scores = sorted(best_by_research.values(), reverse=True)
    best_score, research_id, maximum, evidence = distinct_scores[0]
    second_score = distinct_scores[1][0] if len(distinct_scores) > 1 else 0.0
    if best_score < 0.72 or (
        best_score < 0.99 and best_score - second_score < 0.06
    ):
        return None
    return research_id, maximum, evidence


def map_ocr_card_levels_by_layout(
    cards: Iterable[OcrCardLevel],
    research_entries: Iterable[tuple[str, int, int, int]],
    image_width: int,
) -> list[OcrCandidate]:
    """Map OCR cards to a visible tree slice; ambiguous matches are not applied."""
    card_list = sorted(cards, key=lambda item: (item.y, item.x))
    entries = list(research_entries)
    if not card_list or not entries or image_width <= 0:
        return []
    maximum_column = max(column for _id, _row, column, _maximum in entries)
    column_count = maximum_column + 1
    entries_by_row: dict[int, list[tuple[int, str, int]]] = {}
    for research_id, row, column, maximum in entries:
        entries_by_row.setdefault(row, []).append((column, research_id, maximum))
    for row_entries in entries_by_row.values():
        row_entries.sort()
    available_rows = sorted({row for _id, row, _column, _maximum in entries})

    groups: list[list[tuple[int, OcrCardLevel]]] = []
    for card_index, card in enumerate(card_list):
        if not groups:
            groups.append([(card_index, card)])
            continue
        prior_y = sum(item[1].y for item in groups[-1]) / len(groups[-1])
        tolerance = max(card.height, *(item[1].height for item in groups[-1])) * 1.35
        if abs(card.y - prior_y) <= tolerance:
            groups[-1].append((card_index, card))
        else:
            groups.append([(card_index, card)])
    for group in groups:
        group.sort(key=lambda item: item[1].x)
    if len(groups) > len(available_rows):
        return []

    def maximum_matches(displayed: int, expected: int) -> bool:
        return displayed == expected or (
            expected >= 10 and displayed == expected % 10
        )

    def effective_level(card: OcrCardLevel, maximum: int) -> int:
        if card.is_complete:
            return maximum
        if (
            card.current_level == 0
            and card.displayed_max == 0
            and card.fill_ratio is not None
            and card.fill_ratio > 0
        ):
            return max(1, min(maximum, round(card.fill_ratio * maximum)))
        if maximum_matches(card.displayed_max, maximum):
            return card.current_level
        if card.fill_ratio is not None and card.fill_ratio > 0:
            return max(1, min(maximum, round(card.fill_ratio * maximum)))
        return card.current_level

    scored: list[tuple[int, dict[int, tuple[str, int]]]] = []
    for selected_rows in combinations(available_rows, len(groups)):
        skipped_rows = sum(
            max(0, next_row - previous_row - 1)
            for previous_row, next_row in zip(selected_rows, selected_rows[1:])
        )
        score = -2 * skipped_rows
        mapping: dict[int, tuple[str, int]] = {}
        for group, row in zip(groups, selected_rows):
            row_entries = entries_by_row[row]
            if len(group) > len(row_entries):
                score -= 12 * len(group)
                continue
            if len(group) == len(row_entries):
                selected_entries = tuple(row_entries)
                score += 6
            else:
                entry_choices = list(combinations(row_entries, len(group)))
                choice_scores = []
                for choice in entry_choices:
                    position_error = sum(
                        abs(
                            card.x / image_width
                            - (column + 0.5) / column_count
                        )
                        for (_card_index, card), (column, _research_id, _maximum)
                        in zip(group, choice)
                    )
                    choice_scores.append((position_error, choice))
                best_position_error = min(value for value, _choice in choice_scores)
                best_choices = [
                    choice
                    for value, choice in choice_scores
                    if abs(value - best_position_error) < 0.025
                ]
                if len(best_choices) != 1:
                    score -= 3 * len(group)
                    continue
                selected_entries = best_choices[0]
            for (card_index, card), (_column, research_id, maximum) in zip(
                group, selected_entries
            ):
                inferred_level = effective_level(card, maximum)
                score += (
                    5
                    if card.is_complete
                    or maximum_matches(card.displayed_max, maximum)
                    or card.fill_ratio is not None
                    else -5
                )
                if 0 <= inferred_level <= maximum:
                    score += 2
                    mapping[card_index] = (research_id, maximum)
                else:
                    score -= 8
        scored.append((score, mapping))
    if not scored:
        return []
    best_score = max(score for score, _mapping in scored)
    best_mappings = [mapping for score, mapping in scored if score == best_score]
    if best_score <= 0:
        return []

    candidates: list[OcrCandidate] = []
    seen_ids: set[str] = set()
    for card_index, card in enumerate(card_list):
        mapped_values = {
            mapping[card_index]
            for mapping in best_mappings
            if card_index in mapping
        }
        if len(mapped_values) != 1:
            continue
        research_id, maximum = next(iter(mapped_values))
        if research_id in seen_ids:
            continue
        seen_ids.add(research_id)
        inferred_level = effective_level(card, maximum)
        candidates.append(
            OcrCandidate(
                research_id=research_id,
                level=inferred_level,
                evidence=(
                    f"{card.evidence} -> layout {research_id} "
                    f"{inferred_level}/{maximum}"
                ),
            )
        )
    return candidates


def parse_research_candidates(
    text: str,
    master: MasterData,
    profile: OcrProfile,
) -> list[OcrCandidate]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        lines = [text]

    def canonical(value: str) -> str:
        value = re.sub(r"\s+", "", value)
        for source, replacement in profile.normalization_replacements:
            value = value.replace(source, replacement)
        return value.casefold()

    def levels_in(value: str) -> list[int]:
        found: list[int] = []
        for pattern in profile.level_patterns:
            for match in re.finditer(pattern, value, flags=re.IGNORECASE):
                try:
                    found.append(int(match.group(1)))
                except (IndexError, ValueError):
                    continue
        return found

    candidates: list[OcrCandidate] = []
    for research in master.research:
        localized = master.localized_research(research.id, profile.locale)
        names = {localized.name, research.id.replace("_", " ")}
        match: tuple[int, str] | None = None
        for index, line in enumerate(lines):
            line_value = canonical(line)
            matched_name = next(
                (name for name in names if name and canonical(name) in line_value),
                None,
            )
            if matched_name is not None:
                match = (index, matched_name)
                break
        if match is None:
            continue
        index, matched_name = match
        nearby = lines[index]
        if index + 1 < len(lines):
            nearby += " " + lines[index + 1]
        level = next(
            (
                value
                for value in levels_in(nearby)
                if 0 <= value <= research.max_level
            ),
            0,
        )
        candidates.append(
            OcrCandidate(
                research_id=research.id,
                level=level,
                evidence=f"Matched '{matched_name}'" + (f" and level {level}" if level else ""),
            )
        )
    return candidates
