"""
Vocab Flow Ultra – Streamlit entry point.
UI modules live under ui/, while business logic remains in
constants, resources, extraction, vocab, ai, anki_parse, tts,
anki_package, and state.
"""

import sys
from pathlib import Path

import streamlit as st

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import resources
from ui.helpers import initialize_session_state
from ui.styles import (
    apply_global_styles,
    configure_page,
    render_app_footer,
    render_app_header,
    render_help_panel,
    render_ios_resume_reloader,
)

configure_page()

# Load vocab and expose to resources for modules that read the shared globals.
VOCAB_DICT, FULL_DF = resources.load_vocab_data()
resources.VOCAB_DICT = VOCAB_DICT
resources.FULL_DF = FULL_DF

initialize_session_state()
apply_global_styles()
render_ios_resume_reloader()
render_app_header()
render_help_panel(bool(VOCAB_DICT))

MAIN_SECTIONS = ["1️⃣ 查单词", "2️⃣ 提取单词", "3️⃣ 制作卡片"]
if st.session_state.get("main_section") not in MAIN_SECTIONS:
    st.session_state["main_section"] = MAIN_SECTIONS[0]

section = st.radio(
    "功能",
    MAIN_SECTIONS,
    horizontal=True,
    label_visibility="collapsed",
    key="main_section",
)

if section == "1️⃣ 查单词":
    from ui.lookup import render_lookup_tab

    render_lookup_tab(VOCAB_DICT)
elif section == "2️⃣ 提取单词":
    from ui.extraction import render_extraction_tab

    render_extraction_tab(VOCAB_DICT, FULL_DF)
else:
    from ui.cards import render_cards_tab

    render_cards_tab()

render_app_footer()
