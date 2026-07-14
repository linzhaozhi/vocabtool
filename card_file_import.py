"""Parse card files produced by external AI tools.

The importer accepts common CSV/TXT shapes and normalizes them to the six
fields used by the existing Anki package builder.
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from typing import Any, Iterable, Mapping

from anki_parse import normalize_html_breaks, split_example_translation
from utils import detect_file_encoding


CARD_FIELDS = ("w", "p", "m", "e", "ec", "r")
DISPLAY_COLUMNS = {
    "w": "单词/短语",
    "p": "音标",
    "m": "释义",
    "e": "英文例句",
    "ec": "例句翻译",
    "r": "词源",
}
@dataclass
class CardFileParseResult:
    cards: list[dict[str, str]]
    format_name: str
    warnings: list[str]


class CardFileParseError(ValueError):
    """Raised when an uploaded file cannot be interpreted as card rows."""


def _normalize_label(value: Any) -> str:
    label = str(value or "").replace("\ufeff", "").strip().lower()
    label = re.sub(r"^\s*\d+[.)、]\s*", "", label)
    label = label.strip(" \t\r\n`*_#[](){}<>：:")
    return re.sub(r"[\s_\-/.\\()（）]+", "", label)


_FIELD_ALIAS_GROUPS = {
    "w": {
        "w", "word", "words", "term", "phrase", "wordphrase", "headword", "lemma",
        "expression", "vocabulary", "targetword", "front", "frontside",
        "单词", "词汇", "词语", "短语", "单词或短语", "目标词", "正面",
    },
    "p": {
        "p", "phonetic", "phonetics", "pronunciation", "ipa",
        "音标", "发音", "读音",
    },
    "m": {
        "m", "meaning", "meanings", "definition", "definitions", "translation",
        "wordmeaning", "chinesetranslation", "gloss", "back", "backside",
        "释义", "含义", "意思", "定义", "解释", "翻译", "中文翻译", "背面",
    },
    "e": {
        "e", "example", "examples", "examplesentence", "examplesentences",
        "sentence", "englishsentence", "englishexample", "exampleenglish", "sentenceen",
        "英文例句", "英语例句", "例句",
    },
    "ec": {
        "ec", "exampletranslation", "examplechinese", "chineseexample",
        "sentencetranslation", "translationofexample", "examplecn", "sentencecn",
        "例句翻译", "例句中文",
        "中文例句", "例句译文", "例句释义",
    },
    "r": {
        "r", "etymology", "origin", "wordorigin", "wordhistory", "derivation", "root", "wordroot",
        "词源", "来源", "词根", "构词",
    },
    "pos": {
        "pos", "partofspeech", "wordclass", "词性", "词类",
    },
    "cm": {
        "chinesemeaning", "chinesedefinition", "chinesegloss", "definitioncn", "meaningcn",
        "中文释义", "中文定义", "中文含义", "中文意思",
    },
    "ed": {
        "englishmeaning", "englishdefinition", "englishgloss", "definitionen", "meaningen",
        "英文释义", "英文定义", "英文含义", "英文解释",
    },
}
_FIELD_ALIASES = {
    _normalize_label(alias): field
    for field, aliases in _FIELD_ALIAS_GROUPS.items()
    for alias in aliases
}


def _canonical_field(label: Any) -> str:
    return _FIELD_ALIASES.get(_normalize_label(label), "")


def _value_to_text(value: Any, *, list_separator: str = "<br>") -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        items = [_value_to_text(item) for item in value]
        return list_separator.join(item for item in items if item)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null"}:
        return ""
    return text


def _clean_field(value: Any, field: str) -> str:
    text = _value_to_text(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    if field in {"e", "ec"}:
        text = re.sub(r"\s*\n+\s*", "<br>", text)
        return normalize_html_breaks(text)
    return re.sub(r"\s+", " ", text).strip()


def _append_value(target: dict[str, str], field: str, value: Any) -> None:
    cleaned = _clean_field(value, field)
    if not cleaned:
        return
    existing = target.get(field, "")
    if not existing:
        target[field] = cleaned
        return
    separator = "<br>" if field in {"e", "ec"} else " | "
    if cleaned.casefold() not in {part.strip().casefold() for part in existing.split(separator)}:
        target[field] = f"{existing}{separator}{cleaned}"


def _compose_meaning(values: Mapping[str, Any]) -> str:
    parts: list[str] = []
    for field in ("pos", "cm", "m", "ed"):
        cleaned = _clean_field(values.get(field, ""), field)
        if not cleaned:
            continue
        existing_parts = [part.strip() for part in cleaned.split("|") if part.strip()]
        for part in existing_parts:
            if part.casefold() not in {item.casefold() for item in parts}:
                parts.append(part)
    return " | ".join(parts)


def _mapping_to_card(values: Mapping[Any, Any], *, canonical_keys: bool = False) -> dict[str, str]:
    normalized: dict[str, str] = {}
    for label, value in values.items():
        field = str(label) if canonical_keys else _canonical_field(label)
        if field:
            _append_value(normalized, field, value)

    card = {field: "" for field in CARD_FIELDS}
    for field in ("w", "p", "e", "ec", "r"):
        card[field] = _clean_field(normalized.get(field, ""), field)
    card["m"] = _compose_meaning(normalized)

    if card["e"] and not card["ec"]:
        card["e"], card["ec"] = split_example_translation(card["e"])
    return card


def _positional_row_to_card(row: list[str]) -> dict[str, str]:
    values: dict[str, Any]
    if len(row) >= 6:
        values = {
            "w": row[0],
            "p": row[1],
            "m": row[2],
            "e": row[3],
            "ec": row[4],
            "r": " | ".join(part for part in row[5:] if str(part).strip()),
        }
    elif len(row) == 5:
        values = {"w": row[0], "m": row[1], "e": row[2], "ec": row[3], "r": row[4]}
    elif len(row) == 4:
        values = {"w": row[0], "m": row[1], "e": row[2], "r": row[3]}
    elif len(row) == 3:
        values = {"w": row[0], "m": row[1], "e": row[2]}
    elif len(row) == 2:
        values = {"w": row[0], "m": row[1]}
    else:
        values = {"w": row[0] if row else ""}
    return _mapping_to_card(values, canonical_keys=True)


def _is_separator_row(row: Iterable[str]) -> bool:
    cells = [str(cell).strip().replace(" ", "") for cell in row]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _rows_to_cards(rows: Iterable[list[str]]) -> tuple[list[dict[str, str]], list[str]]:
    clean_rows = []
    for row in rows:
        cleaned = [str(cell).replace("\ufeff", "").strip() for cell in row]
        if not any(cleaned) or _is_separator_row(cleaned):
            continue
        if len(cleaned) == 1 and cleaned[0].lstrip().startswith("#"):
            continue
        clean_rows.append(cleaned)

    if not clean_rows:
        return [], []

    header_fields = [_canonical_field(cell) for cell in clean_rows[0]]
    recognized_fields = [field for field in header_fields if field]
    has_header = "w" in recognized_fields and len(recognized_fields) >= 2
    warnings: list[str] = []
    cards: list[dict[str, str]] = []

    if has_header:
        ignored_headers = [
            clean_rows[0][index]
            for index, field in enumerate(header_fields)
            if not field and clean_rows[0][index]
        ]
        if ignored_headers:
            warnings.append(f"已忽略无法识别的列：{'、'.join(ignored_headers)}")

        for row in clean_rows[1:]:
            values: dict[str, str] = {}
            for index, field in enumerate(header_fields):
                if field and index < len(row):
                    _append_value(values, field, row[index])
            card = _mapping_to_card(values, canonical_keys=True)
            if any(card.values()):
                cards.append(card)
    else:
        cards = [_positional_row_to_card(row) for row in clean_rows]

    return cards, warnings


def _strip_code_fences(text: str) -> str:
    blocks = re.findall(r"```(?:csv|tsv|text|txt|json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if blocks:
        return "\n".join(blocks).strip()
    return re.sub(r"^\s*```[^\n]*$", "", text, flags=re.MULTILINE).strip()


def _parse_json_cards(text: str) -> list[dict[str, str]]:
    stripped = text.lstrip()
    if not stripped.startswith(("[", "{")):
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    if isinstance(payload, dict) and isinstance(payload.get("cards"), list):
        payload = payload["cards"]
    elif isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        return []

    cards = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        card = _mapping_to_card(item)
        if any(card.values()):
            cards.append(card)
    return cards


def _split_markdown_row(line: str) -> list[str]:
    cleaned = line.strip()
    if cleaned.startswith("|"):
        cleaned = cleaned[1:]
    if cleaned.endswith("|"):
        cleaned = cleaned[:-1]
    return [part.replace(r"\|", "|").strip() for part in re.split(r"(?<!\\)\|", cleaned)]


def _parse_markdown_table(text: str) -> tuple[list[dict[str, str]], list[str]]:
    lines = [line for line in text.splitlines() if line.count("|") >= 2 and "|||" not in line]
    if len(lines) < 2:
        return [], []
    return _rows_to_cards(_split_markdown_row(line) for line in lines)


def _parse_labeled_blocks(text: str) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    current: dict[str, str] = {}
    last_field = ""

    def flush() -> None:
        nonlocal current, last_field
        card = _mapping_to_card(current, canonical_keys=True)
        if any(card.values()):
            cards.append(card)
        current = {}
        last_field = ""

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        line = re.sub(r"^\s*(?:\d+[.)、]\s*)?(?:[-*+]\s*)?", "", line)
        match = re.match(r"^(.{1,40}?)[：:]\s*(.*)$", line)
        if match:
            raw_label = match.group(1).strip(" `*_#[]")
            value = match.group(2).strip(" `*")
            field = _canonical_field(raw_label)
            if field:
                if field == "w" and current.get("w"):
                    flush()
                _append_value(current, field, value)
                last_field = field
                continue

        if last_field and current:
            _append_value(current, last_field, line.strip(" -*"))

    if current:
        flush()
    return cards


def _sniff_delimiter(text: str, *, default: str = "") -> str:
    sample = "\n".join(line for line in text.splitlines()[:30] if line.strip())
    if not sample:
        return default
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        if "\t" in sample:
            return "\t"
        return default


def _parse_delimited(text: str, delimiter: str) -> tuple[list[dict[str, str]], list[str]]:
    reader = csv.reader(StringIO(text), delimiter=delimiter, skipinitialspace=True)
    return _rows_to_cards(list(reader))


def parse_card_file(file_name: str, bytes_data: bytes) -> CardFileParseResult:
    """Parse a CSV/TXT upload into the card structure used by the packager."""
    if not bytes_data:
        raise CardFileParseError("文件内容为空。")

    extension = Path(file_name or "").suffix.lower()
    if extension not in {".csv", ".txt"}:
        raise CardFileParseError("仅支持 .csv 和 .txt 文件。")

    encoding = detect_file_encoding(bytes_data)
    try:
        text = bytes_data.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        text = bytes_data.decode("utf-8", errors="replace")
    text = _strip_code_fences(text).replace("\x00", "").strip()
    if not text:
        raise CardFileParseError("文件内容为空。")

    warnings: list[str] = []
    cards: list[dict[str, str]] = []
    format_name = ""

    json_cards = _parse_json_cards(text)
    if json_cards:
        cards = json_cards
        format_name = "JSON 文本"
    elif extension == ".csv":
        delimiter = _sniff_delimiter(text, default=",")
        cards, warnings = _parse_delimited(text, delimiter)
        delimiter_names = {",": "CSV", "\t": "制表符 CSV", ";": "分号分隔 CSV"}
        format_name = delimiter_names.get(delimiter, "CSV")
    elif "|||" in text:
        rows = [line.split("|||") for line in text.splitlines() if "|||" in line]
        cards, warnings = _rows_to_cards(rows)
        format_name = "分隔符 TXT"
    else:
        markdown_cards, markdown_warnings = _parse_markdown_table(text)
        if markdown_cards:
            cards = markdown_cards
            warnings = markdown_warnings
            format_name = "Markdown 表格"
        else:
            labeled_cards = _parse_labeled_blocks(text)
            if labeled_cards:
                cards = labeled_cards
                format_name = "字段式 TXT"
            else:
                delimiter = _sniff_delimiter(text, default="," if extension == ".csv" else "")
                if delimiter:
                    cards, warnings = _parse_delimited(text, delimiter)
                    delimiter_names = {",": "CSV", "\t": "制表符 TXT", ";": "分号分隔文本"}
                    format_name = delimiter_names.get(delimiter, "分隔文本")

    cards = [card for card in cards if any(card.values())]
    if not cards:
        raise CardFileParseError(
            "没有识别到卡片。CSV 请使用表头，TXT 请使用表格、字段标签或 ||| 分隔格式。"
        )
    return CardFileParseResult(cards=cards, format_name=format_name, warnings=warnings)


def cards_to_display_rows(cards: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Convert canonical card dictionaries to editable Chinese-labeled rows."""
    return [
        {DISPLAY_COLUMNS[field]: _clean_field(card.get(field, ""), field) for field in CARD_FIELDS}
        for card in cards
    ]


