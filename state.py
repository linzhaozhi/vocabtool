# Session state helpers.

import os
import random
from typing import Dict, List, Optional, Tuple

import streamlit as st

import constants

logger = __import__("logging").getLogger(__name__)


def clear_all_state() -> None:
    """Clear all session state for fresh start."""
    for path_key in ('anki_pkg_path', 'import_anki_pkg_path'):
        pkg_path = st.session_state.get(path_key)
        if pkg_path and os.path.exists(pkg_path):
            try:
                os.remove(pkg_path)
            except OSError as e:
                logger.warning("Could not remove temp anki package: %s", e)

    if 'url_input_key' in st.session_state:
        st.session_state['url_input_key'] = ""

    keys_to_drop = [
        'gen_words_data', 'raw_count', 'process_time', 'stats_info',
        'prepared_word_list_text', 'card_word_list_editor', 'word_list_editor', 'extract_word_editor',
        'extract_remaining_words_text',
        'anki_pkg_path', 'anki_pkg_name', 'anki_input_text', 'anki_cards_cache',
        'import_anki_pkg_path', 'import_anki_pkg_name', 'import_cards_cache',
        'import_file_signature', 'import_file_cards', 'import_file_format',
        'import_file_warnings', 'import_current_cards', 'import_package_signature',
        'import_source_name', 'import_uploader_nonce'
    ]

    for key in keys_to_drop:
        if key in st.session_state:
            del st.session_state[key]

    st.session_state['uploader_id'] = str(random.randint(constants.MIN_RANDOM_ID, constants.MAX_RANDOM_ID))
    if 'paste_key' in st.session_state:
        st.session_state['paste_key'] = ""


def set_generated_words_state(
    data_list: List[Tuple[str, int]],
    raw_count: int = 0,
    stats_info: Optional[Dict[str, float]] = None
) -> None:
    """Update extracted words and keep editor text in sync with new generation."""
    pkg_path = st.session_state.get('anki_pkg_path')
    if pkg_path and os.path.exists(pkg_path):
        try:
            os.remove(pkg_path)
        except OSError as e:
            logger.warning("Could not remove temp anki package: %s", e)

    st.session_state['anki_pkg_path'] = ""
    st.session_state['anki_pkg_name'] = ""
    st.session_state['anki_cards_cache'] = None
    st.session_state['gen_words_data'] = data_list
    st.session_state['raw_count'] = raw_count
    st.session_state['stats_info'] = stats_info
    st.session_state['extract_remaining_words_text'] = ""
    word_list_text = "\n".join([w for w, _ in data_list])
    st.session_state['prepared_word_list_text'] = word_list_text
    st.session_state['card_word_list_editor'] = word_list_text
    st.session_state['word_list_editor'] = word_list_text
    st.session_state['extract_word_editor'] = word_list_text
