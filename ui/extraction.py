"""Extraction tab rendering."""

import random
import time
from typing import Any

import streamlit as st

import constants
from ai import select_priority_words
from extraction import (
    extract_text_from_file,
    extract_text_from_url,
    get_extraction_error_message,
    is_extraction_error_text,
    is_upload_too_large,
    parse_anki_txt_export,
)
from state import set_generated_words_state
from ui.helpers import (
    clear_direct_wordlist_input,
    clear_paste_input,
    clear_url_input,
    parse_wordlist_candidates,
    parse_unique_words,
    reset_extraction_state,
    restore_word_editor_state,
    set_extract_source_mode,
    sync_extract_editor_to_cards,
)
from utils import render_copy_button, run_gc
from vocab_logic import analyze_logic

SOURCE_BLOCK_OPTIONS = ("用户语料", "单词表", "词库")
SOURCE_BLOCK_MODES = {
    "用户语料": ("文件", "文本", "文章 URL"),
    "单词表": ("单词表", "Anki"),
    "词库": ("词库",),
}


def _source_block_for_mode(source_mode: str) -> str:
    """Return the top-level source block for a detailed source mode."""
    for block_name, source_modes in SOURCE_BLOCK_MODES.items():
        if source_mode in source_modes:
            return block_name
    return "用户语料"


def _rank_interval_options() -> list[tuple[str, int, int]]:
    intervals: list[tuple[str, int, int]] = []
    start_rank = 1
    for cutoff in constants.VOCAB_BASE_RANK_CUTOFFS:
        intervals.append((f"{start_rank}-{cutoff}", start_rank, cutoff))
        start_rank = cutoff + 1
    return intervals


def _render_rank_interval_selector(key_prefix: str) -> tuple[int, int]:
    intervals = _rank_interval_options()
    interval_map = {label: (start, end) for label, start, end in intervals}
    custom_label = "自定义"
    selected_label = st.selectbox(
        "词频区间",
        [*interval_map.keys(), custom_label],
        key=f"{key_prefix}_rank_interval",
    )

    if selected_label == custom_label:
        col_start, col_end = st.columns(2)
        start_rank = col_start.number_input(
            "起始排名",
            1,
            constants.VOCAB_PROJECT_MAX_RANK,
            8000,
            step=100,
            key=f"{key_prefix}_rank_start_custom",
        )
        end_rank = col_end.number_input(
            "结束排名",
            1,
            constants.VOCAB_PROJECT_MAX_RANK,
            10000,
            step=100,
            key=f"{key_prefix}_rank_end_custom",
        )
        return int(start_rank), int(end_rank)

    start_rank, end_rank = interval_map[selected_label]
    st.caption(f"当前区间：{start_rank}-{end_rank}")
    return start_rank, end_rank


def _safe_int(value: Any, default: int | None = None) -> int | None:
    """Convert loose rank values without letting one bad row break the UI."""
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _select_vocab_rows(
    full_df: Any,
    min_rank: int,
    max_rank: int,
    count: int,
    randomize: bool = False,
) -> list[tuple[str, int]]:
    """Select words from the loaded vocabulary rows, supporting list or DataFrame data."""
    if full_df is None:
        return []

    if isinstance(full_df, list):
        rows: list[tuple[str, int]] = []
        for row in full_df:
            if not isinstance(row, dict):
                continue
            word = str(row.get("word", "")).strip()
            rank = _safe_int(row.get("rank"))
            if word and rank is not None and min_rank <= rank <= max_rank:
                rows.append((word, rank))
        if randomize:
            return random.sample(rows, k=min(count, len(rows)))
        return sorted(rows, key=lambda item: item[1])[:count]

    rank_col = next((column for column in full_df.columns if "rank" in str(column).lower()), None)
    word_col = next((column for column in full_df.columns if "word" in str(column).lower()), None)
    if rank_col is None or word_col is None:
        return []

    try:
        subset = full_df.copy()
        subset[rank_col] = subset[rank_col].map(lambda value: _safe_int(value))
        subset = subset.dropna(subset=[rank_col])
        subset[rank_col] = subset[rank_col].astype(int)
        subset = subset[(subset[rank_col] >= min_rank) & (subset[rank_col] <= max_rank)]
    except Exception:
        return []

    if randomize:
        subset = subset.sample(n=min(count, len(subset)))
    else:
        subset = subset.sort_values(rank_col).head(count)
    return [(str(word), int(rank)) for word, rank in zip(subset[word_col], subset[rank_col])]


