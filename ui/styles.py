"""Shared page configuration, styles, and top-level UI chrome."""

import streamlit as st

import constants

GLOBAL_CSS = """
<style>
    :root {
        --vf-text: #0f172a;
        --vf-text-muted: #334155;
        --vf-text-soft: #475569;
        --vf-surface: #f8fafc;
        --vf-surface-soft: #f1f5f9;
        --vf-surface-elevated: #ffffff;
        --vf-border: #cbd5e1;
        --vf-border-strong: #94a3b8;
        --vf-shadow-soft: 0 14px 32px rgba(15, 23, 42, 0.12);
        --vf-primary-soft: #dbeafe;
        --vf-primary-soft-2: #bfdbfe;
        --vf-success-soft: #ecfdf5;
        --vf-success-text: #166534;
        --vf-lookup-def: #1d4ed8;
        --vf-lookup-ety-bg: #ecfdf5;
        --vf-lookup-ety-text: #047857;
        --vf-accent-gradient: linear-gradient(135deg, #2563eb 0%, #1d4ed8 55%, #0f172a 100%);
    }
    @media (prefers-color-scheme: dark) {
        :root {
            --vf-text: #f8fafc;
            --vf-text-muted: #e2e8f0;
            --vf-text-soft: #cbd5e1;
            --vf-surface: #0f172a;
            --vf-surface-soft: #111827;
            --vf-surface-elevated: #1e293b;
            --vf-border: #334155;
            --vf-border-strong: #475569;
            --vf-shadow-soft: 0 16px 36px rgba(2, 6, 23, 0.42);
            --vf-primary-soft: #1d4ed8;
            --vf-primary-soft-2: #1e40af;
            --vf-success-soft: #052e1c;
            --vf-success-text: #bbf7d0;
            --vf-lookup-def: #bfdbfe;
            --vf-lookup-ety-bg: #0f2f2a;
            --vf-lookup-ety-text: #d1fae5;
            --vf-accent-gradient: linear-gradient(135deg, #2563eb 0%, #1d4ed8 48%, #0f172a 100%);
        }
    }
    html[data-theme="dark"],
    body[data-theme="dark"],
    .stApp[data-theme="dark"],
    [data-theme="dark"] {
        --vf-text: #f8fafc;
        --vf-text-muted: #e2e8f0;
        --vf-text-soft: #cbd5e1;
        --vf-surface: #0f172a;
        --vf-surface-soft: #111827;
        --vf-surface-elevated: #1e293b;
        --vf-border: #334155;
        --vf-border-strong: #475569;
        --vf-shadow-soft: 0 16px 36px rgba(2, 6, 23, 0.42);
        --vf-primary-soft: #1d4ed8;
        --vf-primary-soft-2: #1e40af;
        --vf-success-soft: #052e1c;
        --vf-success-text: #bbf7d0;
        --vf-lookup-def: #bfdbfe;
        --vf-lookup-ety-bg: #0f2f2a;
        --vf-lookup-ety-text: #d1fae5;
        --vf-accent-gradient: linear-gradient(135deg, #2563eb 0%, #1d4ed8 48%, #0f172a 100%);
    }
    .stTextArea textarea { font-family: 'Consolas', monospace; font-size: 14px; }
    .stButton>button {
        border-radius: 10px;
        font-weight: 600;
        width: 100%;
        margin-top: 5px;
        border: 1px solid var(--vf-border-strong);
        background: var(--vf-surface-elevated);
        color: var(--vf-text);
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.08);
    }
    .stButton>button:hover {
        border-color: var(--primary-color, #60a5fa);
        color: var(--vf-text);
    }
    .stTextInput > div > div > input,
    .stTextArea textarea,
    .stNumberInput input {
        border-radius: 12px;
        border: 1px solid var(--vf-border-strong);
        background: var(--vf-surface-elevated);
        color: var(--vf-text) !important;
        caret-color: var(--vf-text);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.03);
    }
    .stTextInput > div > div > input::placeholder,
    .stTextArea textarea::placeholder,
    .stNumberInput input::placeholder {
        color: var(--vf-text-soft);
        opacity: 1;
    }
    .stTextInput > div > div > input:disabled,
    .stTextArea textarea:disabled,
    .stNumberInput input:disabled {
        opacity: 1;
        color: var(--vf-text) !important;
        -webkit-text-fill-color: var(--vf-text) !important;
        background: var(--vf-surface-elevated);
    }
    .stTextInput > div > div > input:focus,
    .stTextArea textarea:focus,
    .stNumberInput input:focus {
        border-color: var(--primary-color, #60a5fa);
        box-shadow: 0 0 0 1px rgba(96, 165, 250, 0.34);
    }
    .stat-box {
        padding: 15px;
        background: var(--vf-success-soft);
        border: 1px solid rgba(34, 197, 94, 0.3);
        border-radius: 10px;
        text-align: center;
        color: var(--vf-success-text);
        margin-bottom: 20px;
    }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stExpander {
        border: 1px solid var(--vf-border);
        border-radius: 12px;
        margin-bottom: 10px;
        background: var(--vf-surface-soft);
    }
    .stExpander summary,
    .stExpander summary p,
    .stExpander details,
    .stExpander details * {
        color: var(--vf-text) !important;
    }
    .stProgress > div > div > div > div { background-color: #4CAF50; }
    .ai-warning { font-size: 12px; color: var(--vf-text-soft); margin-top: -5px; margin-bottom: 10px; text-align: center; }
    .stForm {
        border: 1px solid var(--vf-border);
        border-radius: 14px;
        padding: 1.25rem 1.5rem;
        background: var(--vf-surface-soft);
        box-shadow: var(--vf-shadow-soft);
        margin-bottom: 1rem;
    }
    [data-testid="stMetric"] {
        background: linear-gradient(135deg, var(--vf-surface-soft) 0%, var(--vf-surface) 100%);
        padding: 1rem;
        border-radius: 12px;
        border: 1px solid var(--vf-border);
        box-shadow: 0 10px 24px rgba(15, 23, 42, 0.08);
    }
    [data-testid="stMetric"] label,
    [data-testid="stMetric"] p,
    [data-testid="stMetricValue"],
    [data-testid="stMetricDelta"] {
        color: var(--vf-text) !important;
    }
    .stTabs [data-baseweb="tab-list"] { gap: 0.5rem; }
    .stTabs [data-baseweb="tab"] {
        padding: 0.6rem 1rem;
        border-radius: 10px;
        font-weight: 600;
        border: 1px solid var(--vf-border);
        background: var(--vf-surface);
        color: var(--vf-text-soft);
        transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
    }
    .stTabs [data-baseweb="tab"] * {
        color: inherit !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, var(--vf-primary-soft) 0%, var(--vf-primary-soft-2) 100%);
        border-color: rgba(96, 165, 250, 0.5);
        color: #eff6ff;
        box-shadow: 0 10px 24px rgba(37, 99, 235, 0.24);
        transform: translateY(-1px);
    }
    .stRadio [role="radiogroup"] {
        gap: 0.5rem;
        flex-wrap: wrap;
    }
    .stRadio [role="radiogroup"] label {
        background: var(--vf-surface);
        border: 1px solid var(--vf-border);
        border-radius: 999px;
        padding: 0.25rem 0.8rem;
        transition: transform 0.16s ease, box-shadow 0.16s ease, border-color 0.16s ease;
    }
    .stRadio [role="radiogroup"] label * {
        color: var(--vf-text) !important;
    }
    .stRadio [role="radiogroup"] label:hover {
        transform: translateY(-1px);
        border-color: rgba(96, 165, 250, 0.52);
    }
    .stRadio [role="radiogroup"] label:has(input:checked) {
        background: linear-gradient(135deg, var(--vf-primary-soft) 0%, var(--vf-primary-soft-2) 100%);
        border-color: rgba(96, 165, 250, 0.6);
        box-shadow: 0 10px 18px rgba(37, 99, 235, 0.24);
    }
    .stRadio [role="radiogroup"] label:has(input:checked) * {
        color: #eff6ff !important;
    }
    .app-footer {
        margin-top: 2.5rem;
        padding-top: 1rem;
        border-top: 1px solid var(--vf-border);
        text-align: center;
        color: var(--vf-text-soft);
        font-size: 0.875rem;
    }
    .workflow-banner {
        margin: 0.75rem 0 1.25rem;
        padding: 0.95rem 1rem;
        border-radius: 12px;
        background: linear-gradient(135deg, var(--vf-primary-soft) 0%, var(--vf-surface-soft) 100%);
        border: 1px solid rgba(96, 165, 250, 0.45);
        color: var(--vf-text);
        font-size: 0.95rem;
        box-shadow: var(--vf-shadow-soft);
    }
    .stCaptionContainer p,
    .stMarkdown p,
    .stMarkdown li,
    .stMarkdown span,
    .stAlert,
    .stInfo,
    .stSuccess,
    .stWarning,
    .stError {
        color: var(--vf-text);
    }
    [data-testid="stFileUploaderDropzone"] {
        background: var(--vf-surface-elevated);
        border: 1px dashed var(--vf-border-strong);
        border-radius: 12px;
    }
    [data-testid="stFileUploaderDropzone"] * {
        color: var(--vf-text) !important;
    }
    .reading-container {
        background-color: var(--vf-surface);
        padding: 30px;
        border-radius: 12px;
        font-family: 'Georgia', serif;
        font-size: 18px;
        line-height: 1.8;
        color: var(--vf-text);
        box-shadow: var(--vf-shadow-soft);
    }
    .reading-text {
        user-select: text;
        cursor: text;
    }
    .reading-text::selection {
        background-color: color-mix(in srgb, var(--primary-color, #60a5fa) 35%, transparent);
    }
    .word-definition {
        background: var(--vf-surface-elevated);
        border: 2px solid rgba(96, 165, 250, 0.6);
        border-radius: 8px;
        padding: 15px;
        margin-top: 10px;
        box-shadow: var(--vf-shadow-soft);
    }
    .definition-title {
        font-weight: bold;
        color: var(--vf-lookup-def);
        margin-bottom: 8px;
        font-size: 20px;
    }
    .definition-meaning {
        color: var(--vf-text);
        margin-bottom: 12px;
        font-size: 16px;
    }
    .example-sentence {
        background-color: var(--vf-surface-soft);
        padding: 10px;
        border-left: 4px solid rgba(96, 165, 250, 0.78);
        margin: 5px 0;
        font-style: italic;
        color: var(--vf-text);
    }
    .search-box {
        position: sticky;
        top: 0;
        background: var(--vf-surface-elevated);
        padding: 15px;
        border-radius: 8px;
        border: 1px solid var(--vf-border);
        box-shadow: var(--vf-shadow-soft);
        margin-bottom: 20px;
        z-index: 100;
    }
    .quick-lookup-card {
        font-family: 'Noto Sans CJK SC', 'Noto Sans SC', 'WenQuanYi Micro Hei', 'Microsoft YaHei UI', 'Microsoft YaHei', sans-serif;
        font-size: 16px;
        line-height: 1.65;
        color: var(--vf-text);
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
        color: var(--vf-lookup-def);
        margin-bottom: 6px;
    }
    .quick-lookup-phon {
        color: var(--vf-text);
        margin-bottom: 8px;
        font-size: 17px;
        letter-spacing: 0.01em;
    }
    .quick-lookup-ety {
        color: var(--vf-lookup-ety-text);
        background: var(--vf-lookup-ety-bg);
        padding: 6px 10px;
        border-radius: 8px;
        margin: 6px 0;
    }
    .quick-lookup-ex {
        color: var(--vf-text);
        background: var(--vf-surface-soft);
        padding: 8px 10px;
        border-radius: 8px;
        margin-top: 6px;
    }
    .quick-lookup-cn {
        color: var(--vf-text-muted);
        margin-bottom: 8px;
    }
</style>
"""