def display_rows_to_cards(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Convert rows returned by Streamlit's data editor to canonical cards."""
    cards = []
    for row in rows:
        values = {
            field: row.get(DISPLAY_COLUMNS[field], row.get(field, ""))
            for field in CARD_FIELDS
        }
        card = _mapping_to_card(values, canonical_keys=True)
        if any(card.values()):
            cards.append(card)
    return cards


def validate_imported_cards(
    cards: list[dict[str, str]],
    *,
    require_examples: bool = False,
) -> list[str]:
    """Validate only the structure needed to create one note per imported row."""
    issues: list[str] = []
    seen_words: dict[str, int] = {}

    if not cards:
        return ["没有可打包的卡片。"]

    for index, card in enumerate(cards, start=1):
        word = _clean_field(card.get("w", ""), "w")
        meaning = _clean_field(card.get("m", ""), "m")
        example = _clean_field(card.get("e", ""), "e")
        if not word:
            issues.append(f"第 {index} 行缺少单词/短语。")
        if not meaning:
            issues.append(f"第 {index} 行缺少释义。")
        if require_examples and not example:
            issues.append(f"第 {index} 行缺少英文例句。")

        normalized_word = re.sub(r"\s+", " ", word).strip().casefold()
        if normalized_word:
            if normalized_word in seen_words:
                issues.append(
                    f"第 {index} 行与第 {seen_words[normalized_word]} 行的单词/短语重复：{word}。"
                )
            else:
                seen_words[normalized_word] = index

    return issues