def _render_generated_words_result() -> None:
    """Render the shared extracted-word result block."""
    data = st.session_state["gen_words_data"]
    original_count = len(data)

    if st.session_state.get("stats_info"):
        stats = st.session_state["stats_info"]
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            st.metric("📊 词汇覆盖率", f"{stats['coverage']*100:.1f}%")
        with col_s2:
            st.metric("🎯 目标词密度", f"{stats['target_density']*100:.1f}%")

    raw_count = st.session_state.get("raw_count", 0) or original_count
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        st.metric("📦 提取的单词总数", raw_count)
    with col_t2:
        st.metric("✅ 筛选后单词总数", original_count)

    result_step_title = st.session_state.get("_extract_result_step_title", "#### 查看与整理结果")
    next_step_title = st.session_state.get("_extract_next_step_title", "#### 下一步")

    st.markdown(result_step_title)
    st.caption("可以直接在这里删改；改动会自动同步到“制作卡片”。")

    restore_word_editor_state("extract_word_editor")
    edited_words = st.text_area(
        f"提取出的单词列表 (共 {original_count} 个)",
        height=300,
        key="extract_word_editor",
        label_visibility="collapsed",
        help="每行一个单词，也支持粘贴逗号分隔内容。",
        on_change=sync_extract_editor_to_cards,
    )
    st.session_state["card_word_list_editor"] = edited_words
    st.session_state["word_list_editor"] = edited_words

    cleaned_words = parse_unique_words(edited_words)
    st.caption(f"当前词表共 {len(cleaned_words)} 个唯一词条。")
    if edited_words.strip() != "\n".join(cleaned_words):
        st.info("检测到空行、逗号分隔或重复项；制卡时会按整理后的唯一词表处理。")

    st.markdown(next_step_title)
    col_copy, col_clear = st.columns([1, 1])
    with col_copy:
        render_copy_button(edited_words, key="copy_words_btn")
    with col_clear:
        st.button("清空提取结果", type="secondary", on_click=reset_extraction_state, use_container_width=True)

    st.markdown(
        '<div class="flow-next-panel"><strong>下一步：去制作卡片</strong>词表已经同步到 <strong>2️⃣ 制作卡片</strong>，切换过去就能直接生成。</div>',
        unsafe_allow_html=True,
    )
    st.success("➡️ 词表已同步到“制作卡片”，切换后可直接生成。")


