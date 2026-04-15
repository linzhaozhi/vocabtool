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
from ai import generate_topic_word_list, get_word_quick_definition, process_ai_in_batches
from anki_package import cleanup_old_apkg_files, generate_anki_package
from anki_parse import parse_anki_data
from config import get_config
from extraction import (
    extract_text_from_file,
    extract_text_from_url,
    is_upload_too_large,
    parse_anki_txt_export,
)
from state import set_generated_words_state
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
if "anki_cards_cache" not in st.session_state:
    st.session_state["anki_cards_cache"] = None

# Custom CSS
st.markdown("""
<style>
    .stTextArea textarea { font-family: 'Consolas', monospace; font-size: 14px; }
    .stButton>button { border-radius: 8px; font-weight: 600; width: 100%; margin-top: 5px; }
    .stTextInput > div > div > input,
    .stTextArea textarea,
    .stNumberInput input {
        border-radius: 10px;
        border: 1px solid #d7deea;
    }
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
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1rem;
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid #e2e8f0;
        background: #f8fafc;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #dbeafe 0%, #eff6ff 100%);
        border-color: #93c5fd;
        color: #0f172a;
        box-shadow: 0 10px 24px rgba(59, 130, 246, 0.12);
    }
    .stRadio [role="radiogroup"] {
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    .stRadio [role="radiogroup"] label {
        background: #f8fafc;
        border: 1px solid #dbe3ef;
        border-radius: 999px;
        padding: 0.2rem 0.75rem;
    }
    /* App footer */
    .app-footer { margin-top: 2.5rem; padding-top: 1rem; border-top: 1px solid #e5e7eb; text-align: center; color: #64748b; font-size: 0.875rem; }
    .workflow-banner {
        margin: 0.75rem 0 1.25rem;
        padding: 0.95rem 1rem;
        border-radius: 12px;
        background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
        border: 1px solid #bfdbfe;
        color: #1e3a8a;
        font-size: 0.95rem;
    }
    
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
    file_name = st.session_state.get('anki_pkg_name', "词卡.apkg")

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


def reset_anki_state() -> None:
    """Clear generated Anki package state but keep the source word list."""
    st.session_state["anki_cards_cache"] = None
    if st.session_state.get("anki_pkg_path"):
        try:
            if os.path.exists(st.session_state["anki_pkg_path"]):
                os.remove(st.session_state["anki_pkg_path"])
        except OSError as e:
            logger.warning("Could not remove temp anki package: %s", e)
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
    words = []
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
        "what ", "what's ", "what is ", "how ", "why ", "please ",
        "tell me ", "can you ", "could you ", "would you ", "explain ",
        "translate ", "help me ", "give me ", "show me "
    )
    blocked_fragments = (
        " mean", " meaning", " sentence", " example", " examples",
        " explain", " translation", " translate", " usage"
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
        "请", "帮我", "告诉我", "我想", "我想知道", "解释一下", "解释",
        "什么意思", "什么是", "为什么", "怎么", "如何", "能不能",
        "可以吗", "举例", "造句", "写一段", "翻译这句", "帮我翻译", "聊天"
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
    code_blocks = re.findall(r'```(?:text)?\s*(.*?)\s*```', raw_text, re.DOTALL)
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
        "为什么", "怎么", "如何", "解释", "分析", "总结", "翻译", "聊天",
        "请帮我", "告诉我", "what", "why", "how", "tell me", "explain"
    )
    if any(phrase in topic for phrase in blocked_phrases) or any(phrase in lowered for phrase in blocked_phrases):
        return False, "", "⚠️ 这里只支持简短主题，不支持提问或聊天式输入。"

    if re.search(r"[0-9@#<>_=+*{}[\]|\\!?.,;:，。！？；：]", topic):
        return False, "", "⚠️ 主题里不要带数字或整句标点，只保留简短主题词。"

    if not re.fullmatch(r"[A-Za-z\u4e00-\u9fff][A-Za-z\u4e00-\u9fff&/'\- ]*", topic):
        return False, "", "⚠️ 主题建议只填写简短词组，比如“旅游”或“校园生活”。"

    return True, topic, ""


# ==========================================
# UI Components
# ==========================================
st.title("⚡️ Vocab Flow Ultra · 稳定版")
st.caption("把查词、提词、制卡分开处理。支持内置智能释义、词源与语音。")
st.markdown(
    '<div class="workflow-banner">查词、提词、制卡三个步骤已经分开。先确认词，再整理词表，最后生成卡片，路径会更清楚。</div>',
    unsafe_allow_html=True
)


def render_quick_lookup() -> None:
    st.markdown("### 🔍 极速查词")
    st.caption("💡 只支持英文单词、短语，或很短的中文释义词组；不支持聊天式提问")

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
                placeholder="如：serendipity, take off, run into, 偶然发现",
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
        is_valid_query, query_word, error_message = validate_lookup_query(lookup_word)
        if not is_valid_query:
            st.session_state["quick_lookup_last_query"] = ""
            st.session_state["quick_lookup_last_result"] = None
            st.warning(error_message)
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
        lines = [line.strip() for line in raw_content.split('\n') if line.strip()]
        head_lines = []
        definition_lines = []
        example_lines = []
        etymology_lines = []
        other_lines = []

        for idx, line in enumerate(lines):
            safe_line = html.escape(line)

            if line.startswith("🌱"):
                etymology_lines.append(f'<div class="quick-lookup-line quick-lookup-ety">{safe_line}</div>')
            elif "|" in line and len(line) < 50:
                definition_lines.append(f'<div class="quick-lookup-line quick-lookup-def">{safe_line}</div>')
            elif line.startswith("•"):
                example_lines.append(f'<div class="quick-lookup-line quick-lookup-ex">{safe_line}</div>')
            elif idx == 0:
                head_lines.append(f'<div class="quick-lookup-line quick-lookup-cn">{safe_line}</div>')
            else:
                other_lines.append(f'<div class="quick-lookup-line quick-lookup-cn">{safe_line}</div>')

        formatted_lines = head_lines + definition_lines + other_lines + example_lines + etymology_lines
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
                        📊 词频排名：{rank}（{rank_label}）
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

if not VOCAB_DICT:
    st.error("⚠️ 缺失词频数据文件，请检查根目录或 `data/` 目录中的 `coca_cleaned.csv` / `vocab.pkl`。")

with st.expander("📖 使用指南 & 支持格式", expanded=False):
    st.markdown("""
    **🚀 极速工作流**
    1. **查单词**：在“查单词”里快速获取释义、词源和双语例句。
    2. **提取单词**：在“提取单词”里从文本、文件或词频范围整理词表。
    3. **制作卡片**：在“制作卡片”里使用内置智能生成并下载 Anki 牌组。
    
    **📄 支持的文件格式**
    - 📝 文本：TXT
    - 📄 文档：PDF, DOCX, EPUB
    - 📊 表格：CSV, XLSX, XLS
    - 🗄️ 数据库：DB, SQLite
    - 📤 **Anki 导出**：支持 .txt 格式（推荐使用 "Notes in Plain Text"，但也兼容 "Cards in Plain Text"）。
    """)

st.caption("三个功能现在独立分区：先查词，再提词，最后制作卡片。")

tab_lookup, tab_extract, tab_cards = st.tabs([
    "1️⃣ 查单词",
    "2️⃣ 提取单词",
    "3️⃣ 制作卡片"
])

with tab_lookup:
    render_quick_lookup()

    st.markdown("### 🧠 主题词表生成")
    st.caption(f"💡 只要选择主题和个数即可。单次最多生成 {constants.AI_TOPIC_WORDLIST_MAX} 个常见词。")

    if "topic_wordlist_result" not in st.session_state:
        st.session_state["topic_wordlist_result"] = ""
    if "topic_wordlist_words" not in st.session_state:
        st.session_state["topic_wordlist_words"] = []

    with st.form("topic_wordlist_form", clear_on_submit=False):
        col_topic, col_count, col_submit = st.columns([3, 2, 1])
        with col_topic:
            topic_word_topic = st.text_input(
                "输入主题",
                placeholder="如：旅游、商务、校园生活",
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
                help=f"单次最多 {constants.AI_TOPIC_WORDLIST_MAX} 个"
            )
        with col_submit:
            topic_word_submit = st.form_submit_button(
                "生成",
                type="primary",
                use_container_width=True
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
                    st.session_state["topic_wordlist_words"] = generated_words[:constants.AI_TOPIC_WORDLIST_MAX]
                    st.session_state["topic_wordlist_result"] = "\n".join(st.session_state["topic_wordlist_words"])
                else:
                    st.session_state["topic_wordlist_words"] = []
                    st.session_state["topic_wordlist_result"] = ""
                    st.error("❌ 生成失败，返回的词表格式无法解析。")
            else:
                st.error(f"❌ 生成失败：{ai_result.get('error', '未知错误') if ai_result else '未知错误'}")

    if st.session_state["topic_wordlist_result"]:
        st.caption(f"已生成 {len(st.session_state['topic_wordlist_words'])} 个词，可复制或导入到“提取单词”。")

        col_title, col_copy, col_import = st.columns([4, 1, 1])
        with col_title:
            st.markdown("#### 主题词表结果")
        with col_copy:
            render_copy_button(st.session_state["topic_wordlist_result"], key="copy_topic_words_btn")
        with col_import:
            if st.button("导入提取", key="btn_import_topic_words", use_container_width=True):
                words = st.session_state["topic_wordlist_words"]
                data_list = [(w, VOCAB_DICT.get(w.lower(), 99999)) for w in words]
                set_generated_words_state(data_list, len(words), None)
                st.session_state["extract_source_mode"] = "单词列表 / Anki"
                st.success("✅ 已导入到“提取单词”，现在可以继续整理或直接去制作卡片。")

        st.text_area(
            "生成的主题词表",
            value=st.session_state["topic_wordlist_result"],
            height=220,
            label_visibility="collapsed",
            help="一行一个词，方便复制或导入后继续编辑。",
            disabled=True
        )

# ==========================================
# Tab 2: Word Extraction
# ==========================================
with tab_extract:
    st.markdown("### 🧩 提取单词")
    st.caption("先选来源，再整理词表；整理后的结果会自动同步到“制作卡片”。")

    st.markdown("#### 第一步：选择来源")
    extract_source_mode = st.radio(
        "提取来源",
        ["文章 / 文件", "单词列表 / Anki"],
        horizontal=True,
        label_visibility="collapsed",
        key="extract_source_mode"
    )

    if extract_source_mode == "文章 / 文件":
        st.markdown("#### 第二步：设置提取规则")
        col1, col2 = st.columns(2)
        current_rank = col1.number_input("跳过前 N 个高频词", 1, 20000, 6000, step=100)
        target_rank = col2.number_input("保留到第 N 名词频", 2000, 50000, 10000, step=500)

        if target_rank < current_rank:
            st.warning("⚠️ 结束词频排名必须大于等于起始词频排名。")

        st.markdown("#### 第三步：提供内容")
        st.caption("三选一即可：输入文章链接、上传文件，或直接粘贴文本。")

        input_url = st.text_input(
            "🔗 输入文章链接（自动抓取正文）",
            placeholder="https://www.economist.com/...",
            key="url_input_key"
        )

        uploaded_file = st.file_uploader(
            "上传文件",
            type=['txt', 'pdf', 'docx', 'epub', 'csv', 'xlsx', 'xls', 'db', 'sqlite'],
            key=st.session_state['uploader_id']
        )
        if uploaded_file and is_upload_too_large(uploaded_file):
            st.error(f"❌ 文件过大，已限制为 {constants.MAX_UPLOAD_MB}MB。请缩小文件后重试。")
            uploaded_file = None

        pasted_text = st.text_area(
            "或在此粘贴文本",
            height=120,
            key="paste_key",
            placeholder="支持直接粘贴文章内容..."
        )

        if st.button("🚀 开始提取", type="primary", key="btn_extract_context"):
            if target_rank < current_rank:
                st.error("❌ 结束词频排名必须大于等于起始词频排名，请修正后重试。")
            else:
                with st.status("🔍 正在加载资源并分析文本...", expanded=True) as status:
                    start_time = time.time()
                    raw_text = ""

                    if input_url:
                        status.write(f"🌐 正在抓取文章链接：{input_url}")
                        raw_text = extract_text_from_url(input_url)
                    elif uploaded_file:
                        raw_text = extract_text_from_file(uploaded_file)
                    else:
                        raw_text = pasted_text

                    if len(raw_text) > 2:
                        status.write("🧠 正在进行词形还原与词频分级...")
                        final_data, raw_count, stats_info = analyze_logic(
                            raw_text, current_rank, target_rank, False
                        )

                        set_generated_words_state(final_data, raw_count, stats_info)
                        st.session_state['process_time'] = time.time() - start_time
                        run_gc()
                        status.update(label="✅ 提取完成", state="complete", expanded=False)
                    else:
                        status.update(label="⚠️ 内容为空或太短", state="error")

    else:
        st.markdown("#### 第二步：导入词表")
        st.caption("支持直接粘贴单词，也支持先上传 Anki 导出的 .txt 文件。")

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
            height=220,
            value=prefilled_text,
            placeholder="altruism\nhectic\nserendipity"
        )

        if st.button("🚀 导入词表", key="btn_direct", type="primary"):
            with st.spinner("正在解析列表..."):
                unique_words = parse_unique_words(raw_input)
                if unique_words:
                    data_list = [(w, VOCAB_DICT.get(w.lower(), 99999)) for w in unique_words]
                    set_generated_words_state(data_list, len(unique_words), None)
                    st.toast(f"✅ 已加载 {len(unique_words)} 个单词", icon="🎉")
                else:
                    st.warning("⚠️ 内容为空。")

    with st.expander("高级工具：按词频生成词表", expanded=False):
        st.caption("需要时再用；它不会干扰主提取流程。")
        gen_type = st.radio("生成模式", ["🔢 顺序生成", "🔀 随机抽取"], horizontal=True, key="rank_gen_type")

        if "顺序生成" in gen_type:
            col_a, col_b = st.columns(2)
            start_rank = col_a.number_input("起始排名", 1, 20000, 8000, step=100, key="rank_start")
            count = col_b.number_input("数量", 10, 5000, 10, step=10, key="rank_count")

            if st.button("🚀 生成词频列表", key="btn_rank_ordered"):
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
            min_rank = col_min.number_input("最小排名", 1, 20000, 12000, step=100, key="rank_min")
            max_rank = col_max.number_input("最大排名", 1, 25000, 15000, step=100, key="rank_max")
            random_count = col_cnt.number_input("抽取数量", 10, 5000, 10, step=10, key="rank_random_count")

            if max_rank < min_rank:
                st.warning("⚠️ 最大排名必须大于等于最小排名")

            if st.button("🎲 随机抽取词表", key="btn_rank_random"):
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

        st.markdown("#### 第四步：查看与整理结果")
        st.caption("可以直接在这里删改；改动会自动同步到“制作卡片”。")

        edited_words = st.text_area(
            f"提取出的单词列表 (共 {original_count} 个)",
            height=300,
            key="extract_word_editor",
            label_visibility="collapsed",
            help="每行一个单词，也支持粘贴逗号分隔内容。",
            on_change=sync_extract_editor_to_cards
        )
        st.session_state["word_list_editor"] = edited_words

        cleaned_words = parse_unique_words(edited_words)
        st.caption(f"当前词表共 {len(cleaned_words)} 个唯一词条。")
        if edited_words.strip() != "\n".join(cleaned_words):
            st.info("检测到空行、逗号分隔或重复项；制卡时会按整理后的唯一词表处理。")

        st.markdown("#### 第五步：下一步")
        col_copy, col_clear = st.columns([1, 1])
        with col_copy:
            render_copy_button(edited_words, key="copy_words_btn")
        with col_clear:
            st.button("清空提取结果", type="secondary", on_click=reset_extraction_state, use_container_width=True)

        st.success("➡️ 词表已同步到“制作卡片”标签，切换后可直接生成。")

# ==========================================
# Tab 3: Card Creation
# ==========================================
with tab_cards:
    st.markdown("### 📦 制作卡片")
    st.caption("使用内置智能能力，把准备好的词表直接生成 Anki 卡片。")

    current_words_text = st.session_state.get("word_list_editor", "").strip()
    if not current_words_text:
        st.info("先到“提取单词”里准备词表，然后再来制作卡片。")
    else:
        beijing_time_str = get_beijing_time_str()
        default_deck_name = f"词卡_{beijing_time_str}"
        if "deck_name_input" not in st.session_state:
            st.session_state["deck_name_input"] = default_deck_name

        col_name, col_voice = st.columns([2, 3])
        with col_name:
            deck_name = st.text_input("🏷️ 牌组名称", key="deck_name_input")
        with col_voice:
            selected_voice_label = st.radio(
                "🎙️ 英语发音",
                options=list(constants.VOICE_MAP.keys()),
                index=0,
                horizontal=True,
                key="sel_voice_cards"
            )
        selected_voice_code = constants.VOICE_MAP[selected_voice_label]
        st.caption("支持美音和英音；音频只朗读英文单词和英文例句。")

        enable_audio_auto = st.checkbox("生成单词和例句音频", value=True, key="chk_audio_cards")

        col_title, col_copy_btn = st.columns([5, 1])
        with col_title:
            st.markdown("### 📝 待制卡词表")
        with col_copy_btn:
            render_copy_button(st.session_state.get("word_list_editor", ""), key="copy_card_words_btn")

        st.caption("💡 可以在这里继续编辑、新增或删除单词，每行一个。")
        edited_words = st.text_area(
            "待制卡单词列表",
            height=300,
            key="word_list_editor",
            label_visibility="collapsed",
            help="每行一个单词",
            on_change=sync_card_editor_to_extract
        )

        words_only = parse_unique_words(edited_words)

        st.caption(f"当前待制作 {len(words_only)} 个词。")
        st.caption(f"单次最多处理 {constants.MAX_AUTO_LIMIT} 个词。")

        current_word_count = len(words_only)
        if current_word_count > constants.MAX_AUTO_LIMIT:
            st.warning(f"⚠️ 单词数超过 {constants.MAX_AUTO_LIMIT}，内置智能仅处理前 {constants.MAX_AUTO_LIMIT} 个。请缩小列表后再生成。")
            words_for_generation = words_only[:constants.MAX_AUTO_LIMIT]
        else:
            words_for_generation = words_only

        col_generate, col_reset = st.columns([3, 1])
        with col_generate:
            start_auto_gen = st.button(
                "🚀 使用 DeepSeek 生成卡片",
                type="primary",
                use_container_width=True
            )
        with col_reset:
            st.button("清空结果", type="secondary", on_click=reset_anki_state, use_container_width=True)

        if start_auto_gen:
            if not words_for_generation:
                st.warning("⚠️ 当前没有可用于制卡的单词。")
            else:
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_ai_progress(current: int, total: int) -> None:
                    ratio = current / total if total > 0 else 0
                    progress_bar.progress(ratio)
                    status_text.text(f"正在处理 ({current}/{total})")

                status_text.text("🧠 正在请求智能生成...")
                ai_result = process_ai_in_batches(words_for_generation, progress_callback=update_ai_progress)

                if ai_result:
                    status_text.text("✅ 内容生成完成，正在解析...")
                    parsed_data = parse_anki_data(ai_result)

                    if parsed_data:
                        try:
                            status_text.text("📦 正在生成 Anki 包...")
                            final_deck_name = deck_name.strip() or default_deck_name

                            def update_pkg_progress(ratio: float, text: str) -> None:
                                progress_bar.progress(ratio)
                                status_text.text(text)

                            file_path = generate_anki_package(
                                parsed_data,
                                final_deck_name,
                                enable_tts=enable_audio_auto,
                                tts_voice=selected_voice_code,
                                progress_callback=update_pkg_progress
                            )

                            st.session_state["anki_cards_cache"] = parsed_data
                            set_anki_pkg(file_path, final_deck_name)

                            status_text.markdown(f"✅ **处理完成！共生成 {len(parsed_data)} 张卡片**")
                            st.balloons()
                            run_gc()
                        except Exception as e:
                            from errors import ErrorHandler
                            ErrorHandler.handle(e, "生成出错")
                    else:
                        st.error("解析失败，返回内容为空或格式错误。")
                else:
                    st.error("生成失败，请检查 API Key 或网络连接。")

        st.caption("⚠️ 智能生成内容可能存在错误，请人工复核。")

        render_anki_download_button(
            f"📥 下载 {st.session_state.get('anki_pkg_name', '词卡.apkg')}",
            button_type="primary",
            use_container_width=True
        )

        if st.session_state["anki_cards_cache"]:
            cards = st.session_state["anki_cards_cache"]
            with st.expander(f"👀 预览卡片 (前 {constants.MAX_PREVIEW_CARDS} 张)", expanded=True):
                df_view = pd.DataFrame(cards)
                display_cols = ['w', 'm', 'e', 'ec', 'r']
                df_view = df_view[[c for c in display_cols if c in df_view.columns]]
                rename_map = {
                    'w': "正面",
                    'm': "中文/英文释义",
                    'e': "英文例句",
                    'ec': "例句翻译",
                    'r': "词源",
                }
                df_view = df_view.rename(columns=rename_map)
                st.dataframe(df_view.head(constants.MAX_PREVIEW_CARDS), use_container_width=True, hide_index=True)

st.markdown(
    '<p class="app-footer">Vocab Flow Ultra · 文本 → 词表 → Anki 卡片</p>',
    unsafe_allow_html=True
)
