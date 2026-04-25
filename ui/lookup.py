"""Lookup tab rendering."""

import html

import streamlit as st

import constants
from ai import generate_topic_word_list, get_word_quick_definition
from state import set_generated_words_state
from ui.helpers import (
    clear_quick_lookup_state,
    clear_topic_wordlist_state,
    parse_topic_word_list,
    validate_lookup_query,
    validate_topic_label,
)
from utils import render_copy_button


def _render_quick_lookup() -> None:
    st.markdown("### 🔍 极速查词")
    st.caption("💡 只支持英文单词、短语，或很短的中文释义词组；不支持聊天式提问。查询结果显示美音/英音音标。")
    st.markdown("例如：serendipity、take off、run into、偶然发现")

    if "quick_lookup_last_query" not in st.session_state:
        st.session_state["quick_lookup_last_query"] = ""
    if "quick_lookup_last_result" not in st.session_state:
        st.session_state["quick_lookup_last_result"] = None
    if "quick_lookup_is_loading" not in st.session_state:
        st.session_state["quick_lookup_is_loading"] = False
    if "quick_lookup_cache_keys" not in st.session_state:
        st.session_state["quick_lookup_cache_keys"] = []

    with st.form("quick_lookup_form", clear_on_submit=False):
        col_word, col_btn, col_clear = st.columns([4, 1, 1])
        with col_word:
            lookup_word = st.text_input(
                "输入单词或短语",
                placeholder="输入英文单词、短语或中文释义",
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
                cache_key = f"lookup_cache_{query_word.lower()}"
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

    result = st.session_state.get("quick_lookup_last_result")
    if result and "error" not in result:
        raw_content = result["result"]
        lines = [line.strip() for line in raw_content.split("\n") if line.strip()]
        head_lines = []
        phonetic_lines = []
        definition_lines = []
        example_lines = []
        etymology_lines = []
        other_lines = []

        for idx, line in enumerate(lines):
            safe_line = html.escape(line)

            if line.startswith("🌱"):
                etymology_lines.append(f'<div class="quick-lookup-line quick-lookup-ety">{safe_line}</div>')
            elif line.startswith("🔊"):
                phonetic_lines.append(f'<div class="quick-lookup-line quick-lookup-phon">{safe_line}</div>')
            elif "|" in line and len(line) < 50:
                definition_lines.append(f'<div class="quick-lookup-line quick-lookup-def">{safe_line}</div>')
            elif line.startswith("•"):
                example_lines.append(f'<div class="quick-lookup-line quick-lookup-ex">{safe_line}</div>')
            elif idx == 0:
                head_lines.append(f'<div class="quick-lookup-line quick-lookup-cn">{safe_line}</div>')
            else:
                other_lines.append(f'<div class="quick-lookup-line quick-lookup-cn">{safe_line}</div>')

        formatted_lines = head_lines + phonetic_lines + definition_lines + other_lines + example_lines + etymology_lines
        display_html = "".join(formatted_lines).replace("\n", "<br>")
        rank = result.get("rank", 99999)

        if rank <= 5000:
            rank_color = "#10b981"
            rank_label = "高频词"
        elif rank <= 10000:
            rank_color = "#3b82f6"
            rank_label = "常用词"
        elif rank <= 20000:
            rank_color = "#f59e0b"
            rank_label = "进阶词"
        elif rank < 99999:
            rank_color = "#ef4444"
            rank_label = "专业词"
        else:
            rank_color = "#6b7280"
            rank_label = "未收录"

        st.markdown(
            f"""
        <div style="background: var(--vf-accent-gradient); padding: 3px; border-radius: 14px; margin: 15px 0; box-shadow: var(--vf-shadow-soft);">
            <div style="background: var(--vf-surface-elevated); border: 1px solid var(--vf-border); padding: 25px; border-radius: 12px;">
                <div class="quick-lookup-card">
                    {display_html}
                </div>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid var(--vf-border);">
                    <span style="display: inline-block; background: {rank_color}; color: white; padding: 4px 12px; border-radius: 6px; font-size: 14px; font-weight: 600;">
                        📊 {constants.VOCAB_PROJECT_NAME}词频排名：{rank}（{rank_label}）
                    </span>
                </div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    elif result and "error" in result:
        st.error(f"❌ 查询失败：{result.get('error', '未知错误')}")

    st.markdown("---")


if hasattr(st, "fragment"):
    render_quick_lookup = st.fragment(_render_quick_lookup)
else:
    render_quick_lookup = _render_quick_lookup


def render_lookup_tab(vocab_dict: dict[str, int]) -> None:
    """Render the complete lookup tab."""
    render_quick_lookup()

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