def render_extraction_tab(vocab_dict: dict[str, int], full_df: Any) -> None:
    """Render the extraction tab."""
    st.markdown("### 🧩 提取单词")
    st.caption(
        f"来源分为 3 个板块：用户语料、单词表、词库。用户语料会用内置词库筛选；词表和词库会直接整理成待制卡词表。"
    )

    saved_extract_source_mode = set_extract_source_mode(st.session_state.get("extract_source_mode"))
    default_source_block = _source_block_for_mode(saved_extract_source_mode)
    if st.session_state.get("extract_source_block") not in SOURCE_BLOCK_OPTIONS:
        st.session_state["extract_source_block"] = default_source_block

    st.markdown("#### 第一步：选择来源板块")
    source_block = st.radio(
        "来源板块",
        SOURCE_BLOCK_OPTIONS,
        horizontal=True,
        key="extract_source_block",
    )

    if source_block == "用户语料":
        corpus_sources = SOURCE_BLOCK_MODES["用户语料"]
        if st.session_state.get("extract_corpus_source") not in corpus_sources:
            st.session_state["extract_corpus_source"] = (
                saved_extract_source_mode if saved_extract_source_mode in corpus_sources else corpus_sources[0]
            )
        extract_source_mode = st.radio(
            "用户语料类型",
            corpus_sources,
            horizontal=True,
            key="extract_corpus_source",
        )
    elif source_block == "单词表":
        wordlist_sources = SOURCE_BLOCK_MODES["单词表"]
        if st.session_state.get("extract_wordlist_source") not in wordlist_sources:
            st.session_state["extract_wordlist_source"] = (
                saved_extract_source_mode if saved_extract_source_mode in wordlist_sources else wordlist_sources[0]
            )
        extract_source_mode = st.radio(
            "单词表类型",
            wordlist_sources,
            horizontal=True,
            key="extract_wordlist_source",
        )
    else:
        extract_source_mode = "词库"
        st.caption(
            f"使用内置词库按词频范围选词。默认词库来自 {constants.VOCAB_PROJECT_SOURCE}（{constants.VOCAB_PROJECT_NAME}）。"
        )

    if extract_source_mode != st.session_state.get("extract_source_mode"):
        extract_source_mode = set_extract_source_mode(extract_source_mode)
    st.caption(f"当前来源：{source_block} / {extract_source_mode}")

    result_step_title = "#### 查看与整理结果"
    next_step_title = "#### 下一步"

    if extract_source_mode in ("文章 URL", "文件", "文本"):
        st.markdown("#### 第二步：设置提取规则")
        current_rank, target_rank = _render_rank_interval_selector("corpus")

        if target_rank < current_rank:
            st.warning("⚠️ 结束词频排名必须大于等于起始词频排名。")

        input_url = ""
        uploaded_file = None
        pasted_text = ""
        button_key = "btn_extract_context"
        missing_source_message = ""

        if extract_source_mode == "文章 URL":
            st.markdown("#### 输入文章链接")
            st.caption("输入文章链接后自动抓取正文，再按词频范围提取目标词。")
            col_url_input, col_url_clear = st.columns([5, 1])
            with col_url_input:
                input_url = st.text_input(
                    "🔗 输入文章链接",
                    placeholder="https://www.economist.com/...",
                    key="url_input_key",
                )
            with col_url_clear:
                st.button(
                    "清空",
                    type="secondary",
                    key="btn_clear_url_input",
                    on_click=clear_url_input,
                    use_container_width=True,
                )
            button_key = "btn_extract_url"
            missing_source_message = "⚠️ 请先输入文章链接。"
        elif extract_source_mode == "文件":
            st.markdown("#### 上传文件")
            st.caption("上传文档后自动读取正文，再按词频范围提取目标词。")
            uploaded_file = st.file_uploader(
                "上传文件",
                type=["txt", "pdf", "docx", "epub", "csv", "xlsx", "xls", "db", "sqlite"],
                key=st.session_state["uploader_id"],
            )
            if uploaded_file and is_upload_too_large(uploaded_file):
                st.error(f"❌ 文件过大，已限制为 {constants.MAX_UPLOAD_MB}MB。请缩小文件后重试。")
                uploaded_file = None
            button_key = "btn_extract_file"
            missing_source_message = "⚠️ 请先上传要分析的文件。"
        else:
            st.markdown("#### 粘贴文本")
            st.caption("适合直接粘贴文章、笔记或段落内容，再按词频范围提取目标词。")
            col_text_label, col_text_clear = st.columns([5, 1])
            with col_text_label:
                st.markdown("输入文本内容")
            with col_text_clear:
                st.button(
                    "清空",
                    type="secondary",
                    key="btn_clear_paste_input",
                    on_click=clear_paste_input,
                    use_container_width=True,
                )
            pasted_text = st.text_area(
                "粘贴文本内容",
                height=180,
                key="paste_key",
                placeholder="支持直接粘贴文章内容...",
                label_visibility="collapsed",
            )
            button_key = "btn_extract_text"
            missing_source_message = "⚠️ 请先输入要分析的文本内容。"

        if st.button("🚀 开始提取", type="primary", key=button_key):
            if target_rank < current_rank:
                st.error("❌ 结束词频排名必须大于等于起始词频排名，请修正后重试。")
            elif extract_source_mode == "文章 URL" and not input_url.strip():
                st.warning(missing_source_message)
            elif extract_source_mode == "文件" and not uploaded_file:
                st.warning(missing_source_message)
            elif extract_source_mode == "文本" and len(pasted_text.strip()) <= 2:
                st.warning(missing_source_message)
            else:
                with st.status("🔍 正在加载资源并分析文本...", expanded=True) as status:
                    start_time = time.time()
                    raw_text = ""

                    if extract_source_mode == "文章 URL":
                        status.write(f"🌐 正在抓取文章链接：{input_url}")
                        raw_text = extract_text_from_url(input_url)
                    elif extract_source_mode == "文件":
                        status.write("📄 正在读取文件内容...")
                        raw_text = extract_text_from_file(uploaded_file)
                    else:
                        status.write("📝 正在读取文本内容...")
                        raw_text = pasted_text

                    if is_extraction_error_text(raw_text):
                        error_message = get_extraction_error_message(raw_text)
                        status.write(f"❌ {error_message}")
                        status.update(label="❌ 提取失败", state="error")
                    elif len(raw_text) > 2:
                        status.write("🧠 正在进行词形还原与词频分级...")
                        final_data, raw_count, stats_info = analyze_logic(raw_text, current_rank, target_rank, False)

                        set_generated_words_state(final_data, raw_count, stats_info)
                        st.session_state["process_time"] = time.time() - start_time
                        run_gc()
                        status.update(label="✅ 提取完成", state="complete", expanded=False)
                    else:
                        status.update(label="⚠️ 内容为空或太短", state="error")

    elif extract_source_mode == "单词表":
        result_step_title = "#### 查看与整理结果"
        next_step_title = "#### 下一步"
        st.markdown("#### 导入单词表")
        st.caption("支持上传简单词表 `.txt` 文件，也支持直接粘贴现成词表。")

        word_list_file = st.file_uploader("上传单词表文件", type=["txt"], key="wordlist_import_uploader")
        if word_list_file and is_upload_too_large(word_list_file):
            st.error(f"❌ 文件过大，已限制为 {constants.MAX_UPLOAD_MB}MB。请缩小文件后重试。")
            word_list_file = None

        prefilled_text = ""
        if word_list_file:
            with st.spinner("正在读取词表文件..."):
                prefilled_text = extract_text_from_file(word_list_file)
                if is_extraction_error_text(prefilled_text):
                    st.error(f"❌ {get_extraction_error_message(prefilled_text)}")
                    prefilled_text = ""
                elif prefilled_text:
                    st.success("✅ 已读取词表文件内容")

        if "direct_wordlist_input" not in st.session_state:
            st.session_state["direct_wordlist_input"] = ""

        file_signature = ""
        if word_list_file:
            file_signature = f"{getattr(word_list_file, 'name', '')}:{getattr(word_list_file, 'size', '')}"

        if word_list_file and prefilled_text:
            if st.session_state.get("direct_wordlist_file_signature") != file_signature:
                st.session_state["direct_wordlist_input"] = prefilled_text
                st.session_state["direct_wordlist_file_signature"] = file_signature

        col_wordlist_label, col_wordlist_clear = st.columns([5, 1])
        with col_wordlist_label:
            st.markdown("输入单词列表")
        with col_wordlist_clear:
            st.button(
                "清空",
                type="secondary",
                key="btn_clear_direct_wordlist_input",
                on_click=clear_direct_wordlist_input,
                args=(file_signature,),
                use_container_width=True,
            )
        raw_input = st.text_area(
            "✍️ 粘贴单词列表（每行一个或逗号分隔）",
            height=220,
            key="direct_wordlist_input",
            placeholder="altruism\nhectic\nserendipity",
            label_visibility="collapsed",
        )
        if st.session_state.get("direct_wordlist_last_input") != raw_input:
            st.session_state["direct_wordlist_last_input"] = raw_input
            st.session_state["ai_word_selection_selected"] = ""
            st.session_state["ai_word_selection_remaining"] = ""

        candidate_words = parse_wordlist_candidates(raw_input)
        if candidate_words:
            st.caption(f"已识别 {len(candidate_words)} 个候选词/短语。可以导入全部，也可以让 AI 筛出最值得先学的词。")

        col_all_import, col_ai_count, col_ai_select = st.columns([1, 1, 2])
        with col_all_import:
            import_all = st.button("🚀 导入全部", key="btn_direct", type="primary", use_container_width=True)
        with col_ai_count:
            ai_select_count = st.number_input(
                "AI 筛选数量",
                min_value=1,
                max_value=constants.AI_WORD_SELECTION_MAX_OUTPUT,
                value=30,
                step=1,
                key="ai_word_selection_count",
            )
        with col_ai_select:
            ai_select = st.button("✨ AI 筛选值得学的词", key="btn_ai_select_words", use_container_width=True)

        if import_all:
            with st.spinner("正在解析列表..."):
                unique_words = candidate_words
                if unique_words:
                    data_list = [(word, vocab_dict.get(word.lower(), 99999)) for word in unique_words]
                    set_generated_words_state(data_list, len(unique_words), None)
                    st.toast(f"✅ 已加载 {len(unique_words)} 个单词", icon="🎉")
                else:
                    st.warning("⚠️ 内容为空。")

        if ai_select:
            if not candidate_words:
                st.warning("⚠️ 请先输入单词列表。")
            else:
                candidates_for_ai = candidate_words[: constants.AI_WORD_SELECTION_INPUT_LIMIT]
                if len(candidate_words) > constants.AI_WORD_SELECTION_INPUT_LIMIT:
                    st.warning(
                        f"⚠️ 候选词超过 {constants.AI_WORD_SELECTION_INPUT_LIMIT} 个，本次只处理前 {constants.AI_WORD_SELECTION_INPUT_LIMIT} 个。"
                    )
                target_count = min(int(ai_select_count), len(candidates_for_ai))
                with st.spinner("AI 正在按优先级筛选..."):
                    selection_result = select_priority_words(candidates_for_ai, target_count)
                if selection_result and "error" not in selection_result:
                    selected_words = selection_result.get("selected", [])
                    remaining_words = selection_result.get("remaining", [])
                    selected_text = "\n".join(selected_words)
                    remaining_text = "\n".join(remaining_words)

                    st.session_state["ai_word_selection_selected"] = selected_text
                    st.session_state["ai_word_selection_remaining"] = remaining_text

                    if selected_words:
                        data_list = [(word, vocab_dict.get(word.lower(), 99999)) for word in selected_words]
                        set_generated_words_state(data_list, len(candidates_for_ai), None)
                        st.toast(f"✅ 已筛出 {len(selected_words)} 个词，并同步到制卡词表", icon="🎉")
                    else:
                        st.warning("⚠️ AI 没有返回可用筛选结果。")
                else:
                    error_message = selection_result.get("error", "未知错误") if selection_result else "未知错误"
                    st.error(f"❌ AI 筛选失败：{error_message}")

        if st.session_state.get("ai_word_selection_selected") or st.session_state.get("ai_word_selection_remaining"):
            st.markdown("#### AI 筛选结果")
            selected_text = st.session_state.get("ai_word_selection_selected", "")
            remaining_text = st.session_state.get("ai_word_selection_remaining", "")

            col_selected_title, col_selected_copy = st.columns([5, 1])
            with col_selected_title:
                st.markdown("筛选出的单词")
            with col_selected_copy:
                render_copy_button(selected_text, key="copy_ai_selected_words")
            st.code(selected_text or "", language="text")

            col_remaining_title, col_remaining_copy = st.columns([5, 1])
            with col_remaining_title:
                st.markdown("剩余单词")
            with col_remaining_copy:
                render_copy_button(remaining_text, key="copy_ai_remaining_words")
            st.code(remaining_text or "", language="text")

    elif extract_source_mode == "Anki":
        result_step_title = "#### 查看与整理结果"
        next_step_title = "#### 下一步"
        st.markdown("#### 导入 Anki")
        st.caption("这里专门用于导入 Anki 导出的 .txt 文件。")

        anki_export_file = st.file_uploader("上传 Anki 导出的 .txt 文件", type=["txt"], key="anki_import_uploader")
        if anki_export_file and is_upload_too_large(anki_export_file):
            st.error(f"❌ 文件过大，已限制为 {constants.MAX_UPLOAD_MB}MB。请缩小文件后重试。")
            anki_export_file = None

        if st.button("🚀 解析 Anki 导出", key="btn_import_anki", type="primary"):
            if not anki_export_file:
                st.warning("⚠️ 请先上传 Anki 导出的 .txt 文件。")
            else:
                with st.spinner("正在智能解析 Anki 导出文件..."):
                    parsed_text = parse_anki_txt_export(anki_export_file)
                    if is_extraction_error_text(parsed_text):
                        st.error(f"❌ {get_extraction_error_message(parsed_text)}")
                    else:
                        unique_words = parse_unique_words(parsed_text)
                        if unique_words:
                            data_list = [(word, vocab_dict.get(word.lower(), 99999)) for word in unique_words]
                            set_generated_words_state(data_list, len(unique_words), None)
                            st.toast(f"✅ 已从 Anki 导出中提取 {len(unique_words)} 个单词", icon="🎉")
                        else:
                            st.warning("⚠️ 没有从文件中解析到可用单词。")

    else:
        result_step_title = "#### 查看与整理结果"
        next_step_title = "#### 下一步"
        st.markdown("#### 从词库生成词表")
        st.caption(
            f"按来自 {constants.VOCAB_PROJECT_SOURCE} 的 {constants.VOCAB_PROJECT_NAME} 词频范围直接选词，适合快速扩充词表。"
        )
        min_rank, max_rank = _render_rank_interval_selector("bank")
        gen_type = st.radio("生成模式", ["🔢 顺序生成", "🔀 随机抽取"], horizontal=True, key="rank_gen_type")

        if max_rank < min_rank:
            st.warning("⚠️ 结束排名必须大于等于起始排名")

        if "顺序生成" in gen_type:
            count = st.number_input("数量", 10, 5000, 10, step=10, key="rank_count")

            if st.button("🚀 生成词频列表", key="btn_rank_ordered"):
                if max_rank < min_rank:
                    st.error("❌ 结束排名必须大于等于起始排名，请修正后重试。")
                else:
                    with st.spinner("正在提取..."):
                        rows = _select_vocab_rows(full_df, min_rank, max_rank, int(count), randomize=False)
                        if len(rows) < count:
                            st.warning(f"⚠️ 该范围只有 {len(rows)} 个单词，已全部选中")
                        set_generated_words_state(rows, 0, None)
        else:
            random_count = st.number_input("抽取数量", 10, 5000, 10, step=10, key="rank_random_count")

            if st.button("🎲 随机抽取词表", key="btn_rank_random"):
                if max_rank < min_rank:
                    st.error("❌ 结束排名必须大于等于起始排名，请修正后重试。")
                else:
                    with st.spinner("正在抽取..."):
                        rows = _select_vocab_rows(full_df, min_rank, max_rank, int(random_count), randomize=True)
                        if len(rows) < random_count:
                            st.warning(f"⚠️ 该范围只有 {len(rows)} 个单词，已全部选中")
                        set_generated_words_state(rows, 0, None)

    st.session_state["_extract_result_step_title"] = result_step_title
    st.session_state["_extract_next_step_title"] = next_step_title

    if st.session_state.get("gen_words_data"):
        _render_generated_words_result()