def configure_page() -> None:
    """Apply top-level Streamlit page configuration."""
    st.set_page_config(
        page_title="单词流",
        page_icon="⚡️",
        layout="centered",
        initial_sidebar_state="collapsed",
    )


def apply_global_styles() -> None:
    """Inject shared app CSS."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def render_app_header() -> None:
    """Render the static app header."""
    st.title("⚡️ 单词流 · 稳定版")
    st.caption(
        f"把查词、提词、制卡分开处理。支持内置智能释义、词源与语音，默认词库来自 {constants.VOCAB_PROJECT_NAME}。"
    )
    st.markdown(
        '<div class="workflow-banner">查词、提词、制卡三个步骤已经分开。先确认词，再整理词表，最后生成卡片，路径会更清楚。</div>',
        unsafe_allow_html=True,
    )


def render_help_panel(vocab_available: bool) -> None:
    """Render the shared usage guide and vocab availability message."""
    if not vocab_available:
        st.error(
            f"⚠️ 缺失词库数据文件，请检查根目录或 `data/` 目录中的 `{constants.VOCAB_PROJECT_FILE}`（默认）/ `vocab.pkl`。"
        )

    with st.expander("📖 使用指南 & 支持格式", expanded=False):
        st.markdown(
            """
    **🚀 极速工作流**
    1. **查单词**：在“查单词”里快速获取释义、词源和双语例句。
    2. **提取单词**：在“提取单词”里从文本、文件或词频范围整理词表。
    3. **制作卡片**：在“制作卡片”里使用内置智能生成并下载 Anki 牌组。

    **📚 当前词库**
    - 默认词库：NGSL 项目词表（`ngsl_31k.csv`）

    **📄 支持的文件格式**
    - 📝 文本：TXT
    - 📄 文档：PDF, DOCX, EPUB
    - 📊 表格：CSV, XLSX, XLS
    - 🗄️ 数据库：DB, SQLite
    - 📤 **Anki 导出**：支持 .txt 格式（推荐使用 "Notes in Plain Text"，但也兼容 "Cards in Plain Text"）。
    """
        )

    st.caption("三个功能现在独立分区：先查词，再提词，最后制作卡片。")


def render_app_footer() -> None:
    """Render the shared footer."""
    st.markdown(
        '<p class="app-footer">Vocab Flow Ultra · 文本 → 词表 → Anki 卡片</p>',
        unsafe_allow_html=True,
    )
