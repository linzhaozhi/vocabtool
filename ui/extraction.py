"""Extraction tab rendering."""

import time
from typing import Any

import streamlit as st

import constants
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
    EXTRACT_SOURCE_OPTIONS,
    EXTRACT_SOURCE_WIDGET_KEY,
    clear_direct_wordlist_input,
    clear_paste_input,
    clear_url_input,
    handle_extract_source_change,
    normalize_extract_source_mode,
    parse_unique_words,
    reset_extraction_state,
    set_extract_source_mode,
    sync_extract_editor_to_cards,
)
from utils import render_copy_button, run_gc
from vocab import analyze_logic


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

    edited_words = st.text_area(
        f"提取出的单词列表 (共 {original_count} 个)",
        height=300,
        key="extract_word_editor",
        label_visibility="collapsed",
        help="每行一个单词，也支持粘贴逗号分隔内容。",
        on_change=sync_extract_editor_to_cards,
    )
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
        '<div class="flow-next-panel"><strong>下一步：去制作卡片</strong>词表已经同步到 <strong>3️⃣ 制作卡片</strong>，切换过去就能直接生成。</div>',
        unsafe_allow_html=True,
    )
    st.success("➡️ 词表已同步到“制作卡片”标签，切换后可直接生成。")


def render_extraction_tab(vocab_dict: dict[str, int], full_df: Any) -> None:
    """Render the extraction tab."""
    st.markdown("### 🧩 提取单词")
    st.caption(
        f"来源已拆成 6 个入口：文章 URL、文件、文本、单词表、Anki、词库；其中“词库”使用 {constants.VOCAB_PROJECT_NAME} 词表。整理后的结果会自动同步到“制作卡片”。"
    )

    saved_extract_source_mode = set_extract_source_mode(st.session_state.get("extract_source_mode"))
    if EXTRACT_SOURCE_WIDGET_KEY not in st.session_state:
        st.session_state[EXTRACT_SOURCE_WIDGET_KEY] = saved_extract_source_mode
    else:
        widget_extract_source_mode = normalize_extract_source_mode(st.session_state.get(EXTRACT_SOURCE_WIDGET_KEY))
        if widget_extract_source_mode != saved_extract_source_mode:
            st.session_state[EXTRACT_SOURCE_WIDGET_KEY] = saved_extract_source_mode

    st.markdown("#### 第一步：选择来源")
    extract_source_mode = st.radio(
        "提取来源",
        EXTRACT_SOURCE_OPTIONS,
        horizontal=True,
        label_visibility="collapsed",
        key=EXTRACT_SOURCE_WIDGET_KEY,
        on_change=handle_extract_source_change,
    )
    extract_source_mode = normalize_extract_source_mode(extract_source_mode)
    if extract_source_mode != st.session_state.get("extract_source_mode"):
        extract_source_mode = set_extract_source_mode(extract_source_mode)
    st.caption(f"当前来源：{extract_source_mode}")

    result_step_title = "#### 查看与整理结果"
    next_step_title = "#### 下一步"

    if extract_source_mode in ("文章 URL", "文件", "文本"):
        st.markdown("#### 第二步：设置提取规则")
        col1, col2 = st.columns(2)
        current_rank = col1.number_input("跳过前 N 个高频词", 1, 20000, 6000, step=100)
        target_rank = col2.number_input("保留到第 N 名词频", 2000, 50000, 10000, step=500)

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

        if st.button("🚀 导入词表", key="btn_direct", type="primary"):
            with st.spinner("正在解析列表..."):
                unique_words = parse_unique_words(raw_input)
                if unique_words:
                    data_list = [(word, vocab_dict.get(word.lower(), 99999)) for word in unique_words]
                    set_generated_words_state(data_list, len(unique_words), None)
                    st.toast(f"✅ 已加载 {len(unique_words)} 个单词", icon="🎉")
                else:
                    st.warning("⚠️ 内容为空。")

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
        st.caption(f"按 {constants.VOCAB_PROJECT_NAME} 词频范围直接选词，适合快速扩充词表。")
        gen_type = st.radio("生成模式", ["🔢 顺序生成", "🔀 随机抽取"], horizontal=True, key="rank_gen_type")

        if "顺序生成" in gen_type:
            col_a, col_b = st.columns(2)
            start_rank = col_a.number_input("起始排名", 1, 20000, 8000, step=100, key="rank_start")
            count = col_b.number_input("数量", 10, 5000, 10, step=10, key="rank_count")

            if st.button("🚀 生成词频列表", key="btn_rank_ordered"):
                with st.spinner("正在提取..."):
                    if full_df is not None:
                        rank_col = next(column for column in full_df.columns if "rank" in column)
                        word_col = next(column for column in full_df.columns if "word" in column)
                        subset = full_df[full_df[rank_col] >= start_rank].sort_values(rank_col).head(count)
                        set_generated_words_state(list(zip(subset[word_col], subset[rank_col])), 0, None)
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
                        if full_df is not None:
                            rank_col = next(column for column in full_df.columns if "rank" in column)
                            word_col = next(column for column in full_df.columns if "word" in column)
                            pool = full_df[(full_df[rank_col] >= min_rank) & (full_df[rank_col] <= max_rank)]
                            if len(pool) < random_count:
                                st.warning(f"⚠️ 该范围只有 {len(pool)} 个单词，已全部选中")
                            sample = pool.sample(n=min(random_count, len(pool)))
                            set_generated_words_state(list(zip(sample[word_col], sample[rank_col])), 0, None)

    st.session_state["_extract_result_step_title"] = result_step_title
    st.session_state["_extract_next_step_title"] = next_step_title

    if st.session_state.get("gen_words_data"):
        _render_generated_words_result()
