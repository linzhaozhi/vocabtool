"""Shared UI helpers for state, validation, and extraction-source handling."""

import logging
import os
import random
import re

import streamlit as st

import constants

logger = logging.getLogger(__name__)

EXTRACT_SOURCE_OPTIONS = ["文章 URL", "文件", "文本", "单词表", "Anki", "词库"]
EXTRACT_SOURCE_WIDGET_KEY = "extract_source_mode_widget"
EXTRACT_SOURCE_LEGACY_MAP = {
    "文章 / 文件": "文章 URL",
    "单词列表 / Anki": "单词表",
    "单词列表": "单词表",
}


def initialize_session_state() -> None:
    """Initialize session state defaults used across the app."""
    for key, default_value in constants.DEFAULT_SESSION_STATE.items():
        if key not in st.session_state:
            st.session_state[key] = default_value
    if "anki_cards_cache" not in st.session_state:
        st.session_state["anki_cards_cache"] = None
    if "deepseek_chat_messages" not in st.session_state:
        st.session_state["deepseek_chat_messages"] = []
    if "deepseek_chat_last_model" not in st.session_state:
        st.session_state["deepseek_chat_last_model"] = {}


def set_anki_pkg(file_path: str, deck_name: str) -> None:
    """Store Anki package path in session state and clean previous file."""
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError("Generated Anki package file not found.")

    prev_path = st.session_state.get("anki_pkg_path")
    if prev_path and prev_path != file_path:
        try:
            if os.path.exists(prev_path):
                os.remove(prev_path)
        except OSError as exc:
            logger.warning("Could not remove previous anki package: %s", exc)

    st.session_state["anki_pkg_path"] = file_path
    st.session_state["anki_pkg_name"] = f"{deck_name}.apkg"


def render_anki_download_button(
    label: str,
    *,
    button_type: str = "primary",
    use_container_width: bool = False,
) -> None:
    """Safely render Anki package download button if file exists."""
    file_path = st.session_state.get("anki_pkg_path")
    file_name = st.session_state.get("anki_pkg_name", "词卡.apkg")

    if not file_path:
        return
    if not os.path.exists(file_path):
        st.warning("⚠️ 下载文件不存在，请重新生成。")
        st.session_state["anki_pkg_path"] = ""
        return

    try:
        with open(file_path, "rb") as file_obj:
            st.download_button(
                label=label,
                data=file_obj.read(),
                file_name=file_name,
                mime="application/octet-stream",
                type=button_type,
                use_container_width=use_container_width,
            )
    except OSError as exc:
        logger.error("Failed to open package for download: %s", exc)
        st.error("❌ 下载文件读取失败，请重新生成。")


def reset_anki_state() -> None:
    """Clear generated Anki package state but keep the source word list."""
    st.session_state["anki_cards_cache"] = None
    if st.session_state.get("anki_pkg_path"):
        try:
            if os.path.exists(st.session_state["anki_pkg_path"]):
                os.remove(st.session_state["anki_pkg_path"])
        except OSError as exc:
            logger.warning("Could not remove temp anki package: %s", exc)
    st.session_state["anki_pkg_path"] = ""
    st.session_state["anki_pkg_name"] = ""


def reset_extraction_state() -> None:
    """Clear extracted word results and any generated card artifacts."""
    reset_anki_state()
    for key in ("gen_words_data", "raw_count", "process_time", "stats_info", "word_list_editor", "extract_word_editor"):
        if key in st.session_state:
            del st.session_state[key]


def parse_unique_words(raw_text: str) -> list[str]:
    """Normalize a raw word list into unique entries while preserving order."""
    words: list[str] = []
    seen_words = set()
    for word in re.split(r"[,\n\t]+", raw_text):
        cleaned = word.strip()
        if cleaned and cleaned.lower() not in seen_words:
            seen_words.add(cleaned.lower())
            words.append(cleaned)
    return words


def sync_extract_editor_to_cards() -> None:
    """Keep the card creation editor in sync with extraction edits."""
    st.session_state["word_list_editor"] = st.session_state.get("extract_word_editor", "")


def sync_card_editor_to_extract() -> None:
    """Keep the extraction editor in sync with card creation edits."""
    st.session_state["extract_word_editor"] = st.session_state.get("word_list_editor", "")


def normalize_lookup_query(raw_text: str) -> str:
    """Normalize lookup input by collapsing repeated whitespace."""
    return re.sub(r"\s+", " ", raw_text).strip()


def is_english_lookup_query(query: str) -> bool:
    """Allow short English words/phrases, not full sentences or prompts."""
    if len(query) > 40:
        return False
    if re.search(r"[0-9@#<>_=+*{}[\]|\\]", query):
        return False
    if re.search(r"[。！？；：，、“”‘’（）]", query):
        return False
    if query.count(" ") > 4:
        return False
    english_tokens = query.split()
    if not english_tokens:
        return False
    if len(english_tokens) > 5:
        return False
    if not all(re.fullmatch(r"[A-Za-z]+(?:['-][A-Za-z]+)*", token) for token in english_tokens):
        return False

    lowered = query.lower()
    blocked_prefixes = (
        "what ",
        "what's ",
        "what is ",
        "how ",
        "why ",
        "please ",
        "tell me ",
        "can you ",
        "could you ",
        "would you ",
        "explain ",
        "translate ",
        "help me ",
        "give me ",
        "show me ",
    )
    blocked_fragments = (
        " mean",
        " meaning",
        " sentence",
        " example",
        " examples",
        " explain",
        " translation",
        " translate",
        " usage",
    )
    if lowered.startswith(blocked_prefixes):
        return False
    if any(fragment in lowered for fragment in blocked_fragments):
        return False
    return True


