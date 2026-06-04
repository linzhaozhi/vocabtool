# Cached resource loaders (NLP, file parsers, genanki, vocab data).

import logging
import os
import csv
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import streamlit as st

import constants
from errors import ErrorHandler

logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Set by app after load_vocab_data() so vocab module can use them.
VOCAB_DICT: Dict[str, int] = {}
FULL_DF: Optional[Any] = None


def get_vocab_dict() -> Dict[str, int]:
    """Return current VOCAB_DICT (set by app after load_vocab_data())."""
    return VOCAB_DICT


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
                    word = str(row.get(word_field, "")).lower().strip()
                    if not word:
                        continue
                    try:
                        rank = int(float(str(row.get(rank_field, row_index)).strip()))
                    except (TypeError, ValueError):
                        rank = row_index

                    existing = rows_by_word.get(word)
                    if existing is None or rank < int(existing["rank"]):
                        rows_by_word[word] = {"word": word, "rank": rank}

            rows = sorted(rows_by_word.values(), key=lambda item: int(item["rank"]))
            vocab_dict = {str(row["word"]): int(row["rank"]) for row in rows}
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
    pickle_candidates = [BASE_DIR / "vocab.pkl", DATA_DIR / "vocab.pkl"]
    for pickle_path in pickle_candidates:
        if not pickle_path.exists():
            continue
        try:
            import pandas as pd

            df = pd.read_pickle(pickle_path)
            vocab_dict = pd.Series(df['rank'].values, index=df['word']).to_dict()
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
