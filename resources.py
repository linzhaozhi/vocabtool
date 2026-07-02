# Cached resource loaders (NLP, file parsers, genanki, vocab data).

import logging
import os
import csv
import re
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

try:
    import streamlit as st
except ModuleNotFoundError:
    class _StreamlitFallback:
        @staticmethod
        def cache_resource(func=None, **kwargs):
            if func is not None:
                return func

            def decorator(func):
                return func
            return decorator

        @staticmethod
        def cache_data(func=None, **kwargs):
            if func is not None:
                return func

            def decorator(inner):
                return inner
            return decorator

    st = _StreamlitFallback()

import constants
from errors import ErrorHandler

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Set by app after load_vocab_data() so vocab module can use them.
VOCAB_DICT: Dict[str, int] = {}
VOCAB_DISPLAY_DICT: Dict[str, str] = {}
FULL_DF: Optional[Any] = None
VOCAB_LOAD_ATTEMPTED = False


IRREGULAR_VOCAB_FORMS = {
    "ate": "eat",
    "became": "become",
    "been": "be",
    "began": "begin",
    "begun": "begin",
    "bought": "buy",
    "brought": "bring",
    "caught": "catch",
    "children": "child",
    "came": "come",
    "did": "do",
    "done": "do",
    "driven": "drive",
    "drove": "drive",
    "eaten": "eat",
    "fallen": "fall",
    "feet": "foot",
    "felt": "feel",
    "found": "find",
    "gave": "give",
    "given": "give",
    "gone": "go",
    "got": "get",
    "gotten": "get",
    "had": "have",
    "has": "have",
    "held": "hold",
    "kept": "keep",
    "known": "know",
    "left": "leave",
    "lost": "lose",
    "made": "make",
    "men": "man",
    "met": "meet",
    "mice": "mouse",
    "paid": "pay",
    "ran": "run",
    "said": "say",
    "saw": "see",
    "seen": "see",
    "sent": "send",
    "spent": "spend",
    "spoken": "speak",
    "stood": "stand",
    "taken": "take",
    "taught": "teach",
    "teeth": "tooth",
    "thought": "think",
    "took": "take",
    "understood": "understand",
    "was": "be",
    "went": "go",
    "were": "be",
    "women": "woman",
    "won": "win",
    "wore": "wear",
    "worn": "wear",
    "written": "write",
    "wrote": "write",
}


def get_vocab_dict() -> Dict[str, int]:
    """Return current VOCAB_DICT (set by app after load_vocab_data())."""
    global VOCAB_DICT, FULL_DF, VOCAB_LOAD_ATTEMPTED
    if not VOCAB_DICT and not VOCAB_LOAD_ATTEMPTED:
        VOCAB_LOAD_ATTEMPTED = True
        default_path = BASE_DIR / constants.VOCAB_PROJECT_FILE
        if default_path.exists():
            try:
                VOCAB_DICT, FULL_DF = _load_vocab_csv(default_path)
            except Exception as e:
                logger.warning(f"Could not lazy-load default vocab CSV {default_path}: {e}")
    return VOCAB_DICT


def get_vocab_display_dict() -> Dict[str, str]:
    """Return display spelling by normalized word key."""
    if not VOCAB_DISPLAY_DICT:
        get_vocab_dict()
    return VOCAB_DISPLAY_DICT


def _normalize_vocab_lookup_key(value: str) -> str:
    """Normalize a user-facing word into a vocabulary lookup key."""
    cleaned = str(value or "").strip().lower()
    cleaned = cleaned.replace("’", "'").replace("`", "'")
    cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", cleaned)
    cleaned = cleaned.strip("`'\"“”‘’[](){}<>:：,.;!?，。；！？")
    return re.sub(r"\s+", " ", cleaned)


def _add_vocab_candidate(candidates: list[str], value: str) -> None:
    candidate = _normalize_vocab_lookup_key(value)
    if candidate and candidate not in candidates:
        candidates.append(candidate)