def is_chinese_gloss_query(query: str) -> bool:
    """Allow short Chinese glosses that look like meanings, not chat prompts."""
    stripped = query.replace(" ", "")
    if not stripped:
        return False
    if len(stripped) > 12:
        return False
    if re.search(r"[A-Za-z0-9@#<>_=+*{}[\]|\\,.!?;:。！？；：]", query):
        return False
    if not re.fullmatch(r"[\u4e00-\u9fff、/·\- ]+", query):
        return False

    blocked_phrases = (
        "请",
        "帮我",
        "告诉我",
        "我想",
        "我想知道",
        "解释一下",
        "解释",
        "什么意思",
        "什么是",
        "为什么",
        "怎么",
        "如何",
        "能不能",
        "可以吗",
        "举例",
        "造句",
        "写一段",
        "翻译这句",
        "帮我翻译",
        "聊天",
    )
    return not any(phrase in query for phrase in blocked_phrases)


def validate_lookup_query(raw_text: str) -> tuple[bool, str, str]:
    """Validate quick-lookup input and return (is_valid, normalized_query, error)."""
    query = normalize_lookup_query(raw_text)
    if not query:
        return False, "", "⚠️ 请输入单词、短语或简短中文释义。"
    if is_english_lookup_query(query) or is_chinese_gloss_query(query):
        return True, query, ""
    return False, "", "⚠️ 这里只能查询英文单词/短语，或很短的中文释义词组；不支持提问、聊天或整句输入。"


def extract_code_block_text(raw_text: str) -> str:
    """Extract text content from fenced code blocks when present."""
    code_blocks = re.findall(r"```(?:text)?\s*(.*?)\s*```", raw_text, re.DOTALL)
    if code_blocks:
        return "\n".join(code_blocks).strip()
    return raw_text.strip()


def parse_topic_word_list(raw_text: str) -> list[str]:
    """Parse AI-generated topic word list into normalized unique entries."""
    text = extract_code_block_text(raw_text)
    cleaned_lines = []

    for line in text.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)]?)\s*", "", line).strip()
        if not line:
            continue
        if re.fullmatch(r"[A-Za-z]+(?:[ '-][A-Za-z]+)*", line) and line.count(" ") <= 2:
            cleaned_lines.append(line.lower())

    return parse_unique_words("\n".join(cleaned_lines))


def validate_topic_label(raw_text: str) -> tuple[bool, str, str]:
    """Validate short topic labels for AI topic word-list generation."""
    topic = normalize_lookup_query(raw_text)
    if not topic:
        return False, "", "⚠️ 请输入一个主题，比如“旅游”或“校园生活”。"
    if len(topic) > 30:
        return False, "", "⚠️ 主题太长了，请控制在 30 个字符以内。"

    lowered = topic.lower()
    blocked_phrases = (
        "为什么",
        "怎么",
        "如何",
        "解释",
        "分析",
        "总结",
        "翻译",
        "聊天",
        "请帮我",
        "告诉我",
        "what",
        "why",
        "how",
        "tell me",
        "explain",
    )
    if any(phrase in topic for phrase in blocked_phrases) or any(phrase in lowered for phrase in blocked_phrases):
        return False, "", "⚠️ 这里只支持简短主题，不支持提问或聊天式输入。"

    if re.search(r"[0-9@#<>_=+*{}[\]|\\!?.,;:，。！？；：]", topic):
        return False, "", "⚠️ 主题里不要带数字或整句标点，只保留简短主题词。"

    if not re.fullmatch(r"[A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff&/'\- ]*", topic):
        return False, "", "⚠️ 主题建议只填写简短词组，比如“旅游”或“校园生活”。"

    return True, topic, ""


def normalize_extract_source_mode(value: str | None) -> str:
    """Normalize extract source mode, including legacy labels from older UI versions."""
    if not value:
        return EXTRACT_SOURCE_OPTIONS[0]
    normalized = EXTRACT_SOURCE_LEGACY_MAP.get(value, value)
    if normalized not in EXTRACT_SOURCE_OPTIONS:
        return EXTRACT_SOURCE_OPTIONS[0]
    return normalized


def refresh_extract_source_inputs(current_mode: str) -> None:
    """Reset source-specific widgets so switching sources always shows the right inputs."""
    st.session_state["uploader_id"] = str(random.randint(constants.MIN_RANDOM_ID, constants.MAX_RANDOM_ID))

    if current_mode != "文章 URL":
        st.session_state["url_input_key"] = ""
    if current_mode != "文本" and "paste_key" in st.session_state:
        st.session_state["paste_key"] = ""
    if current_mode != "单词表" and "wordlist_import_uploader" in st.session_state:
        del st.session_state["wordlist_import_uploader"]
    if current_mode != "Anki" and "anki_import_uploader" in st.session_state:
        del st.session_state["anki_import_uploader"]


def set_extract_source_mode(mode: str | None) -> str:
    """Persist the current source mode and refresh dependent widgets when it changes."""
    current_mode = normalize_extract_source_mode(mode)
    previous_mode = normalize_extract_source_mode(st.session_state.get("extract_source_mode"))
    st.session_state["extract_source_mode"] = current_mode
    if previous_mode != current_mode:
        refresh_extract_source_inputs(current_mode)
    return current_mode


def handle_extract_source_change() -> None:
    """Handle source changes from the UI widget."""
    set_extract_source_mode(st.session_state.get(EXTRACT_SOURCE_WIDGET_KEY))
