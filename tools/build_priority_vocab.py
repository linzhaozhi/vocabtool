"""Build a learner-priority vocabulary list from local source wordlists.

The app needs a simple `word,rank` CSV, but this script also writes a metadata
CSV so the ranking can be inspected and tuned later.
"""

from __future__ import annotations

import csv
import html
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT_DIR / "data" / "source_wordlists"
OUTPUT_DIR = ROOT_DIR / "data" / "processed"

BASE_31K_FILE = ROOT_DIR / "ngsl_sfi_31k.csv"
NGSL_STATS_FILE = SOURCE_DIR / "ngsl" / "NGSL_1.2_stats.csv"
NGSL_SUPPLEMENT_FILE = SOURCE_DIR / "ngsl" / "NGSL_1.2_supplementary_words.csv"
OXFORD_PAGE_FILE = SOURCE_DIR / "oxford" / "source_page.html"
NAWL_STATS_FILE = SOURCE_DIR / "ngsl_special_purpose" / "NAWL_1.2_stats.csv"
TSL_STATS_FILE = SOURCE_DIR / "ngsl_special_purpose" / "TSL_1.2_stats.csv"
BSL_STATS_FILE = SOURCE_DIR / "ngsl_special_purpose" / "BSL_1.2_stats.csv"

APP_OUTPUT_FILE = OUTPUT_DIR / "ngsl_31k_priority.csv"
METADATA_OUTPUT_FILE = OUTPUT_DIR / "ngsl_31k_priority_metadata.csv"

CEFR_BONUS = {
    "a1": 1.30,
    "a2": 1.10,
    "b1": 0.80,
    "b2": 0.50,
    "c1": 0.25,
}
CEFR_ORDER = {"a1": 1, "a2": 2, "b1": 3, "b2": 4, "c1": 5}

DAYS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}
MONTHS = {
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
}
COMMON_NUMBERS = {
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
    "hundred",
    "thousand",
    "million",
    "billion",
}
LARGE_NUMBERS = {"trillion", "quadrillion", "quintillion"}


@dataclass
class VocabEntry:
    word: str
    display_word: str
    original_rank: int | None = None
    ngsl_rank: int | None = None
    oxford_level: str = ""
    oxford_list: str = ""
    supplement_category: str = ""
    nawl_rank: int | None = None
    tsl_rank: int | None = None
    bsl_rank: int | None = None
    sources: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)
    priority_score: float = 0.0
    rank: int = 0