def _add_simple_inflection_candidates(candidates: list[str], key: str) -> None:
    """Add lightweight English inflection candidates without requiring NLP packages."""
    if not re.fullmatch(r"[a-z][a-z'-]*", key):
        return

    if key in IRREGULAR_VOCAB_FORMS:
        _add_vocab_candidate(candidates, IRREGULAR_VOCAB_FORMS[key])

    if key.endswith("'s") and len(key) > 3:
        _add_vocab_candidate(candidates, key[:-2])
    if key.endswith("s'") and len(key) > 3:
        _add_vocab_candidate(candidates, key[:-1])

    if key.endswith("ies") and len(key) > 4:
        _add_vocab_candidate(candidates, f"{key[:-3]}y")
    if key.endswith("ied") and len(key) > 4:
        _add_vocab_candidate(candidates, f"{key[:-3]}y")
    if key.endswith("ves") and len(key) > 4:
        _add_vocab_candidate(candidates, f"{key[:-3]}f")
        _add_vocab_candidate(candidates, f"{key[:-3]}fe")
    if key.endswith("es") and len(key) > 4:
        _add_vocab_candidate(candidates, key[:-2])
    if key.endswith("s") and len(key) > 3 and not key.endswith(("ss", "us", "is")):
        _add_vocab_candidate(candidates, key[:-1])

    if key.endswith("ing") and len(key) > 5:
        stem = key[:-3]
        _add_vocab_candidate(candidates, stem)
        _add_vocab_candidate(candidates, f"{stem}e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            _add_vocab_candidate(candidates, stem[:-1])
    if key.endswith("ed") and len(key) > 4:
        stem = key[:-2]
        _add_vocab_candidate(candidates, stem)
        _add_vocab_candidate(candidates, f"{stem}e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            _add_vocab_candidate(candidates, stem[:-1])
    if key.endswith("er") and len(key) > 4:
        stem = key[:-2]
        _add_vocab_candidate(candidates, stem)
        _add_vocab_candidate(candidates, f"{stem}e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            _add_vocab_candidate(candidates, stem[:-1])
    if key.endswith("est") and len(key) > 5:
        stem = key[:-3]
        _add_vocab_candidate(candidates, stem)
        _add_vocab_candidate(candidates, f"{stem}e")
        if len(stem) > 2 and stem[-1] == stem[-2]:
            _add_vocab_candidate(candidates, stem[:-1])


def vocab_lookup_candidates(value: str) -> list[str]:
    """Return exact and simple lemma candidates for a vocabulary lookup."""
    candidates: list[str] = []
    key = _normalize_vocab_lookup_key(value)
    _add_vocab_candidate(candidates, key)

    if "-" in key:
        _add_vocab_candidate(candidates, key.replace("-", " "))
        _add_vocab_candidate(candidates, key.replace("-", ""))
    if "'" in key:
        _add_vocab_candidate(candidates, key.replace("'", ""))

    _add_simple_inflection_candidates(candidates, key)
    return candidates


def resolve_vocab_rank(value: str) -> Tuple[Optional[int], str]:
    """Resolve a word/rank pair from the internal 31K vocabulary."""
    vocab_dict = get_vocab_dict()
    display_dict = get_vocab_display_dict()
    for candidate in vocab_lookup_candidates(value):
        rank = vocab_dict.get(candidate)
        if rank is not None:
            return int(rank), display_dict.get(candidate, candidate)
    return None, ""


@st.cache_resource(show_spinner="正在加载分词与词形还原资源...")
def load_nlp_resources() -> Tuple[Any, Any]:
    """Load NLTK and lemminflect resources with proper error handling."""
    import nltk
    import lemminflect

    try:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        nltk_data_dir = os.path.join(root_dir, 'nltk_data')
        os.makedirs(nltk_data_dir, exist_ok=True)
        nltk.data.path.append(nltk_data_dir)

        required_packages = ['averaged_perceptron_tagger', 'punkt', 'punkt_tab']
        for pkg in required_packages:
            try:
                nltk.data.find(f'tokenizers/{pkg}')
            except LookupError:
                logger.info(f"Downloading NLTK package: {pkg}")
                nltk.download(pkg, download_dir=nltk_data_dir, quiet=True)
    except Exception as e:
        ErrorHandler.handle(e, "词形还原资源加载失败")

    return nltk, lemminflect


@st.cache_resource
def get_file_parsers() -> Tuple[Any, Any, Any, Any, Any]:
    """Lazy load file parsing libraries (cached)."""
    import pypdf
    import docx
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    return pypdf, docx, ebooklib, epub, BeautifulSoup


@st.cache_resource
def get_genanki() -> Tuple[Any, Any]:
    """Lazy load genanki library (cached)."""
    import genanki
    import tempfile
    return genanki, tempfile


def _load_vocab_csv(file_path: Path) -> Tuple[Dict[str, int], list[dict[str, Any]]]:
    """Load a simple word/rank CSV without importing pandas at startup."""
    global VOCAB_DISPLAY_DICT
    rows_by_word: dict[str, dict[str, Any]] = {}
    last_error: Optional[Exception] = None

    for encoding in constants.ENCODING_PRIORITY:
        try:
            with file_path.open("r", encoding=encoding, newline="") as csv_file:
                reader = csv.DictReader(csv_file)
                if not reader.fieldnames:
                    return {}, []

                fieldnames = [str(field).strip().lower() for field in reader.fieldnames if field]
                if not fieldnames:
                    return {}, []
                word_field = next((field for field in fieldnames if "word" in field or "lemma" in field), fieldnames[0])
                rank_field = next((field for field in fieldnames if "rank" in field), "")

                for row_index, raw_row in enumerate(reader, start=1):
                    row = {str(key).strip().lower(): value for key, value in raw_row.items()}
                    display_word = str(row.get(word_field, "")).strip()
                    word_key = display_word.lower()
                    if not word_key:
                        continue
                    try:
                        rank = int(float(str(row.get(rank_field, row_index)).strip()))
                    except (TypeError, ValueError):
                        rank = row_index

                    existing = rows_by_word.get(word_key)
                    if existing is None or rank < int(existing["rank"]):
                        rows_by_word[word_key] = {"word": display_word, "rank": rank}

            rows = sorted(rows_by_word.values(), key=lambda item: int(item["rank"]))
            vocab_dict = {str(row["word"]).lower(): int(row["rank"]) for row in rows}
            VOCAB_DISPLAY_DICT = {str(row["word"]).lower(): str(row["word"]) for row in rows}
            return vocab_dict, rows
        except UnicodeDecodeError as e:
            last_error = e
            continue

    if last_error:
        raise last_error
    return {}, []


@st.cache_data
def load_vocab_data() -> Tuple[Dict[str, int], Optional[Any]]:
    """Load vocabulary data from pickle or CSV files."""
    global VOCAB_DISPLAY_DICT
    pickle_candidates = [BASE_DIR / "vocab.pkl", DATA_DIR / "vocab.pkl"]
    for pickle_path in pickle_candidates:
        if not pickle_path.exists():
            continue
        try:
            import pandas as pd

            df = pd.read_pickle(pickle_path)
            vocab_dict = pd.Series(df['rank'].values, index=df['word']).to_dict()
            VOCAB_DISPLAY_DICT = {str(word).lower(): str(word) for word in df['word']}
            return vocab_dict, df
        except Exception as e:
            logger.warning(f"Could not load pickle file: {e}")

    possible_files = [
        BASE_DIR / constants.VOCAB_PROJECT_FILE,
        DATA_DIR / constants.VOCAB_PROJECT_FILE,
        BASE_DIR / "data.csv",
        BASE_DIR / "vocab.csv",
        DATA_DIR / "data.csv",
        DATA_DIR / "vocab.csv",
    ]
    file_path = next((path for path in possible_files if path.exists()), None)

    if file_path:
        try:
            return _load_vocab_csv(file_path)
        except Exception as e:
            logger.error(f"Error loading CSV file {file_path}: {e}")
            return {}, None

    logger.warning("No vocabulary data files found")
    return {}, None
