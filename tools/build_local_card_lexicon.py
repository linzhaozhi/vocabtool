"""Build local dictionary data for card generation.

This file intentionally uses only the Python standard library so the local
lexicon can be rebuilt before app dependencies are installed.
"""

from __future__ import annotations

import csv
import html as html_lib
import re
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "data" / "source_wordlists"
OUTPUT_PATH = ROOT / "data" / "processed" / "local_card_lexicon.csv"
PRIORITY_PATH = ROOT / "data" / "processed" / "ngsl_31k_priority.csv"

XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass
class LexiconEntry:
    word: str
    normalized_word: str
    pos: str = ""
    phonetic: str = ""
    english_definition: str = ""
    example: str = ""
    example_translation: str = ""
    sources: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)


def normalize_word(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    cleaned = cleaned.replace("’", "'").replace("`", "'")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip("`'\"“”‘’[](){}<>:：,.;!?，。；！？")


def clean_text(value: str) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def clean_pos(value: str) -> str:
    text = clean_text(value).lower().replace(".", "")
    pos_map = {
        "n": "noun",
        "n pl": "noun",
        "noun": "noun",
        "noun pl": "noun",
        "v": "verb",
        "verb": "verb",
        "adj": "adjective",
        "adjective": "adjective",
        "adv": "adverb",
        "adverb": "adverb",
        "prep": "preposition",
        "preposition": "preposition",
        "det": "determiner",
        "determiner": "determiner",
        "pron": "pronoun",
        "pronoun": "pronoun",
        "conj": "conjunction",
        "conjunction": "conjunction",
        "phrase": "phrase",
    }
    return pos_map.get(text, clean_text(value))


def read_priority_order() -> dict[str, int]:
    if not PRIORITY_PATH.exists():
        return {}
    with PRIORITY_PATH.open("r", encoding="utf-8", newline="") as csv_file:
        return {
            normalize_word(row.get("word", "")): int(row.get("rank") or index)
            for index, row in enumerate(csv.DictReader(csv_file), start=1)
            if row.get("word")
        }


def read_xlsx_rows(path: Path) -> list[list[str]]:
    with zipfile.ZipFile(path) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", XLSX_NS):
                shared_strings.append("".join(t.text or "" for t in item.findall(".//a:t", XLSX_NS)))

        sheet_names = [name for name in archive.namelist() if name.startswith("xl/worksheets/sheet")]
        if not sheet_names:
            return []

        root = ET.fromstring(archive.read(sheet_names[0]))
        rows: list[list[str]] = []
        for row in root.findall(".//a:row", XLSX_NS):
            values: list[str] = []
            for cell in row.findall("a:c", XLSX_NS):
                value_node = cell.find("a:v", XLSX_NS)
                value = "" if value_node is None else value_node.text or ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared_strings[int(value)]
                values.append(clean_text(value))
            rows.append(values)
        return rows


def upsert(
    entries: dict[str, LexiconEntry],
    *,
    word: str,
    definition: str,
    source: str,
    source_file: Path,
    pos: str = "",
    phonetic: str = "",
    example: str = "",
    example_translation: str = "",
) -> None:
    word = clean_text(word)
    definition = clean_text(definition)
    normalized_word = normalize_word(word)
    if not normalized_word or not definition:
        return

    entry = entries.get(normalized_word)
    if entry is None:
        entry = LexiconEntry(word=word, normalized_word=normalized_word)
        entries[normalized_word] = entry

    if not entry.english_definition:
        entry.english_definition = definition
    if pos and not entry.pos:
        entry.pos = clean_pos(pos)
    if phonetic and not entry.phonetic:
        entry.phonetic = clean_text(phonetic)
    if example and not entry.example:
        entry.example = clean_text(example)
    if example_translation and not entry.example_translation:
        entry.example_translation = clean_text(example_translation)
    if source not in entry.sources:
        entry.sources.append(source)

    relative_source = str(source_file.relative_to(ROOT))
    if relative_source not in entry.source_files:
        entry.source_files.append(relative_source)


WORDNET_POS_MAP = {
    "n": "noun",
    "v": "verb",
    "a": "adjective",
    "s": "adjective",
    "r": "adverb",
}


def parse_wordnet_data_line(line: str) -> tuple[str, str, list[str]] | None:
    if not line or line.startswith("  "):
        return None
    try:
        data, gloss = line.split(" | ", 1)
    except ValueError:
        return None

    parts = data.split()
    if len(parts) < 4:
        return None

    offset = parts[0]
    pos = WORDNET_POS_MAP.get(parts[2], "")
    examples = [clean_text(example) for example in re.findall(r'"([^"]+)"', gloss)]
    definition = clean_text(gloss.split("; \"", 1)[0].strip())
    return offset, pos, [definition, *examples]


def load_wordnet_entries(entries: dict[str, LexiconEntry], allowed_words: set[str]) -> None:
    path = SOURCE_DIR / "wordnet" / "wordnet.zip"
    if not path.exists():
        return

    with zipfile.ZipFile(path) as archive:
        synsets_by_pos: dict[str, dict[str, tuple[str, list[str]]]] = {}
        for pos_name in ("noun", "verb", "adj", "adv"):
            data_name = f"wordnet/data.{pos_name}"
            if data_name not in archive.namelist():
                continue
            synsets: dict[str, tuple[str, list[str]]] = {}
            for raw_line in archive.read(data_name).decode("utf-8", errors="ignore").splitlines():
                parsed = parse_wordnet_data_line(raw_line)
                if parsed is None:
                    continue
                offset, pos, gloss_parts = parsed
                if gloss_parts and gloss_parts[0]:
                    synsets[offset] = (pos, gloss_parts)
            synsets_by_pos[pos_name] = synsets

        for pos_name in ("noun", "verb", "adj", "adv"):
            index_name = f"wordnet/index.{pos_name}"
            if index_name not in archive.namelist():
                continue
            synsets = synsets_by_pos.get(pos_name, {})
            for raw_line in archive.read(index_name).decode("utf-8", errors="ignore").splitlines():
                if not raw_line or raw_line.startswith(" "):
                    continue
                parts = raw_line.split()
                if len(parts) < 6:
                    continue

                word = parts[0].replace("_", " ")
                normalized_word = normalize_word(word)
                if normalized_word not in allowed_words:
                    continue
                if entries.get(normalized_word, None) and entries[normalized_word].english_definition:
                    continue

                try:
                    pointer_count = int(parts[3])
                except ValueError:
                    continue
                offset_start = 4 + pointer_count + 2
                offsets = parts[offset_start:]

                for offset in offsets:
                    synset = synsets.get(offset)
                    if not synset:
                        continue
                    pos, gloss_parts = synset
                    definition = gloss_parts[0]
                    example = gloss_parts[1] if len(gloss_parts) > 1 else ""
                    upsert(
                        entries,
                        word=word,
                        definition=definition,
                        example=example,
                        pos=pos,
                        source="Princeton WordNet via NLTK corpus",
                        source_file=path,
                    )
                    break


def load_ngsl_definitions(entries: dict[str, LexiconEntry]) -> None:
    path = SOURCE_DIR / "ngsl" / "NGSL_1.2_with_English_definitions.xlsx"
    for row in read_xlsx_rows(path)[1:]:
        if len(row) >= 2:
            upsert(
                entries,
                word=row[0],
                definition=row[1],
                source="NGSL 1.2 English definitions",
                source_file=path,
            )


def load_nawl_csv(entries: dict[str, LexiconEntry]) -> None:
    path = SOURCE_DIR / "ngsl_special_purpose" / "NAWL_1.2_with_English_definitions.csv"
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        for row in reader:
            upsert(
                entries,
                word=row.get("Meanings", ""),
                definition=row.get("English Definition", ""),
                pos=row.get("POS", ""),
                source="NAWL 1.2 English definitions",
                source_file=path,
            )


def load_tsl_xlsx(entries: dict[str, LexiconEntry]) -> None:
    path = SOURCE_DIR / "ngsl_special_purpose" / "TSL_1.2_definitions.xlsx"
    for row in read_xlsx_rows(path)[1:]:
        if len(row) >= 2:
            upsert(
                entries,
                word=row[0],
                definition=row[1],
                source="TSL 1.2 English definitions",
                source_file=path,
            )


def strip_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value)
    return clean_text(without_tags)


