"""Lookup tab rendering."""

import html
import re

import streamlit as st

import constants
from ai import (
    answer_english_learning_question,
    generate_topic_word_list,
    get_word_quick_definition,
    get_word_simple_definition,
)
from state import set_generated_words_state
from ui.helpers import (
    clear_english_question_state,
    clear_quick_lookup_state,
    clear_simple_lookup_state,
    clear_topic_wordlist_state,
    parse_topic_word_list,
    validate_english_question,
    validate_lookup_query,
    validate_topic_label,
)
from utils import render_copy_button


def _strip_lookup_html_fragments(raw_content: str) -> str:
    """Remove model-leaked HTML fragments before any lookup rendering."""
    text = str(raw_content or "")
    for _ in range(3):
        unescaped = html.unescape(text)
        if unescaped == text:
            break
        text = unescaped

    html_fragment_pattern = r"</?\s*[A-Za-z][A-Za-z0-9:-]*(?:\s+[^<>]*)?>"
    escaped_fragment_pattern = r"&lt;/?\s*[A-Za-z][A-Za-z0-9:-]*(?:\s+[^&<>]*)?&gt;"
    text = re.sub(html_fragment_pattern, "", text)
    text = re.sub(escaped_fragment_pattern, "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)&(?:amp;)*lt;\s*/?\s*(?:div|span|p|br)\s*(?:&(?:amp;)*gt;|>)", "", text)
    text = re.sub(r"(?i)(?:</?\s*(?:div|span|p|br)\s*>|&lt;/?\s*(?:div|span|p|br)\s*&gt;)", "", text)
    return text.replace("</div>", "").replace("<div>", "")


def _format_lookup_question_answer(raw_content: str) -> str:
    """Render freeform vocabulary answers safely while supporting simple Markdown."""
    text = _strip_lookup_html_fragments(raw_content)
    text = text.strip()
    if not text:
        return ""

    rendered_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            rendered_lines.append('<div class="quick-lookup-gap"></div>')
            continue

        safe_line = html.escape(line)
        safe_line = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", safe_line)

        if safe_line.startswith(("- ", "• ")):
            rendered_lines.append(f'<div class="quick-lookup-answer-bullet">{safe_line[2:].strip()}</div>')
        else:
            rendered_lines.append(f'<div class="quick-lookup-answer-line">{safe_line}</div>')

    return '<div class="quick-lookup-answer">' + "".join(rendered_lines) + "</div>"


