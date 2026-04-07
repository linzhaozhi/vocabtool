# Session state helpers.

import os
import random
from typing import Dict, List, Optional, Tuple

import streamlit as st

import constants

logger = __import__("logging").getLogger(__name__)


def clear_all_state() -> None:
    """Clear all session state for fresh start."""
    pkg_path = st.session_state.get('anki_pkg_path')
    if pkg_path and os.path.exists(pkg_path):
        try:
            os.remove(pkg_path)
        except OSError as e:
            logger.warning("Could not remove temp anki package: %s", e)

    if 'url_input_key' in st.session_state:
        st.session_state['url_input_key'] = ""

    keys_to_drop = [
        'gen_words_data', 'raw_count', 'process_time', 'stats_info',
        'anki_pkg_path', 'anki_pkg_name', 'anki_input_text', 'anki_cards_cache'
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
    st.session_state['gen_words_data'] = data_list
    st.session_state['raw_count'] = raw_count
    st.session_state['stats_info'] = stats_info
    st.session_state['word_list_editor'] = "\n".join([w for w, _ in data_list])
