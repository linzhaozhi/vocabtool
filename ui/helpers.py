"""Shared UI helpers for state, validation, and extraction-source handling."""

from __future__ import annotations

import logging
import os
import random
import re

import streamlit as st

import constants

logger = logging.getLogger(__name__)

EXTRACT_SOURCE_OPTIONS = ["文件", "文本", "文章 URL", "单词表", "Anki", "词库"]
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
    for key in (
        "gen_words_data",
        "raw_count",
        "process_time",
        "stats_info",
        "prepared_word_list_text",
        "card_word_list_editor",
        "word_list_editor",
        "extract_word_editor",
    ):
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


def parse_wordlist_candidates(raw_text: str) -> list[str]:
    """Parse a messy user word list while preserving useful phrases."""
    words: list[str] = []
    seen_words = set()
    for raw_item in re.split(r"[,\n\t]+", str(raw_text or "")):
        cleaned = raw_item.strip()
        cleaned = re.sub(r"^[\s>*•◆◇●○\-–—]+", "", cleaned).strip()
        cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned).strip()
        cleaned = re.sub(r"\s+", " ", cleaned)
        cleaned = cleaned.strip(" \r\n,;:，。；：.!?！？\"“”‘’")
        cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned).strip()

        if not cleaned:
            continue
        if re.fullmatch(r"(?i)chapter\s+\d+", cleaned):
            continue
        if len(cleaned) > 70:
            continue
        if not re.search(r"[A-Za-z]", cleaned):
            continue

        normalized = re.sub(r"\s+", " ", cleaned).lower()
        if normalized not in seen_words:
            seen_words.add(normalized)
            words.append(cleaned)
    return words


def _generated_words_to_text() -> str:
    """Build a word-list text value from the latest generated data."""
    lines: list[str] = []
    for item in st.session_state.get("gen_words_data") or []:
        if isinstance(item, dict):
            word = item.get("word", "")
        elif isinstance(item, (list, tuple)) and item:
            word = item[0]
        else:
            word = item
        cleaned = str(word).strip()
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def get_prepared_word_list_text() -> str:
    """Return the persistent word list shared by extraction and card pages."""
    if "prepared_word_list_text" in st.session_state:
        prepared_text = str(st.session_state.get("prepared_word_list_text") or "")
        if prepared_text.strip():
            return prepared_text

    for legacy_key in ("card_word_list_editor", "word_list_editor", "extract_word_editor"):
        legacy_text = str(st.session_state.get(legacy_key) or "")
        if legacy_text.strip():
            st.session_state["prepared_word_list_text"] = legacy_text
            return legacy_text

    fallback_text = _generated_words_to_text()
    if fallback_text:
        st.session_state["prepared_word_list_text"] = fallback_text
    return fallback_text


def set_prepared_word_list_text(raw_text: str, *, allow_empty: bool = False) -> None:
    """Persist the current word list independently from Streamlit widget keys."""
    text = str(raw_text or "")
    if text.strip() or allow_empty or not get_prepared_word_list_text().strip():
        st.session_state["prepared_word_list_text"] = text


def restore_word_editor_state(editor_key: str) -> str:
    """Restore a page editor from the persistent word list if Streamlit cleaned it."""
    prepared_text = get_prepared_word_list_text()
    current_text = str(st.session_state.get(editor_key) or "")
    if prepared_text and not current_text.strip():
        st.session_state[editor_key] = prepared_text
        current_text = prepared_text
    return current_text


def sync_extract_editor_to_cards() -> None:
    """Keep the card creation editor in sync with extraction edits."""
    editor_text = st.session_state.get("extract_word_editor", "")
    set_prepared_word_list_text(editor_text, allow_empty=True)
    st.session_state["card_word_list_editor"] = editor_text
    st.session_state["word_list_editor"] = editor_text


def sync_card_editor_to_extract() -> None:
    """Keep the extraction editor in sync with card creation edits."""
    editor_text = st.session_state.get("card_word_list_editor", st.session_state.get("word_list_editor", ""))
    set_prepared_word_list_text(editor_text, allow_empty=True)
    st.session_state["extract_word_editor"] = editor_text
    st.session_state["word_list_editor"] = editor_text


def clear_quick_lookup_state() -> None:
    """Clear quick lookup input and its rendered result."""
    st.session_state["quick_lookup_word"] = ""
    st.session_state["quick_lookup_last_query"] = ""
    st.session_state["quick_lookup_last_result"] = None
    st.session_state["quick_lookup_is_loading"] = False


def clear_english_question_state() -> None:
    """Clear English Q&A input and rendered answer."""
    st.session_state["english_question_input"] = ""
    st.session_state["english_question_last_query"] = ""
    st.session_state["english_question_last_result"] = None
    st.session_state["english_question_is_loading"] = False


def clear_topic_wordlist_state() -> None:
    """Clear topic word-list input and generated output."""
    st.session_state["topic_word_topic"] = ""
    st.session_state["topic_wordlist_result"] = ""
    st.session_state["topic_wordlist_words"] = []


def clear_url_input() -> None:
    """Clear article URL input."""
    st.session_state["url_input_key"] = ""


def clear_paste_input() -> None:
    """Clear pasted text input."""
    st.session_state["paste_key"] = ""


def clear_direct_wordlist_input(file_signature: str = "") -> None:
    """Clear direct word-list text input."""
    st.session_state["direct_wordlist_input"] = ""
    st.session_state["direct_wordlist_file_signature"] = file_signature
    st.session_state["ai_word_selection_selected"] = ""
    st.session_state["ai_word_selection_remaining"] = ""


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
        return False, "", "⚠️ 请输入一个英文单词、短语或简短中文释义。"
    if is_english_lookup_query(query) or is_chinese_gloss_query(query):
        return True, query, ""
    return False, "", "⚠️ 查单词只支持单词、短语或简短中文释义；用法、语法、辨析等问题请用下方“英语问答”。"


def validate_english_question(raw_text: str) -> tuple[bool, str, str]:
    """Validate English-learning questions for the standalone Q&A tab."""
    question = raw_text.strip()
    if not question:
        return False, "", "⚠️ 请输入一个英语学习问题。"
    if len(question) > 800:
        return False, "", "⚠️ 问题太长了，请控制在 800 个字符以内。"
    if re.search(r"https?://|www\.|[`<>_=+*{}[\]|\\]", question, flags=re.IGNORECASE):
        return False, "", "⚠️ 暂不支持链接、代码或复杂格式内容。"

    lowered = question.lower()
    allowed_markers = (
        "区别",
        "差别",
        "不同",
        "辨析",
        "用法",
        "语法",
        "时态",
        "例句",
        "造句",
        "翻译",
        "怎么说",
        "怎么表达",
        "改写",
        "润色",
        "自然",
        "地道",
        "纠正",
        "发音",
        "搭配",
        "作文",
        "句子",
        "这句",
        "句话",
        "表达",
        "口语",
        "正式",
        "邮件",
        "单词",
        "短语",
        "英语",
        "英文",
        "meaning",
        "mean",
        "difference",
        "grammar",
        "usage",
        "example",
        "sentence",
        "translate",
        "rewrite",
        "correct",
        "polish",
        "natural",
        "idiomatic",
        "casual",
        "formal",
        "email",
        "pronunciation",
        "collocation",
        "tense",
        "word",
        "phrase",
        "english",
    )
    if any(marker in lowered for marker in allowed_markers) or re.search(r"[A-Za-z]", question):
        return True, question, ""
    return False, "", "⚠️ 这里只回答英语学习相关问题。"


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