def normalize_word(value: str) -> str:
    """Normalize one vocabulary item for ranking."""
    value = html.unescape(str(value or "")).strip().lower()
    value = value.replace("\ufeff", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip("`'\"“”‘’[](){}<>:：;；,.，。")


def parse_int(value: str | None) -> int | None:
    try:
        return int(float(str(value or "").strip()))
    except ValueError:
        return None


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    """Read CSV rows with BOM handling."""
    if not path.exists():
        return []
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            with path.open("r", encoding=encoding, newline="") as csv_file:
                return list(csv.DictReader(csv_file))
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error:
        raise last_error
    return []


def read_supplement_headwords(path: Path) -> dict[str, str]:
    """Read NGSL supplementary headwords and classify them."""
    categories: dict[str, str] = {}
    if not path.exists():
        return categories

    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for raw_line in csv_file:
            parts = [normalize_word(part) for part in raw_line.split(",")]
            parts = [part for part in parts if part]
            if not parts:
                continue
            headword = parts[0]
            if headword in DAYS:
                categories[headword] = "calendar_day"
            elif headword in MONTHS:
                categories[headword] = "calendar_month"
            elif headword in COMMON_NUMBERS:
                categories[headword] = "common_number"
            elif headword in LARGE_NUMBERS:
                categories[headword] = "large_number"
            else:
                categories[headword] = "supplementary"
    return categories


def upsert(entries: dict[str, VocabEntry], word: str) -> VocabEntry | None:
    word = normalize_word(word)
    if not word:
        return None
    if not re.fullmatch(r"[a-z][a-z' -]*", word):
        return None
    if word not in entries:
        entries[word] = VocabEntry(word=word, display_word=word)
    return entries[word]


def load_base_31k(entries: dict[str, VocabEntry]) -> int:
    max_rank = 0
    for row in read_csv_rows(BASE_31K_FILE):
        word = row.get("word", "")
        rank = parse_int(row.get("rank"))
        if rank is None:
            continue
        entry = upsert(entries, word)
        if not entry:
            continue
        entry.original_rank = rank if entry.original_rank is None else min(entry.original_rank, rank)
        entry.sources.add("ngsl_sfi_31k")
        max_rank = max(max_rank, rank)
    return max_rank


def load_ngsl_core(entries: dict[str, VocabEntry]) -> int:
    max_rank = 0
    for row in read_csv_rows(NGSL_STATS_FILE):
        word = row.get("Lemma", "")
        rank = parse_int(row.get("SFI Rank"))
        if rank is None:
            continue
        entry = upsert(entries, word)
        if not entry:
            continue
        entry.ngsl_rank = rank if entry.ngsl_rank is None else min(entry.ngsl_rank, rank)
        entry.sources.add("ngsl_1.2_core")
        max_rank = max(max_rank, rank)
    return max_rank


def load_ngsl_supplement(entries: dict[str, VocabEntry]) -> None:
    for word, category in read_supplement_headwords(NGSL_SUPPLEMENT_FILE).items():
        entry = upsert(entries, word)
        if not entry:
            continue
        entry.supplement_category = category
        if category in {"calendar_day", "calendar_month"}:
            entry.display_word = word.capitalize()
        entry.sources.add("ngsl_1.2_supplement")
        entry.notes.append("NGSL supplementary headword without SFI rank")


def best_cefr_level(current: str, new_level: str) -> str:
    if not current:
        return new_level
    return current if CEFR_ORDER.get(current, 999) <= CEFR_ORDER.get(new_level, 999) else new_level


def load_oxford(entries: dict[str, VocabEntry]) -> None:
    if not OXFORD_PAGE_FILE.exists():
        return
    content = OXFORD_PAGE_FILE.read_text(encoding="utf-8", errors="ignore")
    for match in re.finditer(r"<li\s+([^>]*data-hw=\"[^\"]+\"[^>]*)>", content, flags=re.IGNORECASE):
        attrs = match.group(1)
        hw_match = re.search(r'data-hw="([^"]+)"', attrs)
        if not hw_match:
            continue
        entry = upsert(entries, hw_match.group(1))
        if not entry:
            continue

        ox3000_match = re.search(r'data-ox3000="([^"]+)"', attrs)
        ox5000_match = re.search(r'data-ox5000="([^"]+)"', attrs)
        if ox3000_match:
            level = normalize_word(ox3000_match.group(1))
            entry.oxford_level = best_cefr_level(entry.oxford_level, level)
            entry.oxford_list = "oxford3000"
            entry.sources.add("oxford3000")
        elif ox5000_match:
            level = normalize_word(ox5000_match.group(1))
            entry.oxford_level = best_cefr_level(entry.oxford_level, level)
            if entry.oxford_list != "oxford3000":
                entry.oxford_list = "oxford5000"
            entry.sources.add("oxford5000")


def load_special_list(entries: dict[str, VocabEntry], path: Path, source_name: str, rank_column: str) -> int:
    max_rank = 0
    for row in read_csv_rows(path):
        word = row.get("Word", "")
        rank = parse_int(row.get(rank_column) or row.get("Rank"))
        if rank is None:
            continue
        entry = upsert(entries, word)
        if not entry:
            continue
        if source_name == "nawl_1.2":
            entry.nawl_rank = rank if entry.nawl_rank is None else min(entry.nawl_rank, rank)
        elif source_name == "tsl_1.2":
            entry.tsl_rank = rank if entry.tsl_rank is None else min(entry.tsl_rank, rank)
        elif source_name == "bsl_1.2":
            entry.bsl_rank = rank if entry.bsl_rank is None else min(entry.bsl_rank, rank)
        entry.sources.add(source_name)
        max_rank = max(max_rank, rank)
    return max_rank


def rank_bonus(rank: int | None, max_rank: int, weight: float) -> float:
    if rank is None or rank <= 0 or max_rank <= 1:
        return 0.0
    return weight * max(0.0, 1.0 - math.log(rank) / math.log(max_rank))


def supplement_bonus(category: str) -> float:
    return {
        "calendar_day": 6.40,
        "calendar_month": 6.20,
        "common_number": 6.00,
        "large_number": 2.60,
        "supplementary": 4.00,
    }.get(category, 0.0)


def effective_supplement_bonus(entry: VocabEntry) -> float:
    """Boost supplementary essentials only when frequency data under-ranks them.

    Words such as "may" and "march" are already high-frequency NGSL items due to
    non-calendar meanings. A full calendar boost would incorrectly push those
    homographs above ordinary top-frequency function words.
    """
    if not entry.supplement_category:
        return 0.0
    if entry.original_rank is None or entry.original_rank > 5000:
        return supplement_bonus(entry.supplement_category)
    return 0.35


def score_entries(
    entries: Iterable[VocabEntry],
    *,
    max_original_rank: int,
    max_ngsl_rank: int,
    max_nawl_rank: int,
    max_tsl_rank: int,
    max_bsl_rank: int,
) -> None:
    """Compute priority scores.

    The score keeps corpus frequency as the backbone, then boosts words that
    appear in curated learning lists. The original 31k rank carries the largest
    weight so high-frequency basics such as "two" are not pushed down just
    because they are supplementary rather than NGSL-core ranked.
    """
    for entry in entries:
        score = rank_bonus(entry.original_rank, max_original_rank, 30.0)

        if entry.ngsl_rank is not None:
            score += 5.60 + rank_bonus(entry.ngsl_rank, max_ngsl_rank, 2.00)

        score += effective_supplement_bonus(entry)

        if entry.oxford_list == "oxford3000":
            score += 4.00
        elif entry.oxford_list == "oxford5000":
            score += 2.50
        if entry.oxford_level:
            score += CEFR_BONUS.get(entry.oxford_level, 0.0)

        if entry.nawl_rank is not None:
            score += 1.20 + rank_bonus(entry.nawl_rank, max_nawl_rank, 0.60)
        if entry.tsl_rank is not None:
            score += 1.00 + rank_bonus(entry.tsl_rank, max_tsl_rank, 0.50)
        if entry.bsl_rank is not None:
            score += 0.90 + rank_bonus(entry.bsl_rank, max_bsl_rank, 0.45)

        curated_source_count = len(entry.sources - {"ngsl_sfi_31k"})
        score += min(1.50, curated_source_count * 0.25)
        entry.priority_score = round(score, 6)


def write_outputs(entries: list[VocabEntry]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    app_fields = ["word", "rank"]
    with APP_OUTPUT_FILE.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=app_fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow({"word": entry.display_word, "rank": entry.rank})

    metadata_fields = [
        "word",
        "normalized_word",
        "rank",
        "priority_score",
        "original_rank",
        "ngsl_rank",
        "supplement_category",
        "oxford_list",
        "oxford_level",
        "nawl_rank",
        "tsl_rank",
        "bsl_rank",
        "sources",
        "notes",
    ]
    with METADATA_OUTPUT_FILE.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=metadata_fields)
        writer.writeheader()
        for entry in entries:
            writer.writerow(
                {
                    "word": entry.display_word,
                    "normalized_word": entry.word,
                    "rank": entry.rank,
                    "priority_score": f"{entry.priority_score:.6f}",
                    "original_rank": entry.original_rank or "",
                    "ngsl_rank": entry.ngsl_rank or "",
                    "supplement_category": entry.supplement_category,
                    "oxford_list": entry.oxford_list,
                    "oxford_level": entry.oxford_level,
                    "nawl_rank": entry.nawl_rank or "",
                    "tsl_rank": entry.tsl_rank or "",
                    "bsl_rank": entry.bsl_rank or "",
                    "sources": ";".join(sorted(entry.sources)),
                    "notes": "; ".join(entry.notes),
                }
            )


def build_priority_vocab() -> list[VocabEntry]:
    entries: dict[str, VocabEntry] = {}
    max_original_rank = load_base_31k(entries)
    max_ngsl_rank = load_ngsl_core(entries)
    load_ngsl_supplement(entries)
    load_oxford(entries)
    max_nawl_rank = load_special_list(entries, NAWL_STATS_FILE, "nawl_1.2", "Rank")
    max_tsl_rank = load_special_list(entries, TSL_STATS_FILE, "tsl_1.2", "TSL Rank")
    max_bsl_rank = load_special_list(entries, BSL_STATS_FILE, "bsl_1.2", "BSL Rank")

    score_entries(
        entries.values(),
        max_original_rank=max_original_rank,
        max_ngsl_rank=max_ngsl_rank,
        max_nawl_rank=max_nawl_rank,
        max_tsl_rank=max_tsl_rank,
        max_bsl_rank=max_bsl_rank,
    )

    sorted_entries = sorted(
        entries.values(),
        key=lambda item: (
            -item.priority_score,
            item.original_rank if item.original_rank is not None else 999999,
            item.word,
        ),
    )
    for index, entry in enumerate(sorted_entries, start=1):
        entry.rank = index
    return sorted_entries


def main() -> None:
    entries = build_priority_vocab()
    write_outputs(entries)
    print(f"Wrote {APP_OUTPUT_FILE.relative_to(ROOT_DIR)} ({len(entries)} words)")
    print(f"Wrote {METADATA_OUTPUT_FILE.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
