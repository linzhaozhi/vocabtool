"""
Vocab Flow Ultra – Streamlit entry point.
UI modules live under ui/, while business logic remains in
constants, resources, extraction, vocab, ai, anki_parse, tts,
anki_package, and state.
"""

import streamlit as st

import resources
from anki_package import cleanup_old_apkg_files
from ui.cards import render_cards_tab
from ui.chat import render_chat_tab
from ui.extraction import render_extraction_tab
from ui.helpers import initialize_session_state
from ui.lookup import render_lookup_tab
from ui.styles import (
    apply_global_styles,
    configure_page,
    render_app_footer,
    render_app_header,
    render_help_panel,
)

configure_page()

# Load vocab and expose to resources for modules that read the shared globals.
VOCAB_DICT, FULL_DF = resources.load_vocab_data()
resources.VOCAB_DICT = VOCAB_DICT
resources.FULL_DF = FULL_DF

# Clean old .apkg files from our temp subdir (e.g. from previous sessions).
cleanup_old_apkg_files()

initialize_session_state()
apply_global_styles()
render_app_header()
render_help_panel(bool(VOCAB_DICT))

tab_lookup, tab_extract, tab_cards, tab_chat = st.tabs([
    "1️⃣ 查单词",
    "2️⃣ 提取单词",
    "3️⃣ 制作卡片",
    "4️⃣ DeepSeek 聊天",
])

with tab_lookup:
    render_lookup_tab(VOCAB_DICT)

with tab_extract:
    render_extraction_tab(VOCAB_DICT, FULL_DF)

with tab_cards:
    render_cards_tab()

with tab_chat:
    render_chat_tab()

render_app_footer()