def _render_lookup_result_card(result: dict, *, error_prefix: str) -> None:
    """Render AI lookup output using the shared lookup card styling."""
    if result and "error" not in result:
        raw_content = _strip_lookup_html_fragments(result["result"])
        if result.get("is_question") or result.get("rank") is None:
            display_html = _format_lookup_question_answer(raw_content)
        else:
            lines = [line.strip() for line in raw_content.split("\n") if line.strip()]
            rendered_lines = []

            for idx, line in enumerate(lines):
                safe_line = html.escape(line)

                if line.startswith("🌱") or line.startswith("【"):
                    rendered_lines.append(f'<div class="quick-lookup-line quick-lookup-ety">{safe_line}</div>')
                elif idx == 0:
                    rendered_lines.append(f'<div class="quick-lookup-line quick-lookup-head">{safe_line}</div>')
                elif line.startswith("🔊"):
                    rendered_lines.append(f'<div class="quick-lookup-line quick-lookup-phon">{safe_line}</div>')
                elif "|" in line:
                    rendered_lines.append(f'<div class="quick-lookup-line quick-lookup-def">{safe_line}</div>')
                elif line.startswith("•"):
                    rendered_lines.append(f'<div class="quick-lookup-line quick-lookup-ex">{safe_line}</div>')
                else:
                    rendered_lines.append(f'<div class="quick-lookup-line quick-lookup-para">{safe_line}</div>')

            display_html = "".join(rendered_lines).replace("\n", "<br>")

        st.markdown(
            f"""
        <div style="background: var(--vf-accent-gradient); padding: 3px; border-radius: 14px; margin: 15px 0; box-shadow: var(--vf-shadow-soft);">
            <div style="background: var(--vf-surface-elevated); border: 1px solid var(--vf-border); padding: 25px; border-radius: 12px;">
                <div class="quick-lookup-card">
                    {display_html}
                </div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    elif result and "error" in result:
        st.error(f"❌ {error_prefix}：{result.get('error', '未知错误')}")


def _render_simple_lookup() -> None:
    st.markdown("### 📘 简洁查词")
    st.caption("输入英文单词或短语，返回最多 3 个核心释义；每个释义 1 个自然例句（含中文翻译）。")
    st.markdown("例如：apple、book、school")

    if "simple_lookup_last_query" not in st.session_state:
        st.session_state["simple_lookup_last_query"] = ""
    if "simple_lookup_last_result" not in st.session_state:
        st.session_state["simple_lookup_last_result"] = None
    if "simple_lookup_is_loading" not in st.session_state:
        st.session_state["simple_lookup_is_loading"] = False
    if "simple_lookup_cache_keys" not in st.session_state:
        st.session_state["simple_lookup_cache_keys"] = []
    if st.session_state.get("simple_lookup_cache_version") != constants.SIMPLE_LOOKUP_CACHE_VERSION:
        for key in list(st.session_state.keys()):
            if str(key).startswith("simple_lookup_cache_"):
                del st.session_state[key]
        st.session_state["simple_lookup_cache_keys"] = []
        st.session_state["simple_lookup_last_result"] = None
        st.session_state["simple_lookup_cache_version"] = constants.SIMPLE_LOOKUP_CACHE_VERSION

    with st.form("simple_lookup_form", clear_on_submit=False):
        col_word, col_btn, col_clear = st.columns([4, 1, 1])
        with col_word:
            lookup_word = st.text_input(
                "输入英文单词或短语",
                placeholder="输入英文单词或短语",
                key="simple_lookup_word",
                label_visibility="collapsed",
                autocomplete="off",
            )
        with col_btn:
            lookup_submit = st.form_submit_button(
                "查询中..." if st.session_state["simple_lookup_is_loading"] else "查询",
                type="primary",
                use_container_width=True,
                disabled=st.session_state["simple_lookup_is_loading"],
            )
        with col_clear:
            st.form_submit_button(
                "清空",
                type="secondary",
                use_container_width=True,
                on_click=clear_simple_lookup_state,
            )

    if lookup_submit:
        is_valid_query, query_word, error_message = validate_lookup_query(lookup_word)
        if not is_valid_query:
            st.session_state["simple_lookup_last_query"] = ""
            st.session_state["simple_lookup_last_result"] = None
            st.warning(error_message)
        elif st.session_state["simple_lookup_is_loading"]:
            st.info("⏳ 查询进行中，请稍候。")
        else:
            st.session_state["simple_lookup_is_loading"] = True
            try:
                cache_key = f"simple_lookup_cache_{constants.SIMPLE_LOOKUP_CACHE_VERSION}_{query_word.lower()}"
                if cache_key not in st.session_state:
                    with st.spinner("🔍 查询中..."):
                        st.session_state[cache_key] = get_word_simple_definition(query_word)
                    keys = st.session_state["simple_lookup_cache_keys"]
                    keys.append(cache_key)
                    while len(keys) > constants.QUICK_LOOKUP_CACHE_MAX:
                        old_key = keys.pop(0)
                        if old_key in st.session_state:
                            del st.session_state[old_key]
                    st.session_state["simple_lookup_cache_keys"] = keys
                st.session_state["simple_lookup_last_query"] = query_word
                st.session_state["simple_lookup_last_result"] = st.session_state.get(cache_key)
            finally:
                st.session_state["simple_lookup_is_loading"] = False

    _render_lookup_result_card(st.session_state.get("simple_lookup_last_result"), error_prefix="查询失败")
    st.markdown("---")


def _render_quick_lookup() -> None:
    st.markdown("### 🌱 词源查询")
    st.caption("输入英文单词或短语，返回最多 3 个核心释义、底层逻辑和现代感词源故事。")
    st.markdown("例如：apple、April、school")

    if "quick_lookup_last_query" not in st.session_state:
        st.session_state["quick_lookup_last_query"] = ""
    if "quick_lookup_last_result" not in st.session_state:
        st.session_state["quick_lookup_last_result"] = None
    if "quick_lookup_is_loading" not in st.session_state:
        st.session_state["quick_lookup_is_loading"] = False
    if "quick_lookup_cache_keys" not in st.session_state:
        st.session_state["quick_lookup_cache_keys"] = []
    if st.session_state.get("quick_lookup_cache_version") != constants.QUICK_LOOKUP_CACHE_VERSION:
        for key in list(st.session_state.keys()):
            if str(key).startswith("lookup_cache_"):
                del st.session_state[key]
        st.session_state["quick_lookup_cache_keys"] = []
        st.session_state["quick_lookup_last_result"] = None
        st.session_state["quick_lookup_cache_version"] = constants.QUICK_LOOKUP_CACHE_VERSION

    with st.form("quick_lookup_form", clear_on_submit=False):
        col_word, col_btn, col_clear = st.columns([4, 1, 1])
        with col_word:
            lookup_word = st.text_input(
                "输入英文单词或短语",
                placeholder="输入英文单词或短语",
                key="quick_lookup_word",
                label_visibility="collapsed",
                autocomplete="off",
            )
        with col_btn:
            lookup_submit = st.form_submit_button(
                "查询中..." if st.session_state["quick_lookup_is_loading"] else "查询",
                type="primary",
                use_container_width=True,
                disabled=st.session_state["quick_lookup_is_loading"],
            )
        with col_clear:
            st.form_submit_button(
                "清空",
                type="secondary",
                use_container_width=True,
                on_click=clear_quick_lookup_state,
            )

    if lookup_submit:
        is_valid_query, query_word, error_message = validate_lookup_query(lookup_word)
        if not is_valid_query:
            st.session_state["quick_lookup_last_query"] = ""
            st.session_state["quick_lookup_last_result"] = None
            st.warning(error_message)
        elif st.session_state["quick_lookup_is_loading"]:
            st.info("⏳ 查询进行中，请稍候。")
        else:
            st.session_state["quick_lookup_is_loading"] = True
            try:
                cache_key = f"lookup_cache_{constants.QUICK_LOOKUP_CACHE_VERSION}_{query_word.lower()}"
                if cache_key not in st.session_state:
                    with st.spinner("🔍 查询中..."):
                        st.session_state[cache_key] = get_word_quick_definition(query_word)
                    keys = st.session_state["quick_lookup_cache_keys"]
                    keys.append(cache_key)
                    while len(keys) > constants.QUICK_LOOKUP_CACHE_MAX:
                        old_key = keys.pop(0)
                        if old_key in st.session_state:
                            del st.session_state[old_key]
                    st.session_state["quick_lookup_cache_keys"] = keys
                st.session_state["quick_lookup_last_query"] = query_word
                st.session_state["quick_lookup_last_result"] = st.session_state.get(cache_key)
            finally:
                st.session_state["quick_lookup_is_loading"] = False

    _render_lookup_result_card(st.session_state.get("quick_lookup_last_result"), error_prefix="查询失败")


if hasattr(st, "fragment"):
    render_quick_lookup = st.fragment(_render_quick_lookup)
    render_simple_lookup = st.fragment(_render_simple_lookup)
else:
    render_quick_lookup = _render_quick_lookup
    render_simple_lookup = _render_simple_lookup


def _render_english_questions() -> None:
    st.markdown("### 💬 英语助手")
    st.caption("把平时会问 AI 的英语问题放这里：用法、语法、辨析、翻译、润色、纠错、搭配、发音都可以。")
    st.markdown("例如：affect 和 effect 有什么区别？这句话语法对吗？帮我把这句英文写自然一点。")

    if "english_question_last_query" not in st.session_state:
        st.session_state["english_question_last_query"] = ""
    if "english_question_last_result" not in st.session_state:
        st.session_state["english_question_last_result"] = None
    if "english_question_is_loading" not in st.session_state:
        st.session_state["english_question_is_loading"] = False

    with st.form("english_question_form", clear_on_submit=False):
        question_text = st.text_area(
            "输入英语学习问题",
            height=120,
            key="english_question_input",
            placeholder="输入任何英文相关问题，比如翻译、润色、语法、辨析、例句、搭配、改句子...",
            label_visibility="collapsed",
        )
        col_submit, col_clear = st.columns([1, 1])
        with col_submit:
            question_submit = st.form_submit_button(
                "回答中..." if st.session_state["english_question_is_loading"] else "提问",
                type="primary",
                use_container_width=True,
                disabled=st.session_state["english_question_is_loading"],
            )
        with col_clear:
            st.form_submit_button(
                "清空",
                type="secondary",
                use_container_width=True,
                on_click=clear_english_question_state,
            )

    if question_submit:
        is_valid_question, normalized_question, error_message = validate_english_question(question_text)
        if not is_valid_question:
            st.session_state["english_question_last_query"] = ""
            st.session_state["english_question_last_result"] = None
            st.warning(error_message)
        elif st.session_state["english_question_is_loading"]:
            st.info("⏳ 回答进行中，请稍候。")
        else:
            st.session_state["english_question_is_loading"] = True
            try:
                with st.spinner("💬 正在回答..."):
                    st.session_state["english_question_last_result"] = answer_english_learning_question(
                        normalized_question
                    )
                st.session_state["english_question_last_query"] = normalized_question
            finally:
                st.session_state["english_question_is_loading"] = False

    result = st.session_state.get("english_question_last_result")
    if result and "error" not in result:
        display_html = _format_lookup_question_answer(result.get("result", ""))
        st.markdown(
            f"""
        <div style="background: var(--vf-accent-gradient); padding: 3px; border-radius: 14px; margin: 15px 0; box-shadow: var(--vf-shadow-soft);">
            <div style="background: var(--vf-surface-elevated); border: 1px solid var(--vf-border); padding: 25px; border-radius: 12px;">
                {display_html}
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    elif result and "error" in result:
        st.error(f"❌ 回答失败：{result.get('error', '未知错误')}")

    st.markdown("---")


if hasattr(st, "fragment"):
    render_english_questions = st.fragment(_render_english_questions)
else:
    render_english_questions = _render_english_questions


def render_lookup_tab(_: dict[str, int]) -> None:
    """Render the word-only lookup tab."""
    render_simple_lookup()
    render_quick_lookup()


def render_english_questions_tab(vocab_dict: dict[str, int]) -> None:
    """Render English Q&A and topic word-list tools."""
    render_english_questions()

    st.markdown("### 🧠 主题词表生成")
    st.caption(f"💡 只要选择主题和个数即可。单次最多生成 {constants.AI_TOPIC_WORDLIST_MAX} 个常见词。")
    st.markdown("例如：旅游、商务、校园生活")

    if "topic_wordlist_result" not in st.session_state:
        st.session_state["topic_wordlist_result"] = ""
    if "topic_wordlist_words" not in st.session_state:
        st.session_state["topic_wordlist_words"] = []

    with st.form("topic_wordlist_form", clear_on_submit=False):
        col_topic, col_count, col_submit, col_clear = st.columns([3, 2, 1, 1])
        with col_topic:
            topic_word_topic = st.text_input(
                "输入主题",
                placeholder="输入简短主题",
                key="topic_word_topic",
                label_visibility="collapsed",
                autocomplete="off",
            )
        with col_count:
            topic_word_count = st.slider(
                "个数",
                min_value=1,
                max_value=constants.AI_TOPIC_WORDLIST_MAX,
                value=20,
                step=1,
                key="topic_word_count",
                help=f"单次最多 {constants.AI_TOPIC_WORDLIST_MAX} 个",
            )
        with col_submit:
            topic_word_submit = st.form_submit_button("生成", type="primary", use_container_width=True)
        with col_clear:
            st.form_submit_button(
                "清空",
                type="secondary",
                use_container_width=True,
                on_click=clear_topic_wordlist_state,
            )

    if topic_word_submit:
        is_valid_topic, normalized_topic, error_message = validate_topic_label(topic_word_topic)
        if not is_valid_topic:
            st.warning(error_message)
        else:
            with st.spinner("🧠 正在生成主题词表..."):
                ai_result = generate_topic_word_list(normalized_topic, int(topic_word_count))

            if ai_result and "error" not in ai_result:
                generated_words = parse_topic_word_list(ai_result["result"])
                if generated_words:
                    st.session_state["topic_wordlist_words"] = generated_words[: constants.AI_TOPIC_WORDLIST_MAX]
                    st.session_state["topic_wordlist_result"] = "\n".join(st.session_state["topic_wordlist_words"])
                else:
                    st.session_state["topic_wordlist_words"] = []
                    st.session_state["topic_wordlist_result"] = ""
                    st.error("❌ 生成失败，返回的词表格式无法解析。")
            else:
                error_message = ai_result.get("error", "未知错误") if ai_result else "未知错误"
                st.error(f"❌ 生成失败：{error_message}")

    if st.session_state["topic_wordlist_result"]:
        st.caption(f"已生成 {len(st.session_state['topic_wordlist_words'])} 个词，可复制或导入到“提取单词”。")

        col_title, col_copy, col_import = st.columns([4, 1, 1])
        with col_title:
            st.markdown("#### 主题词表结果")
        with col_copy:
            render_copy_button(st.session_state["topic_wordlist_result"], key="copy_topic_words_btn")
        with col_import:
            st.markdown(
                '<div class="flow-action-panel"><strong>下一步：导入提取</strong>把这份词表送到“提取单词”，继续整理或筛选。</div>',
                unsafe_allow_html=True,
            )
            if st.button("导入提取", key="btn_import_topic_words", use_container_width=True):
                words = st.session_state["topic_wordlist_words"]
                data_list = [(word, vocab_dict.get(word.lower(), 99999)) for word in words]
                set_generated_words_state(data_list, len(words), None)
                st.session_state["extract_source_block"] = "单词表"
                st.session_state["extract_wordlist_source"] = "单词表"
                st.session_state["extract_source_mode"] = "单词表"
                st.success("✅ 已导入到“提取单词”，现在可以继续整理或直接去制作卡片。")

        st.text_area(
            "生成的主题词表",
            value=st.session_state["topic_wordlist_result"],
            height=220,
            label_visibility="collapsed",
            help="一行一个词，方便复制或导入后继续编辑。",
            disabled=True,
        )
