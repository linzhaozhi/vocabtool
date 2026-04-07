"""
Vocab Flow Ultra – Streamlit entry point.
UI and session-state wiring; logic lives in constants, errors, utils,
resources, extraction, vocab, ai, anki_parse, tts, anki_package, state.
"""
import html
import logging
import os
import re
import time

import pandas as pd
import streamlit as st

import constants
import resources
from ai import get_word_quick_definition, process_ai_in_batches
from anki_package import cleanup_old_apkg_files, generate_anki_package
from anki_parse import parse_anki_data
from config import get_config
from extraction import (
    extract_text_from_file,
    extract_text_from_url,
    is_upload_too_large,
    parse_anki_txt_export,
)
from state import clear_all_state, set_generated_words_state
from utils import get_beijing_time_str, render_copy_button, run_gc
from vocab import analyze_logic

# Load vocab and expose to app (and to resources for vocab/ai modules)
VOCAB_DICT, FULL_DF = resources.load_vocab_data()
resources.VOCAB_DICT = VOCAB_DICT
resources.FULL_DF = FULL_DF

# Clean old .apkg files from our temp subdir (e.g. from previous sessions)
cleanup_old_apkg_files()

logger = logging.getLogger(__name__)

# ==========================================
# Page Configuration
# ==========================================
st.set_page_config(
    page_title="Vocab Flow Ultra",
    page_icon="⚡️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# Initialize Session State
for key, default_value in constants.DEFAULT_SESSION_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

# Custom CSS
st.markdown("""
<style>
    .stTextArea textarea { font-family: 'Consolas', monospace; font-size: 14px; }
    .stButton>button { border-radius: 8px; font-weight: 600; width: 100%; margin-top: 5px; }
    .stat-box { padding: 15px; background-color: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; text-align: center; color: #166534; margin-bottom: 20px; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stExpander { border: 1px solid #e0e0e0; border-radius: 8px; margin-bottom: 10px; }
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    .ai-warning { font-size: 12px; color: #666; margin-top: -5px; margin-bottom: 10px; text-align: center; }
    /* Search form: card-style container */
    .stForm { border: 1px solid #e5e7eb; border-radius: 12px; padding: 1.25rem 1.5rem; background: #fafafa; margin-bottom: 1rem; }
    /* Metric cards: subtle background */
    [data-testid="stMetric"] { background: linear-gradient(135deg, #f8fafc 0%, #f1f5f9 100%); padding: 1rem; border-radius: 10px; border: 1px solid #e2e8f0; }
    /* Tab labels: slightly bolder */
    .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
    .stTabs [data-baseweb="tab"] { padding: 0.6rem 1rem; border-radius: 8px; font-weight: 500; }
    /* App footer */
    .app-footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #e5e7eb; text-align: center; color: #64748b; font-size: 0.875rem; }
    
    /* Reading Mode Styles */
    .reading-container {
        background-color: #f9fafb;
        padding: 30px;
        border-radius: 12px;
        font-family: 'Georgia', serif;
        font-size: 18px;
        line-height: 1.8;
        color: #1f2937;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .reading-text {
        user-select: text;
        cursor: text;
    }
    .reading-text::selection {
        background-color: #dbeafe;
    }
    .word-definition {
        background: white;
        border: 2px solid #3b82f6;
        border-radius: 8px;
        padding: 15px;
        margin-top: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .definition-title {
        font-weight: bold;
        color: #1e40af;
        margin-bottom: 8px;
        font-size: 20px;
    }
    .definition-meaning {
        color: #374151;
        margin-bottom: 12px;
        font-size: 16px;
    }
    .example-sentence {
        background-color: #f3f4f6;
        padding: 10px;
        border-left: 4px solid #3b82f6;
        margin: 5px 0;
        font-style: italic;
        color: #4b5563;
    }
    .search-box {
        position: sticky;
        top: 0;
        background: white;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        margin-bottom: 20px;
        z-index: 100;
    }
    .quick-lookup-card {
        font-family: 'Noto Sans CJK SC', 'Noto Sans SC', 'WenQuanYi Micro Hei', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
        font-size: 16px;
        line-height: 1.65;
        color: #1f2937;
        font-weight: 400;
        -webkit-font-smoothing: antialiased;
        text-rendering: optimizeLegibility;
        font-synthesis-weight: none;
    }
    .quick-lookup-line {
        font-family: inherit;
        font-size: 16px;
        line-height: 1.65;
        font-weight: 400;
    }
    .quick-lookup-def {
        color: #1e3a8a;
        margin-bottom: 6px;
    }
    .quick-lookup-ety {
        color: #065f46;
        background: #ecfdf5;
        padding: 6px 10px;
        border-radius: 8px;
        margin: 6px 0;
    }
    .quick-lookup-ex {
        color: #374151;
        margin-top: 6px;
    }
    .quick-lookup-cn {
        color: #6b7280;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)


def set_anki_pkg(file_path: str, deck_name: str) -> None:
    """Store Anki package path in session state and clean previous file."""
    if not file_path or not os.path.exists(file_path):
        raise FileNotFoundError("Generated Anki package file not found.")

    prev_path = st.session_state.get('anki_pkg_path')
    if prev_path and prev_path != file_path:
        try:
            if os.path.exists(prev_path):
                os.remove(prev_path)
        except OSError as e:
            logger.warning("Could not remove previous anki package: %s", e)

    st.session_state['anki_pkg_path'] = file_path
    st.session_state['anki_pkg_name'] = f"{deck_name}.apkg"


def render_anki_download_button(
    label: str,
    *,
    button_type: str = "primary",
    use_container_width: bool = False
) -> None:
    """Safely render Anki package download button if file exists."""
    file_path = st.session_state.get('anki_pkg_path')
    file_name = st.session_state.get('anki_pkg_name', "deck.apkg")

    if not file_path:
        return
    if not os.path.exists(file_path):
        st.warning("⚠️ 下载文件不存在，请重新生成。")
        st.session_state['anki_pkg_path'] = ""
        return

    try:
        with open(file_path, "rb") as f:
            st.download_button(
                label=label,
                data=f.read(),
                file_name=file_name,
                mime="application/octet-stream",
                type=button_type,
                use_container_width=use_container_width
            )
    except OSError as e:
        logger.error("Failed to open package for download: %s", e)
        st.error("❌ 下载文件读取失败，请重新生成。")


# ==========================================
# UI Components
# ==========================================
st.title("⚡️ Vocab Flow Ultra · Stable")
st.caption("文本 → 词表 → Anki 牌组，一步到位。支持 AI 释义、词源与语音。")


def render_quick_lookup() -> None:
    st.markdown("### 🔍 AI 极速查词")
    st.caption("💡 输入单词后按回车或点击查询按钮")

    if "quick_lookup_last_query" not in st.session_state:
        st.session_state["quick_lookup_last_query"] = ""
    if "quick_lookup_last_result" not in st.session_state:
        st.session_state["quick_lookup_last_result"] = None
    if "quick_lookup_is_loading" not in st.session_state:
        st.session_state["quick_lookup_is_loading"] = False
    if "quick_lookup_block_until" not in st.session_state:
        st.session_state["quick_lookup_block_until"] = 0.0
    if "quick_lookup_cache_keys" not in st.session_state:
        st.session_state["quick_lookup_cache_keys"] = []

    now_ts = time.time()
    in_cooldown = now_ts < st.session_state["quick_lookup_block_until"]
    lookup_disabled = st.session_state["quick_lookup_is_loading"] or in_cooldown

    with st.form("quick_lookup_form", clear_on_submit=False):
        col_word, col_btn = st.columns([4, 1])
        with col_word:
            lookup_word = st.text_input(
                "输入单词或短语",
                placeholder="如：serendipity, take off, run into...",
                key="quick_lookup_word",
                label_visibility="collapsed",
                autocomplete="off",
            )
        with col_btn:
            lookup_submit = st.form_submit_button(
                "查询中..." if st.session_state["quick_lookup_is_loading"] else "查询",
                type="primary",
                use_container_width=True,
                disabled=lookup_disabled
            )

    if in_cooldown:
        wait_seconds = max(0.0, st.session_state["quick_lookup_block_until"] - now_ts)
        st.caption(f"⏱️ 请稍候 {wait_seconds:.1f}s 再次查询")

    if lookup_submit:
        query_word = lookup_word.strip()
        if not query_word:
            st.warning("⚠️ 请输入单词或短语。")
        else:
            if st.session_state["quick_lookup_is_loading"]:
                st.info("⏳ 查询进行中，请稍候。")
            elif time.time() < st.session_state["quick_lookup_block_until"]:
                st.info("⏱️ 请求过于频繁，请稍后再试。")
            else:
                st.session_state["quick_lookup_is_loading"] = True
                try:
                    cache_key = f"lookup_cache_{query_word.lower()}"
                    if cache_key not in st.session_state:
                        with st.spinner("🔍 查询中..."):
                            st.session_state[cache_key] = get_word_quick_definition(query_word)
                        # Cap cache size: evict oldest entries
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
                    st.session_state["quick_lookup_block_until"] = time.time() + constants.QUICK_LOOKUP_COOLDOWN_SECONDS

    result = st.session_state.get("quick_lookup_last_result")
    if result and 'error' not in result:
        raw_content = result['result']
        lines = raw_content.split('\n')
        formatted_lines = []

        for line in lines:
            line = line.strip()
            if not line:
                continue
            safe_line = html.escape(line)

            if line.startswith("🌱"):
                formatted_lines.append(f'<div class="quick-lookup-line quick-lookup-ety">{safe_line}</div>')
            elif "|" in line and len(line) < 50:
                formatted_lines.append(f'<div class="quick-lookup-line quick-lookup-def">{safe_line}</div>')
            elif line.startswith("•"):
                formatted_lines.append(f'<div class="quick-lookup-line quick-lookup-ex">{safe_line}</div>')
            else:
                formatted_lines.append(f'<div class="quick-lookup-line quick-lookup-cn">{safe_line}</div>')

        display_html = "".join(formatted_lines).replace('\n', '<br>')
        rank = result.get('rank', 99999)

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

        st.markdown(f"""
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 3px; border-radius: 12px; margin: 15px 0;">
            <div style="background: white; padding: 25px; border-radius: 10px;">
                <div class="quick-lookup-card">
                    {display_html}
                </div>
                <div style="margin-top: 15px; padding-top: 15px; border-top: 1px solid #e5e7eb;">
                    <span style="display: inline-block; background: {rank_color}; color: white; padding: 4px 12px; border-radius: 6px; font-size: 14px; font-weight: 600;">
                        📊 Rank: {rank} ({rank_label})
                    </span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    elif result and 'error' in result:
        st.error(f"❌ 查询失败：{result.get('error', '未知错误')}")

    st.markdown("---")


if hasattr(st, "fragment"):
    render_quick_lookup = st.fragment(render_quick_lookup)

render_quick_lookup()

if not VOCAB_DICT:
    st.error("⚠️ 缺失 `coca_cleaned.csv` 或 `vocab.pkl` 文件，请检查目录。")

with st.expander("📖 使用指南 & 支持格式", expanded=False):
    st.markdown("""
    **🚀 极速工作流**
    1. **查词**：顶部 AI 查词，秒速获取精准释义、**词源拆解**和双语例句。
    2. **提取**：支持 PDF、ePub、Docx、TXT、CSV、Excel (xlsx/xls) 等格式。
    3. **生成**：自动完成文本生成、**并发语音合成**并打包下载。
    
    **📄 支持的文件格式**
    - 📝 文本：TXT
    - 📄 文档：PDF, DOCX, EPUB
    - 📊 表格：CSV, XLSX, XLS
    - 🗄️ 数据库：DB, SQLite
    - 📤 **Anki 导出**：支持 .txt 格式（推荐使用 "Notes in Plain Text"，但也兼容 "Cards in Plain Text"）。
    """)

st.caption("① 单词提取 → ② 卡片制作（或从提取结果直接生成）")

tab_extract, tab_anki = st.tabs([
    "1️⃣ 单词提取",
    "2️⃣ 卡片制作"
])

# ==========================================
# Tab 1: Word Extraction
# ==========================================
with tab_extract:
    mode_context, mode_direct, mode_rank = st.tabs([
        "📄 语境分析",
        "📝 直接输入 (含 Anki 导入)",
        "🔢 词频列表"
    ])

    with mode_context:
        col1, col2 = st.columns(2)
        current_rank = col1.number_input("忽略前 N 高频词 (Min Rank)", 1, 20000, 6000, step=100)
        target_rank = col2.number_input("忽略后 N 低频词 (Max Rank)", 2000, 50000, 10000, step=500)

        if target_rank < current_rank:
            st.warning("⚠️ Max Rank 必须大于等于 Min Rank")

        st.markdown("#### 📥 导入内容")

        input_url = st.text_input(
            "🔗 输入文章 URL (自动抓取)",
            placeholder="https://www.economist.com/...",
            key="url_input_key"
        )

        uploaded_file = st.file_uploader(
            "或直接上传文件",
            type=['txt', 'pdf', 'docx', 'epub', 'csv', 'xlsx', 'xls', 'db', 'sqlite'],
            key=st.session_state['uploader_id'],
            label_visibility="collapsed"
        )
        if uploaded_file and is_upload_too_large(uploaded_file):
            st.error(f"❌ 文件过大，已限制为 {constants.MAX_UPLOAD_MB}MB。请缩小文件后重试。")
            uploaded_file = None

        pasted_text = st.text_area(
            "或在此粘贴文本",
            height=100,
            key="paste_key",
            placeholder="支持直接粘贴文章内容..."
        )

        if st.button("🚀 开始分析", type="primary"):
            if target_rank < current_rank:
                st.error("❌ Max Rank 必须大于等于 Min Rank，请修正后重试。")
            else:
                with st.status("🔍 正在加载资源并分析文本...", expanded=True) as status:
                    start_time = time.time()
                    raw_text = ""

                    if input_url:
                        status.write(f"🌐 正在抓取 URL: {input_url}...")
                        raw_text = extract_text_from_url(input_url)
                    elif uploaded_file:
                        raw_text = extract_text_from_file(uploaded_file)
                    else:
                        raw_text = pasted_text

                    if len(raw_text) > 2:
                        status.write("🧠 正在进行 NLP 词形还原与分级...")
                        final_data, raw_count, stats_info = analyze_logic(
                            raw_text, current_rank, target_rank, False
                        )

                        set_generated_words_state(final_data, raw_count, stats_info)
                        st.session_state['process_time'] = time.time() - start_time
                        run_gc()
                        status.update(label="✅ 分析完成", state="complete", expanded=False)
                    else:
                        status.update(label="⚠️ 内容为空或太短", state="error")

    with mode_direct:
        st.markdown("#### 📤 导入 Anki 牌组导出文件 (可选)")
        st.caption("💡 提示：在 Anki 导出时，推荐选择 **'Notes in Plain Text'** (笔记纯文本)。但如果您选择了 **'Cards in Plain Text'**，系统也会尝试自动解析。")

        anki_export_file = st.file_uploader(
            "上传 Anki 导出的 .txt 文件",
            type=['txt'],
            key="anki_import_uploader"
        )
        if anki_export_file and is_upload_too_large(anki_export_file):
            st.error(f"❌ 文件过大，已限制为 {constants.MAX_UPLOAD_MB}MB。请缩小文件后重试。")
            anki_export_file = None

        prefilled_text = ""
        if anki_export_file:
            with st.spinner("正在智能解析 Anki 导出文件..."):
                prefilled_text = parse_anki_txt_export(anki_export_file)
                if prefilled_text:
                    st.success(f"✅ 成功提取 {len(prefilled_text.splitlines())} 个单词")

        raw_input = st.text_area(
            "✍️ 粘贴单词列表 (每行一个 或 逗号分隔)",
            height=200,
            value=prefilled_text,
            placeholder="altruism\nhectic\nserendipity"
        )

        if st.button("🚀 生成列表", key="btn_direct", type="primary"):
            with st.spinner("正在解析列表..."):
                if raw_input.strip():
                    words = [w.strip() for w in re.split(r'[,\n\t]+', raw_input) if w.strip()]
                    unique_words = []
                    seen = set()

                    for word in words:
                        if word.lower() not in seen:
                            seen.add(word.lower())
                            unique_words.append(word)

                    data_list = [(w, VOCAB_DICT.get(w.lower(), 99999)) for w in unique_words]
                    set_generated_words_state(data_list, len(unique_words), None)
                    st.toast(f"✅ 已加载 {len(unique_words)} 个单词", icon="🎉")
                else:
                    st.warning("⚠️ 内容为空。")

    with mode_rank:
        gen_type = st.radio("生成模式", ["🔢 顺序生成", "🔀 随机抽取"], horizontal=True)

        if "顺序生成" in gen_type:
            col_a, col_b = st.columns(2)
            start_rank = col_a.number_input("起始排名", 1, 20000, 8000, step=100)
            count = col_b.number_input("数量", 10, 5000, 10, step=10)

            if st.button("🚀 生成列表"):
                with st.spinner("正在提取..."):
                    if FULL_DF is not None:
                        rank_col = next(c for c in FULL_DF.columns if 'rank' in c)
                        word_col = next(c for c in FULL_DF.columns if 'word' in c)
                        subset = FULL_DF[FULL_DF[rank_col] >= start_rank].sort_values(rank_col).head(count)
                        set_generated_words_state(
                            list(zip(subset[word_col], subset[rank_col])),
                            0,
                            None
                        )
        else:
            col_min, col_max, col_cnt = st.columns([1, 1, 1])
            min_rank = col_min.number_input("最小排名", 1, 20000, 12000, step=100)
            max_rank = col_max.number_input("最大排名", 1, 25000, 15000, step=100)
            random_count = col_cnt.number_input("抽取数量", 10, 5000, 10, step=10)

            if max_rank < min_rank:
                st.warning("⚠️ 最大排名必须大于等于最小排名")

            if st.button("🎲 随机抽取"):
                if max_rank < min_rank:
                    st.error("❌ 最大排名必须大于等于最小排名，请修正后重试。")
                else:
                    with st.spinner("正在抽取..."):
                        if FULL_DF is not None:
                            rank_col = next(c for c in FULL_DF.columns if 'rank' in c)
                            word_col = next(c for c in FULL_DF.columns if 'word' in c)
                            pool = FULL_DF[(FULL_DF[rank_col] >= min_rank) & (FULL_DF[rank_col] <= max_rank)]
                            if len(pool) < random_count:
                                st.warning(f"⚠️ 该范围只有 {len(pool)} 个单词，已全部选中")
                            sample = pool.sample(n=min(random_count, len(pool)))
                            set_generated_words_state(
                                list(zip(sample[word_col], sample[rank_col])),
                                0,
                                None
                            )

    # Display results (shared across all modes)
    if st.session_state.get('gen_words_data'):
        data = st.session_state['gen_words_data']
        original_count = len(data)

        if st.session_state.get('stats_info'):
            stats = st.session_state['stats_info']
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.metric("📊 词汇覆盖率", f"{stats['coverage']*100:.1f}%")
            with col_s2:
                st.metric("🎯 目标词密度", f"{stats['target_density']*100:.1f}%")

        raw_count = st.session_state.get('raw_count', 0)
        if not raw_count:
            raw_count = original_count
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.metric("📦 提取的单词总数", raw_count)
        with col_t2:
            st.metric("✅ 筛选后单词总数", original_count)

        st.markdown(f"### ✅ 提取成功！")
        words_only = [w for w, r in data]
        words_text = "\n".join(words_only)
        if "word_list_editor" not in st.session_state:
            st.session_state["word_list_editor"] = words_text

        col_title, col_copy_btn = st.columns([5, 1])
        with col_title:
            st.markdown("### 📝 单词列表")
        with col_copy_btn:
            current_words_text = st.session_state.get("word_list_editor", words_text)
            render_copy_button(current_words_text, key="copy_words_btn")
        st.caption("💡 可以在下方文本框中编辑、新增或删除单词，每行一个单词")

        edited_words = st.text_area(
            f"✍️ 单词列表 (共 {original_count} 个)",
            height=300,
            key="word_list_editor",
            label_visibility="collapsed",
            help="每行一个单词"
        )

        if edited_words != words_text:
            edited_word_list = [w.strip() for w in edited_words.split('\n') if w.strip()]
            st.info(f"📝 已编辑：当前共 {len(edited_word_list)} 个单词")
            words_only = edited_word_list
        else:
            words_only = [w for w, r in data]

        st.markdown("---")
        st.markdown("### 🤖 AI 生成 Anki 卡片")

        col_ai_btn, col_copy_hint = st.columns([1, 2])

        with col_ai_btn:
            ai_model_label = get_config()["openai_model"]

            selected_voice_label = st.radio(
                "🎙️ 发音人",
                options=list(constants.VOICE_MAP.keys()),
                index=0,
                horizontal=True,
                key="sel_voice_auto"
            )
            selected_voice_code = constants.VOICE_MAP[selected_voice_label]

            enable_audio_auto = st.checkbox("启用语音", value=True, key="chk_audio_auto")

            current_word_count = len(words_only)
            if current_word_count > constants.MAX_AUTO_LIMIT:
                st.warning(f"⚠️ 单词数超过 {constants.MAX_AUTO_LIMIT}，内置 AI 仅处理前 {constants.MAX_AUTO_LIMIT} 个。建议使用手动 Prompt 分批处理。")
                words_only = words_only[:constants.MAX_AUTO_LIMIT]

            if st.button(f"🚀 使用 {ai_model_label} 生成", type="primary", use_container_width=True):
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_ai_progress(current: int, total: int) -> None:
                    ratio = current / total if total > 0 else 0
                    progress_bar.progress(ratio)
                    status_text.text(f"正在处理 ({current}/{total})")

                status_text.text("🧠 正在请求 AI 生成...")
                ai_result = process_ai_in_batches(words_only, progress_callback=update_ai_progress)

                if ai_result:
                    status_text.text("✅ AI 生成完成，正在解析...")
                    parsed_data = parse_anki_data(ai_result)

                    if parsed_data:
                        try:
                            status_text.text("📦 正在生成 Anki 包...")
                            deck_name = f"Vocab_{get_beijing_time_str()}"

                            def update_pkg_progress(ratio: float, text: str) -> None:
                                progress_bar.progress(ratio)
                                status_text.text(text)

                            file_path = generate_anki_package(
                                parsed_data,
                                deck_name,
                                enable_tts=enable_audio_auto,
                                tts_voice=selected_voice_code,
                                progress_callback=update_pkg_progress
                            )

                            set_anki_pkg(file_path, deck_name)

                            status_text.markdown(f"✅ **处理完成！共生成 {len(parsed_data)} 张卡片**")
                            st.balloons()
                            run_gc()
                        except Exception as e:
                            from errors import ErrorHandler
                            ErrorHandler.handle(e, "生成出错")
                    else:
                        st.error("解析失败，AI 返回内容为空或格式错误。")
                else:
                    st.error("AI 生成失败，请检查 API Key 或网络连接。")

            st.caption("⚠️ AI 生成内容可能存在错误，请人工复核。")

        render_anki_download_button(
            f"📥 立即下载 {st.session_state.get('anki_pkg_name', 'deck.apkg')}",
            button_type="primary",
            use_container_width=True
        )

        with col_copy_hint:
            st.info("👈 点击左侧按钮自动生成。如使用第三方 AI，请复制下方 Prompt。")

        with st.expander("📌 手动复制 Prompt (第三方 AI 用)"):
            batch_size_prompt = st.number_input("🔢 分组大小 (Max 500)", 10, 500, 50, step=10)
            current_batch_words = []

            if words_only:
                total_w = len(words_only)
                num_batches = (total_w + batch_size_prompt - 1) // batch_size_prompt
                batch_options = [
                    f"第 {i+1} 组 ({i*batch_size_prompt+1} - {min((i+1)*batch_size_prompt, total_w)})"
                    for i in range(num_batches)
                ]
                selected_batch_str = st.selectbox("📂 选择当前分组", batch_options)
                sel_idx = batch_options.index(selected_batch_str)
                current_batch_words = words_only[
                    sel_idx*batch_size_prompt:min((sel_idx+1)*batch_size_prompt, total_w)
                ]
            else:
                st.warning("⚠️ 暂无单词数据，请先提取单词。")

            words_str_for_prompt = ", ".join(current_batch_words) if current_batch_words else "[INSERT YOUR WORD LIST HERE]"

            strict_prompt_template = f"""# Role
You are an expert English Lexicographer and Anki Card Designer. Your goal is to convert a list of target words into high-quality, import-ready Anki flashcards focusing on **natural collocations** (word chunks).
Make sure to process everything in one go, without missing anything.

# Input Data
{words_str_for_prompt}

# Output Format Guidelines
1. **Output Container**: Strictly inside a single ```text code block.
2. **Layout**: One entry per line.
3. **Separator**: Use `|||` as the delimiter.
4. **Target Structure**:
   `Natural Phrase/Collocation` ||| `Concise Definition of the Phrase` ||| `Short Example Sentence` ||| `Etymology breakdown (Simplified Chinese)`

# Field Constraints (Strict)
1. **Field 1: Phrase (CRITICAL)**
   - DO NOT output the single target word.
   - You MUST generate a high-frequency **collocation** or **short phrase** containing the target word.
   - Example: If input is "rain", output "heavy rain" or "torrential rain".
   
2. **Field 2: Definition (English)**
   - Define the *phrase*, not just the isolated word. Keep it concise (B2-C1 level English).

3. **Field 3: Example**
   - A short, authentic sentence containing the phrase.

4. **Field 4: Roots/Etymology (Simplified Chinese)**
   - Format: `prefix- (meaning) + root (meaning) + -suffix (meaning)`.
   - If no classical roots exist, explain the origin briefly in Chinese.
   - Use Simplified Chinese for meanings.

# Valid Example (Follow this logic strictly)
Input: altruism
Output:
motivated by altruism ||| acting out of selfless concern for the well-being of others ||| His donation was motivated by altruism, not a desire for fame. ||| alter (其他) + -ism (主义/行为)

Input: hectic
Output:
a hectic schedule ||| a timeline full of frantic activity and very busy ||| She has a hectic schedule with meetings all day. ||| hect- (持续的/习惯性的 - 来自希腊语hektikos) + -ic (形容词后缀)

# Task
Process the provided input list strictly adhering to the format above."""
            st.code(strict_prompt_template, language="text")

# ==========================================
# Tab 2: Manual Anki Card Creation
# ==========================================
with tab_anki:
    st.markdown("### 📦 手动制作 Anki 牌组")

    if 'anki_cards_cache' not in st.session_state:
        st.session_state['anki_cards_cache'] = None

    def reset_anki_state() -> None:
        st.session_state['anki_cards_cache'] = None
        if st.session_state.get('anki_pkg_path'):
            try:
                if os.path.exists(st.session_state['anki_pkg_path']):
                    os.remove(st.session_state['anki_pkg_path'])
            except OSError as e:
                logger.warning("Could not remove temp anki package: %s", e)
        st.session_state['anki_pkg_path'] = ""
        st.session_state['anki_pkg_name'] = ""
        st.session_state['anki_input_text'] = ""

    col_input, col_act = st.columns([3, 1])
    with col_input:
        beijing_time_str = get_beijing_time_str()
        deck_name = st.text_input("🏷️ 牌组名称", f"Vocab_{beijing_time_str}")

    ai_response = st.text_area(
        "粘贴 AI 返回内容",
        height=300,
        key="anki_input_text",
        placeholder='hectic ||| 忙乱的 ||| She has a hectic schedule today.'
    )

    manual_voice_label = st.radio(
        "🎙️ 发音人",
        options=list(constants.VOICE_MAP.keys()),
        index=0,
        horizontal=True,
        key="sel_voice_manual"
    )
    manual_voice_code = constants.VOICE_MAP[manual_voice_label]

    enable_audio = st.checkbox("启用语音", value=True, key="chk_audio_manual")

    col_btn1, col_btn2 = st.columns([1, 4])
    with col_btn1:
        start_gen = st.button("🚀 生成卡片", type="primary", use_container_width=True)
    with col_btn2:
        st.button("🗑️ 清空重置", type="secondary", on_click=reset_anki_state, key="btn_clear_anki")

    if start_gen:
        if not ai_response.strip():
            st.warning("⚠️ 输入框为空。")
        else:
            progress_container = st.container()
            with progress_container:
                progress_bar_manual = st.progress(0)
                status_manual = st.empty()

            def update_progress_manual(ratio: float, text: str) -> None:
                progress_bar_manual.progress(ratio)
                status_manual.text(text)

            with st.spinner("⏳ 正在解析并生成..."):
                parsed_data = parse_anki_data(ai_response)
                if parsed_data:
                    st.session_state['anki_cards_cache'] = parsed_data
                    try:
                        file_path = generate_anki_package(
                            parsed_data,
                            deck_name,
                            enable_tts=enable_audio,
                            tts_voice=manual_voice_code,
                            progress_callback=update_progress_manual
                        )

                        set_anki_pkg(file_path, deck_name)

                        status_manual.markdown(f"✅ **生成完毕！共制作 {len(parsed_data)} 张卡片**")
                        st.balloons()
                        st.toast("任务完成！", icon="🎉")
                        run_gc()
                    except Exception as e:
                        from errors import ErrorHandler
                        ErrorHandler.handle(e, "生成文件出错")
                else:
                    st.error("❌ 解析失败，请检查输入格式。")

    if st.session_state['anki_cards_cache']:
        cards = st.session_state['anki_cards_cache']
        with st.expander(f"👀 预览卡片 (前 {constants.MAX_PREVIEW_CARDS} 张)", expanded=True):
            df_view = pd.DataFrame(cards)
            display_cols = ['w', 'm', 'e', 'r']
            df_view = df_view[[c for c in display_cols if c in df_view.columns]]
            col_labels = ["正面", "中文/英文释义", "例句"]
            if len(df_view.columns) > 3:
                col_labels.append("词源")
            df_view.columns = col_labels[:len(df_view.columns)]
            st.dataframe(df_view.head(constants.MAX_PREVIEW_CARDS), use_container_width=True, hide_index=True)

        render_anki_download_button(
            f"📥 下载 {st.session_state.get('anki_pkg_name', 'deck.apkg')}",
            button_type="primary"
        )

st.markdown(
    '<p class="app-footer">Vocab Flow Ultra · 文本 → 词表 → Anki</p>',
    unsafe_allow_html=True
)
