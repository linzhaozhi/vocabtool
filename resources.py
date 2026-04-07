# Cached resource loaders (NLP, file parsers, genanki, vocab data).

import logging
import os
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import streamlit as st

import constants
from errors import ErrorHandler

logger = logging.getLogger(__name__)

# Set by app after load_vocab_data() so vocab module can use them.
VOCAB_DICT: Dict[str, int] = {}
FULL_DF: Optional[pd.DataFrame] = None


def get_vocab_dict() -> Dict[str, int]:
    """Return current VOCAB_DICT (set by app after load_vocab_data())."""
    return VOCAB_DICT


@st.cache_resource(show_spinner="正在加载 NLP 引擎...")
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
        ErrorHandler.handle(e, "NLP 资源加载失败")

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


@st.cache_data
def load_vocab_data() -> Tuple[Dict[str, int], Optional[pd.DataFrame]]:
    """Load vocabulary data from pickle or CSV files."""
    if os.path.exists("vocab.pkl"):
        try:
            df = pd.read_pickle("vocab.pkl")
            vocab_dict = pd.Series(df['rank'].values, index=df['word']).to_dict()
            return vocab_dict, df
        except (FileNotFoundError, pd.errors.PickleError, KeyError) as e:
            logger.warning(f"Could not load pickle file: {e}")

    possible_files = ["coca_cleaned.csv", "data.csv", "vocab.csv"]
    file_path = next((f for f in possible_files if os.path.exists(f)), None)

    if file_path:
        try:
            df = pd.read_csv(file_path)
            df.columns = [c.strip().lower() for c in df.columns]

            word_col = next((c for c in df.columns if 'word' in c), df.columns[0])
            rank_col = next((c for c in df.columns if 'rank' in c), df.columns[1])

            df = df.dropna(subset=[word_col])
            df[word_col] = df[word_col].astype(str).str.lower().str.strip()
            df[rank_col] = pd.to_numeric(df[rank_col], errors='coerce')
            df = df.sort_values(rank_col).drop_duplicates(subset=[word_col], keep='first')

            vocab_dict = pd.Series(df[rank_col].values, index=df[word_col]).to_dict()
            return vocab_dict, df
        except Exception as e:
            logger.error(f"Error loading CSV file {file_path}: {e}")
            return {}, None

    logger.warning("No vocabulary data files found")
    return {}, None