def load_learning_dictionary_html(entries: dict[str, LexiconEntry], path: Path, source: str) -> None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    rows = re.findall(r"<tr>(.*?)</tr>", text, flags=re.IGNORECASE | re.DOTALL)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.IGNORECASE | re.DOTALL)
        if len(cells) < 5:
            continue
        upsert(
            entries,
            word=strip_html(cells[1]),
            phonetic=strip_html(cells[2]),
            pos=strip_html(cells[3]),
            definition=strip_html(cells[4]),
            source=source,
            source_file=path,
        )


def build_entries() -> dict[str, LexiconEntry]:
    entries: dict[str, LexiconEntry] = {}
    priority_order = read_priority_order()
    allowed_words = set(priority_order)
    load_ngsl_definitions(entries)
    load_learning_dictionary_html(
        entries,
        SOURCE_DIR / "ngsl_special_purpose" / "NAWL_1.2_learning_dictionary.html",
        "NAWL 1.2 learning dictionary",
    )
    load_nawl_csv(entries)
    load_learning_dictionary_html(
        entries,
        SOURCE_DIR / "ngsl_special_purpose" / "TSL_1.2_learning_dictionary.html",
        "TSL 1.2 learning dictionary",
    )
    load_tsl_xlsx(entries)
    load_wordnet_entries(entries, allowed_words)
    return entries


def write_entries(entries: dict[str, LexiconEntry]) -> None:
    priority_order = read_priority_order()
    rows = sorted(
        entries.values(),
        key=lambda entry: (
            priority_order.get(entry.normalized_word, 999999),
            entry.normalized_word,
        ),
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as csv_file:
        fieldnames = [
            "word",
            "normalized_word",
            "pos",
            "phonetic",
            "english_definition",
            "example",
            "example_translation",
            "sources",
            "source_files",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for entry in rows:
            writer.writerow({
                "word": entry.word,
                "normalized_word": entry.normalized_word,
                "pos": entry.pos,
                "phonetic": entry.phonetic,
                "english_definition": entry.english_definition,
                "example": entry.example,
                "example_translation": entry.example_translation,
                "sources": "; ".join(entry.sources),
                "source_files": "; ".join(entry.source_files),
            })


def main() -> None:
    entries = build_entries()
    write_entries(entries)
    with_examples = sum(1 for entry in entries.values() if entry.example)
    print(f"Wrote {len(entries)} local entries to {OUTPUT_PATH}")
    print(f"Entries with local examples: {with_examples}")


if __name__ == "__main__":
    main()
